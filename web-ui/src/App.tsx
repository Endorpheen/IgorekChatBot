import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import './App.css';
import { BrowserRouter, useLocation, useNavigate } from 'react-router-dom';

import type { ThreadSettings, ThreadSettingsMap } from './types/chat';
import type { McpServer, McpTool } from './types/mcp';
import { callAgent, uploadImagesForAnalysis, fetchMcpServers, fetchMcpBindings, fetchMcpServerTools, runMcpTool } from './utils/api';
import { COMMON_COMMANDS } from './constants/chat';
import { useChatState } from './hooks/useChatState';
import { useSpeechRecognition } from './hooks/useSpeechRecognition';
import { useImageUpload } from './hooks/useImageUpload';
import { useAudioPlayer } from './hooks/useAudioPlayer';
import { ensureCsrfToken } from './utils/csrf';
import { getImageSessionId } from './utils/session';

import Header from './components/Header';
import ThreadsPanel from './components/ThreadsPanel';
import ChatPanel from './components/ChatPanel';
import Footer from './components/Footer';
import SettingsPanel from './components/SettingsPanel';
import ImageGenerationPanel from './components/ImageGenerationPanel';

interface PendingAttachment {
  id: string;
  file: File;
  previewUrl: string;
  name: string;
  mimeType: string;
}

