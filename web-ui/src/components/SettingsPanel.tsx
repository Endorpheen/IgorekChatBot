import React, { useState, useEffect } from 'react';
import { X, Eye, EyeOff } from 'lucide-react';
import type { ThreadSettings } from '../types/settings';
import ImageGenerationSettings from './ImageGenerationSettings';
import { buildApiUrl } from '../utils/api';

interface SettingsPanelProps {
  isSettingsOpen: boolean;
  closeSettings: () => void;
  threadSettings: Record<string, ThreadSettings>;
  updateCurrentThreadSettings: (updates: Partial<ThreadSettings>) => void;
  threadNames: Record<string, string>;
  threadId: string;
  onImageKeyChange?: () => void;
}

const SettingsPanel: React.FC<SettingsPanelProps> = ({
  isSettingsOpen,
  closeSettings,
  threadSettings,
  updateCurrentThreadSettings,
  threadNames,
  threadId,
  onImageKeyChange,
}) => {
  const [showApiKey, setShowApiKey] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [showSystemPromptInput, setShowSystemPromptInput] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState<string>('');
  const [agentAvailableModels, setAgentAvailableModels] = useState<string[]>([]);
  const [isLoadingAgentModels, setIsLoadingAgentModels] = useState(false);

  useEffect(() => {
    const savedSystemPrompt = localStorage.getItem('systemPrompt');
    if (savedSystemPrompt) {
      setSystemPrompt(savedSystemPrompt);
    }
  }, []);

  const getCurrentThreadSettings = () => {
    return threadSettings[threadId] || {
      openRouterEnabled: false,
      openRouterApiKey: '',
      openRouterModel: 'openai/gpt-4o-mini',
      historyMessageCount: 5, // Default value

      // Chat provider selection (default OpenRouter)
      chatProvider: 'openrouter' as const,

      // AgentRouter defaults
      agentRouterBaseUrl: '',
      agentRouterApiKey: '',
      agentRouterModel: 'openai/gpt-4o-mini',
    };
  };

  const loadAvailableModels = async () => {
    const currentSettings = getCurrentThreadSettings();
    if (!currentSettings.openRouterApiKey) {
      setAvailableModels([]);
      return;
    }

    setIsLoadingModels(true);
    try {
      const response = await fetch('https://openrouter.ai/api/v1/models', {
        headers: {
          'Authorization': `Bearer ${currentSettings.openRouterApiKey}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to load models: ${response.status}`);
      }

      const data = await response.json();
      const models = data.data.map((model: { id: string }) => model.id).sort();
      setAvailableModels(models);

      if (models.length > 0 && !models.includes(currentSettings.openRouterModel)) {
        updateCurrentThreadSettings({ openRouterModel: models[0] });
      }
    } catch (error) {
      console.error('Failed to load OpenRouter models:', error);
      setAvailableModels([]);
    } finally {
      setIsLoadingModels(false);
    }
  };

  const loadAgentAvailableModels = async () => {
    const currentSettings = getCurrentThreadSettings();
    const baseUrl = (currentSettings.agentRouterBaseUrl || '').trim();
    const apiKey = (currentSettings.agentRouterApiKey || '').trim();

    if (!baseUrl || !apiKey) {
      setAgentAvailableModels([]);
      return;
    }

    setIsLoadingAgentModels(true);
    try {
      const url = new URL(buildApiUrl('/api/providers/agentrouter/models'));
      url.searchParams.set('base_url', baseUrl);

      const response = await fetch(url.toString(), {
        headers: {
          'Authorization': `Bearer ${apiKey}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to load AgentRouter models: ${response.status}`);
      }

      const data = await response.json();
      const models: string[] = Array.isArray(data.models) ? data.models : [];
      setAgentAvailableModels(models);

      if (models.length > 0 && !models.includes(currentSettings.agentRouterModel || '')) {
        updateCurrentThreadSettings({ agentRouterModel: models[0] });
      }
    } catch (error) {
      console.error('Failed to load AgentRouter models:', error);
      setAgentAvailableModels([]);
    } finally {
      setIsLoadingAgentModels(false);
    }
  };

  useEffect(() => {
    if (isSettingsOpen && getCurrentThreadSettings().openRouterApiKey) {
      loadAvailableModels();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSettingsOpen, threadSettings[threadId]?.openRouterApiKey]);

  useEffect(() => {
    const s = getCurrentThreadSettings();
    if (
      isSettingsOpen &&
      (s.chatProvider ?? 'openrouter') === 'agentrouter' &&
      s.agentRouterBaseUrl &&
      s.agentRouterApiKey
    ) {
      loadAgentAvailableModels();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isSettingsOpen,
    threadSettings[threadId]?.agentRouterBaseUrl,
    threadSettings[threadId]?.agentRouterApiKey,
    threadSettings[threadId]?.chatProvider
  ]);

  if (!isSettingsOpen) {
    return null;
  }

  return (
    <div className="settings-overlay" onClick={closeSettings}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h3>Настройки</h3>
          <button type="button" className="close-button" onClick={closeSettings}>
            <X className="icon" />
          </button>
        </div>

        <div className="settings-content">
          <div className="settings-section">
            <ImageGenerationSettings isOpen={isSettingsOpen} onKeyChange={onImageKeyChange} />
          </div>

          <div className="settings-section">
            <div className="settings-section-header">
              <h4 className="settings-section-title">Провайдер чата</h4>
              <p className="settings-section-subtitle">
                Выберите поставщика OpenAI-совместимого API для текущего треда
              </p>
            </div>

            <div className="setting-field">
              <label className="setting-label" htmlFor="chatProvider">Провайдер</label>
              <select
                id="chatProvider"
                value={getCurrentThreadSettings().chatProvider ?? 'openrouter'}
                onChange={(e) => updateCurrentThreadSettings({ chatProvider: e.target.value as 'openrouter' | 'agentrouter' })}
                className="settings-select"
              >
                <option value="openrouter">OpenRouter</option>
                <option value="agentrouter">AgentRouter</option>
              </select>
            </div>
          </div>

          <div className="settings-section">
            <div className="settings-section-header">
              <h4 className="settings-section-title">Настройки OpenRouter</h4>
              <p className="settings-section-subtitle">
                Настройка применяется только к текущему треду: {threadNames[threadId] ?? 'Без названия'}
              </p>
            </div>

            <label className="setting-toggle">
              <input
                type="checkbox"
                checked={getCurrentThreadSettings().openRouterEnabled}
                onChange={(e) => updateCurrentThreadSettings({ openRouterEnabled: e.target.checked })}
              />
              <span>Использовать OpenRouter (облачная модель)</span>
            </label>

            {(getCurrentThreadSettings().chatProvider ?? 'openrouter') === 'openrouter' && getCurrentThreadSettings().openRouterEnabled && (
              <>
                <div className="setting-field">
                  <label className="setting-label" htmlFor="openRouterApiKey">
                    API Key OpenRouter
                  </label>
                  <div className="input-with-icon">
                    <input
                      id="openRouterApiKey"
                      type={showApiKey ? 'text' : 'password'}
                      value={getCurrentThreadSettings().openRouterApiKey}
                      onChange={(e) => updateCurrentThreadSettings({ openRouterApiKey: e.target.value })}
                      placeholder="sk-or-v1-..."
                      className="settings-input"
                    />
                    <button
                      type="button"
                      className="input-icon-button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      title={showApiKey ? 'Скрыть API ключ' : 'Показать API ключ'}
                    >
                      {showApiKey ? <EyeOff className="icon" /> : <Eye className="icon" />}
                    </button>
                  </div>
                </div>

                <div className="setting-field">
                  <label className="setting-label" htmlFor="openRouterModel">
                    Модель
                  </label>
                  <select
                    id="openRouterModel"
                    value={getCurrentThreadSettings().openRouterModel}
                    onChange={(e) => updateCurrentThreadSettings({ openRouterModel: e.target.value })}
                    className="settings-select"
                    disabled={isLoadingModels || !getCurrentThreadSettings().openRouterApiKey}
                  >
                    {isLoadingModels ? (
                      <option>Загрузка моделей...</option>
                    ) : availableModels.length > 0 ? (
                      availableModels.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))
                    ) : (
                      <option disabled>Укажите API ключ для загрузки моделей</option>
                    )}
                  </select>
                </div>
              </>
            )}
          </div>

          <div className="settings-section">
            <div className="settings-section-header">
              <h4 className="settings-section-title">Настройки AgentRouter</h4>
              <p className="settings-section-subtitle">
                Укажите Base URL и API Key для OpenAI-совместимого конечного точки. Модели загружаются автоматически.
              </p>
            </div>

            {(getCurrentThreadSettings().chatProvider ?? 'openrouter') === 'agentrouter' && (
              <>
                <div className="setting-field">
                  <label className="setting-label" htmlFor="agentRouterBaseUrl">Base URL</label>
                  <input
                    id="agentRouterBaseUrl"
                    type="text"
                    value={getCurrentThreadSettings().agentRouterBaseUrl ?? ''}
                    onChange={(e) => updateCurrentThreadSettings({ agentRouterBaseUrl: e.target.value })}
                    placeholder="https://your-agentrouter.example.com/v1"
                    className="settings-input"
                  />
                </div>

                <div className="setting-field">
                  <label className="setting-label" htmlFor="agentRouterApiKey">API Key AgentRouter</label>
                  <div className="input-with-icon">
                    <input
                      id="agentRouterApiKey"
                      type={showApiKey ? 'text' : 'password'}
                      value={getCurrentThreadSettings().agentRouterApiKey ?? ''}
                      onChange={(e) => updateCurrentThreadSettings({ agentRouterApiKey: e.target.value })}
                      placeholder="sk-..."
                      className="settings-input"
                    />
                    <button
                      type="button"
                      className="input-icon-button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      title={showApiKey ? 'Скрыть API ключ' : 'Показать API ключ'}
                    >
                      {showApiKey ? <EyeOff className="icon" /> : <Eye className="icon" />}
                    </button>
                  </div>
                </div>

                <div className="setting-field">
                  <label className="setting-label" htmlFor="agentRouterModel">Модель</label>
                  <select
                    id="agentRouterModel"
                    value={getCurrentThreadSettings().agentRouterModel ?? ''}
                    onChange={(e) => updateCurrentThreadSettings({ agentRouterModel: e.target.value })}
                    className="settings-select"
                    disabled={isLoadingAgentModels || !(getCurrentThreadSettings().agentRouterBaseUrl && getCurrentThreadSettings().agentRouterApiKey)}
                  >
                    {isLoadingAgentModels ? (
                      <option>Загрузка моделей...</option>
                    ) : agentAvailableModels.length > 0 ? (
                      agentAvailableModels.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))
                    ) : (
                      <option disabled>Укажите Base URL и API Key для загрузки моделей</option>
                    )}
                  </select>
                </div>
              </>
            )}
          </div>

          <hr className="settings-separator" />

          <div className="settings-section">
            <div className="settings-section-header">
              <h4 className="settings-section-title">История сообщений</h4>
              <p className="settings-section-subtitle">
                Укажите, сколько последних сообщений использовать при генерации ответа.
              </p>
            </div>
            <div className="setting-field">
              <label className="setting-label" htmlFor="historyMessageCount">
                Количество сообщений в истории
              </label>
              <input
                type="number"
                id="historyMessageCount"
                className="settings-input"
                min="0"
                max="50"
                value={getCurrentThreadSettings().historyMessageCount}
                onChange={(e) => {
                  const value = parseInt(e.target.value, 10);
                  updateCurrentThreadSettings({
                    historyMessageCount: isNaN(value) ? 5 : Math.max(0, Math.min(50, value)),
                  });
                }}
              />
            </div>
            {getCurrentThreadSettings().historyMessageCount === 0 && (
              <div className="setting-warning">
                Внимание: при значении 0 история сообщений не будет учитываться. Бот будет видеть только системный промпт и текущее сообщение.
              </div>
            )}
          </div>

          <div className="settings-section">
            <div className="settings-section-header">
              <h4 className="settings-section-title">Системный промпт</h4>
              <p className="settings-section-subtitle">
                Дополнительные инструкции для бота. Можно скрыть или сбросить при необходимости.
              </p>
            </div>
            <div className="settings-inline-actions">
              <button
                type="button"
                className="settings-button"
                onClick={() => setShowSystemPromptInput(!showSystemPromptInput)}
              >
                {showSystemPromptInput ? 'Скрыть поле' : 'Показать поле'}
              </button>
              {showSystemPromptInput && (
                <button
                  type="button"
                  className="settings-button secondary"
                  onClick={() => {
                    setSystemPrompt('');
                    localStorage.removeItem('systemPrompt');
                  }}
                >
                  Сбросить
                </button>
              )}
            </div>
            {showSystemPromptInput && (
              <div className="system-prompt-container">
                <textarea
                  className="settings-textarea"
                  value={systemPrompt}
                  onChange={(e) => {
                    setSystemPrompt(e.target.value);
                    localStorage.setItem('systemPrompt', e.target.value);
                  }}
                  placeholder="Введите системный промпт..."
                  rows={5}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsPanel;
