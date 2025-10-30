import type { DBSchema, IDBPDatabase, IndexNames, StoreNames } from 'idb';

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

export const ensureChatbotSchema = <Schema extends DBSchema>(
  database: IDBPDatabase<Schema>,
  oldVersion: number,
  newVersion: number | null,
): void => {
  const createdStores: string[] = [];
  const messageStoreName = MESSAGE_STORE_NAME as StoreNames<Schema>;
  const messageIndexName = MESSAGE_BY_THREAD_INDEX as IndexNames<Schema, typeof messageStoreName>;
  const messageTimeIndexName = MESSAGE_BY_THREAD_TIME_INDEX as IndexNames<Schema, typeof messageStoreName>;
  if (!database.objectStoreNames.contains(messageStoreName)) {
    const store = database.createObjectStore(messageStoreName, { keyPath: 'id' });
    store.createIndex(messageIndexName, 'threadId');
    store.createIndex(messageTimeIndexName, ['threadId', 'createdAt']);
    createdStores.push(MESSAGE_STORE_NAME);
  }

  const settingsStoreName = SETTINGS_STORE_NAME as StoreNames<Schema>;
  if (!database.objectStoreNames.contains(settingsStoreName)) {
    database.createObjectStore(settingsStoreName, { keyPath: 'threadId' });
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
