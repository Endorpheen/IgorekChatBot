import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { ThreadSettings } from '../types/chat';
import {
  CHATBOT_DB_NAME,
  CHATBOT_DB_VERSION,
  MESSAGE_STORE_NAME,
  MESSAGE_BY_THREAD_INDEX,
  MESSAGE_BY_THREAD_TIME_INDEX,
  SETTINGS_STORE_NAME,
  ensureChatbotSchema,
} from './chatbotDbConfig';

interface ChatbotDB extends DBSchema {
  [MESSAGE_STORE_NAME]: {
    key: string;
    value: unknown;
    indexes: {
      [MESSAGE_BY_THREAD_INDEX]: string;
      [MESSAGE_BY_THREAD_TIME_INDEX]: [string, string];
    };
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
    dbPromise = openDB<ChatbotDB>(CHATBOT_DB_NAME, CHATBOT_DB_VERSION, {
      upgrade(database, oldVersion, newVersion) {
        ensureChatbotSchema(database, oldVersion, newVersion ?? CHATBOT_DB_VERSION);
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
