import type { ThreadSettings } from '../types/settings';

export type ImageProvider = 'openrouter' | 'agentrouter';

const POSITIVE_KEYWORDS = [
  'vision',
  'multimodal',
  'image',
  'gpt-4o',
  'gpt4o',
  'gpt-4.1',
  'gpt4.1',
  'gpt-4v',
  'claude-3.5',
  'claude-3-opus',
  'sonnet',
  'omni',
  'llava',
];

const NEGATIVE_KEYWORDS = [
  'gpt-3.5',
  'gpt-3.1',
  'text-only',
  'text',
  'embedding',
  'rerank',
  'tts',
  'whisper',
  'audio',
  'speech',
];

export const FALLBACK_OPENROUTER_MODEL = 'openai/gpt-4o-mini';
export const FALLBACK_AGENTROUTER_MODEL = 'gpt-4o-mini';

const normalize = (value?: string | null): string => (value ?? '').trim().toLowerCase();

export const supportsVisionModel = (
  provider: ImageProvider,
  model?: string | null,
  hint?: boolean | null,
): boolean => {
  const normalizedModel = normalize(model);
  if (!normalizedModel) {
    return false;
  }

  if (hint === false) {
    return false;
  }
  if (hint === true) {
    return true;
  }

  if (NEGATIVE_KEYWORDS.some((keyword) => normalizedModel.includes(keyword))) {
    return false;
  }

  if (POSITIVE_KEYWORDS.some((keyword) => normalizedModel.includes(keyword))) {
    return true;
  }

  if (provider === 'openrouter' && normalizedModel === normalize(FALLBACK_OPENROUTER_MODEL)) {
    return true;
  }
  if (provider === 'agentrouter' && normalizedModel === normalize(FALLBACK_AGENTROUTER_MODEL)) {
    return true;
  }

  return false;
};

export const validateImageProviderSettings = (
  provider: ImageProvider,
  settings: ThreadSettings,
): string | null => {
  if (provider === 'agentrouter') {
    const baseUrl = settings.agentRouterBaseUrl?.trim();
    const apiKey = settings.agentRouterApiKey?.trim();
    const model = settings.agentRouterModel?.trim();
    if (!baseUrl || !apiKey) {
      return 'Для анализа изображений укажите base URL и API ключ OpenAI Compatible.';
    }
    if (!supportsVisionModel('agentrouter', model)) {
      return 'Эта модель без vision. Выберите модель с поддержкой изображений.';
    }
    return null;
  }

  if (!settings.openRouterApiKey?.trim()) {
    return 'Для анализа изображений укажите API ключ OpenRouter.';
  }
  if (!supportsVisionModel('openrouter', settings.openRouterModel)) {
    return 'Эта модель OpenRouter без vision. Выберите модель с поддержкой изображений.';
  }
  return null;
};

export const providerSupportsVision = (
  provider: ImageProvider,
  settings: ThreadSettings,
): boolean => {
  if (provider === 'agentrouter') {
    if (!settings.agentRouterApiKey?.trim() || !settings.agentRouterBaseUrl?.trim()) {
      return false;
    }
    return supportsVisionModel('agentrouter', settings.agentRouterModel);
  }
  if (!settings.openRouterApiKey?.trim()) {
    return false;
  }
  return supportsVisionModel('openrouter', settings.openRouterModel);
};

export const pickFallbackVisionModel = (provider: ImageProvider): string => (
  provider === 'agentrouter' ? FALLBACK_AGENTROUTER_MODEL : FALLBACK_OPENROUTER_MODEL
);
