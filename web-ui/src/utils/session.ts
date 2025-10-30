const SESSION_STORAGE_KEY = 'image-generation-session-id';
let fallbackId: string | null = null;
let fallbackCounter = 0;

const generateId = (): string => {
  if (typeof crypto !== 'undefined') {
    if (typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }

    if (typeof crypto.getRandomValues === 'function') {
      const randomBuffer = new Uint32Array(1);
      crypto.getRandomValues(randomBuffer);
      const randomSegment = randomBuffer[0].toString(36).padStart(6, '0').slice(-6);
      return `${Date.now().toString(36)}-${randomSegment}`;
    }
  }

  fallbackCounter += 1;
  const fallbackSegment = fallbackCounter.toString(36).padStart(6, '0').slice(-6);
  return `${Date.now().toString(36)}-${fallbackSegment}`;
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
  } catch {
    if (!fallbackId) {
      fallbackId = generateId();
    }
    setSessionCookie(fallbackId);
    return fallbackId;
  }
};
