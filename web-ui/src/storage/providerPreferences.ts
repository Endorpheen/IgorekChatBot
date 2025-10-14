const ENABLED_KEY = 'image-enabled-providers';

const readRaw = (): Record<string, boolean> => {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(ENABLED_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).map(([provider, value]) => [provider, Boolean(value)]),
    );
  } catch (error) {
    console.warn('Не удалось прочитать список активных провайдеров', error);
    return {};
  }
};

const writeRaw = (value: Record<string, boolean>) => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(ENABLED_KEY, JSON.stringify(value));
  } catch (error) {
    console.warn('Не удалось сохранить список активных провайдеров', error);
  }
};

export const listEnabledProviders = (): Record<string, boolean> => readRaw();

export const isProviderEnabled = (providerId: string): boolean => {
  const map = readRaw();
  const value = map[providerId];
  if (typeof value === 'boolean') {
    return value;
  }
  // По умолчанию провайдер активен.
  return true;
};

export const setProviderEnabled = (providerId: string, enabled: boolean) => {
  const map = readRaw();
  map[providerId] = enabled;
  writeRaw(map);
};

export const resetProviderEnabled = (providerId: string) => {
  const map = readRaw();
  delete map[providerId];
  writeRaw(map);
};
