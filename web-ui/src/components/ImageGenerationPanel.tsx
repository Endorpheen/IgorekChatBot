import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, ImageIcon, Loader2, RefreshCcw, Search } from 'lucide-react';
import type {
  ImageJobStatus,
  ImageJobStatusResponse,
  ProviderListResponse,
  ProviderModelSpec,
  ProviderModelsResponse,
  ProviderSummary,
} from '../types/image';
import {
  InvalidPinError,
  loadMetadata,
  loadProviderKey,
} from '../storage/togetherKeyStorage';
import {
  deleteCatalog,
  readCatalog,
  writeCatalog,
} from '../storage/modelCatalogStorage';
import { isProviderEnabled, listEnabledProviders } from '../storage/providerPreferences';
import {
  ApiError,
  buildApiUrl,
  createImageGenerationJob,
  fetchImageJobStatus,
  fetchProviderList,
  fetchProviderModels,
  searchProviderModels,
  validateProviderKey,
} from '../utils/api';
import { getImageSessionId } from '../utils/session';

interface ImageGenerationPanelProps {
  onRequireKeySetup?: () => void;
  refreshKeySignal?: number;
}

const MAX_PROMPT_LENGTH = 800;
const SESSION_STATE_KEY = 'image-generation-state';
const DEFAULT_PROVIDER = 'together';

interface StoredImageGenerationState {
  providerId: string;
  modelId: string | null;
  prompt: string;
  width: number | null;
  height: number | null;
  steps: number | null;
  cfg: number | null;
  seed: number | null;
  mode: string | null;
  jobId: string | null;
  downloadUrl: string | null;
}

