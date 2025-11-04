/* @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest';

import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
import SettingsPanel from '../../src/components/SettingsPanel';

const baseThreadSettings = {
  openRouterApiKey: '',
  openRouterModel: 'openai/gpt-4o-mini',
  historyMessageCount: 5,
  chatProvider: 'openrouter' as const,
  agentRouterBaseUrl: '',
  agentRouterApiKey: '',
  agentRouterModel: 'openai/gpt-4o-mini',
};

const renderSettings = (options?: {
  overrides?: Partial<typeof baseThreadSettings>;
  props?: Partial<ComponentProps<typeof SettingsPanel>>;
}) => {
  const { overrides, props } = options ?? {};
  const updateCurrentThreadSettings = vi.fn();
  const threadSettings = {
    default: {
      ...baseThreadSettings,
      ...overrides,
    },
  };

  render(
    <SettingsPanel
      isSettingsOpen
      closeSettings={() => {}}
      threadSettings={threadSettings}
      updateCurrentThreadSettings={updateCurrentThreadSettings}
      threadNames={{ default: 'Главный тред' }}
      threadId="default"
      {...props}
    />,
  );

  return { updateCurrentThreadSettings };
};

describe('SettingsPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('загружает модели OpenRouter и обновляет выбранную, если текущая недоступна', async () => {
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        data: [
          { id: 'new-model-a' },
          { id: 'new-model-b' },
        ],
      }),
    } as Response);

    const { updateCurrentThreadSettings } = renderSettings({
      overrides: {
        openRouterApiKey: 'sk-test',
        openRouterModel: 'legacy-model',
        chatProvider: 'openrouter',
      },
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const openRouterCall = fetchMock.mock.calls.find(([url]) => url === 'https://openrouter.ai/api/v1/models');
    expect(openRouterCall).toBeDefined();
    if (openRouterCall) {
      const [, options] = openRouterCall;
      expect(options).toEqual(expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer sk-test',
        }),
      }));
    }

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'new-model-a' })).toBeInTheDocument();
    });

    expect(updateCurrentThreadSettings).toHaveBeenCalledWith({ openRouterModel: 'new-model-a' });
  });

  it('переходит в ручной режим выбора модели при ошибке 400/404 от AgentRouter', async () => {
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({}),
    } as Response);

    renderSettings({
      overrides: {
        chatProvider: 'agentrouter',
        agentRouterBaseUrl: 'https://agentrouter.example/v1',
        agentRouterApiKey: 'secret-key',
        agentRouterModel: 'legacy-model',
      },
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const modelInput = await screen.findByPlaceholderText('gpt-4o-mini');
    expect(modelInput).toHaveAttribute('type', 'text');

    expect(screen.getByText(/Сервис вернул ошибку 400\/404/i)).toBeInTheDocument();
  });
});
