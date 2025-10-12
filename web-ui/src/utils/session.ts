const SESSION_STORAGE_KEY = 'image-generation-session-id';
let fallbackId: string | null = null;

const generateId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
};

const setSessionCookie = (sessionId: string) => {
  if (typeof document === 'undefined') {
    return;
  }
  const secure = typeof window !== 'undefined' && window.location.protocol === 'https:';
  const parts = [`client_session=${sessionId}`, 'Path=/', 'SameSite=Lax', 'Max-Age=31536000'];
  if (secure) {
    parts.push('Secure');
  }
  document.cookie = parts.join('; ');
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
      setSessionCookie(existing);
      return existing;
    }
    const created = generateId();
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, created);
    setSessionCookie(created);
    return created;
  } catch (error) {
    if (!fallbackId) {
      fallbackId = generateId();
    }
    setSessionCookie(fallbackId);
    return fallbackId;
  }
};
