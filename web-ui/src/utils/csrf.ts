const STORAGE_KEY = 'csrf-token';
let inMemoryToken: string | null = null;

const generateToken = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2, 12);
};

const writeCookie = (token: string) => {
  if (typeof document === 'undefined') {
    return;
  }
  const secure = typeof window !== 'undefined' && window.location.protocol === 'https:';
  const attributes = [`csrf-token=${token}`, 'path=/', 'SameSite=Strict'];
  if (secure) {
    attributes.push('Secure');
  }
  document.cookie = attributes.join('; ');
};

const readCookie = (): string | null => {
  if (typeof document === 'undefined') {
    return null;
  }
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const [name, value] = part.trim().split('=');
    if (name === 'csrf-token') {
      return value;
    }
  }
  return null;
};

export const ensureCsrfToken = (): string => {
  if (inMemoryToken) {
    return inMemoryToken;
  }
  if (typeof window === 'undefined') {
    inMemoryToken = generateToken();
    return inMemoryToken;
  }

  let token: string | null = null;
  try {
    token = window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    token = null;
  }

  if (!token) {
    token = readCookie();
  }

  if (!token) {
    token = generateToken();
  }

  try {
    window.sessionStorage.setItem(STORAGE_KEY, token);
  } catch {
    // ignore storage errors (e.g. private mode)
  }

  writeCookie(token);
  inMemoryToken = token;
  return token;
};

export const buildCsrfHeader = (): Record<string, string> => {
  const token = ensureCsrfToken();
  return { 'X-CSRF-Token': token };
};
