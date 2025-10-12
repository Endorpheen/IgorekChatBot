const SESSION_STORAGE_KEY = 'image-generation-session-id';
let fallbackId: string | null = null;

const generateId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
};

export const getImageSessionId = (): string => {
  if (typeof window === 'undefined') {
    if (!fallbackId) {
      fallbackId = generateId();
    }
    return fallbackId;
  }

  try {
    const existing = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) {
      return existing;
    }
    const created = generateId();
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  } catch (error) {
    if (!fallbackId) {
      fallbackId = generateId();
    }
    return fallbackId;
  }
};
