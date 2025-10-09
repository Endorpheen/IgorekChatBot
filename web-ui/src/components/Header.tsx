import React from 'react';
import { Terminal, Power, VolumeX, Volume2, MessageSquareText, MessageSquareOff, Menu } from 'lucide-react';
import { clearMessages } from '../storage/messagesStorage';

interface HeaderProps {
  userName: string;
  toggleMusicMute: () => void;
  musicMuted: boolean;
  audioEnabled: boolean;
  setAudioEnabled: (enabled: boolean) => void;
  setIsMenuOpen: (isOpen: boolean) => void;
}

const Header: React.FC<HeaderProps> = ({
  userName,
  toggleMusicMute,
  musicMuted,
  audioEnabled,
  setAudioEnabled,
  setIsMenuOpen,
}) => {
  return (
    <header className="app-header">
      <div className="app-header__identity">
        <Terminal className="icon" />
        <div>
          <div className="app-title">Igorek Control Terminal</div>
          <div className="app-subtitle">Режим: оперативный | Пользователь: {userName}</div>
        </div>
      </div>
      <div className="app-header__actions">
        <button
          className="power-button"
          type="button"
          onClick={async () => {
            const confirmed = window.confirm('Очистить локальное хранилище и перезагрузить интерфейс?');
            if (!confirmed) {
              return;
            }
            try {
              await clearMessages();
            } catch (error) {
              console.error('Не удалось очистить IndexedDB:', error);
            }
            localStorage.removeItem('roo_agent_messages');
            localStorage.removeItem('agent_messages');
            localStorage.removeItem('roo_agent_threads');
            localStorage.removeItem('roo_agent_thread');
            localStorage.removeItem('roo_agent_thread_names');
            window.location.reload();
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
        <button
          className="tts-button desktop-only"
          type="button"
          onClick={() => setAudioEnabled(!audioEnabled)}
          title={audioEnabled ? 'Выключить озвучивание' : 'Включить озвучивание'}
        >
          {audioEnabled ? <MessageSquareText className="icon" /> : <MessageSquareOff className="icon" />}
        </button>
        <button
          className="burger-button"
          type="button"
          onClick={() => setIsMenuOpen(true)}
          title="Открыть меню"
        >
          <Menu className="icon" />
        </button>
      </div>
    </header>
  );
};

export default Header;
