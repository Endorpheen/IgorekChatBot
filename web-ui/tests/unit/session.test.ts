import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const importSessionModule = async () => {
  return import('../../src/utils/session.ts');
};

describe('session id generation', () => {
  const GLOBALS_TO_RESET = ['crypto', 'window', 'document'] as const;
  const originalGlobals: Record<(typeof GLOBALS_TO_RESET)[number], unknown> = {
    crypto: globalThis.crypto,
    window: (globalThis as typeof globalThis & { window?: unknown }).window,
    document: (globalThis as typeof globalThis & { document?: unknown }).document,
  };

  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
    // ensure pristine globals before each test
    for (const key of GLOBALS_TO_RESET) {
      if (originalGlobals[key] === undefined) {
        delete (globalThis as Record<string, unknown>)[key];
      } else {
        Object.defineProperty(globalThis, key, {
          value: originalGlobals[key],
          configurable: true,
          writable: true,
          enumerable: true,
        });
      }
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // clean up any globals we might have stubbed
    for (const key of GLOBALS_TO_RESET) {
      if (originalGlobals[key] === undefined) {
        delete (globalThis as Record<string, unknown>)[key];
      } else {
        Object.defineProperty(globalThis, key, {
          value: originalGlobals[key],
          configurable: true,
          writable: true,
          enumerable: true,
        });
      }
    }
  });

  it('uses crypto.randomUUID when available', async () => {
    const randomUUID = vi.fn(() => 'uuid-from-randomUUID');
    Object.defineProperty(globalThis, 'crypto', {
      value: { randomUUID },
      configurable: true,
      writable: true,
      enumerable: true,
    });
    const { getImageSessionId } = await importSessionModule();
    const id = getImageSessionId();
    expect(id).toBe('uuid-from-randomUUID');
    expect(randomUUID).toHaveBeenCalledOnce();
  });

  it('falls back to crypto.getRandomValues when randomUUID is unavailable', async () => {
    const timestamp = 1_700_000_000_000;
    const timestampSegment = timestamp.toString(36);
    vi.spyOn(Date, 'now').mockReturnValue(timestamp);

    const randomValue = 0x00abcdef;
    const getRandomValues = vi.fn((buffer: Uint32Array) => {
      buffer[0] = randomValue;
      return buffer;
    });

    Object.defineProperty(globalThis, 'crypto', {
      value: { getRandomValues },
      configurable: true,
      writable: true,
      enumerable: true,
    });

    const { getImageSessionId } = await importSessionModule();
    const id = getImageSessionId();
    const expectedRandomSegment = randomValue.toString(36).padStart(6, '0').slice(-6);
    expect(id).toBe(`${timestampSegment}-${expectedRandomSegment}`);
    expect(getRandomValues).toHaveBeenCalledOnce();
  });

  it('produces deterministic fallback ids when crypto is unavailable', async () => {
    const timestamp = 1_700_000_123_456;
    const timestampSegment = timestamp.toString(36);
    vi.spyOn(Date, 'now').mockReturnValue(timestamp);

    Object.defineProperty(globalThis, 'crypto', {
      value: undefined,
      configurable: true,
      writable: true,
      enumerable: true,
    });

    const storage = new Map<string, string>();
    const getItem = vi.fn((key: string) => storage.get(key) ?? null);
    const setItem = vi.fn((key: string, value: string) => {
      storage.set(key, value);
    });

    Object.defineProperty(globalThis, 'window', {
      value: {
        location: { protocol: 'https:' },
        sessionStorage: { getItem, setItem },
      },
      configurable: true,
      writable: true,
      enumerable: true,
    });

    Object.defineProperty(globalThis, 'document', {
      value: undefined,
      configurable: true,
      writable: true,
      enumerable: true,
    });

    const { getImageSessionId } = await importSessionModule();
    const id = getImageSessionId();
    expect(id).toBe(`${timestampSegment}-000001`);
    expect(setItem).toHaveBeenCalledWith('image-generation-session-id', id);
  });
});
