import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { ThreadSettings } from '../types/chat';

const DB_NAME = 'chatbotDB';
const DB_VERSION = 2; // Increment version for schema change
const SETTINGS_STORE_NAME = 'settings';
const MESSAGES_STORE_NAME = 'messages';

interface ChatbotDB extends DBSchema {
  [MESSAGES_STORE_NAME]: {
    key: string;
    value: any; // Assuming message type from messagesStorage
    indexes: { [key: string]: any };
  };
  [SETTINGS_STORE_NAME]: {
    key: string; // threadId
    value: ThreadSettings;
  };
}

const isBrowser = typeof window !== 'undefined';
const canUseIndexedDB = isBrowser && typeof indexedDB !== 'undefined';

let dbPromise: Promise<IDBPDatabase<ChatbotDB>> | null = null;

const getDb = async (): Promise<IDBPDatabase<ChatbotDB>> => {
  if (!canUseIndexedDB) {
    throw new Error('IndexedDB is not available in this environment');
  }

  if (!dbPromise) {
    dbPromise = openDB<ChatbotDB>(DB_NAME, DB_VERSION, {
      upgrade(database, oldVersion) {
        if (oldVersion < 1) {
            if (!database.objectStoreNames.contains(MESSAGES_STORE_NAME)) {
                const store = database.createObjectStore(MESSAGES_STORE_NAME, { keyPath: 'id' });
                store.createIndex('by-thread', 'threadId');
                store.createIndex('by-thread-createdAt', ['threadId', 'createdAt']);
            }
        }
        if (oldVersion < 2) {
          if (!database.objectStoreNames.contains(SETTINGS_STORE_NAME)) {
            database.createObjectStore(SETTINGS_STORE_NAME, { keyPath: 'threadId' });
          }
        }
      },
    });
  }

  return dbPromise;
};

export const saveThreadSettings = async (settings: ThreadSettings & { threadId: string }): Promise<void> => {
  if (!canUseIndexedDB) return;
  const db = await getDb();
  await db.put(SETTINGS_STORE_NAME, settings);
};

export const loadAllThreadSettings = async (): Promise<Record<string, ThreadSettings>> => {
  if (!canUseIndexedDB) return {};
  const db = await getDb();
  const allSettings = await db.getAll(SETTINGS_STORE_NAME);
  const settingsMap: Record<string, ThreadSettings> = {};
  for (const setting of allSettings) {
    if (!setting.threadId) continue;
    settingsMap[setting.threadId] = setting;
  }
  return settingsMap;
};
