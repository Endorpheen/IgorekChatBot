import { memo, useMemo, type ReactNode } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import CopyButton from './CopyButton';

interface CodeBlockProps {
  inline?: boolean;
  className?: string;
  children: ReactNode;
  [key: string]: unknown;
}

const CodeBlock = memo(({ inline, className, children, ...props }: CodeBlockProps) => {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  const code = useMemo(() => String(children).replace(/\n$/, ''), [children]);

  if (!inline && language) {
    return (
      <div className="code-block-container">
        <div className="code-block-header">
          <span className="code-language">{language}</span>
          <CopyButton code={code} />
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
});

export default CodeBlock;
