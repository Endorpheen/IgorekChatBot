/* @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CopyButton from '../../src/components/CopyButton';

describe('CopyButton', () => {
  const originalClipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
  const originalExecCommand = (document as Partial<Document> & Record<string, unknown>).execCommand;
  let user: ReturnType<typeof userEvent.setup>;

  beforeEach(() => {
    user = userEvent.setup();
  });

  afterEach(() => {
    vi.resetAllMocks();
    cleanup();

    if (originalClipboardDescriptor) {
      Object.defineProperty(navigator, 'clipboard', { ...originalClipboardDescriptor });
    } else {
      delete (navigator as Record<string, unknown>).clipboard;
    }

    if (originalExecCommand) {
      (document as Record<string, unknown>).execCommand = originalExecCommand;
    } else {
      delete (document as Record<string, unknown>).execCommand;
    }
  });

  it('копирует текст через navigator.clipboard и показывает уведомление', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    render(<CopyButton code="console.log('hello');" resetDelayMs={100} />);

    await user.click(screen.getByRole('button', { name: 'Копировать код' }));

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith("console.log('hello');");
    expect(await screen.findByText('Скопировано!')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText('Скопировано!')).not.toBeInTheDocument();
    });
  });

  it('использует document.execCommand, когда clipboard API недоступен', async () => {
    delete (navigator as Record<string, unknown>).clipboard;
    const execCommand = vi.fn().mockReturnValue(true);
    (document as unknown as { execCommand: (command: string) => boolean }).execCommand = execCommand;

    render(<CopyButton code="alert('fallback');" resetDelayMs={100} />);

    await user.click(screen.getByRole('button', { name: 'Копировать код' }));

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(await screen.findByText('Скопировано!')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText('Скопировано!')).not.toBeInTheDocument();
    });
  });
});
