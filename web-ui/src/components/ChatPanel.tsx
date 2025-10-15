import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import { Command, Mic, Send, Upload, MoreVertical, Check, X } from 'lucide-react';
import CodeBlock from './CodeBlock';
import type { ChatMessage } from '../types/chat';
import type { McpTool } from '../types/mcp';

interface ChatPanelProps {
  messages: ChatMessage[];
  isTyping: boolean;
  input: string;
  isRecording: boolean;
  audioEnabled: boolean;
  handleInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleVoiceInput: () => void;
  handleImageUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleSubmit: (event: React.FormEvent) => void;
  handleCommandClick: (command: string) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  triggerFileInput: () => void;
  COMMON_COMMANDS: string[];
  pendingAttachments: Array<{ id: string; previewUrl: string; name: string }>;
  removeAttachment: (id: string) => void;
  mcpOptions?: Array<{ serverId: string; serverName: string; tools: McpTool[] }>;
  onRunMcpTool?: (serverId: string, tool: McpTool, args: Record<string, unknown>) => Promise<void>;
  isMcpBusy?: boolean;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  isTyping,
  input,
  isRecording,
  audioEnabled,
  handleInputChange,
  handleVoiceInput,
  handleImageUpload,
  handleSubmit,
  handleCommandClick,
  messagesEndRef,
  fileInputRef,
  triggerFileInput,
  COMMON_COMMANDS,
  pendingAttachments,
  removeAttachment,
  mcpOptions,
  onRunMcpTool,
  isMcpBusy,
}) => {
  const [openMessageMenu, setOpenMessageMenu] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [selectedToolKey, setSelectedToolKey] = useState<string>('');

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

  const flatMcpTools = useMemo(() => {
    if (!mcpOptions) {
      return [] as Array<{ option: { serverId: string; serverName: string; tools: McpTool[] }; tool: McpTool; key: string }>;
    }
    return mcpOptions.flatMap(option => option.tools.map(tool => ({
      option,
      tool,
      key: `${option.serverId}::${tool.name}`,
    })));
  }, [mcpOptions]);

  useEffect(() => {
    if (selectedToolKey && !flatMcpTools.some(item => item.key === selectedToolKey)) {
      setSelectedToolKey('');
    }
    if (!selectedToolKey && flatMcpTools.length === 1) {
      setSelectedToolKey(flatMcpTools[0].key);
    }
  }, [flatMcpTools, selectedToolKey]);

  const collectArguments = useCallback(async (tool: McpTool) => {
    const schema = tool.inputSchema;
    if (!schema || typeof schema !== 'object') {
      return {};
    }

    const properties = (schema as Record<string, unknown>).properties as Record<string, any> | undefined;
    if (!properties || typeof properties !== 'object') {
      return {};
    }
    const required = new Set<string>(Array.isArray((schema as Record<string, any>).required) ? (schema as Record<string, any>).required : []);
    const args: Record<string, unknown> = {};

    for (const [name, property] of Object.entries(properties)) {
      const prop = property ?? {};
      const type = typeof prop === 'object' && prop !== null && typeof prop.type === 'string' ? prop.type : 'string';
      const enumValues = Array.isArray((prop as Record<string, unknown>).enum) ? (prop as Record<string, unknown>).enum as unknown[] : undefined;
      const description = typeof prop?.description === 'string' ? prop.description : '';
      const promptLabel = [name, description].filter(Boolean).join(' — ');
      const defaultValue = typeof prop?.default !== 'undefined' ? String(prop.default) : '';

      const promptText = enumValues
        ? `${promptLabel}\nВарианты: ${enumValues.map(String).join(', ')}`
        : promptLabel;

      const userInput = window.prompt(promptText || `Введите значение ${name}`, defaultValue);

      if (userInput === null) {
        if (required.has(name)) {
          alert(`Поле ${name} обязательно для заполнения.`);
          return null;
        }
        continue;
      }

      const trimmed = userInput.trim();
      if (!trimmed) {
        if (required.has(name)) {
          alert(`Поле ${name} обязательно для заполнения.`);
          return null;
        }
        continue;
      }

      if (enumValues && !enumValues.map(String).includes(trimmed)) {
        alert(`Недопустимое значение для ${name}`);
        return null;
      }

      switch (type) {
        case 'integer':
        case 'number': {
          const numeric = Number(trimmed);
          if (Number.isNaN(numeric)) {
            alert(`Ожидалось числовое значение для ${name}`);
            return null;
          }
          args[name] = numeric;
          break;
        }
        case 'boolean':
          args[name] = ['true', '1', 'yes', 'да'].includes(trimmed.toLowerCase());
          break;
        default:
          args[name] = trimmed;
          break;
      }
    }

    return args;
  }, []);

  const handleRunSelectedTool = useCallback(async () => {
    if (!onRunMcpTool || !selectedToolKey) {
      return;
    }
    const entry = flatMcpTools.find(item => item.key === selectedToolKey);
    if (!entry) {
      return;
    }
    const args = await collectArguments(entry.tool);
    if (args === null) {
      return;
    }
    try {
      await onRunMcpTool(entry.option.serverId, entry.tool, args);
    } catch (error) {
      console.error('Не удалось выполнить MCP-инструмент', error);
      alert(`Ошибка запуска инструмента: ${(error as Error).message}`);
    }
  }, [collectArguments, flatMcpTools, onRunMcpTool, selectedToolKey]);

  return (
    <main className="chat-panel">
      <div className="chat-window">
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message chat-message--${msg.type}`}>
            <span className="chat-prefix">{msg.type === 'user' ? '>' : '$'}</span>
          {msg.contentType === 'text' ? (
            <div className="chat-content">
              <ReactMarkdown components={markdownComponents}>
                {msg.content}
              </ReactMarkdown>
            </div>
          ) : (
              <img
                src={msg.url ?? msg.content}
                alt={msg.fileName ?? 'Uploaded image'}
                className="chat-image"
              />
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
        ))}
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
        <div className="mcp-tool-picker">
          <label htmlFor="mcp-tool-select" className="mcp-tool-label">
            Инструменты MCP
          </label>
          <div className="mcp-tool-controls">
            <select
              id="mcp-tool-select"
              className="mcp-tool-select"
              value={selectedToolKey}
              onChange={(event) => setSelectedToolKey(event.target.value)}
              disabled={isTyping || isMcpBusy || flatMcpTools.length === 0}
            >
              <option value="">
                {flatMcpTools.length === 0 ? 'Нет доступных инструментов' : 'Выберите инструмент'}
              </option>
              {mcpOptions?.map(option => (
                <optgroup key={option.serverId} label={`MCP · ${option.serverName}`}>
                  {option.tools.map(tool => (
                    <option key={`${option.serverId}::${tool.name}`} value={`${option.serverId}::${tool.name}`}>
                      {tool.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <button
              type="button"
              className="mcp-tool-run"
              onClick={handleRunSelectedTool}
              disabled={isTyping || isMcpBusy || !selectedToolKey}
            >
              Запустить
            </button>
          </div>
          {flatMcpTools.length === 0 && (
            <div className="mcp-tool-empty">Нет серверов — добавьте MCP Server</div>
          )}
        </div>
        {pendingAttachments.length > 0 && (
          <div className="attachment-preview-list">
            {pendingAttachments.map(attachment => (
              <div key={attachment.id} className="attachment-preview-item">
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
              </div>
            ))}
          </div>
        )}
        <div className="chat-input-container">
          <input
            type="text"
            className="chat-input"
            placeholder="Введите команду или запрос..."
            value={input}
            onChange={handleInputChange}
            disabled={isTyping}
          />
          <button
            type="button"
            className={`voice-button ${isRecording ? 'recording' : ''}`}
            onClick={handleVoiceInput}
            disabled={isTyping}
            title="Голосовой ввод"
          >
            <Mic className="icon" />
          </button>
          <button
            type="button"
            className="upload-button"
            onClick={triggerFileInput}
            disabled={isTyping}
            title="Загрузить изображение для анализа"
          >
            <Upload className="icon" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleImageUpload}
            multiple
            hidden
          />
          <button type="submit" className="send-button" disabled={isTyping} title="Отправить">
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
