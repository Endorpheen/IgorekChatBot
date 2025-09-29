import type { ReactNode } from 'react';
import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  inline?: boolean;
  className?: string;
  children: ReactNode;
  [key: string]: unknown;
}

const copyCodeToClipboard = async (code: string, setCopied: (isCopied: boolean) => void) => {
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
    setTimeout(() => setCopied(false), 2000); // Reset after 2 seconds
  } catch (error) {
    console.error('Failed to copy code:', error);
  }
};

const CodeBlock = ({ inline, className, children, ...props }: CodeBlockProps) => {
  console.log(children);
  const [isCopied, setIsCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  const code = String(children).replace(/\n$/, '');

  if (!inline && language) {
    return (
      <div className="code-block-container">
        <div className="code-block-header">
          <span className="code-language">{language}</span>
          <button
            className={`code-copy-button ${isCopied ? 'copied' : ''}`}
            onClick={() => copyCodeToClipboard(code, setIsCopied)}
            type="button"
            title="Копировать код"
          >
            {isCopied ? <Check className="icon" /> : <Copy className="icon" />}
          </button>
          {isCopied && <span className="copy-notification">Скопировано!</span>}
        </div>
        <SyntaxHighlighter
          style={vscDarkPlus}
          language={language}
          PreTag="div"
          customStyle={{
            margin: 0,
            borderRadius: '0 0 0.5rem 0.5rem',
            fontSize: '0.9rem',
          }}
          {...props}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    );
  }

  return (
    <code className={className} {...props}>
      {children}
    </code>
  );
};

export default CodeBlock;
