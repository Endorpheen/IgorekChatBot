import type { IDBPDatabase } from 'idb';

export const CHATBOT_DB_NAME = 'chatbotDB';
export const CHATBOT_DB_VERSION = 2;

export const MESSAGE_STORE_NAME = 'messages';
export const MESSAGE_BY_THREAD_INDEX = 'by-thread';
export const MESSAGE_BY_THREAD_TIME_INDEX = 'by-thread-createdAt';

export const SETTINGS_STORE_NAME = 'settings';

type UpgradeLogFn = (message?: string) => void;

const logUpgrade: UpgradeLogFn = (message) => {
  if (message) {
    console.info(`[IndexedDB] ${message}`);
  }
};

export const ensureChatbotSchema = (
  database: IDBPDatabase<any>,
  oldVersion: number,
  newVersion: number | null,
): void => {
  const createdStores: string[] = [];
  if (!database.objectStoreNames.contains(MESSAGE_STORE_NAME)) {
    const store = database.createObjectStore(MESSAGE_STORE_NAME, { keyPath: 'id' });
    store.createIndex(MESSAGE_BY_THREAD_INDEX, 'threadId');
    store.createIndex(MESSAGE_BY_THREAD_TIME_INDEX, ['threadId', 'createdAt']);
    createdStores.push(MESSAGE_STORE_NAME);
  }

  if (!database.objectStoreNames.contains(SETTINGS_STORE_NAME)) {
    database.createObjectStore(SETTINGS_STORE_NAME, { keyPath: 'threadId' });
    createdStores.push(SETTINGS_STORE_NAME);
  }

  if (createdStores.length > 0) {
    const fromVersion = oldVersion || 0;
    const targetVersion = newVersion ?? CHATBOT_DB_VERSION;
    logUpgrade(
      `chatbotDB upgraded from v${fromVersion} to v${targetVersion}: ensured stores ${createdStores.join(', ')}`,
    );
  }
};
