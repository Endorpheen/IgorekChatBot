import { useState, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { ChatMessage, ThreadNameMap } from '../types/chat';
import { INITIAL_GREETING } from '../constants/chat';

type ThreadSortOrder = 'newest-first' | 'oldest-first';

export const useChatState = () => {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const stored = localStorage.getItem('roo_agent_messages');
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as ChatMessage[];
        if (parsed.length > 0) {
          return parsed;
        }
      } catch (error) {
        console.warn('Failed to parse stored messages', error);
      }
    }
    return [
      {
        id: uuidv4(),
        type: 'bot',
        contentType: 'text',
        content: INITIAL_GREETING,
        threadId: 'default',
        createdAt: new Date().toISOString(),
      },
    ];
  });

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
    localStorage.setItem('roo_agent_messages', JSON.stringify(messages));
  }, [messages]);

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
    setMessages((prev) => [
      ...prev,
      {
        ...message,
        id: uuidv4(),
        createdAt: new Date().toISOString(),
      },
    ]);
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
