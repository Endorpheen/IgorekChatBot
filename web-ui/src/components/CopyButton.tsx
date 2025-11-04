import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface CopyButtonProps {
  code: string;
  resetDelayMs?: number;
}

const HIDE_NOTIFICATION_DELAY = 2000;

const copyCodeToClipboard = async (
  code: string,
  setCopied: (isCopied: boolean) => void,
  resetDelayMs: number,
) => {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(code);
      console.log('✅ Скопировано в буфер обмена');
    } else {
      const textArea = document.createElement('textarea');
      textArea.value = code;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      console.log('✅ Скопировано в буфер обмена');
    }
    setCopied(true);
    setTimeout(() => setCopied(false), resetDelayMs);
  } catch (error) {
    console.error('Failed to copy code:', error);
  }
};

const CopyButton = ({ code, resetDelayMs = HIDE_NOTIFICATION_DELAY }: CopyButtonProps) => {
  const [isCopied, setIsCopied] = useState(false);

  return (
    <>
      <button
        className={`code-copy-button ${isCopied ? 'copied' : ''}`}
        onClick={() => copyCodeToClipboard(code, setIsCopied, resetDelayMs)}
        type="button"
        title="Копировать код"
      >
        {isCopied ? <Check className="icon" /> : <Copy className="icon" />}
      </button>
      {isCopied && <span className="copy-notification">Скопировано!</span>}
    </>
  );
};

export default CopyButton;
