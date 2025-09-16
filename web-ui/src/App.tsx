import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Command, Hammer, Mic, Power, Send, Terminal, Volume2, VolumeX, Copy, Check } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import MatrixRain from './MatrixRain';
import './App.css';

type MessageAuthor = 'user' | 'bot';
type MessageContentType = 'text' | 'image';

interface ChatMessage {
  id: string;
  type: MessageAuthor;
  contentType: MessageContentType;
  content: string;
  threadId: string;
  createdAt: string;
}

interface ThreadNameMap {
  [threadId: string]: string;
}

interface ChatResponse {
  status: string;
  response: string;
  thread_id?: string;
}

const INITIAL_GREETING = `SYSTEM INITIALIZED...
Welcome to Roo Control Terminal
Ready for input...`;

const COMMON_COMMANDS = ['/help'];

const buildApiUrl = (path: string): string => {
  const base = import.meta.env.VITE_AGENT_API_BASE ?? 'http://localhost:8018';
  return `${base.replace(/\/$/, '')}${path}`;
};

function ElevenLabsConvaiWidget() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://elevenlabs.io/convai-widget/index.js';
    script.async = true;
    script.type = 'text/javascript';
    document.body.appendChild(script);

    const widgetElement = document.createElement('elevenlabs-convai');
    widgetElement.setAttribute('agent-id', 'Yfxp2vAkqHQT469GVM4p');

    const container = containerRef.current;
    container?.appendChild(widgetElement);

    return () => {
      if (container?.contains(widgetElement)) {
        container.removeChild(widgetElement);
      }
      document.body.removeChild(script);
    };
  }, []);

  return <div className="convai-widget" ref={containerRef} />;
}

