import { openDB, type DBSchema, type IDBPDatabase } from 'idb';

const DB_NAME = 'togetherKeyDB';
const DB_VERSION = 1;
const STORE_NAME = 'keys';
const PRIMARY_KEY = 'primary';
const DEFAULT_ITERATIONS = 150_000;

const isBrowser = typeof window !== 'undefined';
const hasIndexedDB = isBrowser && typeof indexedDB !== 'undefined';

const textEncoder = (() => (typeof TextEncoder !== 'undefined' ? new TextEncoder() : null))();
const textDecoder = (() => (typeof TextDecoder !== 'undefined' ? new TextDecoder() : null))();

export class PinRequiredError extends Error {
  constructor() {
    super('PIN_REQUIRED');
    this.name = 'PinRequiredError';
  }
}

export class InvalidPinError extends Error {
  constructor() {
    super('INVALID_PIN');
    this.name = 'InvalidPinError';
  }
}

interface StoredKeyRecord {
  id: string;
  encrypted: boolean;
  key: string;
  iv?: string;
  salt?: string;
  iterations?: number;
  createdAt: string;
  updatedAt: string;
}

interface TogetherKeyDB extends DBSchema {
  [STORE_NAME]: {
    key: string;
    value: StoredKeyRecord;
  };
}

let dbPromise: Promise<IDBPDatabase<TogetherKeyDB>> | null = null;
let memoryRecord: StoredKeyRecord | null = null;

const getDb = async (): Promise<IDBPDatabase<TogetherKeyDB>> => {
  if (!hasIndexedDB) {
    throw new Error('IndexedDB недоступна в текущей среде');
  }

  if (!dbPromise) {
    dbPromise = openDB<TogetherKeyDB>(DB_NAME, DB_VERSION, {
      upgrade(database) {
        if (!database.objectStoreNames.contains(STORE_NAME)) {
          database.createObjectStore(STORE_NAME, { keyPath: 'id' });
        }
      },
    });
  }

  return dbPromise;
};

const bufferToBase64 = (buffer: ArrayBuffer | Uint8Array): string => {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  if (isBrowser && typeof window.btoa === 'function') {
    return window.btoa(binary);
  }
  throw new Error('Base64 кодирование недоступно в данной среде');
};

const base64ToBytes = (value: string): Uint8Array => {
  if (!isBrowser || typeof window.atob !== 'function') {
    throw new Error('Base64 декодирование недоступно в данной среде');
  }
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
};

const getCrypto = (): Crypto => {
  if (!isBrowser || !window.crypto?.subtle) {
    throw new Error('WebCrypto недоступен');
  }
  return window.crypto;
};

const deriveAesKey = async (pin: string, salt: Uint8Array, iterations: number): Promise<CryptoKey> => {
  if (!textEncoder) {
    throw new Error('TextEncoder недоступен');
  }
  const crypto = getCrypto();
  const baseKey = await crypto.subtle.importKey(
    'raw',
    textEncoder.encode(pin),
    { name: 'PBKDF2' },
    false,
    ['deriveKey'],
  );

  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
};

const encryptValue = async (
  value: string,
  pin: string,
): Promise<{ key: string; iv: string; salt: string; iterations: number }> => {
  if (!textEncoder) {
    throw new Error('TextEncoder недоступен');
  }
  const crypto = getCrypto();
  const salt = new Uint8Array(16);
  crypto.getRandomValues(salt);
  const iv = new Uint8Array(12);
  crypto.getRandomValues(iv);
  const iterations = DEFAULT_ITERATIONS;

  const aesKey = await deriveAesKey(pin, salt, iterations);
  const encoded = textEncoder.encode(value);
  const cipherBuffer = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aesKey, encoded);

  return {
    key: bufferToBase64(cipherBuffer),
    iv: bufferToBase64(iv),
    salt: bufferToBase64(salt),
    iterations,
  };
};

