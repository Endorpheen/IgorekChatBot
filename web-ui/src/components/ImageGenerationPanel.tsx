import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, ImageIcon, AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import type { ImageJobStatusResponse, ImageJobStatus } from '../types/image';
import {
  PinRequiredError,
  InvalidPinError,
  loadMetadata,
  loadTogetherKey,
} from '../storage/togetherKeyStorage';
import {
  ApiError,
  buildApiUrl,
  createImageGenerationJob,
  fetchImageCapabilities,
  fetchImageJobStatus,
} from '../utils/api';
import { getImageSessionId } from '../utils/session';
import type { ImageModelCapabilities } from '../types/image';

interface ImageGenerationPanelProps {
  onRequireKeySetup?: () => void;
  refreshKeySignal?: number;
}

const MAX_PROMPT_LENGTH = 800;

const STATUS_LABELS: Record<ImageJobStatus, string> = {
  queued: 'В очереди',
  running: 'Генерация',
  done: 'Готово',
  error: 'Ошибка',
};

const ImageGenerationPanel: React.FC<ImageGenerationPanelProps> = ({ onRequireKeySetup, refreshKeySignal }) => {
  const [prompt, setPrompt] = useState('');
  const [sizeValue, setSizeValue] = useState<number | null>(null);
  const [steps, setSteps] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<ImageJobStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [keyAvailable, setKeyAvailable] = useState(false);
  const objectUrlRef = useRef<string | null>(null);
  const [capabilities, setCapabilities] = useState<ImageModelCapabilities | null>(null);

  useEffect(() => {
    const refresh = async () => {
      try {
        const metadata = await loadMetadata();
        setKeyAvailable(metadata.hasKey);
      } catch (error) {
        setKeyAvailable(false);
      }
    };
    refresh();
  }, [refreshKeySignal]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const fetched = await fetchImageCapabilities();
        if (cancelled) {
          return;
        }
        setCapabilities(fetched);
        setSteps((prev) => (prev === null ? fetched.default_steps : prev));
        setSizeValue((prev) => (prev === null ? fetched.default_size : prev));
      } catch (error) {
        if (!cancelled) {
          setCapabilities(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
    }
  }, []);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await fetchImageJobStatus(jobId);
        if (cancelled) {
          return;
        }
        setJobStatus(status);
        if (status.status === 'done') {
          setIsGenerating(false);
          await fetchResultImage(status);
        } else if (status.status === 'error') {
          setIsGenerating(false);
          setStatusError(status.error_message ?? 'Генерация завершилась с ошибкой');
        } else {
          setTimeout(poll, 2500);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError) {
          if (error.code === 'model_not_allowed') {
            const modelName = capabilities?.model ?? 'неизвестно';
            setStatusError(`Модель недоступна. Разрешена: ${modelName}`);
          } else {
            setStatusError(error.message);
          }
        } else {
          setStatusError('Не удалось получить статус задачи');
        }
        setIsGenerating(false);
      }
    };

    poll();

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const fetchResultImage = async (status: ImageJobStatusResponse) => {
    if (!status.result_url) {
      setStatusError('Сервер не предоставил ссылку на изображение');
      return;
    }

    try {
      const response = await fetch(buildApiUrl(status.result_url), {
        headers: {
          'X-Client-Session': getImageSessionId(),
        },
      });
      if (!response.ok) {
        setStatusError('Не удалось загрузить изображение результата');
        return;
      }
      const blob = await response.blob();
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
      }
      const objectUrl = URL.createObjectURL(blob);
      objectUrlRef.current = objectUrl;
      setImageUrl(objectUrl);
    } catch (error) {
      setStatusError('Не удалось загрузить изображение результата');
    }
  };

  const readTogetherKey = async (): Promise<string> => {
    const metadata = await loadMetadata();
    if (!metadata.hasKey) {
      throw new Error('Сохраните Together API Key в настройках.');
    }
    setKeyAvailable(true);

    try {
      const { key } = await loadTogetherKey();
      return key;
    } catch (error) {
      if (error instanceof PinRequiredError) {
        const pin = window.prompt('Введите PIN для Together API Key');
        if (!pin) {
          throw new Error('Для генерации требуется PIN-код.');
        }
        try {
          const { key } = await loadTogetherKey(pin.trim());
          return key;
        } catch (innerError) {
          if (innerError instanceof InvalidPinError) {
            throw new Error('Неверный PIN. Откройте настройки, чтобы повторно расшифровать ключ.');
          }
          throw innerError instanceof Error ? innerError : new Error('Не удалось расшифровать ключ');
        }
      }
      throw error instanceof Error ? error : new Error('Не удалось загрузить ключ');
    }
  };

  const handleGenerate = async () => {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      setSubmitError('Введите промпт для генерации изображения');
      return;
    }
    if (trimmedPrompt.length > MAX_PROMPT_LENGTH) {
      setSubmitError(`Промпт не может быть длиннее ${MAX_PROMPT_LENGTH} символов.`);
      return;
    }
    if (steps === null || sizeValue === null) {
      setSubmitError('Параметры модели ещё загружаются. Подождите пару секунд.');
      return;
    }
    setSubmitError(null);
    setStatusError(null);
    setImageUrl(null);
    setJobStatus(null);
    setJobId(null);

    let togetherKeyValue: string | null = null;
    try {
      togetherKeyValue = await readTogetherKey();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Не удалось получить Together Key';
      setSubmitError(message);
      if (!keyAvailable && onRequireKeySetup) {
        onRequireKeySetup();
      }
      return;
    }

    setIsGenerating(true);
    try {
      const response = await createImageGenerationJob({
        prompt: trimmedPrompt,
        width: sizeValue,
        height: sizeValue,
        steps,
        togetherKey: togetherKeyValue,
      });
      setJobId(response.job_id);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === 'model_not_allowed') {
          const modelName = capabilities?.model ?? 'неизвестно';
          setSubmitError(`Модель недоступна. Разрешена: ${modelName}`);
        } else {
          setSubmitError(error.message);
        }
      } else {
        const message = error instanceof Error ? error.message : 'Не удалось создать задачу генерации';
        setSubmitError(message);
      }
      setIsGenerating(false);
    } finally {
      togetherKeyValue = null;
    }
  };

  const statusBadgeClass = useMemo(() => {
    const status = jobStatus?.status;
    if (!status) {
      return 'status-idle';
    }
    if (status === 'done') {
      return 'status-success';
    }
    if (status === 'error') {
      return 'status-error';
    }
    return 'status-progress';
  }, [jobStatus]);

  return (
    <section className="image-generation-panel">
      <header className="panel-header">
        <div className="panel-title">
          <ImageIcon className="icon" />
          <div>
            <h3>Генерация изображений (Together FLUX)</h3>
            <p>
              BYOK — ключ хранится в IndexedDB, на сервер передаётся только в рамках запроса. Разрешённая модель:
              {' '}
              <strong>{capabilities?.model ?? 'загружается…'}</strong>. Для FLUX.1-schnell-Free допустимы steps 1–4 (дефолт: 4).
            </p>
          </div>
        </div>
        {!keyAvailable && (
          <div className="cta-warning" role="alert">
            <AlertTriangle className="icon" />
            <span>Сохраните Together API Key в настройках, чтобы разблокировать генерацию.</span>
          </div>
        )}
      </header>

      <div className="panel-body">
        <label className="setting-label" htmlFor="imagePrompt">Промпт</label>
        <textarea
          id="imagePrompt"
          className="settings-textarea"
          rows={4}
          maxLength={MAX_PROMPT_LENGTH}
          placeholder="Опишите желаемое изображение..."
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          disabled={isGenerating}
        />
        <div className="panel-row">
          <div className="panel-field">
            <label className="setting-label" htmlFor="imageSize">Размер</label>
            <select
              id="imageSize"
              className="settings-select"
              value={sizeValue ?? ''}
              onChange={(event) => {
                const value = Number(event.target.value);
                setSizeValue(Number.isFinite(value) ? value : null);
              }}
              disabled={isGenerating || !capabilities}
            >
              <option value="" disabled>{capabilities ? 'Выберите размер' : 'Загрузка…'}</option>
              {(capabilities?.sizes_allowed ?? []).map((option) => (
                <option key={option} value={option}>{`${option} x ${option}`}</option>
              ))}
            </select>
          </div>
          <div className="panel-field">
            <label className="setting-label" htmlFor="imageSteps">Steps</label>
            <select
              id="imageSteps"
              className="settings-select"
              value={steps ?? ''}
              onChange={(event) => {
                const value = Number(event.target.value);
                setSteps(Number.isFinite(value) ? value : null);
              }}
              disabled={isGenerating || !capabilities}
            >
              <option value="" disabled>{capabilities ? 'Выберите steps' : 'Загрузка…'}</option>
              {(capabilities?.steps_allowed ?? []).map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          className="settings-button"
          onClick={handleGenerate}
          disabled={isGenerating || !keyAvailable || !capabilities}
        >
          {isGenerating ? (
            <>
              <Loader2 className="icon spin" />
              Генерация...
            </>
          ) : (
            'Сгенерировать'
          )}
        </button>

        {submitError && (
          <div className="feedback feedback-error">
            <AlertTriangle className="icon" />
            <span>{submitError}</span>
          </div>
        )}

        {jobStatus && (
          <div className={`job-status ${statusBadgeClass}`}>
            <div className="status-row">
              <span className="status-label">Статус:</span>
              <strong>{STATUS_LABELS[jobStatus.status]}</strong>
              {jobStatus.status === 'running' && <Loader2 className="icon spin" />}
              {jobStatus.status === 'queued' && <Clock className="icon" />}
              {jobStatus.status === 'done' && <CheckCircle2 className="icon" />}
              {jobStatus.status === 'error' && <AlertTriangle className="icon" />}
            </div>
            <div className="status-meta">
              <span>Job ID: {jobStatus.job_id}</span>
              {jobStatus.duration_ms && (
                <span>Время: {(jobStatus.duration_ms / 1000).toFixed(1)} с</span>
              )}
              <span>
                Размер: {jobStatus.width}×{jobStatus.height}, steps {jobStatus.steps}
              </span>
            </div>
            {jobStatus.error_message && (
              <div className="status-error-message" role="alert">
                <AlertTriangle className="icon" />
                <span>{jobStatus.error_message}</span>
              </div>
            )}
          </div>
        )}

        {statusError && (
          <div className="feedback feedback-error">
            <AlertTriangle className="icon" />
            <span>{statusError}</span>
          </div>
        )}

        {imageUrl && (
          <div className="result-preview">
            <img src={imageUrl} alt="Результат генерации" className="result-image" />
            <a
              className="settings-button secondary"
              href={imageUrl}
              download={`together-flux-${jobId ?? 'result'}.webp`}
            >
              Скачать WEBP
            </a>
          </div>
        )}
      </div>
    </section>
  );
};

export default ImageGenerationPanel;
