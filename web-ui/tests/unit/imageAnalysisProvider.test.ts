import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { uploadImagesForAnalysis } from '../../src/utils/api';
import { validateImageProviderSettings } from '../../src/utils/imageProvider';
import type { ThreadSettings } from '../../src/types/settings';

const createFile = () => new File(['123'], 'sample.png', { type: 'image/png' });

const baseThreadSettings: ThreadSettings = {
  openRouterApiKey: 'sk-or-test',
  openRouterModel: 'openai/gpt-4o-mini',
  historyMessageCount: 5,
  chatProvider: 'openrouter',
};

describe('image analysis provider routing', () => {
beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

  it('validates OpenRouter settings', () => {
    const message = validateImageProviderSettings('openrouter', {
      ...baseThreadSettings,
      openRouterApiKey: '',
    });
    expect(message).toContain('OpenRouter');

    const ok = validateImageProviderSettings('openrouter', baseThreadSettings);
    expect(ok).toBeNull();
  });

  it('validates OpenAI Compatible settings', () => {
    const missing = validateImageProviderSettings('agentrouter', {
      ...baseThreadSettings,
      chatProvider: 'agentrouter',
      agentRouterApiKey: '',
      agentRouterModel: '',
      agentRouterBaseUrl: '',
    });
    expect(missing).toContain('OpenAI Compatible');

    const ok = validateImageProviderSettings('agentrouter', {
      ...baseThreadSettings,
      chatProvider: 'agentrouter',
      agentRouterApiKey: 'sk-agent',
      agentRouterModel: 'gpt-4o-mini',
      agentRouterBaseUrl: 'https://api.example.com/v1',
    });
    expect(ok).toBeNull();
  });

  it('sends OpenRouter fields when provider is openrouter', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', response: 'good', thread_id: 't0' }),
      text: async () => '',
    });
    vi.stubGlobal('fetch', fetchMock);

    await uploadImagesForAnalysis({
      files: [createFile()],
      threadId: 'thread-openrouter',
      history: [],
      settings: baseThreadSettings,
      systemPrompt: null,
      prompt: 'Что на изображении?',
      provider: 'openrouter',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [RequestInfo, RequestInit];
    const body = init.body as FormData;
    const entries = Array.from(body.entries());

    expect(entries).toContainEqual(['provider_type', 'openrouter']);
    expect(entries).toContainEqual(['open_router_api_key', baseThreadSettings.openRouterApiKey]);
    expect(entries.some(([key]) => key.startsWith('agent_router'))).toBe(false);
  });

  it('sends OpenAI Compatible fields when provider is agentrouter', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', response: 'good', thread_id: 't1' }),
      text: async () => '',
    });
    vi.stubGlobal('fetch', fetchMock);

    const agentSettings: ThreadSettings = {
      ...baseThreadSettings,
      chatProvider: 'agentrouter',
      agentRouterApiKey: 'sk-agent',
      agentRouterModel: 'gpt-4.1-mini',
      agentRouterBaseUrl: 'https://api.example.com/v1',
    };

    await uploadImagesForAnalysis({
      files: [createFile()],
      threadId: 'thread-agent',
      history: [],
      settings: agentSettings,
      systemPrompt: null,
      prompt: 'Что на изображении?',
      provider: 'agentrouter',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [RequestInfo, RequestInit];
    const body = init.body as FormData;
    const entries = Array.from(body.entries());

    expect(entries).toContainEqual(['provider_type', 'agentrouter']);
    expect(entries).toContainEqual(['agent_router_api_key', agentSettings.agentRouterApiKey]);
    expect(entries).toContainEqual(['agent_router_model', agentSettings.agentRouterModel]);
    expect(entries).toContainEqual(['agent_router_base_url', agentSettings.agentRouterBaseUrl]);
    expect(entries.some(([key]) => key === 'open_router_api_key')).toBe(false);
  });
});