const decryptValue = async (record: StoredKeyRecord, pin: string): Promise<string> => {
  if (!textDecoder) {
    throw new Error('TextDecoder недоступен');
  }
  if (!record.iv || !record.salt) {
    throw new Error('Запись повреждена');
  }
  const iterations = record.iterations ?? DEFAULT_ITERATIONS;
  const salt = base64ToBytes(record.salt);
  const iv = base64ToBytes(record.iv);
  const aesKey = await deriveAesKey(pin, salt, iterations);
  const cipherBytes = base64ToBytes(record.key);
  const crypto = getCrypto();
  const decryptedBuffer = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, aesKey, cipherBytes);
  return textDecoder.decode(decryptedBuffer);
};

const readRecord = async (): Promise<StoredKeyRecord | null> => {
  if (!hasIndexedDB) {
    return memoryRecord;
  }
  const db = await getDb();
  const record = await db.get(STORE_NAME, PRIMARY_KEY);
  return record ?? null;
};

const writeRecord = async (record: StoredKeyRecord | null): Promise<void> => {
  if (!hasIndexedDB) {
    memoryRecord = record;
    return;
  }
  const db = await getDb();
  if (record) {
    await db.put(STORE_NAME, record);
  } else {
    await db.delete(STORE_NAME, PRIMARY_KEY);
  }
};

export interface TogetherKeyMetadata {
  hasKey: boolean;
  encrypted: boolean;
  updatedAt?: string;
  createdAt?: string;
}

export interface TogetherKeyValue {
  key: string;
  encrypted: boolean;
}

export const loadMetadata = async (): Promise<TogetherKeyMetadata> => {
  const record = await readRecord();
  if (!record) {
    return { hasKey: false, encrypted: false };
  }
  return {
    hasKey: true,
    encrypted: record.encrypted,
    updatedAt: record.updatedAt,
    createdAt: record.createdAt,
  };
};

export const loadTogetherKey = async (pin?: string): Promise<TogetherKeyValue> => {
  const record = await readRecord();
  if (!record) {
    throw new Error('Ключ не найден');
  }
  if (!record.encrypted) {
    return { key: record.key, encrypted: false };
  }
  if (!pin) {
    throw new PinRequiredError();
  }
  try {
    const key = await decryptValue(record, pin);
    return { key, encrypted: true };
  } catch (error) {
    throw new InvalidPinError();
  }
};

export const saveTogetherKey = async (key: string, options: { encrypt: boolean; pin?: string }): Promise<void> => {
  const trimmed = key.trim();
  if (!trimmed) {
    throw new Error('Пустой ключ нельзя сохранить');
  }
  const now = new Date().toISOString();

  if (options.encrypt) {
    if (!options.pin) {
      throw new PinRequiredError();
    }
    const encrypted = await encryptValue(trimmed, options.pin);
    await writeRecord({
      id: PRIMARY_KEY,
      encrypted: true,
      key: encrypted.key,
      iv: encrypted.iv,
      salt: encrypted.salt,
      iterations: encrypted.iterations,
      createdAt: now,
      updatedAt: now,
    });
    return;
  }

  await writeRecord({
    id: PRIMARY_KEY,
    encrypted: false,
    key: trimmed,
    createdAt: now,
    updatedAt: now,
  });
};

export const updateEncryptionMode = async (encrypt: boolean, pin?: string): Promise<void> => {
  const record = await readRecord();
  if (!record) {
    throw new Error('Нет сохранённого ключа');
  }

  if (encrypt) {
    if (!pin) {
      throw new PinRequiredError();
    }
    const decrypted = record.encrypted ? await loadTogetherKey(pin) : { key: record.key, encrypted: false };
    await saveTogetherKey(decrypted.key, { encrypt: true, pin });
    return;
  }

  const keyValue = record.encrypted ? await loadTogetherKey(pin) : { key: record.key, encrypted: false };
  await saveTogetherKey(keyValue.key, { encrypt: false });
};

export const deleteTogetherKey = async (): Promise<void> => {
  await writeRecord(null);
};
