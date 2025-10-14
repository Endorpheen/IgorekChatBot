import React, { useEffect, useMemo, useState } from 'react';
import { ShieldCheck, ShieldOff, CheckCircle2, AlertCircle, KeyRound } from 'lucide-react';
import {
  deleteProviderKey,
  InvalidPinError,
  loadMetadata,
  loadProviderKey,
  PinRequiredError,
  saveProviderKey,
  updateEncryptionMode,
} from '../storage/togetherKeyStorage';
import { ApiError, fetchProviderList, validateProviderKey } from '../utils/api';
import type { ProviderSummary } from '../types/image';
import { isProviderEnabled, setProviderEnabled } from '../storage/providerPreferences';

interface ImageGenerationSettingsProps {
  isOpen: boolean;
  onKeyChange?: () => void;
}

type Feedback = { type: 'success' | 'error'; message: string } | null;

interface ProviderFormState {
  keyValue: string;
  encrypt: boolean;
  needsPin: boolean;
  unlockPin: string;
  pinForUnlock: string;
  pinForSave: string;
  pinConfirm: string;
  feedback: Feedback;
  isBusy: boolean;
  hasKey: boolean;
  showKey: boolean;
  activated: boolean;
}

const defaultFormState = (): ProviderFormState => ({
  keyValue: '',
  encrypt: false,
  needsPin: false,
  unlockPin: '',
  pinForUnlock: '',
  pinForSave: '',
  pinConfirm: '',
  feedback: null,
  isBusy: false,
  hasKey: false,
  showKey: false,
  activated: true,
});