const readStoredState = (): StoredImageGenerationState => {
  if (typeof window === 'undefined') {
    return {
      providerId: DEFAULT_PROVIDER,
      modelId: null,
      prompt: '',
      width: null,
      height: null,
      steps: null,
      cfg: null,
      seed: null,
      mode: null,
      jobId: null,
      downloadUrl: null,
    };
  }
  try {
    const raw = window.sessionStorage.getItem(SESSION_STATE_KEY);
    if (!raw) {
      return {
        providerId: DEFAULT_PROVIDER,
        modelId: null,
        prompt: '',
        width: null,
        height: null,
        steps: null,
        cfg: null,
        seed: null,
        mode: null,
        jobId: null,
        downloadUrl: null,
      };
    }
    const parsed = JSON.parse(raw) as Partial<StoredImageGenerationState>;
    return {
      providerId: typeof parsed.providerId === 'string' ? parsed.providerId : DEFAULT_PROVIDER,
      modelId: typeof parsed.modelId === 'string' ? parsed.modelId : null,
      prompt: typeof parsed.prompt === 'string' ? parsed.prompt : '',
      width: typeof parsed.width === 'number' ? parsed.width : null,
      height: typeof parsed.height === 'number' ? parsed.height : null,
      steps: typeof parsed.steps === 'number' ? parsed.steps : null,
      cfg: typeof parsed.cfg === 'number' ? parsed.cfg : null,
      seed: typeof parsed.seed === 'number' ? parsed.seed : null,
      mode: typeof parsed.mode === 'string' ? parsed.mode : null,
      jobId: typeof parsed.jobId === 'string' ? parsed.jobId : null,
      downloadUrl: typeof parsed.downloadUrl === 'string' ? parsed.downloadUrl : null,
    };
  } catch (error) {
    console.warn('Не удалось прочитать сохранённое состояние генерации:', error);
    return {
      providerId: DEFAULT_PROVIDER,
      modelId: null,
      prompt: '',
      width: null,
      height: null,
      steps: null,
      cfg: null,
      seed: null,
      mode: null,
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

const SIZE_PRESETS = [
  { id: 'preset-1024', label: '1:1 (1024×1024)', width: 1024, height: 1024 },
  { id: 'preset-1344x768', label: '16:9 (1344×768)', width: 1344, height: 768 },
  { id: 'preset-768x1344', label: '9:16 (768×1344)', width: 768, height: 1344 },
  { id: 'preset-1216x832', label: '3:2 (1216×832)', width: 1216, height: 832 },
  { id: 'preset-832x1216', label: '2:3 (832×1216)', width: 832, height: 1216 },
  { id: 'custom', label: 'Custom', width: 0, height: 0 },
];

const ImageGenerationPanel: React.FC<ImageGenerationPanelProps> = ({ onRequireKeySetup, refreshKeySignal }) => {
  const storedStateRef = useRef<StoredImageGenerationState | null>(null);
  if (!storedStateRef.current) {
    storedStateRef.current = readStoredState();
  }

  const [providerList, setProviderList] = useState<ProviderSummary[]>([]);
  const [providerId, setProviderId] = useState<string>(storedStateRef.current.providerId ?? DEFAULT_PROVIDER);
  const [providerKeys, setProviderKeys] = useState<Record<string, { hasKey: boolean; encrypted: boolean }>>({});
  const [enabledProviders, setEnabledProviders] = useState<Record<string, boolean>>(() => listEnabledProviders());
  const [models, setModels] = useState<ProviderModelSpec[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelId, setModelId] = useState<string | null>(storedStateRef.current.modelId);
  const [modelSearch, setModelSearch] = useState('');
  const [recommendedOnly, setRecommendedOnly] = useState(false);
  const [searchResults, setSearchResults] = useState<ProviderModelSpec[] | null>(null);
  const [isSearchingModels, setIsSearchingModels] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const searchRequestIdRef = useRef(0);

  const [prompt, setPrompt] = useState<string>(storedStateRef.current.prompt ?? '');
  const [width, setWidth] = useState<number | null>(storedStateRef.current.width ?? null);
  const [height, setHeight] = useState<number | null>(storedStateRef.current.height ?? null);
  const [steps, setSteps] = useState<number | null>(storedStateRef.current.steps ?? null);
  const [cfg, setCfg] = useState<number | null>(storedStateRef.current.cfg ?? null);
  const [seed, setSeed] = useState<number | null>(storedStateRef.current.seed ?? null);
  const [mode, setMode] = useState<string | null>(storedStateRef.current.mode ?? null);

  const [jobId, setJobId] = useState<string | null>(storedStateRef.current.jobId ?? null);
  const [jobStatus, setJobStatus] = useState<ImageJobStatusResponse | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(storedStateRef.current.downloadUrl ?? null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isFetchingKey, setIsFetchingKey] = useState(false);

  const objectUrlRef = useRef<string | null>(null);
  const pollTimeoutRef = useRef<number | null>(null);
  const pendingPollRef = useRef<(() => void) | null>(null);

  const selectedModel = useMemo(() => {
    const source = searchResults ?? models;
    return source.find(model => model.id === modelId) ?? null;
  }, [searchResults, models, modelId]);

  const effectiveLimits = useMemo(() => {
    const limits = selectedModel?.limits ?? {};
    const defaults = selectedModel?.defaults ?? {};
    return {
      minSteps: limits.min_steps ?? 1,
      maxSteps: limits.max_steps ?? 50,
      minCfg: limits.min_cfg ?? 0,
      maxCfg: limits.max_cfg ?? 20,
      minWidth: limits.min_width ?? 512,
      maxWidth: limits.max_width ?? 1536,
      minHeight: limits.min_height ?? 512,
      maxHeight: limits.max_height ?? 1536,
      presets: (limits.presets ?? []).map(pair => ({ width: pair[0], height: pair[1] })),
      defaultWidth: defaults.width ?? 1024,
      defaultHeight: defaults.height ?? 1024,
      defaultSteps: defaults.steps ?? 28,
      defaultCfg: defaults.cfg ?? 4.5,
    };
  }, [selectedModel]);

  const sizeOptions = useMemo(() => {
    const options = [...SIZE_PRESETS.filter(option => option.id !== 'custom')];
    for (const preset of effectiveLimits.presets) {
      if (!options.some(option => option.width === preset.width && option.height === preset.height)) {
        options.push({
          id: `preset-${preset.width}x${preset.height}`,
          label: `${preset.width}×${preset.height}`,
          width: preset.width,
          height: preset.height,
        });
      }
    }
    options.sort((a, b) => a.label.localeCompare(b.label));
    options.push(SIZE_PRESETS.find(option => option.id === 'custom')!);
    return options;
  }, [effectiveLimits.presets]);

  const sizePresetId = useMemo(() => {
    if (!width || !height) {
      return 'custom';
    }
    const match = sizeOptions.find(option => option.width === width && option.height === height);
    return match ? match.id : 'custom';
  }, [sizeOptions, width, height]);

  const supportsMode = selectedModel?.capabilities?.supports_mode && (selectedModel.capabilities.modes?.length ?? 0) > 0;

  const searchActive = isSearchingModels || searchResults !== null;
  const displayedModels = useMemo(() => {
    let list = searchActive ? (searchResults ?? []) : models;

    if (!searchActive) {
      const normalizedSearch = modelSearch.trim().toLowerCase();
      if (normalizedSearch) {
        list = list.filter(model => {
          return model.display_name.toLowerCase().includes(normalizedSearch) || model.id.toLowerCase().includes(normalizedSearch);
        });
      }
    }

    if (recommendedOnly) {
      list = list.filter(model => model.recommended);
    }

    return list;
  }, [searchActive, searchResults, models, modelSearch, recommendedOnly]);
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
  return downloadUrl.startsWith('http') ? downloadUrl : buildApiUrl(downloadUrl);
}, [downloadUrl]);

  const isLoadingModelOptions = modelsLoading || isSearchingModels;
  const noModelsAvailable = !isLoadingModelOptions && displayedModels.length === 0;
  const emptyModelsMessage = searchResults !== null
    ? (searchError ? `Ошибка поиска: ${searchError}` : 'По запросу ничего не найдено.')
    : 'Нет моделей, удовлетворяющих критериям.';

  const updateStoredState = useCallback((partial: Partial<StoredImageGenerationState>) => {
    const nextState: StoredImageGenerationState = {
      providerId: providerId,
      modelId: modelId,
      prompt,
      width,
      height,
      steps,
      cfg,
      seed,
      mode,
      jobId,
      downloadUrl,
      ...partial,
    } as StoredImageGenerationState;
    storedStateRef.current = nextState;
    writeStoredState(nextState);
  }, [providerId, modelId, prompt, width, height, steps, cfg, seed, mode, jobId, downloadUrl]);

  useEffect(() => {
    updateStoredState({});
  }, [prompt, width, height, steps, cfg, seed, mode, jobId, downloadUrl, providerId, modelId, updateStoredState]);

  useEffect(() => {
    const source = searchResults ?? models;
    if (source.length === 0) {
      return;
    }
    if (!modelId || !source.some(model => model.id === modelId)) {
      setModelId(source[0]?.id ?? null);
    }
  }, [searchResults, models, modelId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetchProviderList();
        if (cancelled) {
          return;
        }
        const providers = (response as ProviderListResponse).providers ?? [];
        setProviderList(providers);
        if (!providers.some(provider => provider.id === providerId)) {
          setProviderId(providers[0]?.id ?? DEFAULT_PROVIDER);
        }
        const metadataEntries = await Promise.all(
          providers.map(async provider => {
            try {
              const metadata = await loadMetadata(provider.id);
              return [provider.id, { hasKey: metadata.hasKey, encrypted: metadata.encrypted }] as const;
            } catch {
              return [provider.id, { hasKey: false, encrypted: false }] as const;
            }
          }),
        );
        if (!cancelled) {
          setProviderKeys(Object.fromEntries(metadataEntries));
          setEnabledProviders(listEnabledProviders());
        }
      } catch (error) {
        console.error('Не удалось загрузить список провайдеров', error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!providerList.length) {
      return;
    }
    let cancelled = false;
    (async () => {
      const entries = await Promise.all(providerList.map(async provider => {
        try {
          const metadata = await loadMetadata(provider.id);
          return [provider.id, { hasKey: metadata.hasKey, encrypted: metadata.encrypted }] as const;
        } catch {
          return [provider.id, { hasKey: false, encrypted: false }] as const;
        }
      }));
      if (!cancelled) {
        setProviderKeys(Object.fromEntries(entries));
        setEnabledProviders(listEnabledProviders());
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKeySignal, providerList]);

  const readProviderApiKey = useCallback(async (targetProviderId: string): Promise<string> => {
    setIsFetchingKey(true);
    try {
      const metadata = await loadMetadata(targetProviderId);
      if (!metadata.hasKey) {
        throw new Error('Сохраните API ключ в настройках.');
      }
      if (!metadata.encrypted) {
        const { key } = await loadProviderKey(targetProviderId);
        return key;
      }
      while (true) {
        const pin = window.prompt(`Введите PIN для ключа провайдера ${targetProviderId.toUpperCase()}`);
        if (!pin) {
          throw new Error('Для генерации требуется PIN-код.');
        }
        try {
          const { key } = await loadProviderKey(targetProviderId, pin.trim());
          return key;
        } catch (error) {
          if (error instanceof InvalidPinError) {
            alert('Неверный PIN. Попробуйте снова.');
            continue;
          }
          throw error instanceof Error ? error : new Error('Не удалось расшифровать ключ');
        }
      }
    } finally {
      setIsFetchingKey(false);
    }
  }, []);

  const ensureModelsLoaded = useCallback(async (targetProviderId: string, force = false) => {
    if (!providerKeys[targetProviderId]?.hasKey || enabledProviders[targetProviderId] === false) {
      setModels([]);
      setModelId(null);
      return;
    }

    setModelsLoading(true);
    setSearchError(null);
    setSubmitError(null);

    let cachedUsed = false;
    try {
      if (!force) {
        const cached = await readCatalog(targetProviderId);
        if (cached && Array.isArray(cached.models) && cached.models.length > 0) {
          const cachedModels = cached.models.map(model => ({ ...model, recommended: Boolean(model.recommended) }));
          setModels(cachedModels);
          if (!cachedModels.some(model => model.id === modelId)) {
            setModelId(cachedModels[0]?.id ?? null);
          }
          cachedUsed = true;
        }
      }

      const apiKey = await readProviderApiKey(targetProviderId);
      const fresh = await fetchProviderModels(targetProviderId, apiKey, { force });
      const responseModels = (fresh as ProviderModelsResponse).models ?? [];
      const normalizedModels = responseModels.map(model => ({ ...model, recommended: Boolean(model.recommended) }));

      setModels(normalizedModels);
      await writeCatalog(targetProviderId, normalizedModels);
      if (!normalizedModels.some(model => model.id === modelId)) {
        setModelId(normalizedModels[0]?.id ?? null);
      }
      cachedUsed = false;
    } catch (error) {
      console.error('Не удалось получить список моделей:', error);
      if (!cachedUsed) {
        if (error instanceof ApiError) {
          setSubmitError(error.message);
        } else if (error instanceof Error) {
          setSubmitError(error.message);
        } else {
          setSubmitError('Не удалось загрузить список моделей');
        }
      }
    } finally {
      setModelsLoading(false);
    }
  }, [modelId, providerKeys, readProviderApiKey, enabledProviders]);

  useEffect(() => {
    if (!providerList.length) {
      return;
    }
    void ensureModelsLoaded(providerId, false);
  }, [providerId, providerList, ensureModelsLoaded, enabledProviders]);

  useEffect(() => {
    if (!selectedModel) {
      return;
    }
    const defaults = selectedModel.defaults ?? {};
    if (width === null) {
      setWidth(defaults.width ?? 1024);
    }
    if (height === null) {
      setHeight(defaults.height ?? 1024);
    }
    if (steps === null) {
      setSteps(defaults.steps ?? 28);
    }
    if (cfg === null) {
      setCfg(defaults.cfg ?? 4.5);
    }
    if (selectedModel.capabilities?.supports_seed && seed === null && defaults.seed) {
      setSeed(defaults.seed);
    }
    if (selectedModel.capabilities?.supports_mode && !mode && defaults.mode) {
      setMode(defaults.mode);
    }
  }, [selectedModel, width, height, steps, cfg, seed, mode]);

  useEffect(() => {
    if (!downloadUrl) {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      setImageUrl(null);
      return;
    }

    const fetchPreview = async () => {
      try {
        const response = await fetch(downloadUrl.startsWith('http') ? downloadUrl : buildApiUrl(downloadUrl), {
          headers: {
            'X-Client-Session': getImageSessionId(),
          },
        });
        if (!response.ok) {
          throw new Error('Статус ответа не 200');
        }
        const blob = await response.blob();
        if (objectUrlRef.current) {
          URL.revokeObjectURL(objectUrlRef.current);
        }
        const objectUrl = URL.createObjectURL(blob);
        objectUrlRef.current = objectUrl;
        setImageUrl(objectUrl);
      } catch (error) {
        console.warn('Не удалось загрузить изображение результата', error);
        setStatusError('Не удалось загрузить изображение результата');
      }
    };

    fetchPreview();

    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [downloadUrl]);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    let cancelled = false;

    const clearScheduledPoll = () => {
      if (pollTimeoutRef.current !== null) {
        clearTimeout(pollTimeoutRef.current);
        pollTimeoutRef.current = null;
      }
      pendingPollRef.current = null;
    };

    const schedulePoll = () => {
      pendingPollRef.current = poll;
      pollTimeoutRef.current = window.setTimeout(() => {
        pollTimeoutRef.current = null;
        if (pendingPollRef.current) {
          pendingPollRef.current();
        }
      }, 2500);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        clearScheduledPoll();
        pendingPollRef.current = poll;
      } else if (document.visibilityState === 'visible' && pendingPollRef.current) {
        const restart = pendingPollRef.current;
        pendingPollRef.current = null;
        void restart();
      }
    };

    const poll = async () => {
      if (cancelled || document.visibilityState === 'hidden') {
        pendingPollRef.current = poll;
        return;
      }

      try {
        const status = await fetchImageJobStatus(jobId);
        if (cancelled) {
          return;
        }
        setJobStatus(status);
        if (status.status === 'done') {
          setIsGenerating(false);
          setDownloadUrl(status.result_url ?? null);
          clearScheduledPoll();
        } else if (status.status === 'error') {
          setIsGenerating(false);
          setStatusError(status.error_message ?? 'Генерация завершилась с ошибкой');
          setDownloadUrl(null);
          clearScheduledPoll();
        } else {
          schedulePoll();
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError) {
          setStatusError(error.message);
        } else {
          setStatusError('Не удалось получить статус задачи');
        }
        setIsGenerating(false);
        setDownloadUrl(null);
        clearScheduledPoll();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    void poll();

    return () => {
      cancelled = true;
      clearScheduledPoll();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [jobId]);

  const providerEnabled = enabledProviders[providerId] ?? isProviderEnabled(providerId);
  const keyAvailable = providerEnabled && (providerKeys[providerId]?.hasKey ?? false);

  useEffect(() => {
    const trimmedSearch = modelSearch.trim();
    const isReplicate = providerId.toLowerCase() === 'replicate';

    if (!isReplicate || !keyAvailable || trimmedSearch.length < 2) {
      setSearchResults(null);
      setIsSearchingModels(false);
      setSearchError(null);
      return;
    }

    let cancelled = false;
    const requestId = ++searchRequestIdRef.current;
    const timer = window.setTimeout(() => {
      (async () => {
        setIsSearchingModels(true);
        setSearchError(null);
        try {
          const apiKey = await readProviderApiKey(providerId);
          if (cancelled || searchRequestIdRef.current !== requestId) {
            return;
          }
          const response = await searchProviderModels(providerId, apiKey, trimmedSearch, { limit: 50 });
          console.log('Search results:', response);
          if (!cancelled && searchRequestIdRef.current === requestId) {
            setSearchResults(response.models ?? []);
          }
        } catch (error) {
          console.error('Не удалось выполнить поиск моделей:', error);
          if (!cancelled && searchRequestIdRef.current === requestId) {
            setSearchResults([]);
            if (error instanceof ApiError) {
              setSearchError(error.message);
            } else if (error instanceof Error) {
              setSearchError(error.message);
            } else {
              setSearchError('Не удалось выполнить поиск моделей');
            }
          }
        } finally {
          if (!cancelled && searchRequestIdRef.current === requestId) {
            setIsSearchingModels(false);
          }
        }
      })();
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [modelSearch, providerId, keyAvailable, readProviderApiKey]);

  const handleRefreshModels = async () => {
    try {
      await deleteCatalog(providerId);
      await ensureModelsLoaded(providerId, true);
    } catch (error) {
      console.error('Не удалось обновить список моделей', error);
    }
  };

  const handleValidateKey = async () => {
    try {
      const apiKey = await readProviderApiKey(providerId);
      await validateProviderKey(providerId, apiKey);
      alert('Ключ успешно прошёл проверку');
    } catch (error) {
      if (error instanceof ApiError) {
        alert(error.message);
      } else if (error instanceof Error) {
        alert(error.message);
      } else {
        alert('Проверка ключа не удалась');
      }
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
    if (!providerId) {
      setSubmitError('Выберите провайдера');
      return;
    }
    if (!providerEnabled) {
      setSubmitError('Провайдер отключён. Включите его в настройках.');
      return;
    }
    if (!modelId) {
      setSubmitError('Выберите модель');
      return;
    }
    if (!selectedModel) {
      setSubmitError('Выбранная модель недоступна.');
      return;
    }
    if (!providerKeys[providerId]?.hasKey) {
      setSubmitError('Сохраните ключ провайдера в настройках.');
      if (onRequireKeySetup) {
        onRequireKeySetup();
      }
      return;
    }
    if (width === null || height === null) {
      setSubmitError('Выберите размер изображения');
      return;
    }
    if (steps === null) {
      setSubmitError('Укажите количество шагов');
      return;
    }
    setSubmitError(null);
    setStatusError(null);
    setImageUrl(null);
    setJobStatus(null);
    setJobId(null);
    setDownloadUrl(null);

    let apiKey: string;
    try {
      apiKey = await readProviderApiKey(providerId);
    } catch (error) {
      if (error instanceof Error) {
        setSubmitError(error.message);
      } else {
        setSubmitError('Не удалось получить API ключ');
      }
      if (onRequireKeySetup) {
        onRequireKeySetup();
      }
      return;
    }

    setIsGenerating(true);
    try {
      const extras: Record<string, unknown> = {};
      if (selectedModel.metadata) {
        extras.metadata = selectedModel.metadata;
      }
      const response = await createImageGenerationJob({
        provider: providerId,
        model: modelId,
        prompt: trimmedPrompt,
        width,
        height,
        steps,
        cfg: cfg ?? undefined,
        seed: seed ?? undefined,
        mode: mode ?? undefined,
        extras,
        apiKey,
      });
      setJobId(response.job_id);
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
      } else if (error instanceof Error) {
        setSubmitError(error.message);
      } else {
        setSubmitError('Не удалось создать задачу генерации');
      }
      setIsGenerating(false);
    }
  };


  return (
    <section className="image-generation-panel">
      <header className="panel-header">
        <div className="panel-title">
          <ImageIcon className="icon" />
          <div>
            <h3>Генерация изображений</h3>
            <p>Выберите провайдера, модель и параметры. Ключи хранятся локально (IndexedDB, PIN по желанию).</p>
          </div>
        </div>
        {!providerEnabled && (
          <div className="cta-warning" role="alert">
            <AlertTriangle className="icon" />
            <span>Провайдер отключён. Включите его во вкладке настроек, чтобы использовать.</span>
          </div>
        )}
        {providerEnabled && !keyAvailable && (
          <div className="cta-warning" role="alert">
            <AlertTriangle className="icon" />
            <span>Сохраните API ключ выбранного провайдера в настройках, чтобы разблокировать генерацию.</span>
          </div>
        )}
      </header>

      <div className="panel-body">
        <div className="panel-row">
          <div className="panel-field">
            <label className="setting-label" htmlFor="imageProvider">Провайдер</label>
            <select
              id="imageProvider"
              className="settings-select"
              value={providerId}
              onChange={(event) => {
                setProviderId(event.target.value);
                setModelSearch('');
                setRecommendedOnly(false);
                setModelId(null);
                setSearchResults(null);
                setSearchError(null);
                setIsSearchingModels(false);
              }}
            >
              {providerList.map(provider => (
                <option key={provider.id} value={provider.id}>{provider.label}</option>
              ))}
            </select>
          </div>
          <div className="panel-field">
            <label className="setting-label" htmlFor="imageProviderRefresh">Модели</label>
            <div className="model-selector-header">
              <button
                type="button"
                id="imageProviderRefresh"
                className="settings-button secondary"
                onClick={handleRefreshModels}
                disabled={isLoadingModelOptions || !keyAvailable}
              >
                <RefreshCcw className="icon" />
                Обновить модели
              </button>
              <button
                type="button"
                className="settings-button secondary"
                onClick={handleValidateKey}
                disabled={isFetchingKey || !keyAvailable}
              >
                Проверить ключ
              </button>
            </div>
          </div>
        </div>

        <div className="model-filter">
          <div className="model-filter-search">
            <Search className="icon" />
            <input
              type="text"
              value={modelSearch}
              onChange={(event) => setModelSearch(event.target.value)}
              placeholder="Найти модель..."
            />
          </div>
          <label className="model-filter-checkbox">
            <input
              type="checkbox"
              checked={recommendedOnly}
              onChange={(event) => setRecommendedOnly(event.target.checked)}
            />
            Только рекомендованные
          </label>
        </div>

        <div className="model-list">
          {isLoadingModelOptions && (
            <div className="model-loading">
              <Loader2 className="icon spin" /> {isSearchingModels ? 'Поиск моделей...' : 'Загрузка моделей...'}
            </div>
          )}
          {noModelsAvailable && (
            <div className="model-empty">{emptyModelsMessage}</div>
          )}
          {!isLoadingModelOptions && displayedModels.length > 0 && (
            <select
              className="settings-select"
              value={modelId ?? ''}
              onChange={(event) => setModelId(event.target.value)}
            >
              <option value="" disabled>Выберите модель</option>
              {displayedModels.map(model => (
                <option key={model.id} value={model.id}>
                  {`${model.recommended ? '★ ' : ''}${model.display_name}`}
                </option>
              ))}
            </select>
          )}
        </div>

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
              value={sizePresetId}
              onChange={(event) => {
                const option = sizeOptions.find(item => item.id === event.target.value);
                if (!option || option.id === 'custom') {
                  setWidth(width ?? effectiveLimits.defaultWidth);
                  setHeight(height ?? effectiveLimits.defaultHeight);
                  return;
                }
                setWidth(option.width);
                setHeight(option.height);
              }}
              disabled={isGenerating || isLoadingModelOptions || !selectedModel}
            >
              {sizeOptions.map(option => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
            {sizePresetId === 'custom' && (
              <div className="custom-size-inputs">
                <input
                  type="number"
                  min={effectiveLimits.minWidth}
                  max={effectiveLimits.maxWidth}
                  value={width ?? ''}
                  onChange={(event) => setWidth(Number(event.target.value))}
                  placeholder="Ширина"
                />
                <input
                  type="number"
                  min={effectiveLimits.minHeight}
                  max={effectiveLimits.maxHeight}
                  value={height ?? ''}
                  onChange={(event) => setHeight(Number(event.target.value))}
                  placeholder="Высота"
                />
              </div>
            )}
          </div>
          <div className="panel-field">
            <label className="setting-label" htmlFor="imageSteps">Steps</label>
            <input
              id="imageSteps"
              type="number"
              className="settings-input"
              value={steps ?? ''}
              min={effectiveLimits.minSteps}
              max={effectiveLimits.maxSteps}
              onChange={(event) => setSteps(Number(event.target.value))}
              disabled={isGenerating || !selectedModel}
            />
            <div className="field-hint">Допустимо: {effectiveLimits.minSteps}–{effectiveLimits.maxSteps}</div>
          </div>
        </div>

        <div className="panel-row">
          {selectedModel?.capabilities?.supports_cfg !== false && (
            <div className="panel-field">
              <label className="setting-label" htmlFor="imageCfg">CFG / Guidance</label>
              <input
                id="imageCfg"
                type="number"
                className="settings-input"
                value={cfg ?? ''}
                min={effectiveLimits.minCfg}
                max={effectiveLimits.maxCfg}
                step={0.5}
                onChange={(event) => setCfg(Number(event.target.value))}
                disabled={isGenerating}
              />
              <div className="field-hint">Допустимо: {effectiveLimits.minCfg}–{effectiveLimits.maxCfg}</div>
            </div>
          )}
          {selectedModel?.capabilities?.supports_seed !== false && (
            <div className="panel-field">
              <label className="setting-label" htmlFor="imageSeed">Seed</label>
              <input
                id="imageSeed"
                type="number"
                className="settings-input"
                value={seed ?? ''}
                onChange={(event) => setSeed(Number(event.target.value))}
                disabled={isGenerating}
              />
              <div className="field-hint">0 = случайно</div>
            </div>
          )}
          {supportsMode && (
            <div className="panel-field">
              <label className="setting-label" htmlFor="imageMode">Режим</label>
              <select
                id="imageMode"
                className="settings-select"
                value={mode ?? ''}
                onChange={(event) => setMode(event.target.value || null)}
                disabled={isGenerating}
              >
                <option value="">Авто</option>
                {selectedModel?.capabilities?.modes?.map(option => (
                  <option key={option.id} value={option.id}>
                    {option.label ?? option.id}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <button
          type="button"
          className="settings-button"
          onClick={handleGenerate}
          disabled={isGenerating || !keyAvailable || !selectedModel}
        >
          {isGenerating ? (
            <>
              <Loader2 className="icon spin" /> Генерация...
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
              <span>Провайдер: {jobStatus.provider}</span>
              <span>Модель: {jobStatus.model}</span>
              <span>Размер: {jobStatus.width}×{jobStatus.height}, steps {jobStatus.steps}</span>
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
                download={`${providerId}-${jobId ?? 'result'}.webp`}
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
