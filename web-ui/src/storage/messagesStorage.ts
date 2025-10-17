import { openDB, type DBSchema, type IDBPDatabase, type IDBPTransaction } from 'idb';
import type { ChatMessage } from '../types/chat';

const DB_NAME = 'chatbotDB';
const STORE_NAME = 'messages';
const THREAD_INDEX = 'by-thread';
const THREAD_TIME_INDEX = 'by-thread-createdAt';
const MESSAGE_LIMIT_PER_THREAD = 200;

type MessageRole = ChatMessage['type'];
type MessageContentType = ChatMessage['contentType'];

interface StoredMessage {
  id: string;
  threadId: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  contentType: MessageContentType;
  fileName?: string;
  url?: string;
  mimeType?: string;
}

interface ChatbotDB extends DBSchema {
  [STORE_NAME]: {
    key: string;
    value: StoredMessage;
    indexes: {
      [THREAD_INDEX]: string;
      [THREAD_TIME_INDEX]: [string, string];
    };
  };
}

const isBrowser = typeof window !== 'undefined';
const canUseIndexedDB = isBrowser && typeof indexedDB !== 'undefined';

let dbPromise: Promise<IDBPDatabase<ChatbotDB>> | null = null;
let initPromise: Promise<void> | null = null;
let memoryStore: StoredMessage[] = [];

const buildId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
};

const toStored = (message: ChatMessage): StoredMessage => ({
  id: message.id,
  threadId: message.threadId,
  role: message.type,
  content: message.content,
  createdAt: message.createdAt,
  contentType: message.contentType,
  fileName: message.fileName,
  url: message.url,
  mimeType: message.mimeType,
});

const fromStored = (stored: StoredMessage): ChatMessage => ({
  id: stored.id,
  threadId: stored.threadId,
  type: stored.role,
  content: stored.content,
  createdAt: stored.createdAt,
  contentType: stored.contentType ?? 'text',
  fileName: stored.fileName,
  url: stored.url,
  mimeType: stored.mimeType,
});

const sortByCreatedAt = <T extends { createdAt: string }>(items: T[]): T[] =>
  [...items].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());

const limitPerThread = (messages: StoredMessage[]): StoredMessage[] => {
  const sorted = sortByCreatedAt(messages);
  const grouped = new Map<string, StoredMessage[]>();

  for (const message of sorted) {
    const list = grouped.get(message.threadId) ?? [];
    list.push(message);
    grouped.set(message.threadId, list);
  }

  const limited: StoredMessage[] = [];
  for (const list of grouped.values()) {
    const slice = list.length > MESSAGE_LIMIT_PER_THREAD
      ? list.slice(list.length - MESSAGE_LIMIT_PER_THREAD)
      : list;
    limited.push(...slice);
  }

  return sortByCreatedAt(limited);
};

const collectLegacyMessages = (): ChatMessage[] => {
  if (!isBrowser || !('localStorage' in window)) {
    return [];
  }

  const legacyKeys = ['roo_agent_messages', 'agent_messages'];
  const aggregated: ChatMessage[] = [];

  for (const key of legacyKeys) {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      continue;
    }

    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        for (const entry of parsed) {
          const normalised = normaliseLegacyMessage(entry);
          if (normalised) {
            aggregated.push(normalised);
          }
        }
      }
    } catch (error) {
      console.warn(`Не удалось мигрировать сообщения из ${key}:`, error);
    }

    window.localStorage.removeItem(key);
  }

  return aggregated;
};

const normaliseLegacyMessage = (entry: unknown): ChatMessage | null => {
  if (!entry || typeof entry !== 'object') {
    return null;
  }

  const obj = entry as Record<string, unknown>;
  const threadId = typeof obj.threadId === 'string'
    ? obj.threadId
    : typeof obj.thread_id === 'string'
      ? obj.thread_id
      : 'default';
  const content = typeof obj.content === 'string' ? obj.content : '';
  if (!content) {
    return null;
  }

  const typeValue = obj.type ?? obj.role;
  const type: MessageRole = typeValue === 'bot' ? 'bot' : 'user';
  const createdAtRaw = typeof obj.createdAt === 'string' ? obj.createdAt : obj.created_at;
  const createdAt = typeof createdAtRaw === 'string' && !Number.isNaN(Date.parse(createdAtRaw))
    ? createdAtRaw
    : new Date().toISOString();

  const contentTypeValue = obj.contentType;
  const contentType: MessageContentType = contentTypeValue === 'image' ? 'image' : 'text';
  const idValue = obj.id;
  const id = typeof idValue === 'string' ? idValue : buildId();

  const fileName = typeof obj.fileName === 'string' ? obj.fileName : undefined;
  const url = typeof obj.url === 'string' ? obj.url : undefined;
  const mimeType = typeof obj.mimeType === 'string' ? obj.mimeType : undefined;

  return {
    id,
    threadId,
    type,
    content,
    createdAt,
    contentType,
    fileName,
    url,
    mimeType,
  };
};