const MAX_PENDING_ATTACHMENTS = 4;
const AppContent = () => {
  const {
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
  } = useChatState();

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const [threadSettings, setThreadSettings] = useState<ThreadSettingsMap>(() => {
    const stored = localStorage.getItem('roo_agent_thread_settings');
    return stored ? JSON.parse(stored) : {};
  });

  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isAwaitingImageDescription, setIsAwaitingImageDescription] = useState(false);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [musicMuted, setMusicMuted] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [keyRefreshToken, setKeyRefreshToken] = useState(0);
  const [mcpServersState, setMcpServersState] = useState<McpServer[]>([]);
  const [mcpBindingsState, setMcpBindingsState] = useState<Record<string, string[]>>({});
  const [mcpToolsState, setMcpToolsState] = useState<Record<string, McpTool[]>>({});
  const [isMcpLoading, setIsMcpLoading] = useState(false);
  const [isMcpRunning, setIsMcpRunning] = useState(false);
  const mcpToolsRef = useRef<Record<string, McpTool[]>>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const userName = useMemo(() => import.meta.env.VITE_USER_NAME ?? 'Оператор', []);
  const agentUserId = useMemo(() => import.meta.env.VITE_TELEGRAM_USER_ID ?? 'local-user', []);
  const location = useLocation();
  const navigate = useNavigate();
  const isImagesRoute = location.pathname.startsWith('/images');

  const { isRecording, toggleRecognition } = useSpeechRecognition({
    onResult: (transcript) => setInput(prev => prev + ' ' + transcript),
    onError: (error) => console.error('Speech recognition error:', error),
  });

  const readFileAsDataUrl = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(reader.error ?? new Error('Не удалось прочитать файл'));
      reader.readAsDataURL(file);
    });
  };

  const handlePendingImages = async (files: File[]) => {
    if (pendingAttachments.length >= MAX_PENDING_ATTACHMENTS) {
      alert(`Можно прикрепить не более ${MAX_PENDING_ATTACHMENTS} изображений за раз.`);
      return;
    }

    const availableSlots = MAX_PENDING_ATTACHMENTS - pendingAttachments.length;
    const filesToProcess = files.slice(0, availableSlots);
    if (filesToProcess.length < files.length) {
      alert(`Добавлены только первые ${availableSlots} изображения. Остальные игнорированы.`);
    }

    try {
      const previews = await Promise.all(filesToProcess.map(readFileAsDataUrl));
      const attachmentsToAdd = filesToProcess.map((file, index) => ({
        id: uuidv4(),
        file,
        previewUrl: previews[index],
        name: file.name,
        mimeType: file.type,
      }));
      setPendingAttachments(prev => [...prev, ...attachmentsToAdd]);
    } catch (error) {
      console.error('Ошибка чтения изображения:', error);
      alert('Не удалось подготовить изображение. Попробуйте снова.');
    }
  };

  const handleRemoveAttachment = (id: string) => {
    setPendingAttachments(prev => prev.filter(attachment => attachment.id !== id));
  };

  const { fileInputRef, handleImageUpload, triggerFileInput } = useImageUpload({
    onImageUpload: handlePendingImages,
  });

  const { audioRef, sendAudioRef } = useAudioPlayer({ musicMuted });

  const handleRunMcpTool = useCallback(async (serverId: string, tool: McpTool, args: Record<string, unknown>) => {
    const serverName = mcpServersState.find((server) => server.id === serverId)?.name ?? serverId;
    const wasTyping = isTyping;
    if (!wasTyping) {
      setIsTyping(true);
    }
    setIsMcpRunning(true);
    try {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: `Запускаю MCP-инструмент ${tool.name} (сервер: ${serverName}).`,
        threadId,
      });
      const result = await runMcpTool({
        server_id: serverId,
        tool_name: tool.name,
        arguments: args,
        thread_id: threadId,
      });

      const formattedOutput = (() => {
        if (typeof result.output === 'string') {
          return result.output;
        }
        if (result.output && typeof result.output === 'object') {
          try {
            return JSON.stringify(result.output, null, 2);
          } catch (error) {
            console.error('Не удалось сериализовать ответ инструмента', error);
          }
        }
        return result.output ? String(result.output) : '';
      })();

      const lines = [
        `MCP · ${serverName} · ${tool.name}`,
        `Статус: ${result.status.toUpperCase()}`,
        result.duration_ms ? `Длительность: ${result.duration_ms} мс` : null,
        result.truncated ? 'Ответ обрезан по лимиту вывода.' : null,
        formattedOutput ? `Ответ:\n${formattedOutput}` : null,
        result.error ? `Ошибка: ${result.error}` : null,
        `Trace ID: ${result.trace_id}`,
      ].filter(Boolean).join('\n');

      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: lines,
        threadId,
      });
    } catch (error) {
      console.error('Ошибка запуска MCP инструмента', error);
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: `Ошибка при запуске MCP инструмента: ${(error as Error).message}`,
        threadId,
      });
    } finally {
      if (!wasTyping) {
        setIsTyping(false);
      }
      setIsMcpRunning(false);
    }
  }, [isTyping, mcpServersState, persistMessage, threadId]);

  const refreshMcpServers = useCallback(async () => {
    setIsMcpLoading(true);
    try {
      const list = await fetchMcpServers();
      setMcpServersState(list);
      return list;
    } catch (error) {
      console.error('Не удалось загрузить MCP серверы', error);
      return [] as McpServer[];
    } finally {
      setIsMcpLoading(false);
    }
  }, []);

  const getCurrentThreadSettings = (): ThreadSettings => {
    return threadSettings[threadId] || {
      openRouterEnabled: false,
      openRouterApiKey: '',
      openRouterModel: 'openai/gpt-4o-mini',
      historyMessageCount: 5,
      mcpBindings: {},
    };
  };

  const updateCurrentThreadSettings = (updates: Partial<ThreadSettings>) => {
    setThreadSettings((prev: ThreadSettingsMap) => ({ ...prev, [threadId]: { ...getCurrentThreadSettings(), ...updates } }));
  };

  useEffect(() => {
    localStorage.setItem('roo_agent_thread_settings', JSON.stringify(threadSettings));
  }, [threadSettings]);

  useEffect(() => {
    ensureCsrfToken();
    getImageSessionId();
  }, []);

  useEffect(() => {
    void refreshMcpServers();
  }, [refreshMcpServers]);

  useEffect(() => {
    if (!threadId) {
      setMcpBindingsState({});
      return;
    }

    let cancelled = false;

    const loadBindings = async () => {
      setIsMcpLoading(true);
      try {
        const data = await fetchMcpBindings(threadId);
        if (cancelled) {
          return;
        }
        const mapping: Record<string, string[]> = {};
        data.forEach(binding => {
          mapping[binding.server_id] = binding.enabled_tools;
        });
        setMcpBindingsState(mapping);

        const missingTools = Object.keys(mapping).filter(serverId => !mcpToolsRef.current[serverId]);
        await Promise.all(missingTools.map(async (serverId) => {
          try {
            const tools = await fetchMcpServerTools(serverId);
            if (!cancelled) {
              setMcpToolsState(prev => ({ ...prev, [serverId]: tools.tools }));
            }
          } catch (error) {
            console.error('Не удалось получить инструменты MCP', error);
          }
        }));
      } catch (error) {
        console.error('Не удалось получить привязки MCP', error);
        if (!cancelled) {
          setMcpBindingsState({});
        }
      } finally {
        if (!cancelled) {
          setIsMcpLoading(false);
        }
      }
    };

    void loadBindings();

    return () => {
      cancelled = true;
    };
  }, [threadId]);

  useEffect(() => {
    const missing = Object.keys(mcpBindingsState).filter(serverId => !mcpToolsRef.current[serverId]);
    if (missing.length === 0) {
      return;
    }
    let cancelled = false;
    const loadMissing = async () => {
      try {
        await Promise.all(missing.map(async (serverId) => {
          try {
            const tools = await fetchMcpServerTools(serverId);
            if (!cancelled) {
              setMcpToolsState(prev => ({ ...prev, [serverId]: tools.tools }));
            }
          } catch (error) {
            console.error('Не удалось получить инструменты MCP', error);
          }
        }));
      } finally {
        // nothing
      }
    };
    void loadMissing();
    return () => {
      cancelled = true;
    };
  }, [mcpBindingsState]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, threadId]);

  useEffect(() => {
    mcpToolsRef.current = mcpToolsState;
  }, [mcpToolsState]);

  const handleNewThread = () => {
    const newThreadId = uuidv4();
    const name = prompt('Введите название нового треда:')?.trim();
    setThreads(prev => [...prev, newThreadId]);
    setThreadNames((prev: { [x: string]: string; }) => ({ ...prev, [newThreadId]: name || `Тред ${Object.keys(prev).length + 1}` }));
    setThreadId(newThreadId);
  };

  const handleDeleteThread = (target: string) => {
    if (target === 'default') return alert('Нельзя удалить основной тред');
    if (!window.confirm('Вы уверены, что хотите удалить выбранный тред?')) return;
    setThreads(prev => prev.filter(id => id !== target));
    setThreadNames((prev: { [x: string]: string; }) => { const updated = { ...prev }; delete updated[target]; return updated; });
    setMessages(prev => prev.filter(msg => msg.threadId !== target));
    if (threadId === target) setThreadId('default');
  };

  const handleRenameThread = (id: string) => {
    const currentName = threadNames[id] ?? 'Без названия';
    const newName = prompt('Введите новое название треда:', currentName);
    if (newName && newName.trim() && newName.trim() !== currentName) {
      setThreadNames(prev => ({ ...prev, [id]: newName.trim() }));
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (isAwaitingImageDescription) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Пожалуйста, дождитесь завершения анализа изображения.',
        threadId,
      });
      return;
    }

    const trimmed = input.trim();
    const hasImages = pendingAttachments.length > 0;

    if (!trimmed && !hasImages) {
      return;
    }

    const isCommand = !!trimmed && COMMON_COMMANDS.includes(trimmed);
    if (isCommand && hasImages) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Команды нельзя отправлять вместе с изображениями. Отправьте сначала команду, затем прикрепите файл.',
        threadId,
      });
      return;
    }

    const attachmentsToSend = [...pendingAttachments];
    const currentSettings = getCurrentThreadSettings();
    const userApiKey = currentSettings.openRouterApiKey;
    const selectedModel = currentSettings.openRouterModel;
    const historyMessages = messages.filter(msg => msg.threadId === threadId);

    if (trimmed) {
      persistMessage({ type: 'user', contentType: 'text', content: trimmed, threadId });
    }

    setInput('');

    if (isCommand && trimmed === '/help') {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: `Igorek - ваш ИИ-ассистент для выполнения задач\n\n**Функции веб-интерфейса:**\n- **Чат**: Отправляйте текстовые сообщения боту через поле ввода или голосовой ввод (кнопка микрофона).\n- **Темы**: Создавайте новые темы чатов кнопкой "Новый тред" для организации разговоров.\n- **Команды**: Используйте /help для этого сообщения.\n- **TTS**: Включите/выключите озвучивание ответов бота кнопкой "TTS включен/выключен".\n- **Голосовой ввод**: Кнопка микрофона для голосового ввода сообщений.\n- **Очистка состояния**: Кнопка с иконкой питания очищает локальное хранилище и перезагружает интерфейс.\n- **Подписка**: Узнавайте об обновлениях на сайте проекта.\n- **История**: Сообщения сохраняются в браузере, можно переключаться между темами.\n\nВведите команду или запрос для взаимодействия.`,
        threadId,
      });
      return;
    }

    const shouldSendText = !!trimmed && (trimmed !== '/help') && !hasImages;

    if (!shouldSendText && !hasImages) {
      return;
    }

    setIsTyping(true);
    setIsAwaitingImageDescription(hasImages);

    let uploadSucceeded = false;

    try {
      if (shouldSendText) {
        const payload = {
          message: trimmed,
          thread_id: threadId,
          user_id: agentUserId,
          history: historyMessages,
          openRouterApiKey: userApiKey,
          openRouterModel: selectedModel,
        };
        try {
          const response = await callAgent(payload);
          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: response.response ?? '...',
            threadId: response.thread_id ?? threadId,
          });
        } catch (error) {
          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: `Ошибка: ${(error as Error).message}`,
            threadId,
          });
        }
      }

      if (hasImages) {
        if (!currentSettings.openRouterEnabled || !currentSettings.openRouterApiKey) {
          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: 'Для анализа изображений включите OpenRouter и укажите API ключ в настройках этого треда.',
            threadId,
          });
          return;
        }

        const systemPrompt = localStorage.getItem('systemPrompt');
        try {
          const response = await uploadImagesForAnalysis({
            files: attachmentsToSend.map(attachment => attachment.file),
            threadId,
            history: historyMessages,
            settings: currentSettings,
            systemPrompt,
            prompt: trimmed,
          });

          const targetThreadId = response.thread_id ?? threadId;
          const imagePayloads = response.images ?? (response.image ? [response.image] : []);

          imagePayloads.forEach(image => {
            if (!image?.url || !image.filename) {
              return;
            }
            persistMessage({
              type: 'user',
              contentType: 'image',
              content: image.url,
              threadId: targetThreadId,
              url: image.url,
              fileName: image.filename,
              mimeType: image.content_type,
            });
          });

          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: response.response ?? 'Не удалось получить описание изображений.',
            threadId: targetThreadId,
          });
          uploadSucceeded = true;
        } catch (error) {
          console.error('Image description error:', error);
          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: `Ошибка при анализе изображения: ${(error as Error).message}`,
            threadId,
          });
        }
      }
    } finally {
      setIsTyping(false);
      setIsAwaitingImageDescription(false);
      if (uploadSucceeded) {
        setPendingAttachments([]);
      }
    }
  };

  const sortedThreads = useMemo(() => {
    const list = [...threads];
    return threadSortOrder === 'newest-first' ? list.reverse() : list;
  }, [threads, threadSortOrder]);

  const messagesToRender = useMemo(() => messages.filter(msg => msg.threadId === threadId), [messages, threadId]);

  const mcpOptions = useMemo(() => {
    return mcpServersState
      .map(server => {
        const enabled = mcpBindingsState[server.id] || [];
        if (enabled.length === 0) {
          return null;
        }
        const tools = (mcpToolsState[server.id] || []).filter(tool => enabled.includes(tool.name));
        if (tools.length === 0) {
          return null;
        }
        return {
          serverId: server.id,
          serverName: server.name,
          tools,
        };
      })
      .filter((item): item is { serverId: string; serverName: string; tools: McpTool[] } => item !== null);
  }, [mcpServersState, mcpBindingsState, mcpToolsState]);

  useEffect(() => {
    if (location.pathname === '/' || isImagesRoute) {
      return;
    }
    navigate('/', { replace: true });
  }, [location.pathname, isImagesRoute, navigate]);

  return (
    <>
      <div className="app-root">
        <div className={`app-shell${isImagesRoute ? ' image-page-shell' : ''}`}>
          {isImagesRoute ? (
            <>
              <div className="image-page-header">
                <button
                  type="button"
                  className="image-back-button"
                  onClick={() => navigate('/')}
                >
                  ← В чат
                </button>
                <div className="image-page-actions">
                  <button
                    type="button"
                    className="settings-button secondary"
                    onClick={() => setIsSettingsOpen(true)}
                  >
                    Настройки
                  </button>
                </div>
              </div>
              <ImageGenerationPanel
                onRequireKeySetup={() => setIsSettingsOpen(true)}
                refreshKeySignal={keyRefreshToken}
              />
              <Footer openSettings={() => setIsSettingsOpen(true)} />
            </>
          ) : (
            <>
              <div className="disclaimer-banner">Игорёк очень любит галлюцинации 🤪, будьте осторожны!!! Проверяйте важную информацию!</div>
              <Header
                userName={userName}
                toggleMusicMute={() => setMusicMuted(!musicMuted)}
                musicMuted={musicMuted}
                audioEnabled={audioEnabled}
                setAudioEnabled={setAudioEnabled}
                setIsMenuOpen={setIsMenuOpen}
                showImageNavigation
                onNavigateToImages={() => navigate('/images')}
              />
              <div className="grid">
                <ThreadsPanel
                  isMenuOpen={isMenuOpen}
                  setIsMenuOpen={setIsMenuOpen}
                  sortedThreads={sortedThreads}
                  threadSettings={threadSettings}
                  threadNames={threadNames}
                  threadId={threadId}
                  openMenuId={openMenuId}
                  setOpenMenuId={setOpenMenuId}
                  handleRenameThread={handleRenameThread}
                  handleDeleteThread={handleDeleteThread}
                  setThreadId={setThreadId}
                  handleNewThread={handleNewThread}
                  toggleThreadSortOrder={() => setThreadSortOrder((p) => (p === 'newest-first' ? 'oldest-first' : 'newest-first'))}
                  threadSortOrder={threadSortOrder}
                  openSettings={() => setIsSettingsOpen(true)}
                  audioEnabled={audioEnabled}
                  setAudioEnabled={setAudioEnabled}
                />
                <ChatPanel
                  messages={messagesToRender}
                  isTyping={isTyping}
                  input={input}
                  isRecording={isRecording}
                  audioEnabled={audioEnabled}
                  handleInputChange={(e) => setInput(e.target.value)}
                  handleVoiceInput={toggleRecognition}
                  handleImageUpload={handleImageUpload}
                  handleSubmit={handleSubmit}
                  handleCommandClick={(cmd) => setInput(cmd)}
                  messagesEndRef={messagesEndRef}
                  fileInputRef={fileInputRef}
                  triggerFileInput={triggerFileInput}
                  COMMON_COMMANDS={COMMON_COMMANDS}
                  pendingAttachments={pendingAttachments.map(({ id, previewUrl, name }) => ({ id, previewUrl, name }))}
                  removeAttachment={handleRemoveAttachment}
                  mcpOptions={mcpOptions}
                  onRunMcpTool={handleRunMcpTool}
                  isMcpBusy={isMcpRunning || isMcpLoading}
                />
              </div>
              <Footer openSettings={() => setIsSettingsOpen(true)} />
            </>
          )}
        </div>
      </div>
      <SettingsPanel
        isSettingsOpen={isSettingsOpen}
        closeSettings={() => setIsSettingsOpen(false)}
        threadSettings={threadSettings}
        updateCurrentThreadSettings={updateCurrentThreadSettings}
        threadNames={threadNames}
        threadId={threadId}
        onImageKeyChange={() => setKeyRefreshToken((value) => value + 1)}
        onMcpServersUpdated={setMcpServersState}
        onMcpBindingsUpdated={setMcpBindingsState}
      />
      <audio
        ref={audioRef}
        src="/web-ui/abrupt-stop-and-disk-failure.mp3"
        preload="auto"
        loop={false}
        style={{ display: 'none' }}
      />
      <audio
        ref={sendAudioRef}
        src="/web-ui/sound12.mp3"
        preload="auto"
        style={{ display: 'none' }}
      />
    </>
  );
};

const App: React.FC = () => (
  <BrowserRouter>
    <AppContent />
  </BrowserRouter>
);

export default App;