const ImageGenerationSettings: React.FC<ImageGenerationSettingsProps> = ({ isOpen, onKeyChange }) => {
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [activeProviderId, setActiveProviderId] = useState<string>('together');
  const [forms, setForms] = useState<Record<string, ProviderFormState>>({});

  const activeForm = useMemo(() => forms[activeProviderId] ?? defaultFormState(), [forms, activeProviderId]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const response = await fetchProviderList();
        if (cancelled) {
          return;
        }
        const list = response.providers ?? [];
        setProviders(list);
        if (!list.some(provider => provider.id === activeProviderId)) {
          setActiveProviderId(list[0]?.id ?? 'together');
        }
        const nextForms: Record<string, ProviderFormState> = {};
        for (const provider of list) {
          try {
            const metadata = await loadMetadata(provider.id);
            const state = defaultFormState();
            state.encrypt = metadata.encrypted;
            state.needsPin = metadata.encrypted;
            state.hasKey = metadata.hasKey;
            state.activated = isProviderEnabled(provider.id);
            if (metadata.hasKey && !metadata.encrypted) {
              try {
                const value = await loadProviderKey(provider.id);
                state.keyValue = value.key;
                state.showKey = true;
              } catch (error) {
                console.warn('Не удалось загрузить ключ провайдера', provider.id, error);
              }
            }
            nextForms[provider.id] = state;
          } catch {
            const state = defaultFormState();
            state.activated = isProviderEnabled(provider.id);
            nextForms[provider.id] = state;
          }
        }
        if (!cancelled) {
          setForms(nextForms);
        }
      } catch (error) {
        console.error('Не удалось загрузить список провайдеров', error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeProviderId]);

  const updateForm = (providerId: string, patch: Partial<ProviderFormState>) => {
    setForms(prev => ({
      ...prev,
      [providerId]: {
        ...(prev[providerId] ?? defaultFormState()),
        ...patch,
      },
    }));
  };

  if (!isOpen) {
    return null;
  }

  const providersToRender = providers.length > 0 ? providers : [{ id: 'together', label: 'Together AI', enabled: true, recommended_models: [] }];
  const activeProviderLabel = providersToRender.find(provider => provider.id === activeProviderId)?.label ?? activeProviderId;

  const handleUnlock = async () => {
    const form = forms[activeProviderId] ?? defaultFormState();
    if (!form.pinForUnlock.trim()) {
      updateForm(activeProviderId, { feedback: { type: 'error', message: 'Введите PIN для расшифровки' } });
      return;
    }
    updateForm(activeProviderId, { isBusy: true, feedback: null });
    try {
      const value = await loadProviderKey(activeProviderId, form.pinForUnlock.trim());
      updateForm(activeProviderId, {
        keyValue: value.key,
        needsPin: false,
        unlockPin: form.pinForUnlock.trim(),
        pinForUnlock: '',
        feedback: { type: 'success', message: 'Ключ расшифрован и отображён' },
        showKey: true,
      });
    } catch (error) {
      if (error instanceof InvalidPinError) {
        updateForm(activeProviderId, { feedback: { type: 'error', message: 'Неверный PIN. Попробуйте снова.' } });
      } else {
        const message = error instanceof Error ? error.message : 'Не удалось расшифровать ключ';
        updateForm(activeProviderId, { feedback: { type: 'error', message } });
      }
    } finally {
      updateForm(activeProviderId, { isBusy: false });
    }
  };

  const validatePinConfirmation = (form: ProviderFormState): string | null => {
    if (!form.encrypt) {
      return null;
    }
    if (form.pinForSave) {
      if (form.pinForSave.length < 4) {
        return 'PIN должен содержать минимум 4 символа';
      }
      if (form.pinForSave !== form.pinConfirm) {
        return 'PIN и подтверждение не совпадают';
      }
    }
    if (!form.pinForSave && !form.unlockPin) {
      return 'Введите PIN для шифрования или расшифруйте ключ';
    }
    return null;
  };

  const handleSave = async () => {
    const form = forms[activeProviderId] ?? defaultFormState();
    if (!form.keyValue.trim()) {
      updateForm(activeProviderId, { feedback: { type: 'error', message: 'Введите API ключ перед сохранением' } });
      return;
    }
    const pinError = validatePinConfirmation(form);
    if (pinError) {
      updateForm(activeProviderId, { feedback: { type: 'error', message: pinError } });
      return;
    }
    updateForm(activeProviderId, { isBusy: true, feedback: null });
    try {
      if (form.encrypt) {
        const effectivePin = form.pinForSave || form.unlockPin;
        await saveProviderKey(activeProviderId, form.keyValue.trim(), { encrypt: true, pin: effectivePin });
        updateForm(activeProviderId, {
          unlockPin: effectivePin,
          needsPin: true,
          feedback: { type: 'success', message: 'Ключ сохранён и зашифрован' },
          hasKey: true,
          pinForSave: '',
          pinConfirm: '',
        });
      } else {
        await saveProviderKey(activeProviderId, form.keyValue.trim(), { encrypt: false });
        updateForm(activeProviderId, {
          unlockPin: '',
          needsPin: false,
          feedback: { type: 'success', message: 'Ключ сохранён в IndexedDB' },
          hasKey: true,
          pinForSave: '',
          pinConfirm: '',
        });
      }
      if (onKeyChange) {
        onKeyChange();
      }
    } catch (error) {
      if (error instanceof PinRequiredError) {
        updateForm(activeProviderId, { feedback: { type: 'error', message: 'Для шифрования требуется PIN' } });
      } else {
        const message = error instanceof Error ? error.message : 'Не удалось сохранить ключ';
        updateForm(activeProviderId, { feedback: { type: 'error', message } });
      }
    } finally {
      updateForm(activeProviderId, { isBusy: false });
    }
  };

  const handleValidate = async () => {
    const form = forms[activeProviderId] ?? defaultFormState();
    if (!form.hasKey) {
      updateForm(activeProviderId, { feedback: { type: 'error', message: 'Сначала сохраните API ключ' } });
      return;
    }
    updateForm(activeProviderId, { isBusy: true, feedback: null });
    try {
      const value = form.encrypt ? await loadProviderKey(activeProviderId, form.unlockPin || undefined) : await loadProviderKey(activeProviderId);
      await validateProviderKey(activeProviderId, value.key);
      updateForm(activeProviderId, { feedback: { type: 'success', message: 'Ключ успешно прошёл проверку' } });
    } catch (error) {
      if (error instanceof ApiError) {
        updateForm(activeProviderId, { feedback: { type: 'error', message: error.message } });
      } else if (error instanceof PinRequiredError) {
        updateForm(activeProviderId, { feedback: { type: 'error', message: 'Укажите PIN для проверки' } });
      } else if (error instanceof Error) {
        updateForm(activeProviderId, { feedback: { type: 'error', message: error.message } });
      } else {
        updateForm(activeProviderId, { feedback: { type: 'error', message: 'Проверка не удалась' } });
      }
    } finally {
      updateForm(activeProviderId, { isBusy: false });
    }
  };

  const handleReset = async () => {
    const form = forms[activeProviderId] ?? defaultFormState();
    if (!form.hasKey) {
      updateForm(activeProviderId, { feedback: { type: 'error', message: 'Ключ ещё не сохранён' } });
      return;
    }
    const confirmed = window.confirm(`Удалить API ключ для провайдера ${activeProviderLabel}?`);
    if (!confirmed) {
      return;
    }
    updateForm(activeProviderId, { isBusy: true, feedback: null });
    try {
      await deleteProviderKey(activeProviderId);
      updateForm(activeProviderId, defaultFormState());
      if (onKeyChange) {
        onKeyChange();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Не удалось удалить ключ';
      updateForm(activeProviderId, { feedback: { type: 'error', message } });
    } finally {
      updateForm(activeProviderId, { isBusy: false });
    }
  };

  const toggleEncryption = async (encrypt: boolean) => {
    const form = forms[activeProviderId] ?? defaultFormState();
    updateForm(activeProviderId, { encrypt, feedback: null });
    if (!form.hasKey) {
      return;
    }
    try {
      await updateEncryptionMode(activeProviderId, encrypt, form.unlockPin || undefined);
      updateForm(activeProviderId, { needsPin: encrypt, feedback: { type: 'success', message: 'Режим шифрования обновлён' } });
    } catch (error) {
      if (error instanceof PinRequiredError) {
        updateForm(activeProviderId, { feedback: { type: 'error', message: 'Для включения шифрования нужен PIN' } });
      } else if (error instanceof InvalidPinError) {
        updateForm(activeProviderId, { feedback: { type: 'error', message: 'Неверный PIN. Расшифруйте ключ заново.' } });
      } else {
        const message = error instanceof Error ? error.message : 'Не удалось изменить режим шифрования';
        updateForm(activeProviderId, { feedback: { type: 'error', message } });
      }
    }
  };

  const toggleActivation = (enabled: boolean) => {
    setProviderEnabled(activeProviderId, enabled);
    updateForm(activeProviderId, { activated: enabled });
    if (onKeyChange) {
      onKeyChange();
    }
  };

  return (
    <div className="provider-settings">
      <div className="provider-tabs">
        {providersToRender.map(provider => (
          <button
            key={provider.id}
            type="button"
            className={`provider-tab ${provider.id === activeProviderId ? 'active' : ''}`}
            onClick={() => setActiveProviderId(provider.id)}
          >
            {provider.label}
          </button>
        ))}
      </div>

      <div className="provider-settings-body">
          <div className="setting-group">
            <label className="setting-label">
              <input
                type="checkbox"
                checked={activeForm.activated}
                onChange={(event) => toggleActivation(event.target.checked)}
              />
              Активировать провайдера
            </label>
            <div className="setting-description">
              Провайдер будет доступен в /images только когда активирован и сохранён ключ.
            </div>
          </div>

          <div className="setting-group">
            <label className="setting-label">API Key ({activeProviderLabel})</label>
            <div className="input-with-icon">
              <input
                type={activeForm.showKey ? 'text' : 'password'}
                value={activeForm.keyValue}
                onChange={(e) => updateForm(activeProviderId, { keyValue: e.target.value })}
                placeholder="sk-..."
                className="settings-input"
              />
              <button
                type="button"
                className="input-icon-button"
                onClick={() => updateForm(activeProviderId, { showKey: !activeForm.showKey })}
                title={activeForm.showKey ? 'Скрыть API ключ' : 'Показать API ключ'}
              >
                {activeForm.showKey ? <ShieldOff className="icon" /> : <ShieldCheck className="icon" />}
              </button>
            </div>
          </div>

          <div className="setting-group toggle-row">
            <label className="setting-label">
              <input
                type="checkbox"
                checked={activeForm.encrypt}
                onChange={(event) => toggleEncryption(event.target.checked)}
              />
              Шифровать в IndexedDB (PIN)
            </label>
          </div>

          {activeForm.needsPin && (
            <div className="setting-group">
              <label className="setting-label">PIN для расшифровки</label>
              <div className="pin-row">
                <input
                  type="password"
                  value={activeForm.pinForUnlock}
                  onChange={(e) => updateForm(activeProviderId, { pinForUnlock: e.target.value })}
                  placeholder="Введите PIN"
                  className="settings-input"
                />
                <button type="button" className="settings-button secondary" onClick={handleUnlock} disabled={activeForm.isBusy}>
                  <KeyRound className="icon" /> Расшифровать
                </button>
              </div>
            </div>
          )}

          {activeForm.encrypt && (
            <div className="setting-group">
              <label className="setting-label">PIN для сохранения</label>
              <div className="pin-row">
                <input
                  type="password"
                  value={activeForm.pinForSave}
                  onChange={(e) => updateForm(activeProviderId, { pinForSave: e.target.value })}
                  placeholder="PIN"
                  className="settings-input"
                />
                <input
                  type="password"
                  value={activeForm.pinConfirm}
                  onChange={(e) => updateForm(activeProviderId, { pinConfirm: e.target.value })}
                  placeholder="Подтверждение"
                  className="settings-input"
                />
              </div>
            </div>
          )}

          <div className="settings-actions">
            <button type="button" className="settings-button" onClick={handleSave} disabled={activeForm.isBusy}>
              Сохранить
            </button>
            <button type="button" className="settings-button secondary" onClick={handleValidate} disabled={activeForm.isBusy}>
              Проверить ключ
            </button>
            <button type="button" className="settings-button danger" onClick={handleReset} disabled={activeForm.isBusy}>
              Удалить ключ
            </button>
          </div>

        {activeForm.feedback && (
          <div className={`feedback feedback-${activeForm.feedback.type}`}>
            {activeForm.feedback.type === 'success' ? <CheckCircle2 className="icon" /> : <AlertCircle className="icon" />}
            <span>{activeForm.feedback.message}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ImageGenerationSettings;
