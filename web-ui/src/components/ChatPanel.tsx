import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import { Command, Mic, Send, Upload, MoreVertical, Check, X, FileText, Loader2 } from 'lucide-react';
import CodeBlock from './CodeBlock';
import type { ChatMessage } from '../types/chat';

const formatBytes = (value?: number | null): string | null => {
  if (typeof value !== 'number' || Number.isNaN(value) || value < 0) {
    return null;
  }
  if (value === 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const size = value / 1024 ** exponent;
  const formatted = size >= 10 || exponent === 0 ? size.toFixed(0) : size.toFixed(1);
  return `${formatted} ${units[exponent]}`;
};

interface ChatPanelProps {
  messages: ChatMessage[];
  isTyping: boolean;
  input: string;
  isRecording: boolean;
  audioEnabled: boolean;
  handleInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleVoiceInput: () => void;
  handleFileUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleSubmit: (event: React.FormEvent) => void;
  handleCommandClick: (command: string) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  triggerFileInput: () => void;
  COMMON_COMMANDS: string[];
  pendingAttachments: Array<{ id: string; name: string; kind: 'image' | 'document'; previewUrl?: string; status: 'loading' | 'ready' | 'processing' }>;
  removeAttachment: (id: string) => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  isTyping,
  input,
  isRecording,
  audioEnabled,
  handleInputChange,
  handleVoiceInput,
  handleFileUpload,
  handleSubmit,
  handleCommandClick,
  messagesEndRef,
  fileInputRef,
  triggerFileInput,
  COMMON_COMMANDS,
  pendingAttachments,
  removeAttachment,
}) => {
  const [openMessageMenu, setOpenMessageMenu] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  useEffect(() => {
    const handleClickOutside = () => setOpenMessageMenu(null);
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const codeComponent = useCallback(({ inline, className, children, ...props }: React.HTMLAttributes<HTMLElement> & { inline?: boolean }) => (
    <CodeBlock
      inline={inline}
      className={className}
      {...props}
    >
      {children}
    </CodeBlock>
  ), []);

  const markdownComponents = useMemo<Components>(() => ({
    a: ({ ...props }) => (
      <a {...props} target="_blank" rel="noopener noreferrer" />
    ),
    p: ({ children, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => <span className="chat-text" {...props}>{children}</span>,
    code: codeComponent,
  }), [codeComponent]);

  const copyToClipboard = async (text: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  const speak = async (text: string) => {
    if (!audioEnabled) return;
    try {
      const response = await fetch('http://127.0.0.1:5001/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(`HTTP status ${response.status}`);
      const blob = await response.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      await audio.play();
    } catch (error) {
      console.error('TTS error', error);
    }
  };

  return (
    <main className="chat-panel">
      <div className="chat-window">
        {messages.map((msg) => {
          const attachmentMetaParts: string[] = [];
          if (msg.mimeType) {
            attachmentMetaParts.push(msg.mimeType);
          }
          const attachmentSize = formatBytes(msg.size);
          if (attachmentSize) {
            attachmentMetaParts.push(attachmentSize);
          }

          return (
            <div
              key={msg.id}
              className={`chat-message chat-message--${msg.type}`}
              data-testid="chat-message"
              data-role={msg.type}
            >
              <span className="chat-prefix">{msg.type === 'user' ? '>' : '$'}</span>
              {msg.contentType === 'text' ? (
                <div className="chat-content">
                  <ReactMarkdown components={markdownComponents}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
              ) : msg.contentType === 'image' ? (
                <img
                  src={msg.url ?? msg.content}
                  alt={msg.fileName ?? 'Uploaded image'}
                  className="chat-image"
                />
              ) : msg.contentType === 'attachment' ? (
                <div className="chat-attachment-message">
                  <FileText className="icon" />
                  <div className="chat-attachment-details">
                    <div className="chat-attachment-name">{msg.fileName ?? msg.content}</div>
                    {attachmentMetaParts.length > 0 ? (
                      <div className="chat-attachment-meta">{attachmentMetaParts.join(' • ')}</div>
                    ) : null}
                    {msg.description ? (
                      <div className="chat-attachment-description">{msg.description}</div>
                    ) : null}
                    {msg.url ? (
                      <a
                        className="chat-attachment-link"
                        href={msg.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid="chat-attachment-download"
                      >
                        Скачать
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="chat-document-message">
                  <FileText className="icon" />
                  <div className="chat-document-text" title={msg.content}>
                    {msg.content}
                  </div>
                </div>
              )}
              <div className="message-actions">
                <button
                  className="menu-button"
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setOpenMessageMenu(openMessageMenu === msg.id ? null : msg.id);
                  }}
                  title="Действия с сообщением"
                >
                  <MoreVertical className="icon" />
                </button>
                {openMessageMenu === msg.id && (
                  <div className="message-menu" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="menu-item"
                      onClick={() => {
                        copyToClipboard(msg.content, msg.id);
                        setOpenMessageMenu(null);
                      }}
                    >
                      Скопировать сообщение
                      {copiedMessageId === msg.id && <Check className="menu-item-icon" />}
                    </button>
                    {msg.type === 'bot' && msg.contentType === 'text' && (
                      <button
                        type="button"
                        className="menu-item"
                        onClick={() => {
                          speak(msg.content);
                          setOpenMessageMenu(null);
                        }}
                      >
                        Озвучить сообщение
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {isTyping && (
          <div className="typing-indicator">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        {pendingAttachments.length > 0 && (
          <div className="attachment-preview-list" data-testid="pending-attachments">
            {pendingAttachments.map(attachment => (
              <div
                key={attachment.id}
                className={`attachment-preview-item ${attachment.kind === 'document' ? 'attachment-preview-item--document' : ''}`}
                data-testid={`pending-attachment-${attachment.kind}`}
              >
                {attachment.kind === 'document' ? (
                  <div className="attachment-document-card">
                    <div className="attachment-document-icon">
                      {attachment.status === 'processing' || attachment.status === 'loading' ? (
                        <Loader2 className="icon attachment-spinner" />
                      ) : (
                        <FileText className="icon" />
                      )}
                    </div>
                    <div className="attachment-document-meta">
                      <span className="attachment-document-name" title={attachment.name}>{attachment.name}</span>
                      <span className="attachment-document-status">
                        {attachment.status === 'loading'
                          ? 'Подготовка...'
                          : attachment.status === 'processing'
                            ? 'Обработка...'
                            : 'Ожидает запроса'}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="attachment-remove"
                      onClick={() => removeAttachment(attachment.id)}
                      title="Удалить документ"
                      disabled={isTyping || attachment.status === 'processing'}
                    >
                      <X className="icon" />
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="attachment-thumb">
                      <img src={attachment.previewUrl} alt={`Предпросмотр ${attachment.name}`} />
                      <button
                        type="button"
                        className="attachment-remove"
                        onClick={() => removeAttachment(attachment.id)}
                        title="Убрать изображение"
                        disabled={isTyping}
                      >
                        <X className="icon" />
                      </button>
                    </div>
                    <span className="attachment-name" title={attachment.name}>{attachment.name}</span>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="chat-input-container" data-testid="chat-input-container">
          <input
            type="text"
            className="chat-input"
            placeholder="Введите команду или запрос..."
            value={input}
            onChange={handleInputChange}
            disabled={isTyping}
            data-testid="chat-input"
          />
          <button
            type="button"
            className={`voice-button ${isRecording ? 'recording' : ''}`}
            onClick={handleVoiceInput}
            disabled={isTyping}
            title="Голосовой ввод"
            data-testid="chat-voice"
          >
            <Mic className="icon" />
          </button>
          <button
            type="button"
            className="upload-button"
            onClick={triggerFileInput}
            disabled={isTyping}
            title="Прикрепить файл"
            data-testid="chat-attach-trigger"
          >
            <Upload className="icon" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.pdf,.md,.txt,.docx"
            onChange={handleFileUpload}
            multiple
            hidden
            data-testid="chat-file-input"
          />
          <button
            type="submit"
            className="send-button"
            disabled={isTyping}
            title="Отправить"
            data-testid="chat-send"
          >
            <Send className="icon" />
          </button>
        </div>
      </form>

      <div className="command-grid">
        {COMMON_COMMANDS.map((command) => (
          <button
            key={command}
            type="button"
            className="command-button"
            onClick={() => handleCommandClick(command)}
          >
            <Command className="icon" />
            {command}
          </button>
        ))}
      </div>
    </main>
  );
};

export default ChatPanel;
