import { describe, it, expect } from 'vitest';
import {
  supportsVisionModel,
  validateImageProviderSettings,
  providerSupportsVision,
  pickFallbackVisionModel,
} from '../../src/utils/imageProvider';
import type { ThreadSettings } from '../../src/types/settings';

const baseSettings: ThreadSettings = {
  openRouterApiKey: 'sk-or',
  openRouterModel: 'openai/gpt-4o-mini',
  historyMessageCount: 5,
  chatProvider: 'openrouter',
};

describe('image provider vision helpers', () => {
  it('detects keywords for OpenRouter models', () => {
    expect(supportsVisionModel('openrouter', 'openai/gpt-4o-mini')).toBe(true);
    expect(supportsVisionModel('openrouter', 'openai/gpt-3.5-turbo')).toBe(false);
  });

  it('detects keywords for agent router models', () => {
    expect(supportsVisionModel('agentrouter', 'gpt-4o')).toBe(true);
    expect(supportsVisionModel('agentrouter', 'gpt-3.5-turbo')).toBe(false);
  });

  it('validates OpenRouter settings', () => {
    const missingKey = validateImageProviderSettings('openrouter', {
      ...baseSettings,
      openRouterApiKey: '',
    });
    expect(missingKey).toContain('API ключ');

    const ok = validateImageProviderSettings('openrouter', baseSettings);
    expect(ok).toBeNull();
  });

  it('validates agent router settings', () => {
    const invalid = validateImageProviderSettings('agentrouter', {
      ...baseSettings,
      chatProvider: 'agentrouter',
      agentRouterApiKey: '',
      agentRouterBaseUrl: '',
      agentRouterModel: '',
    });
    expect(invalid).toContain('base URL');

    const ok = validateImageProviderSettings('agentrouter', {
      ...baseSettings,
      chatProvider: 'agentrouter',
      agentRouterApiKey: 'sk-agent',
      agentRouterBaseUrl: 'https://api.example.com/v1',
      agentRouterModel: 'gpt-4o-mini',
    });
    expect(ok).toBeNull();
  });

  it('checks provider capability when credentials exist', () => {
    expect(providerSupportsVision('openrouter', baseSettings)).toBe(true);
    expect(
      providerSupportsVision('agentrouter', {
        ...baseSettings,
        chatProvider: 'agentrouter',
        agentRouterApiKey: 'sk-agent',
        agentRouterBaseUrl: 'https://api.example.com/v1',
        agentRouterModel: 'gpt-4o',
      }),
    ).toBe(true);
  });

  it('provides sensible fallback models', () => {
    expect(pickFallbackVisionModel('openrouter')).toBe('openai/gpt-4o-mini');
    expect(pickFallbackVisionModel('agentrouter')).toBe('gpt-4o-mini');
  });
});
