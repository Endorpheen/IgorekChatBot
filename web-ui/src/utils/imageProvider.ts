import type { ThreadSettings } from '../types/settings';

export type SupportedImageProvider = 'openrouter' | 'agentrouter';

export const validateImageProviderSettings = (
  provider: SupportedImageProvider,
  settings: ThreadSettings,
): string | null => {
  if (provider === 'agentrouter') {
    const base = settings.agentRouterBaseUrl?.trim();
    const apiKey = settings.agentRouterApiKey?.trim();
    const model = settings.agentRouterModel?.trim();
    if (!base || !apiKey || !model) {
      return 'Для анализа изображений через OpenAI Compatible укажите base URL, API ключ и модель в настройках этого треда.';
    }
    return null;
  }

  const apiKey = settings.openRouterApiKey?.trim();
  if (!apiKey) {
    return 'Для анализа изображений укажите API ключ OpenRouter в настройках этого треда.';
  }
  return null;
};
