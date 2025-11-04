/* @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const importCsrfModule = () => import('../../src/utils/csrf');

describe('csrf utilities', () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalCrypto = globalThis.crypto;

  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
    // jsdom already provides window/document, just ensure clean storage
    window.sessionStorage.clear();
    document.cookie = '';
  });

  afterEach(() => {
    vi.resetModules();
    if (originalWindow === undefined) {
      delete (globalThis as Record<string, unknown>).window;
    } else {
      Object.defineProperty(globalThis, 'window', {
        value: originalWindow,
        configurable: true,
        writable: true,
        enumerable: true,
      });
    }
    if (originalDocument === undefined) {
      delete (globalThis as Record<string, unknown>).document;
    } else {
      Object.defineProperty(globalThis, 'document', {
        value: originalDocument,
        configurable: true,
        writable: true,
        enumerable: true,
      });
    }
    if (originalCrypto === undefined) {
      delete (globalThis as Record<string, unknown>).crypto;
    } else {
      Object.defineProperty(globalThis, 'crypto', {
        value: originalCrypto,
        configurable: true,
        writable: true,
        enumerable: true,
      });
    }
  });

  it('повторно использует один и тот же токен и сохраняет его в sessionStorage и cookie', async () => {
    const sessionSpy = vi.spyOn(Storage.prototype, 'setItem');
    const { ensureCsrfToken, buildCsrfHeader } = await importCsrfModule();

    const firstToken = ensureCsrfToken();
    expect(firstToken).toMatch(/^[a-z0-9-]+$/i);
    expect(window.sessionStorage.getItem('csrf-token')).toBe(firstToken);
    expect(document.cookie).toContain(`csrf-token=${firstToken}`);

    const secondToken = ensureCsrfToken();
    expect(secondToken).toBe(firstToken);
    expect(buildCsrfHeader()).toEqual({ 'X-CSRF-Token': firstToken });
    expect(sessionSpy).toHaveBeenCalledOnce();
  });

  it('создаёт токен в среде без window и document', async () => {
    vi.stubGlobal('window', undefined);
    vi.stubGlobal('document', undefined);
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'server-generated-token') });

    const { ensureCsrfToken } = await importCsrfModule();
    const token = ensureCsrfToken();

    expect(token).toBe('server-generated-token');
  });
});
