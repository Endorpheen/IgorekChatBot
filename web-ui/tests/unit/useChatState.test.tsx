/* @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest';

import { render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';

const storageMocks = vi.hoisted(() => ({
  loadMessages: vi.fn(),
  saveMessage: vi.fn(),
  clearMessages: vi.fn(),
}));

vi.mock('../../src/storage/messagesStorage', () => ({
  loadMessages: storageMocks.loadMessages,
  saveMessage: storageMocks.saveMessage,
  clearMessages: storageMocks.clearMessages,
}));

import { useChatState } from '../../src/hooks/useChatState';

const storedMessages = [
  {
    id: 'msg-1',
    type: 'bot' as const,
    contentType: 'text' as const,
    content: 'Привет из IndexedDB',
    threadId: 'default',
    createdAt: new Date().toISOString(),
  },
];

const TestHarness: React.FC = () => {
  const { messages } = useChatState();
  return (
    <ul>
      {messages.map((message) => (
        <li key={message.id}>{message.content}</li>
      ))}
    </ul>
  );
};

describe('useChatState', () => {
  it('восстанавливает сообщения, загруженные из IndexedDB', async () => {
    storageMocks.loadMessages.mockResolvedValueOnce(storedMessages);
    storageMocks.saveMessage.mockResolvedValue(undefined);
    storageMocks.clearMessages.mockResolvedValue(undefined);

    render(<TestHarness />);

    expect(await screen.findByText('Привет из IndexedDB')).toBeInTheDocument();
    expect(storageMocks.loadMessages).toHaveBeenCalledWith();
    expect(storageMocks.saveMessage).not.toHaveBeenCalled();
    expect(storageMocks.clearMessages).not.toHaveBeenCalled();
  });
});
