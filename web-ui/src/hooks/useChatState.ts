import { useState, useEffect, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { ChatMessage, ThreadNameMap } from '../types/chat';
import { INITIAL_GREETING } from '../constants/chat';
import {
  loadMessages,
  saveMessage as storeMessage,
  clearMessages as clearStoredMessages,
} from '../storage/messagesStorage';

type ThreadSortOrder = 'newest-first' | 'oldest-first';

export const useChatState = () => {
  const [messages, setMessagesState] = useState<ChatMessage[]>([]);
  const storageQueueRef = useRef<Promise<void>>(Promise.resolve());

  const enqueueStorageTask = (task: () => Promise<void>) => {
    storageQueueRef.current = storageQueueRef.current
      .then(task)
      .catch((error) => {
        console.error('Ошибка работы с IndexedDB:', error);
      });
  };

  useEffect(() => {
    let cancelled = false;

    const initialiseMessages = async () => {
      try {
        const storedMessages = await loadMessages();
        if (cancelled) {
          return;
        }
        if (storedMessages.length > 0) {
          setMessagesState(storedMessages);
          return;
        }

        const defaultMessage: ChatMessage = {
          id: uuidv4(),
          type: 'bot',
          contentType: 'text',
          content: INITIAL_GREETING,
          threadId: 'default',
          createdAt: new Date().toISOString(),
        };

        setMessagesState([defaultMessage]);
        enqueueStorageTask(async () => {
          await clearStoredMessages();
          await storeMessage(defaultMessage);
        });
      } catch (error) {
        console.error('Не удалось загрузить сообщения из IndexedDB:', error);
        if (cancelled) {
          return;
        }
        const fallbackMessage: ChatMessage = {
          id: uuidv4(),
          type: 'bot',
          contentType: 'text',
          content: INITIAL_GREETING,
          threadId: 'default',
          createdAt: new Date().toISOString(),
        };
        setMessagesState([fallbackMessage]);
      }
    };

    void initialiseMessages();

    return () => {
      cancelled = true;
    };
  }, []);

  const [threadId, setThreadId] = useState(() => {
    const stored = localStorage.getItem('roo_agent_thread');
    return stored ?? 'default';
  });

  const [threads, setThreads] = useState<string[]>(() => {
    const stored = localStorage.getItem('roo_agent_threads');
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as string[];
        return parsed.length > 0 ? parsed : ['default'];
      } catch {
        return ['default'];
      }
    }
    return ['default'];
  });

  const [threadNames, setThreadNames] = useState<ThreadNameMap>(() => {
    const stored = localStorage.getItem('roo_agent_thread_names');
    return stored ? (JSON.parse(stored) as ThreadNameMap) : { default: 'Главный тред' };
  });

  const [threadSortOrder, setThreadSortOrder] = useState<ThreadSortOrder>(() => {
    const stored = localStorage.getItem('roo_agent_thread_sort');
    return stored === 'newest-first' ? 'newest-first' : 'oldest-first';
  });

  useEffect(() => {
    localStorage.setItem('roo_agent_thread', threadId);
  }, [threadId]);

  useEffect(() => {
    localStorage.setItem('roo_agent_threads', JSON.stringify(threads));
  }, [threads]);

  useEffect(() => {
    localStorage.setItem('roo_agent_thread_names', JSON.stringify(threadNames));
  }, [threadNames]);

  useEffect(() => {
    localStorage.setItem('roo_agent_thread_sort', threadSortOrder);
  }, [threadSortOrder]);

  const persistMessage = (message: Omit<ChatMessage, 'id' | 'createdAt'>) => {
    const newMessage: ChatMessage = {
      ...message,
      id: uuidv4(),
      createdAt: new Date().toISOString(),
    };

    setMessagesState((prev) => [...prev, newMessage]);
    enqueueStorageTask(async () => {
      await storeMessage(newMessage);
    });
  };

  type MessagesUpdater = ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[]);

  const setMessages = (updater: MessagesUpdater) => {
    setMessagesState((prev) => {
      const next = typeof updater === 'function'
        ? (updater as (value: ChatMessage[]) => ChatMessage[])(prev)
        : updater;

      enqueueStorageTask(async () => {
        await clearStoredMessages();
        for (const entry of next) {
          await storeMessage(entry);
        }
      });

      return next;
    });
  };

  return {
    messages,
    setMessages,
    threadId,
    setThreadId,
    threads,
    setThreads,
    threadNames,
    setThreadNames,
    threadSortOrder,
    setThreadSortOrder,
    persistMessage,
  };
};
