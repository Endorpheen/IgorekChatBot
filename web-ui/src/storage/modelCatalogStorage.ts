import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { ProviderModelSpec } from '../types/image';

const DB_NAME = 'igorek_images';
const DB_VERSION = 1;
const STORE_NAME = 'model_catalog';
const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000;

interface CatalogRecord {
  providerId: string;
  models: ProviderModelSpec[];
  fetchedAt: number;
  ttlMs: number;
}

interface ModelCatalogDB extends DBSchema {
  [STORE_NAME]: {
    key: string;
    value: CatalogRecord;
  };
}

let dbPromise: Promise<IDBPDatabase<ModelCatalogDB>> | null = null;

const isBrowser = typeof window !== 'undefined';
const hasIndexedDB = isBrowser && typeof indexedDB !== 'undefined';

const getDb = async (): Promise<IDBPDatabase<ModelCatalogDB>> => {
  if (!hasIndexedDB) {
    throw new Error('IndexedDB недоступна в текущей среде');
  }
  if (!dbPromise) {
    dbPromise = openDB<ModelCatalogDB>(DB_NAME, DB_VERSION, {
      upgrade(database) {
        if (!database.objectStoreNames.contains(STORE_NAME)) {
          database.createObjectStore(STORE_NAME, { keyPath: 'providerId' });
        }
      },
    });
  }
  return dbPromise;
};

export interface CatalogEntry {
  models: ProviderModelSpec[];
  fetchedAt: number;
  ttlMs: number;
}

export const readCatalog = async (providerId: string): Promise<CatalogEntry | null> => {
  if (!hasIndexedDB) {
    return null;
  }
  const db = await getDb();
  const record = await db.get(STORE_NAME, providerId);
  if (!record) {
    return null;
  }
  return {
    models: record.models,
    fetchedAt: record.fetchedAt,
    ttlMs: record.ttlMs,
  };
};

export const writeCatalog = async (providerId: string, models: ProviderModelSpec[], ttlMs = DEFAULT_TTL_MS): Promise<void> => {
  if (!hasIndexedDB) {
    return;
  }
  const db = await getDb();
  await db.put(STORE_NAME, {
    providerId,
    models,
    fetchedAt: Date.now(),
    ttlMs,
  });
};

export const deleteCatalog = async (providerId: string): Promise<void> => {
  if (!hasIndexedDB) {
    return;
  }
  const db = await getDb();
  await db.delete(STORE_NAME, providerId);
};

export const isStale = (entry: CatalogEntry | null): boolean => {
  if (!entry) {
    return true;
  }
  return Date.now() - entry.fetchedAt > entry.ttlMs;
};
