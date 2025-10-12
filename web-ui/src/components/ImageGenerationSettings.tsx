import React, { useEffect, useMemo, useState } from 'react';
import { ShieldCheck, ShieldOff, CheckCircle2, AlertCircle, KeyRound } from 'lucide-react';
import {
  deleteTogetherKey,
  InvalidPinError,
  loadMetadata,
  loadTogetherKey,
  PinRequiredError,
  saveTogetherKey,
} from '../storage/togetherKeyStorage';
import { ApiError, validateTogetherKey } from '../utils/api';

interface ImageGenerationSettingsProps {
  isOpen: boolean;
  onKeyChange?: () => void;
}

type Feedback = { type: 'success' | 'error'; message: string } | null;

const ImageGenerationSettings: React.FC<ImageGenerationSettingsProps> = ({ isOpen, onKeyChange }) => {
  const [keyValue, setKeyValue] = useState('');
  const [encrypt, setEncrypt] = useState(false);
  const [needsPin, setNeedsPin] = useState(false);
  const [unlockPin, setUnlockPin] = useState('');
  const [pinForUnlock, setPinForUnlock] = useState('');
  const [pinForSave, setPinForSave] = useState('');
  const [pinConfirm, setPinConfirm] = useState('');
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [hasKey, setHasKey] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setKeyValue('');
      setUnlockPin('');
      setPinForUnlock('');
      setPinForSave('');
      setPinConfirm('');
      setFeedback(null);
      setNeedsPin(false);
      return;
    }

    let cancelled = false;
    (async () => {
      setIsBusy(true);
      try {
        const metadata = await loadMetadata();
        if (cancelled) {
          return;
        }
        setEncrypt(metadata.encrypted);
        setHasKey(metadata.hasKey);
        if (!metadata.hasKey) {
          setKeyValue('');
          setNeedsPin(false);
          return;
        }
        if (metadata.encrypted) {
          setNeedsPin(true);
          setKeyValue('');
          setFeedback({ type: 'error', message: 'Ключ зашифрован. Введите PIN, чтобы показать значение.' });
          return;
        }
        const value = await loadTogetherKey();
        if (cancelled) {
          return;
        }
        setKeyValue(value.key);
        setNeedsPin(false);
        setFeedback(null);
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : 'Не удалось загрузить ключ';
          setFeedback({ type: 'error', message });
        }
      } finally {
        if (!cancelled) {
          setIsBusy(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const handleUnlock = async () => {
    if (!pinForUnlock.trim()) {
      setFeedback({ type: 'error', message: 'Введите PIN для расшифровки' });
      return;
    }
    setIsBusy(true);
    setFeedback(null);
    try {
      const value = await loadTogetherKey(pinForUnlock.trim());
      setKeyValue(value.key);
      setNeedsPin(false);
      setUnlockPin(pinForUnlock.trim());
      setPinForUnlock('');
      setFeedback({ type: 'success', message: 'Ключ расшифрован и отображён' });
    } catch (error) {
      if (error instanceof InvalidPinError) {
        setFeedback({ type: 'error', message: 'Неверный PIN. Попробуйте снова.' });
      } else {
        const message = error instanceof Error ? error.message : 'Не удалось расшифровать ключ';
        setFeedback({ type: 'error', message });
      }
    } finally {
      setIsBusy(false);
    }
  };

  const validatePinConfirmation = (): string | null => {
    if (!encrypt) {
      return null;
    }
    if (pinForSave) {
      if (pinForSave.length < 4) {
        return 'PIN должен содержать минимум 4 символа';
      }
      if (pinForSave !== pinConfirm) {
        return 'PIN и подтверждение не совпадают';
      }
    }
    if (!pinForSave && !unlockPin) {
      return 'Введите PIN для шифрования или расшифруйте ключ';
    }
    return null;
  };

  const handleSave = async () => {
    if (!keyValue.trim()) {
      setFeedback({ type: 'error', message: 'Введите Together API Key перед сохранением' });
      return;
    }

    const pinError = validatePinConfirmation();
    if (pinError) {
      setFeedback({ type: 'error', message: pinError });
      return;
    }

    setIsBusy(true);
    setFeedback(null);
    try {
      if (encrypt) {
        const effectivePin = pinForSave || unlockPin;
        await saveTogetherKey(keyValue.trim(), { encrypt: true, pin: effectivePin });
        setUnlockPin(effectivePin);
        setFeedback({ type: 'success', message: 'Ключ сохранён и зашифрован в IndexedDB' });
        setNeedsPin(false);
      } else {
        await saveTogetherKey(keyValue.trim(), { encrypt: false });
        setUnlockPin('');
        setNeedsPin(false);
        setFeedback({ type: 'success', message: 'Ключ сохранён в IndexedDB' });
      }
      setPinForSave('');
      setPinConfirm('');
      setHasKey(true);
      if (onKeyChange) {
        onKeyChange();
      }
    } catch (error) {
      if (error instanceof PinRequiredError) {
        setFeedback({ type: 'error', message: 'Для шифрования требуется PIN' });
      } else {
        const message = error instanceof Error ? error.message : 'Не удалось сохранить ключ';
        setFeedback({ type: 'error', message });
      }
    } finally {
      setIsBusy(false);
    }
  };

  const handleValidate = async () => {
    if (!keyValue.trim()) {
      setFeedback({ type: 'error', message: 'Сначала сохраните Together API Key' });
      return;
    }
    setIsBusy(true);
    setFeedback(null);
    try {
      await validateTogetherKey(keyValue.trim());
      setFeedback({ type: 'success', message: 'Ключ успешно прошёл проверку' });
    } catch (error) {
      if (error instanceof ApiError) {
        setFeedback({ type: 'error', message: error.message });
      } else {
        const message = error instanceof Error ? error.message : 'Проверка не удалась';
        setFeedback({ type: 'error', message });
      }
    } finally {
      setIsBusy(false);
    }
  };

  const handleReset = async () => {
    if (!hasKey) {
      setFeedback({ type: 'error', message: 'Ключ ещё не сохранён' });
      return;
    }
    const confirmed = window.confirm('Удалить Together API Key из IndexedDB?');
    if (!confirmed) {
      return;
    }
    setIsBusy(true);
    setFeedback(null);
    try {
      await deleteTogetherKey();
      setKeyValue('');
      setUnlockPin('');
      setPinForSave('');
      setPinConfirm('');
      setNeedsPin(false);
      setHasKey(false);
      setFeedback({ type: 'success', message: 'Ключ удалён. Генерация заблокирована до повторного ввода.' });
      if (onKeyChange) {
        onKeyChange();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Не удалось удалить ключ';
      setFeedback({ type: 'error', message });
    } finally {
      setIsBusy(false);
    }
  };

  const handleCopy = async () => {
    if (!keyValue) {
      setFeedback({ type: 'error', message: 'Нет ключа для копирования' });
      return;
    }
    try {
      await navigator.clipboard.writeText(keyValue);
      setFeedback({ type: 'success', message: 'Ключ скопирован в буфер обмена' });
    } catch (error) {
      setFeedback({ type: 'error', message: 'Не удалось скопировать ключ' });
    }
  };

  const feedbackClass = useMemo(() => {
    if (!feedback) {
      return '';
    }
    return feedback.type === 'success' ? 'feedback-success' : 'feedback-error';
  }, [feedback]);

  const disableActions = isBusy || needsPin;

  return (
    <div className="image-settings">
      <div className="setting-group">
        <div className="setting-header">
          <h4 className="setting-title">Together FLUX Image Generation</h4>
          <span className="setting-subtitle">BYOK хранится только в вашем браузере</span>
        </div>

        <label className="setting-label" htmlFor="togetherKey">
          Together API Key (полностью отображается)
        </label>
        <div className="key-input-row">
          <textarea
            id="togetherKey"
            className="settings-textarea key-textarea"
            value={keyValue}
            placeholder="tg-..."
            onChange={(event) => setKeyValue(event.target.value)}
            spellCheck={false}
            disabled={isBusy || needsPin}
            rows={3}
          />
          <button
            type="button"
            className="settings-button secondary"
            onClick={handleCopy}
            disabled={!keyValue || needsPin || isBusy}
          >
            Скопировать
          </button>
        </div>

        {needsPin && (
          <div className="pin-unlock-block">
            <label className="setting-label" htmlFor="unlockPin">Введите PIN для расшифровки</label>
            <div className="pin-row">
              <input
                id="unlockPin"
                type="password"
                className="settings-input"
                value={pinForUnlock}
                onChange={(event) => setPinForUnlock(event.target.value)}
                placeholder="Введите PIN"
                autoComplete="off"
              />
              <button
                type="button"
                className="settings-button"
                onClick={handleUnlock}
                disabled={isBusy || !pinForUnlock}
              >
                Расшифровать
              </button>
            </div>
          </div>
        )}

        <div className="encryption-toggle">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={encrypt}
              onChange={(event) => {
                setEncrypt(event.target.checked);
                setFeedback(null);
              }}
              disabled={isBusy}
            />
            <span className="flex items-center gap-2">
              {encrypt ? <ShieldCheck className="icon" /> : <ShieldOff className="icon" />}
              Encrypt in IndexedDB (PIN-код)
            </span>
          </label>
          <div className="toggle-hint">
            Изменения режима шифрования применяются после сохранения.
          </div>
        </div>

        {encrypt && (
          <div className="pin-save-block">
            <label className="setting-label" htmlFor="pinForSave">PIN для шифрования</label>
            <input
              id="pinForSave"
              type="password"
              className="settings-input"
              value={pinForSave}
              onChange={(event) => setPinForSave(event.target.value)}
              placeholder="Введите новый PIN или оставьте пустым, чтобы использовать текущий"
              autoComplete="off"
            />
            <label className="setting-label" htmlFor="pinConfirm">Подтвердите PIN</label>
            <input
              id="pinConfirm"
              type="password"
              className="settings-input"
              value={pinConfirm}
              onChange={(event) => setPinConfirm(event.target.value)}
              placeholder="Повторите PIN"
              autoComplete="off"
            />
          </div>
        )}

        <div className="settings-actions">
          <button type="button" className="settings-button" onClick={handleSave} disabled={isBusy}>
            Сохранить
          </button>
          <button
            type="button"
            className="settings-button secondary"
            onClick={handleValidate}
            disabled={disableActions || !keyValue.trim()}
          >
            Проверить ключ
          </button>
          <button
            type="button"
            className="settings-button danger"
            onClick={handleReset}
            disabled={isBusy || !hasKey}
          >
            Reset key
          </button>
        </div>

        {feedback && (
          <div className={`feedback ${feedbackClass}`}>
            {feedback.type === 'success' ? <CheckCircle2 className="icon" /> : <AlertCircle className="icon" />}
            <span>{feedback.message}</span>
          </div>
        )}

        <div className="storage-hint">
          <KeyRound className="icon" />
          <div>
            Ключ хранится <strong>только</strong> в IndexedDB вашего браузера. Сервер не сохраняет и не логирует его. Удалить можно кнопкой Reset или полной очисткой данных сайта.
          </div>
        </div>
      </div>
    </div>
  );
};

export default ImageGenerationSettings;
