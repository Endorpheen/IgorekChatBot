import React, { useEffect, useMemo, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import './App.css';
import { BrowserRouter, useLocation, useNavigate } from 'react-router-dom';

import type { ThreadSettings, ThreadSettingsMap } from './types/chat';
import { analyzeDocument, callAgent, uploadImagesForAnalysis } from './utils/api';
import { validateImageProviderSettings } from './utils/imageProvider';
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
import McpPanel from './components/McpPanel';

type AttachmentKind = 'image' | 'document';

interface PendingAttachment {
  id: string;
  file: File;
  name: string;
  mimeType: string;
  size: number;
  kind: AttachmentKind;
  previewUrl?: string;
  status: 'loading' | 'ready' | 'processing';
  persisted?: boolean;
}

const MAX_PENDING_ATTACHMENTS = 4;
const MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024;
const DOCUMENT_EXTENSIONS = new Set(['.pdf', '.md', '.txt', '.docx']);
const DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'application/x-pdf',
  'text/markdown',
  'text/plain',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

const getFileExtension = (file: File): string => {
  const name = file.name ?? '';
  const idx = name.lastIndexOf('.');
  if (idx === -1) {
    return '';
  }
  return name.slice(idx).toLowerCase();
};

const isDocumentFile = (file: File): boolean => {
  const sanitizedExt = getFileExtension(file);
  const mime = (file.type || '').toLowerCase();

  if (!DOCUMENT_EXTENSIONS.has(sanitizedExt)) {
    return false;
  }

  if (!mime) {
    return true;
  }

  if (mime === 'application/octet-stream') {
    return true;
  }

  if (DOCUMENT_MIME_TYPES.has(mime)) {
    return true;
  }

  if (sanitizedExt === '.md' && mime === 'text/plain') {
    return true;
  }

  return false;
};

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
  const [voiceAssistantEnabled, setVoiceAssistantEnabled] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [keyRefreshToken, setKeyRefreshToken] = useState(0);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const userName = useMemo(() => import.meta.env.VITE_USER_NAME ?? 'Оператор', []);
  const agentUserId = useMemo(() => import.meta.env.VITE_TELEGRAM_USER_ID ?? 'local-user', []);
  const location = useLocation();
  const navigate = useNavigate();
  const isImagesRoute = location.pathname.startsWith('/images');
  const isMcpRoute = location.pathname.startsWith('/mcp');

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

  const handlePendingDocuments = async (files: File[]) => {
    if (files.length === 0) {
      return;
    }

    if (pendingAttachments.filter(attachment => attachment.kind === 'document').length > 0) {
      alert('Можно прикрепить только один документ за раз. Удалите предыдущий документ, чтобы загрузить новый.');
      return;
    }

    if (pendingAttachments.some(attachment => attachment.kind === 'image')) {
      alert('Документы и изображения не поддерживаются в одном запросе. Удалите изображения или отправьте их отдельно.');
      return;
    }

    const docFile = files[0];

    if (!isDocumentFile(docFile)) {
      alert('Тип выбранного документа не поддерживается. Допустимы PDF, Markdown, TXT и DOCX.');
      return;
    }

    if (docFile.size > MAX_DOCUMENT_SIZE_BYTES) {
      alert('Размер документа превышает 10 МБ. Выберите файл поменьше.');
      return;
    }

    const attachmentId = uuidv4();
    setPendingAttachments(prev => [
      ...prev,
      {
        id: attachmentId,
        file: docFile,
        name: docFile.name,
        mimeType: docFile.type || 'application/octet-stream',
        size: docFile.size,
        kind: 'document',
        status: 'loading',
        persisted: false,
      },
    ]);

    setTimeout(() => {
      setPendingAttachments(prev => prev.map(item => (item.id === attachmentId ? { ...item, status: 'ready' } : item)));
    }, 400);
  };

  const handlePendingImages = async (files: File[]) => {
    if (pendingAttachments.filter(attachment => attachment.kind === 'image').length >= MAX_PENDING_ATTACHMENTS) {
      alert(`Можно прикрепить не более ${MAX_PENDING_ATTACHMENTS} изображений за раз.`);
      return;
    }

    if (pendingAttachments.some(attachment => attachment.kind === 'document')) {
      alert('Сначала отправьте или удалите загруженные документы, затем добавьте изображения.');
      return;
    }

    const availableSlots = MAX_PENDING_ATTACHMENTS - pendingAttachments.filter(attachment => attachment.kind === 'image').length;
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
        size: file.size,
        kind: 'image' as const,
        status: 'ready' as const,
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

  const handleSelectedFiles = async (files: File[]) => {
    if (!files.length) {
      return;
    }

    const imageFiles = files.filter(file => file.type.startsWith('image/'));
    const documentFiles = files.filter(file => !file.type.startsWith('image/') && isDocumentFile(file));

    const unsupportedFiles = files.filter(
      file => !imageFiles.includes(file) && !documentFiles.includes(file),
    );

    if (unsupportedFiles.length > 0) {
      alert(`Некоторые файлы не были добавлены из-за неподдерживаемого формата: ${unsupportedFiles.map(file => file.name).join(', ')}`);
    }

    if (documentFiles.length > 1) {
      alert('За один раз можно загрузить только один документ. Добавлен первый документ из выбранных.');
    }

    if (documentFiles.length > 0) {
      await handlePendingDocuments(documentFiles.slice(0, 1));
    }

    if (imageFiles.length > 0) {
      await handlePendingImages(imageFiles);
    }
  };

  const { fileInputRef, handleImageUpload: handleAttachmentUpload, triggerFileInput } = useImageUpload({
    onFilesSelected: handleSelectedFiles,
  });

  const { audioRef, sendAudioRef } = useAudioPlayer({ musicMuted });

  const getCurrentThreadSettings = (): ThreadSettings => {
    return threadSettings[threadId] || {
      openRouterApiKey: '',
      openRouterModel: 'openai/gpt-4o-mini',
      historyMessageCount: 5,

      // Chat provider selection (default OpenRouter)
      chatProvider: 'openrouter',

      // AgentRouter defaults
      agentRouterBaseUrl: '',
      agentRouterApiKey: '',
      agentRouterModel: 'openai/gpt-4o-mini',
    };
  };

  const updateCurrentThreadSettings = (updates: Partial<ThreadSettings>) => {
    setThreadSettings((prev: ThreadSettingsMap) => ({ ...prev, [threadId]: { ...getCurrentThreadSettings(), ...updates } }));
  };

  useEffect(() => {
    localStorage.setItem('roo_agent_thread_settings', JSON.stringify(threadSettings));
  }, [threadSettings]);

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        setVoiceAssistantEnabled(false);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  useEffect(() => {
    ensureCsrfToken();
    getImageSessionId();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, threadId]);

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
    const attachmentsToSend = [...pendingAttachments];
    const documentAttachments = attachmentsToSend.filter(attachment => attachment.kind === 'document');
    const imageAttachments = attachmentsToSend.filter(attachment => attachment.kind === 'image');
    const hasDocuments = documentAttachments.length > 0;
    const hasImages = imageAttachments.length > 0;

    if (!trimmed && !hasImages && !hasDocuments) {
      return;
    }

    if (hasDocuments && hasImages) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Нельзя отправлять документы вместе с изображениями. Удалите лишние вложения и попробуйте снова.',
        threadId,
      });
      return;
    }

    if (hasDocuments && documentAttachments.some(attachment => attachment.status === 'loading')) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Документ ещё подготавливается. Подождите пару секунд.',
        threadId,
      });
      return;
    }

    if (documentAttachments.some(attachment => attachment.status === 'processing')) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Обработка документа уже выполняется. Дождитесь результата.',
        threadId,
      });
      return;
    }

    if (hasDocuments && !trimmed) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Чтобы проанализировать документ, задайте вопрос или инструкцию в поле ввода.',
        threadId,
      });
      return;
    }

    const isCommand = !!trimmed && COMMON_COMMANDS.includes(trimmed);
    if (isCommand && (hasImages || hasDocuments)) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Команды нельзя отправлять вместе с файлами. Отправьте команду отдельно.',
        threadId,
      });
      return;
    }

    const currentSettings = getCurrentThreadSettings();
    const provider = currentSettings.chatProvider ?? 'openrouter';
    const _userApiKey = provider === 'agentrouter' ? (currentSettings.agentRouterApiKey ?? '') : currentSettings.openRouterApiKey;
    const _selectedModel = provider === 'agentrouter' ? (currentSettings.agentRouterModel ?? '') : currentSettings.openRouterModel;
    void [_userApiKey, _selectedModel];
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

    const shouldSendText = !!trimmed && (trimmed !== '/help') && !hasImages && !hasDocuments;

    if (!shouldSendText && !hasImages && !hasDocuments) {
      return;
    }

    setIsTyping(true);
    setIsAwaitingImageDescription(hasImages);

    let uploadImagesSucceeded = false;
    let documentProcessed = false;

    try {
      if (shouldSendText) {
        const payload: Parameters<typeof callAgent>[0] = {
          message: trimmed,
          thread_id: threadId,
          user_id: agentUserId,
          history: historyMessages,
        };

        if (provider === 'agentrouter') {
          payload.providerType = 'agentrouter';
          payload.agentRouterApiKey = currentSettings.agentRouterApiKey;
          payload.agentRouterModel = currentSettings.agentRouterModel;
          payload.agentRouterBaseUrl = currentSettings.agentRouterBaseUrl;
        } else {
          payload.providerType = 'openrouter';
          payload.openRouterApiKey = currentSettings.openRouterApiKey;
          payload.openRouterModel = currentSettings.openRouterModel;
        }
        try {
          const response = await callAgent(payload);
          const targetThreadId = response.thread_id ?? threadId;
          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: response.response ?? '...',
            threadId: targetThreadId,
          });
          if (response.attachments?.length) {
            response.attachments.forEach((attachment) => {
              const label = attachment.description
                ? attachment.description
                : attachment.filename;
              persistMessage({
                type: 'bot',
                contentType: 'attachment',
                content: label,
                threadId: targetThreadId,
                fileName: attachment.filename,
                url: attachment.url,
                mimeType: attachment.contentType,
                size: attachment.size,
                description: attachment.description ?? null,
              });
            });
          }
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
        const validationMessage = validateImageProviderSettings(provider, currentSettings);
        if (validationMessage) {
          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: validationMessage,
            threadId,
          });
          return;
        }

        const systemPrompt = localStorage.getItem('systemPrompt');
        try {
          const response = await uploadImagesForAnalysis({
            files: imageAttachments.map(attachment => attachment.file),
            threadId,
            history: historyMessages,
            settings: currentSettings,
            systemPrompt,
            prompt: trimmed,
            provider,
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
          uploadImagesSucceeded = true;
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

      if (hasDocuments) {
        setPendingAttachments(prev => prev.map(item => (item.kind === 'document' ? { ...item, status: 'processing' } : item)));
        const systemPrompt = localStorage.getItem('systemPrompt');
        try {
          const response = await analyzeDocument({
            file: documentAttachments[0].file,
            threadId,
            history: historyMessages,
            settings: currentSettings,
            systemPrompt,
            query: trimmed,
            provider,
          });

          const targetThreadId = response.thread_id ?? threadId;

          documentAttachments.forEach(attachment => {
            if (!attachment.persisted) {
              persistMessage({
                type: 'user',
                contentType: 'document',
                content: `Документ: ${attachment.name}`,
                threadId: targetThreadId,
                fileName: attachment.name,
                mimeType: attachment.mimeType,
              });
            }
          });

          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: response.response ?? 'Документ обработан.',
            threadId: targetThreadId,
          });

          documentProcessed = true;
        } catch (error) {
          console.error('Document analysis error:', error);
          persistMessage({
            type: 'bot',
            contentType: 'text',
            content: `Ошибка обработки документа: ${(error as Error).message}`,
            threadId,
          });
        }
      }
    } finally {
      setIsTyping(false);
      setIsAwaitingImageDescription(false);
      if (uploadImagesSucceeded) {
        setPendingAttachments(prev => prev.filter(attachment => attachment.kind !== 'image'));
      }
      if (hasDocuments) {
        setPendingAttachments(prev => prev.map(attachment => {
          if (attachment.kind !== 'document') {
            return attachment;
          }
          return {
            ...attachment,
            status: 'ready',
            persisted: documentProcessed ? true : attachment.persisted,
          };
        }));
      }
    }
  };

  const sortedThreads = useMemo(() => {
    const list = [...threads];
    return threadSortOrder === 'newest-first' ? list.reverse() : list;
  }, [threads, threadSortOrder]);

  const messagesToRender = useMemo(() => messages.filter(msg => msg.threadId === threadId), [messages, threadId]);

  useEffect(() => {
    if (location.pathname === '/' || isImagesRoute || isMcpRoute) {
      return;
    }
    navigate('/', { replace: true });
  }, [location.pathname, isImagesRoute, isMcpRoute, navigate]);

  return (
    <>
      <div className="app-root">
        <div className={`app-shell${isImagesRoute || isMcpRoute ? ' image-page-shell' : ''}`}>
          {isImagesRoute ? (
            <>
              <div className="image-page-header">
                <button
                  type="button"
                  className="image-back-button"
                  onClick={() => navigate('/')}
                  data-testid="back-to-chat"
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
              <div className="page-content">
                <ImageGenerationPanel
                  onRequireKeySetup={() => setIsSettingsOpen(true)}
                  refreshKeySignal={keyRefreshToken}
                />
              </div>
              <Footer
                openSettings={() => setIsSettingsOpen(true)}
                voiceAssistantEnabled={voiceAssistantEnabled}
                toggleVoiceAssistant={() => setVoiceAssistantEnabled((prev) => !prev)}
              />
            </>
          ) : isMcpRoute ? (
            <>
              <div className="image-page-header">
                <button
                  type="button"
                  className="image-back-button"
                  onClick={() => navigate('/')}
                  data-testid="back-to-chat"
                >
                  ← В чат
                </button>
              </div>
              <div className="page-content">
                <McpPanel />
              </div>
              <Footer
                openSettings={() => setIsSettingsOpen(true)}
                voiceAssistantEnabled={voiceAssistantEnabled}
                toggleVoiceAssistant={() => setVoiceAssistantEnabled((prev) => !prev)}
              />
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
                onNavigateToMcp={() => navigate('/mcp')}
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
                  voiceAssistantEnabled={voiceAssistantEnabled}
                  toggleVoiceAssistant={() => setVoiceAssistantEnabled((prev) => !prev)}
                />
                <ChatPanel
                  messages={messagesToRender}
                  isTyping={isTyping}
                  input={input}
                  isRecording={isRecording}
                  audioEnabled={audioEnabled}
                  handleInputChange={(e) => setInput(e.target.value)}
                  handleVoiceInput={toggleRecognition}
                  handleFileUpload={handleAttachmentUpload}
                  handleSubmit={handleSubmit}
                  handleCommandClick={(cmd) => setInput(cmd)}
                  messagesEndRef={messagesEndRef}
                  fileInputRef={fileInputRef}
                  triggerFileInput={triggerFileInput}
                  COMMON_COMMANDS={COMMON_COMMANDS}
                  pendingAttachments={pendingAttachments}
                  removeAttachment={handleRemoveAttachment}
                />
              </div>
              <Footer
                openSettings={() => setIsSettingsOpen(true)}
                voiceAssistantEnabled={voiceAssistantEnabled}
                toggleVoiceAssistant={() => setVoiceAssistantEnabled((prev) => !prev)}
              />
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
