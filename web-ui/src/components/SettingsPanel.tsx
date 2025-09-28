import React, { useState, useEffect } from 'react';
import { X, Eye, EyeOff } from 'lucide-react';

interface SettingsPanelProps {
  isSettingsOpen: boolean;
  closeSettings: () => void;
  threadSettings: any;
  updateCurrentThreadSettings: (updates: any) => void;
  threadNames: any;
  threadId: string;
}

const SettingsPanel: React.FC<SettingsPanelProps> = ({
  isSettingsOpen,
  closeSettings,
  threadSettings,
  updateCurrentThreadSettings,
  threadNames,
  threadId,
}) => {
  const [showApiKey, setShowApiKey] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);

  const getCurrentThreadSettings = () => {
    return threadSettings[threadId] || {
      openRouterEnabled: false,
      openRouterApiKey: '',
      openRouterModel: 'openai/gpt-4o-mini'
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
      const models = data.data.map((model: any) => model.id).sort();
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

  useEffect(() => {
    if (isSettingsOpen && getCurrentThreadSettings().openRouterApiKey) {
      loadAvailableModels();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSettingsOpen, threadSettings[threadId]?.openRouterApiKey]);

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
          <div className="setting-group">
            <label className="setting-label">
              <input
                type="checkbox"
                checked={getCurrentThreadSettings().openRouterEnabled}
                onChange={(e) => updateCurrentThreadSettings({ openRouterEnabled: e.target.checked })}
              />
              Использовать OpenRouter (облачная модель)
            </label>
            <div className="setting-description">
              Настройка применяется только к текущему треду: {threadNames[threadId] ?? 'Без названия'}
            </div>
          </div>

          {getCurrentThreadSettings().openRouterEnabled && (
            <>
              <div className="setting-group">
                <label className="setting-label">API Key OpenRouter</label>
                <div className="input-with-icon">
                  <input
                    type={showApiKey ? "text" : "password"}
                    value={getCurrentThreadSettings().openRouterApiKey}
                    onChange={(e) => updateCurrentThreadSettings({ openRouterApiKey: e.target.value })}
                    placeholder="sk-or-v1-..."
                    className="settings-input"
                  />
                  <button
                    type="button"
                    className="input-icon-button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    title={showApiKey ? "Скрыть API ключ" : "Показать API ключ"}
                  >
                    {showApiKey ? <EyeOff className="icon" /> : <Eye className="icon" />}
                  </button>
                </div>
              </div>

              <div className="setting-group">
                <label className="setting-label">Модель</label>
                <select
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
      </div>
    </div>
  );
};

export default SettingsPanel;