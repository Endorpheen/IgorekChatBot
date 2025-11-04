/* @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CopyButton from '../../src/components/CopyButton';

describe('CopyButton', () => {
  const originalClipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.runOnlyPendingTimers();
    vi.useRealTimers();

    if (originalClipboardDescriptor) {
      Object.defineProperty(navigator, 'clipboard', { ...originalClipboardDescriptor });
    } else {
      delete (navigator as Record<string, unknown>).clipboard;
    }
  });

  it('копирует текст через navigator.clipboard и показывает уведомление', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    render(<CopyButton code="console.log('hello');" />);

    await user.click(screen.getByRole('button', { name: 'Копировать код' }));

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith("console.log('hello');");
    expect(screen.getByText('Скопировано!')).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(2000);
    expect(screen.queryByText('Скопировано!')).not.toBeInTheDocument();
  });

  it('использует document.execCommand, когда clipboard API недоступен', async () => {
    delete (navigator as Record<string, unknown>).clipboard;
    const execCommand = vi.fn().mockReturnValue(true);
    (document as unknown as { execCommand: (command: string) => boolean }).execCommand = execCommand;

    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    render(<CopyButton code="alert('fallback');" />);

    await user.click(screen.getByRole('button', { name: 'Копировать код' }));

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(screen.getByText('Скопировано!')).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(2000);
    expect(screen.queryByText('Скопировано!')).not.toBeInTheDocument();
  });
});
