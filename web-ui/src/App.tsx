import React, { useEffect, useMemo, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import './App.css';

import type { ChatMessage, ThreadSettings, ThreadSettingsMap } from './types/chat';
import { callOpenRouter, callAgent } from './utils/api';
import { COMMON_COMMANDS } from './constants/chat';
import { useChatState } from './hooks/useChatState';
import { useSpeechRecognition } from './hooks/useSpeechRecognition';
import { useImageUpload } from './hooks/useImageUpload';
import { useAudioPlayer } from './hooks/useAudioPlayer';

import Header from './components/Header';
import ThreadsPanel from './components/ThreadsPanel';
import ChatPanel from './components/ChatPanel';
import Footer from './components/Footer';
import SettingsPanel from './components/SettingsPanel';

const App = () => {
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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const userName = useMemo(() => import.meta.env.VITE_USER_NAME ?? 'Оператор', []);
  const agentUserId = useMemo(() => import.meta.env.VITE_TELEGRAM_USER_ID ?? 'local-user', []);

  const { isRecording, toggleRecognition } = useSpeechRecognition({
    onResult: (transcript) => setInput(prev => prev + ' ' + transcript),
    onError: (error) => console.error('Speech recognition error:', error),
  });

  const { fileInputRef, handleImageUpload, triggerFileInput } = useImageUpload({
    onImageUpload: (dataUrl: string) => {
      persistMessage({
        type: 'user',
        contentType: 'image',
        content: dataUrl,
        threadId,
      });
      describeImage(dataUrl);
    },
  });

  const { audioRef, sendAudioRef } = useAudioPlayer({ musicMuted });

  const getCurrentThreadSettings = (): ThreadSettings => {
    return threadSettings[threadId] || { openRouterEnabled: false, openRouterApiKey: '', openRouterModel: 'openai/gpt-4o-mini', historyMessageCount: 5 };
  };

  const updateCurrentThreadSettings = (updates: Partial<ThreadSettings>) => {
    setThreadSettings((prev: ThreadSettingsMap) => ({ ...prev, [threadId]: { ...getCurrentThreadSettings(), ...updates } }));
  };

  const describeImage = async (imageDataUrl: string) => {
    setIsTyping(true);
    setIsAwaitingImageDescription(true);
    const currentSettings = getCurrentThreadSettings();
    if (!currentSettings.openRouterEnabled || !currentSettings.openRouterApiKey) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Для анализа изображений включите OpenRouter в настройках этого треда.',
        threadId,
      });
      setIsTyping(false);
      setIsAwaitingImageDescription(false);
      return;
    }

    const historyMessages = messages.filter(msg => msg.threadId === threadId);

    const imageMessage: ChatMessage = {
      id: uuidv4(),
      threadId,
      createdAt: new Date().toISOString(),
      type: 'user',
      content: imageDataUrl,
      contentType: 'image',
    };

    const payload = {
      message: 'Опиши это изображение подробно, извлеки весь текст если есть.',
      thread_id: threadId,
      history: [...historyMessages, imageMessage],
      useTools: false,
    };

    try {
      const response = await callOpenRouter(payload, { openRouterApiKey: currentSettings.openRouterApiKey, openRouterModel: currentSettings.openRouterModel }, currentSettings);
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: response.response ?? 'Не удалось получить описание изображения.',
        threadId: response.thread_id ?? threadId,
      });
    } catch (error) {
      console.error('Image description error:', error);
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: `Ошибка при анализе изображения: ${(error as Error).message}`,
        threadId,
      });
    } finally {
      setIsTyping(false);
      setIsAwaitingImageDescription(false);
    }
  };

  useEffect(() => {
    localStorage.setItem('roo_agent_thread_settings', JSON.stringify(threadSettings));
  }, [threadSettings]);

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
    const trimmed = input.trim();
    if (!trimmed) return;

    persistMessage({ type: 'user', contentType: 'text', content: trimmed, threadId });
    setInput('');
    setIsTyping(true);

    const currentSettings = getCurrentThreadSettings();
    const userApiKey = currentSettings.openRouterApiKey;
    const selectedModel = currentSettings.openRouterModel;
    const payload = {
      message: trimmed,
      thread_id: threadId,
      user_id: agentUserId,
      history: messages.filter(m => m.threadId === threadId),
      openRouterApiKey: userApiKey,
      openRouterModel: selectedModel,
    };

    if (isAwaitingImageDescription) {
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: 'Пожалуйста, дождитесь завершения анализа изображения.',
        threadId,
      });
      setIsTyping(false);
      return;
    }

    if (COMMON_COMMANDS.includes(trimmed)) {
      if (trimmed === '/help') {
        persistMessage({
          type: 'bot',
          contentType: 'text',
          content: `Igorek - ваш ИИ-ассистент для выполнения задач\n\n**Функции веб-интерфейса:**\n- **Чат**: Отправляйте текстовые сообщения боту через поле ввода или голосовой ввод (кнопка микрофона).\n- **Темы**: Создавайте новые темы чатов кнопкой "Новый тред" для организации разговоров.\n- **Команды**: Используйте /help для этого сообщения.\n- **TTS**: Включите/выключите озвучивание ответов бота кнопкой "TTS включен/выключен".\n- **Голосовой ввод**: Кнопка микрофона для голосового ввода сообщений.\n- **Очистка состояния**: Кнопка с иконкой питания очищает локальное хранилище и перезагружает интерфейс.\n- **Подписка**: Кнопка "Подпишись на нас" ведет на Telegram канал.\n- **История**: Сообщения сохраняются в браузере, можно переключаться между темами.\n\nВведите команду или запрос для взаимодействия.`,
          threadId,
        });
        setInput('');
        setIsTyping(false);
        return;
      }
    }

    try {
      const response = await callAgent(payload);
      persistMessage({ type: 'bot', contentType: 'text', content: response.response ?? '...', threadId: response.thread_id ?? threadId });
    } catch (error) {
      persistMessage({ type: 'bot', contentType: 'text', content: `Ошибка: ${(error as Error).message}`, threadId });
    } finally {
      setIsTyping(false);
    }
  };

  const sortedThreads = useMemo(() => {
    const list = [...threads];
    return threadSortOrder === 'newest-first' ? list.reverse() : list;
  }, [threads, threadSortOrder]);

  const messagesToRender = useMemo(() => messages.filter(msg => msg.threadId === threadId), [messages, threadId]);

  return (
    <div className="app-root">
      <div className="app-shell">
        <div className="disclaimer-banner">Игорёк очень любит галлюцинации 🤪, будьте осторожны!!! Проверяйте важную информацию!</div>
        <Header 
          userName={userName}
          toggleMusicMute={() => setMusicMuted(!musicMuted)}
          musicMuted={musicMuted}
          audioEnabled={audioEnabled}
          setAudioEnabled={setAudioEnabled}
          setIsMenuOpen={setIsMenuOpen}
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
            toggleThreadSortOrder={() => setThreadSortOrder(p => p === 'newest-first' ? 'oldest-first' : 'newest-first')}
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
          />
        </div>
        <Footer openSettings={() => setIsSettingsOpen(true)} />
      </div>
      <SettingsPanel 
        isSettingsOpen={isSettingsOpen}
        closeSettings={() => setIsSettingsOpen(false)}
        threadSettings={threadSettings}
        updateCurrentThreadSettings={updateCurrentThreadSettings}
        threadNames={threadNames}
        threadId={threadId}
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
    </div>
  );
};

export default App;