const getDb = async (): Promise<IDBPDatabase<ChatbotDB>> => {
  if (!canUseIndexedDB) {
    throw new Error('IndexedDB недоступна в текущей среде');
  }

  if (!dbPromise) {
    dbPromise = openDB<ChatbotDB>(DB_NAME, undefined, {
      upgrade(database) {
        if (!database.objectStoreNames.contains(STORE_NAME)) {
          const store = database.createObjectStore(STORE_NAME, { keyPath: 'id' });
          store.createIndex(THREAD_INDEX, 'threadId');
          store.createIndex(THREAD_TIME_INDEX, ['threadId', 'createdAt']);
        }
      },
    });
  }

  return dbPromise;
};

const initStore = async (): Promise<void> => {
  if (initPromise) {
    return initPromise;
  }

  initPromise = (async () => {
    const legacyMessages = collectLegacyMessages();
    if (legacyMessages.length === 0) {
      return;
    }

    const deduped = new Map<string, ChatMessage>();
    for (const message of legacyMessages) {
      deduped.set(message.id, message);
    }

    const limited = limitPerThread(Array.from(deduped.values()).map(toStored));

    if (canUseIndexedDB) {
      const db = await getDb();
      const tx = db.transaction(STORE_NAME, 'readwrite');
      await tx.store.clear();
      for (const stored of limited) {
        await tx.store.put(stored);
      }
      await tx.done;
    } else {
      memoryStore = limited;
    }
  })();

  await initPromise;
};

const withInitialisation = async <T>(operation: () => Promise<T>): Promise<T> => {
  await initStore();
  return operation();
};

const pruneThread = async (
  tx: IDBPTransaction<ChatbotDB, [typeof STORE_NAME], 'readwrite'>,
  threadId: string,
): Promise<void> => {
  const index = tx.store.index(THREAD_TIME_INDEX);
  const range = IDBKeyRange.bound([threadId, ''], [threadId, '￿']);
  const keys = await index.getAllKeys(range);
  const excess = keys.length - MESSAGE_LIMIT_PER_THREAD;
  if (excess <= 0) {
    return;
  }

  for (let i = 0; i < excess; i += 1) {
    const key = keys[i];
    if (typeof key === 'string') {
      await tx.store.delete(key);
    }
  }
};

const saveMessageIndexedDB = async (message: ChatMessage): Promise<void> => {
  const db = await getDb();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  await tx.store.put(toStored(message));
  await pruneThread(tx, message.threadId);
  await tx.done;
};

const loadMessagesIndexedDB = async (threadId?: string): Promise<ChatMessage[]> => {
  const db = await getDb();
  const tx = db.transaction(STORE_NAME, 'readonly');
  if (threadId) {
    const index = tx.store.index(THREAD_TIME_INDEX);
    const range = IDBKeyRange.bound([threadId, ''], [threadId, '￿']);
    const records = await index.getAll(range);
    await tx.done;
    return records.map(fromStored);
  }

  const records = await tx.store.getAll();
  await tx.done;
  return records.map(fromStored);
};

const clearMessagesIndexedDB = async (threadId?: string): Promise<void> => {
  const db = await getDb();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  if (!threadId) {
    await tx.store.clear();
    await tx.done;
    return;
  }

  const index = tx.store.index(THREAD_INDEX);
  for await (const cursor of index.iterate(threadId)) {
    await cursor.delete();
  }
  await tx.done;
};

const saveMessageMemory = async (message: ChatMessage): Promise<void> => {
  memoryStore = limitPerThread([
    ...memoryStore.filter((item) => item.id !== message.id),
    toStored(message),
  ]);
};

const loadMessagesMemory = async (threadId?: string): Promise<ChatMessage[]> => {
  const target = threadId
    ? memoryStore.filter((item) => item.threadId === threadId)
    : memoryStore;
  return target.map(fromStored);
};

const clearMessagesMemory = async (threadId?: string): Promise<void> => {
  if (!threadId) {
    memoryStore = [];
    return;
  }
  memoryStore = memoryStore.filter((item) => item.threadId !== threadId);
};

export const saveMessage = (message: ChatMessage): Promise<void> =>
  withInitialisation(() => (canUseIndexedDB
    ? saveMessageIndexedDB(message)
    : saveMessageMemory(message)));

export const loadMessages = (threadId?: string): Promise<ChatMessage[]> =>
  withInitialisation(async () => {
    const records = canUseIndexedDB
      ? await loadMessagesIndexedDB(threadId)
      : await loadMessagesMemory(threadId);
    return sortByCreatedAt(records.map((record) => ({ ...record })));
  });

export const clearMessages = (threadId?: string): Promise<void> =>
  withInitialisation(() => (canUseIndexedDB
    ? clearMessagesIndexedDB(threadId)
    : clearMessagesMemory(threadId)));