const App = () => {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const stored = localStorage.getItem('roo_agent_messages');
    if (stored) {
      try {
        return JSON.parse(stored) as ChatMessage[];
      } catch (error) {
        console.warn('Failed to parse stored messages', error);
      }
    }
    return [
      {
        id: uuidv4(),
        type: 'bot',
        contentType: 'text',
        content: INITIAL_GREETING,
        threadId: 'default',
        createdAt: new Date().toISOString(),
      },
    ];
  });

  const [threadId, setThreadId] = useState(() => {
    const stored = localStorage.getItem('roo_agent_thread');
    return stored ?? 'default';
  });

  const [threads, setThreads] = useState<string[]>(() => {
    const stored = localStorage.getItem('roo_agent_threads');
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as string[];
        return parsed.length > 0 ? parsed : ['default'];
      } catch {
        return ['default'];
      }
    }
    return ['default'];
  });

  const [threadNames, setThreadNames] = useState<ThreadNameMap>(() => {
    const stored = localStorage.getItem('roo_agent_thread_names');
    return stored ? (JSON.parse(stored) as ThreadNameMap) : { default: 'Главный тред' };
  });

  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isAwaitingImageDescription, setIsAwaitingImageDescription] = useState(false);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [copiedCodeBlockId, setCopiedCodeBlockId] = useState<string | null>(null);
  const [musicMuted, setMusicMuted] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const sendAudioRef = useRef<HTMLAudioElement>(null);
  const userName = useMemo(() => import.meta.env.VITE_USER_NAME ?? 'Оператор', []);

  const agentUserId = useMemo(() => import.meta.env.VITE_TELEGRAM_USER_ID ?? 'local-user', []);

  // Speech Recognition setup
  const recognition = useMemo(() => {
    if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
      const rec = new ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)();
      rec.lang = 'ru-RU';
      rec.continuous = false;
      rec.interimResults = false;
      rec.onstart = () => setIsRecording(true);
      rec.onend = () => setIsRecording(false);
      rec.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setInput(prev => prev + ' ' + transcript);
      };
      rec.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error);
        setIsRecording(false);
      };
      return rec;
    }
    return null;
  }, []);

  const handleVoiceInput = () => {
    if (!recognition) {
      alert('Speech Recognition не поддерживается в этом браузере.');
      return;
    }
    if (isRecording) {
      recognition.stop();
    } else {
      recognition.start();
    }
  };

  useEffect(() => {
    localStorage.setItem('roo_agent_messages', JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    localStorage.setItem('roo_agent_thread', threadId);
  }, [threadId]);

  useEffect(() => {
    localStorage.setItem('roo_agent_threads', JSON.stringify(threads));
  }, [threads]);

  useEffect(() => {
    localStorage.setItem('roo_agent_thread_names', JSON.stringify(threadNames));
  }, [threadNames]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, threadId]);

  // Auto-play background music on page load and restart on any button interaction
  useEffect(() => {
    const playAudio = async () => {
      if (audioRef.current && !musicMuted) {
        try {
          audioRef.current.currentTime = 0; // Reset to beginning
          audioRef.current.volume = 0.3; // Set initial volume to 30%
          await audioRef.current.play();
        } catch (error) {
          console.log('Audio playback failed:', error);
        }
      }
    };

    // Small delay to ensure DOM is ready
    const timer = setTimeout(playAudio, 100);

    // Add handler for button clicks to restart music
    const handleButtonClick = (event: Event) => {
      const target = event.target as HTMLElement;
      if (target?.tagName === 'BUTTON' && !musicMuted) {
        const buttonText = target.textContent?.trim() || '';

        // Check if it's the send button or contains "Отправить"
        if (buttonText.includes('Отправить') || target.classList.contains('send-button')) {
          // Play send sound for input/send interactions
          if (sendAudioRef.current) {
            sendAudioRef.current.currentTime = 0;
            sendAudioRef.current.volume = 0.5;
            sendAudioRef.current.play().catch(error => {
              console.log('Failed to play send sound:', error);
            });
          }
        } else {
          // Play abrupt sound for all other button interactions
          playAudio();
        }
      }
    };

    // Add global click handler to enable audio on user interaction (for initial play)
    const enableAudio = async () => {
      if (audioRef.current && audioRef.current.paused) {
        try {
          audioRef.current.volume = 0.3;
          await audioRef.current.play();
          // Remove the initial enable listeners after successful play
          document.removeEventListener('click', enableAudio);
          document.removeEventListener('keydown', enableAudio);
        } catch (error) {
          console.log('Failed to enable audio on interaction:', error);
        }
      }
    };

    // Handle input field interactions
    const handleInputInteraction = (event: Event) => {
      const target = event.target as HTMLElement;
      if ((target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA') && !musicMuted) {
        if (sendAudioRef.current) {
          sendAudioRef.current.currentTime = 0;
          sendAudioRef.current.volume = 0.3;
          sendAudioRef.current.play().catch(error => {
            console.log('Failed to play input sound:', error);
          });
        }
      }
    };

    document.addEventListener('click', handleButtonClick);
    document.addEventListener('focus', handleInputInteraction);
    document.addEventListener('input', handleInputInteraction);
    document.addEventListener('click', enableAudio);
    document.addEventListener('keydown', enableAudio);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('click', handleButtonClick);
      document.removeEventListener('focus', handleInputInteraction);
      document.removeEventListener('input', handleInputInteraction);
      document.removeEventListener('click', enableAudio);
      document.removeEventListener('keydown', enableAudio);
    };
  }, [musicMuted]);

  const handleNewThread = () => {
    const newThreadId = uuidv4();
    const name = prompt('Введите название нового треда:')?.trim();
    setThreads((prev) => [...prev, newThreadId]);
    setThreadNames((prev) => ({
      ...prev,
      [newThreadId]: name && name.length > 0 ? name : `Тред ${prev ? Object.keys(prev).length + 1 : 1}`,
    }));
    setThreadId(newThreadId);
  };

  const handleDeleteThread = (target: string) => {
    if (target === 'default') {
      alert('Нельзя удалить основной тред');
      return;
    }
    const confirmed = window.confirm('Вы уверены, что хотите удалить выбранный тред?');
    if (!confirmed) {
      return;
    }
    setThreads((prev) => prev.filter((id) => id !== target));
    setThreadNames((prev) => {
      const updated = { ...prev };
      delete updated[target];
      return updated;
    });
    setMessages((prev) => prev.filter((msg) => msg.threadId !== target));
    if (threadId === target) {
      setThreadId('default');
    }
  };

  const speak = async (text: string) => {
    if (!audioEnabled) {
      return;
    }
    try {
      const response = await fetch('http://127.0.0.1:5001/tts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      });

      if (!response.ok) {
        throw new Error(`HTTP status ${response.status}`);
      }

      const blob = await response.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      await audio.play();
    } catch (error) {
      console.error('TTS error', error);
    }
  };

  const copyToClipboard = async (text: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000); // Reset after 2 seconds
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  const copyCodeToClipboard = async (code: string, codeBlockId: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCodeBlockId(codeBlockId);
      setTimeout(() => setCopiedCodeBlockId(null), 2000); // Reset after 2 seconds
    } catch (error) {
      console.error('Failed to copy code:', error);
    }
  };

  const toggleMusicMute = () => {
    if (audioRef.current) {
      if (musicMuted) {
        audioRef.current.volume = 0.3; // Restore volume
        setMusicMuted(false);
      } else {
        audioRef.current.volume = 0; // Mute
        setMusicMuted(true);
      }
    }
  };


  // Custom component for code blocks with syntax highlighting and copy functionality
  const CodeBlock = ({ node, inline, className, children, ...props }: any) => {
    const match = /language-(\w+)/.exec(className || '');
    const language = match ? match[1] : '';
    const code = String(children).replace(/\n$/, '');
    const codeBlockId = useMemo(() => `code-${Math.random().toString(36).substr(2, 9)}`, []);

    if (!inline && language) {
      return (
        <div className="code-block-container">
          <div className="code-block-header">
            <span className="code-language">{language}</span>
            <button
              className={`code-copy-button ${copiedCodeBlockId === codeBlockId ? 'copied' : ''}`}
              onClick={() => copyCodeToClipboard(code, codeBlockId)}
              type="button"
              title="Копировать код"
            >
              {copiedCodeBlockId === codeBlockId ? <Check className="icon" /> : <Copy className="icon" />}
            </button>
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

    // For inline code or code without language specification
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  };

  const persistMessage = (message: Omit<ChatMessage, 'id' | 'createdAt'>) => {
    setMessages((prev) => [
      ...prev,
      {
        ...message,
        id: uuidv4(),
        createdAt: new Date().toISOString(),
      },
    ]);
  };

  const callAgent = async (payload: { message: string; thread_id?: string; history?: any[] }) => {
    const response = await fetch(buildApiUrl('/chat'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: payload.message,
        thread_id: payload.thread_id,
        user_id: agentUserId,
        history: payload.history,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Agent API error: ${response.status} ${errorText}`);
    }

    const data = (await response.json()) as ChatResponse;
    return data;
  };

  const sendMessage = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }

    persistMessage({
      type: 'user',
      contentType: 'text',
      content: trimmed,
      threadId,
    });

    setIsTyping(true);

    const payload = {
      message: trimmed,
      thread_id: threadId,
      user_id: agentUserId,
    };

    try {
      // Подготовить историю для отправки
      const historyMessages = messages.filter(msg => msg.threadId === threadId && (msg.type === 'user' || msg.type === 'bot'));
      const payloadWithHistory = {
        ...payload,
        history: historyMessages.map(msg => ({
          type: msg.type,
          content: msg.content
        }))
      };
      const response = await callAgent(payloadWithHistory);
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: response.response ?? 'Бот ничего не ответил.',
        threadId: response.thread_id ?? threadId,
      });
    } catch (error) {
      console.error(error);
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: `Не удалось отправить сообщение: ${(error as Error).message}`,
        threadId,
      });
    } finally {
      setIsTyping(false);
    }
  };

  const handleCommandClick = (command: string) => {
    setInput(command);
  };

  const isCommonCommand = (text: string) => COMMON_COMMANDS.some((command) => text.startsWith(command));

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) {
      return;
    }


    persistMessage({
      type: 'user',
      contentType: 'text',
      content: trimmed,
      threadId,
    });

    setInput('');
    setIsTyping(true);

    const payload = {
      message: trimmed,
      thread_id: threadId,
      user_id: agentUserId,
    };

    if (isAwaitingImageDescription) {
      try {
        // Подготовить историю для отправки
        const historyMessages = messages.filter(msg => msg.threadId === threadId && msg.type === 'user' || msg.type === 'bot');
        const payloadWithHistory = {
          ...payload,
          history: historyMessages.map(msg => ({
            type: msg.type,
            content: msg.content
          }))
        };
        const response = await callAgent(payloadWithHistory);
        persistMessage({
          type: 'bot',
          contentType: 'text',
          content: response.response ?? 'Бот ничего не ответил.',
          threadId: response.thread_id ?? threadId,
        });
      } catch (error) {
        persistMessage({
          type: 'bot',
          contentType: 'text',
          content: `Ошибка при отправке описания изображения: ${(error as Error).message}`,
          threadId,
        });
      } finally {
        setIsAwaitingImageDescription(false);
        setIsTyping(false);
      }
      return;
    }

    if (isCommonCommand(trimmed)) {
      if (trimmed === '/help') {
        persistMessage({
          type: 'bot',
          contentType: 'text',
          content: `Igorek - ваш ИИ-ассистент для выполнения задач 

**Функции веб-интерфейса:**
- **Чат**: Отправляйте текстовые сообщения боту через поле ввода или голосовой ввод (кнопка микрофона).
- **Темы**: Создавайте новые темы чатов кнопкой "Новый тред" для организации разговоров.
- **Команды**: Используйте /help для этого сообщения.
- **Reboot мозг**: Кнопка с молотком отправляет запрос на получение краткого резюме заметки "USER.MD" для напоминания модели о пользователе.
- **TTS**: Включите/выключите озвучивание ответов бота кнопкой "TTS включен/выключен".
- **Голосовой ввод**: Кнопка микрофона для голосового ввода сообщений.
- **Очистка состояния**: Кнопка с иконкой питания очищает локальное хранилище и перезагружает интерфейс.
- **Подписка**: Кнопка "Подпишись на нас" ведет на Telegram канал.
- **История**: Сообщения сохраняются в браузере, можно переключаться между темами.

Введите команду или запрос для взаимодействия.`,
          threadId,
        });
        setInput('');
        setIsTyping(false);
        return;
      }

      try {
        // Подготовить историю для отправки
        const historyMessages = messages.filter(msg => msg.threadId === threadId && msg.type === 'user' || msg.type === 'bot');
        const payloadWithHistory = {
          ...payload,
          history: historyMessages.map(msg => ({
            type: msg.type,
            content: msg.content
          }))
        };
        const response = await callAgent(payloadWithHistory);
        persistMessage({
          type: 'bot',
          contentType: 'text',
          content: response.response ?? 'Бот ничего не ответил.',
          threadId: response.thread_id ?? threadId,
        });
      } catch (error) {
        persistMessage({
          type: 'bot',
          contentType: 'text',
          content: `Ошибка при выполнении команды: ${(error as Error).message}`,
          threadId,
        });
      } finally {
        setIsTyping(false);
      }
      return;
    }

    try {
      // Подготовить историю для отправки
      const historyMessages = messages.filter(msg => msg.threadId === threadId && msg.type === 'user' || msg.type === 'bot');
      const payloadWithHistory = {
        ...payload,
        history: historyMessages.map(msg => ({
          type: msg.type,
          content: msg.content
        }))
      };
      const response = await callAgent(payloadWithHistory);
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: response.response ?? 'Бот ничего не ответил.',
        threadId: response.thread_id ?? threadId,
      });
    } catch (error) {
      console.error(error);
      persistMessage({
        type: 'bot',
        contentType: 'text',
        content: `Не удалось отправить сообщение: ${(error as Error).message}`,
        threadId,
      });
    } finally {
      setIsTyping(false);
    }
  };

  const messagesToRender = useMemo(
    () => messages.filter((msg) => msg.threadId === threadId),
    [messages, threadId],
  );

  return (
    <div className="app-root">
      <MatrixRain />
      <div className="app-shell">
        <header className="app-header">
          <div className="app-header__identity">
            <Terminal className="icon" />
            <div>
              <div className="app-title">Roo Control Terminal</div>
              <div className="app-subtitle">Режим: оперативный | Пользователь: {userName}</div>
            </div>
          </div>
          <div className="app-header__actions">
            <button
              className="power-button"
              type="button"
              onClick={() => {
                const confirmed = window.confirm('Очистить локальное хранилище и перезагрузить интерфейс?');
                if (confirmed) {
                  localStorage.removeItem('roo_agent_messages');
                  localStorage.removeItem('roo_agent_threads');
                  localStorage.removeItem('roo_agent_thread');
                  localStorage.removeItem('roo_agent_thread_names');
                  window.location.reload();
                }
              }}
              title="Очистить состояние"
            >
              <Power className="icon" />
            </button>
            <button
              className="music-button"
              type="button"
              onClick={toggleMusicMute}
              title={musicMuted ? 'Включить звук' : 'Выключить звук'}
            >
              {musicMuted ? <VolumeX className="icon" /> : <Volume2 className="icon" />}
            </button>
          </div>
        </header>

        <div className="telegram-banner">
          <button
            type="button"
            className="telegram-button"
            onClick={() => window.open('https://t.me/ezoneenews', '_blank')}
          >
            Подпишись на нас
          </button>
        </div>

        <div className="grid">
          <aside className="threads-panel">
            <div className="panel-title">Темы</div>
            <ul className="threads-list">
              {threads.map((id) => (
                <li key={id} className={id === threadId ? 'active' : ''}>
                  <button type="button" onClick={() => setThreadId(id)} className="thread-button">
                    {threadNames[id] ?? 'Без названия'}
                  </button>
                  {id !== 'default' && (
                    <button
                      className="thread-delete"
                      type="button"
                      onClick={() => handleDeleteThread(id)}
                      title="Удалить тред"
                    >
                      ✖
                    </button>
                  )}
                </li>
              ))}
            </ul>
            <div className="threads-actions">
              <button type="button" onClick={handleNewThread} className="command-button">
                <Command className="icon" />
                Новый тред
              </button>
              <button
                type="button"
                className={`command-button ${audioEnabled ? 'enabled' : 'disabled'}`}
                onClick={() => setAudioEnabled((prev) => !prev)}
              >
                <Volume2 className="icon" />
                {audioEnabled ? 'TTS включен' : 'TTS выключен'}
              </button>
            </div>
            <ElevenLabsConvaiWidget />
          </aside>

          <main className="chat-panel">
            <div className="chat-window">
              {messagesToRender.map((msg) => (
                <div key={msg.id} className={`chat-message chat-message--${msg.type}`}>
                  <span className="chat-prefix">{msg.type === 'user' ? '>' : '$'}</span>
                  {msg.contentType === 'text' ? (
                    <div className="chat-content">
                      <ReactMarkdown
                        components={{
                          a: ({ node, ...props }) => (
                            <a {...props} target="_blank" rel="noopener noreferrer" />
                          ),
                          p: ({ children }) => <span className="chat-text">{children}</span>,
                          code: CodeBlock,
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <img src={`data:image/png;base64,${msg.content}`} alt="Generated" className="chat-image" />
                  )}
                  <div className="message-actions">
                    <button
                      className={`copy-button ${copiedMessageId === msg.id ? 'copied' : ''}`}
                      type="button"
                      onClick={() => copyToClipboard(msg.content, msg.id)}
                      title="Копировать сообщение"
                    >
                      {copiedMessageId === msg.id ? <Check className="icon" /> : <Copy className="icon" />}
                    </button>
                    {msg.type === 'bot' && msg.contentType === 'text' && (
                      <button className="tts-button" type="button" onClick={() => speak(msg.content)}>
                        🔊
                      </button>
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
              <input
                type="text"
                className="chat-input"
                placeholder="Введите команду или запрос..."
                value={input}
                onChange={(event) => setInput(event.target.value)}
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
              <button type="submit" className="send-button" disabled={isTyping}>
                <Send className="icon" />
                Отправить
              </button>
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
              <button
                type="button"
                className="command-button"
                onClick={() => sendMessage('Выполни fetch для заметки "USER.MD" и верни краткое резюме содержимого')}
                disabled={isTyping}
              >
                <Hammer className="icon" />
                Reboot мозг
              </button>
            </div>
          </main>
        </div>

        <footer className="app-footer">
          <div>
            Code by <span className="accent">Igorek</span> / <span className="accent">Roo</span>
          </div>
          <div>
            Produced by <span className="accent">end0</span>
          </div>
        </footer>

        {/* Background music - plays once on page load */}
        <audio
          ref={audioRef}
          src="/abrupt-stop-and-disk-failure.mp3"
          preload="auto"
          loop={false}
          style={{ display: 'none' }}
        />

        {/* Send button and input sound effect */}
        <audio
          ref={sendAudioRef}
          src="/sound12.mp3"
          preload="auto"
          style={{ display: 'none' }}
        />

      </div>
    </div>
  );
};

export default App;
