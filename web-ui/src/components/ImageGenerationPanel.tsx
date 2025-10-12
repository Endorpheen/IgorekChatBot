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
import { useLocation } from 'react-router-dom';

interface ImageGenerationPanelProps {
  onRequireKeySetup?: () => void;
  refreshKeySignal?: number;
}

const MAX_PROMPT_LENGTH = 800;
const SESSION_STATE_KEY = 'image-generation-state';

interface StoredImageGenerationState {
  prompt: string;
  size: number | null;
  steps: number | null;
  jobId: string | null;
  downloadUrl: string | null;
}

const readStoredState = (): StoredImageGenerationState => {
  if (typeof window === 'undefined') {
    return {
      prompt: '',
      size: null,
      steps: null,
      jobId: null,
      downloadUrl: null,
    };
  }
  try {
    const raw = window.sessionStorage.getItem(SESSION_STATE_KEY);
    if (!raw) {
      return {
        prompt: '',
        size: null,
        steps: null,
        jobId: null,
        downloadUrl: null,
      };
    }
    const parsed = JSON.parse(raw) as Partial<StoredImageGenerationState>;
    return {
      prompt: typeof parsed.prompt === 'string' ? parsed.prompt : '',
      size: typeof parsed.size === 'number' ? parsed.size : null,
      steps: typeof parsed.steps === 'number' ? parsed.steps : null,
      jobId: typeof parsed.jobId === 'string' ? parsed.jobId : null,
      downloadUrl: typeof parsed.downloadUrl === 'string' ? parsed.downloadUrl : null,
    };
  } catch (error) {
    console.warn('Не удалось прочитать сохранённое состояние генерации:', error);
    return {
      prompt: '',
      size: null,
      steps: null,
      jobId: null,
      downloadUrl: null,
    };
  }
};

const writeStoredState = (state: StoredImageGenerationState) => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage.setItem(SESSION_STATE_KEY, JSON.stringify(state));
  } catch (error) {
    console.warn('Не удалось сохранить состояние генерации:', error);
  }
};

const STATUS_LABELS: Record<ImageJobStatus, string> = {
  queued: 'В очереди',
  running: 'Генерация',
  done: 'Готово',
  error: 'Ошибка',
};

const ImageGenerationPanel: React.FC<ImageGenerationPanelProps> = ({ onRequireKeySetup, refreshKeySignal }) => {
  const location = useLocation();
  const storedStateRef = useRef<StoredImageGenerationState | null>(null);
  if (!storedStateRef.current) {
    storedStateRef.current = readStoredState();
  }
  const storedState = storedStateRef.current;

  const [prompt, setPrompt] = useState<string>(storedState?.prompt ?? '');
  const [sizeValue, setSizeValue] = useState<number | null>(storedState?.size ?? null);
  const [steps, setSteps] = useState<number | null>(storedState?.steps ?? null);
  const [jobId, setJobId] = useState<string | null>(storedState?.jobId ?? null);
  const [jobStatus, setJobStatus] = useState<ImageJobStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(storedState?.downloadUrl ?? null);
  const [keyAvailable, setKeyAvailable] = useState(false);
  const objectUrlRef = useRef<string | null>(null);
  const [capabilities, setCapabilities] = useState<ImageModelCapabilities | null>(null);
  const pendingParamsRef = useRef<{ size?: number | null; steps?: number | null } | null>(null);

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
        setSteps((prev) => {
          const pendingValue = pendingParamsRef.current?.steps;
          if (typeof pendingValue === 'number' && fetched.steps_allowed.includes(pendingValue)) {
            return pendingValue;
          }
          if (prev !== null && fetched.steps_allowed.includes(prev)) {
            return prev;
          }
          return fetched.default_steps;
        });
        setSizeValue((prev) => {
          const pendingValue = pendingParamsRef.current?.size;
          if (typeof pendingValue === 'number' && fetched.sizes_allowed.includes(pendingValue)) {
            return pendingValue;
          }
          if (prev !== null && fetched.sizes_allowed.includes(prev)) {
            return prev;
          }
          return fetched.default_size;
        });
        pendingParamsRef.current = null;
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

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.has('prompt')) {
      const promptParam = params.get('prompt') ?? '';
      if (promptParam !== prompt) {
        setPrompt(promptParam);
      }
    }

    const next: { size?: number | null; steps?: number | null } = {};
    if (params.has('size')) {
      const parsed = Number(params.get('size'));
      next.size = Number.isFinite(parsed) ? parsed : null;
    }
    if (params.has('steps')) {
      const parsed = Number(params.get('steps'));
      next.steps = Number.isFinite(parsed) ? parsed : null;
    }

    if (Object.keys(next).length > 0) {
      pendingParamsRef.current = next;
      if (capabilities) {
        if (typeof next.size === 'number' && capabilities.sizes_allowed.includes(next.size)) {
          setSizeValue(next.size);
        }
        if (typeof next.steps === 'number' && capabilities.steps_allowed.includes(next.steps)) {
          setSteps(next.steps);
        }
        pendingParamsRef.current = null;
      }
    }
  }, [location.search, capabilities, prompt]);

  useEffect(() => {
    const nextState: StoredImageGenerationState = {
      prompt,
      size: sizeValue,
      steps,
      jobId,
      downloadUrl,
    };
    writeStoredState(nextState);
    storedStateRef.current = nextState;
  }, [prompt, sizeValue, steps, jobId, downloadUrl]);

  useEffect(() => {
    if (!downloadUrl) {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      setImageUrl(null);
      return;
    }

    if (imageUrl) {
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const response = await fetch(buildApiUrl(downloadUrl), {
          headers: {
            'X-Client-Session': getImageSessionId(),
          },
        });
        if (!response.ok || cancelled) {
          return;
        }
        const blob = await response.blob();
        if (cancelled) {
          return;
        }
        if (objectUrlRef.current) {
          URL.revokeObjectURL(objectUrlRef.current);
        }
        const objectUrl = URL.createObjectURL(blob);
        objectUrlRef.current = objectUrl;
        setImageUrl(objectUrl);
      } catch (error) {
        if (!cancelled) {
          setStatusError('Не удалось загрузить изображение результата');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [downloadUrl, imageUrl]);

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
          setDownloadUrl(null);
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
        setDownloadUrl(null);
      }
    };

    poll();

    return () => {
      cancelled = true;
    };
  }, [jobId, capabilities]);

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
      setDownloadUrl(status.result_url);
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
    setDownloadUrl(null);

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

  const downloadHref = useMemo(() => {
    if (!downloadUrl) {
      return undefined;
    }
    return buildApiUrl(downloadUrl);
  }, [downloadUrl]);

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
            {downloadHref ? (
              <a
                className="settings-button secondary"
                href={downloadHref}
                download={`together-flux-${jobId ?? 'result'}.webp`}
              >
                Скачать WEBP
              </a>
            ) : (
              <button type="button" className="settings-button secondary" disabled>
                Подготовка файла...
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
};

export default ImageGenerationPanel;
