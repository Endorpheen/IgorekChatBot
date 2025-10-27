import React from 'react';
import { Command, MoreVertical, X, ArrowDownWideNarrow, Settings, Volume2, VolumeX } from 'lucide-react';
import type { ThreadSettings } from '../types/settings';

interface ThreadsPanelProps {
  isMenuOpen: boolean;
  setIsMenuOpen: (isOpen: boolean) => void;
  sortedThreads: string[];
  threadSettings: Record<string, ThreadSettings>;
  threadNames: Record<string, string>;
  threadId: string;
  openMenuId: string | null;
  setOpenMenuId: (id: string | null) => void;
  handleRenameThread: (id: string) => void;
  handleDeleteThread: (id: string) => void;
  setThreadId: (id: string) => void;
  handleNewThread: () => void;
  toggleThreadSortOrder: () => void;
  threadSortOrder: string;
  openSettings: () => void;
  audioEnabled: boolean;
  setAudioEnabled: (enabled: boolean) => void;
}

const ThreadsPanel: React.FC<ThreadsPanelProps> = ({
  isMenuOpen,
  setIsMenuOpen,
  sortedThreads,
  threadSettings,
  threadNames,
  threadId,
  openMenuId,
  setOpenMenuId,
  handleRenameThread,
  handleDeleteThread,
  setThreadId,
  handleNewThread,
  toggleThreadSortOrder,
  threadSortOrder,
  openSettings,
  audioEnabled,
  setAudioEnabled,
}) => {
  return (
    <>
      {isMenuOpen && (
        <div className="menu-overlay" onClick={() => setIsMenuOpen(false)} />
      )}
      <aside id="threads-panel" className={`threads-panel ${isMenuOpen ? 'mobile-open' : ''}`}>
        <div className="panel-title">Темы</div>
        {isMenuOpen && (
          <button
            className="close-menu-button"
            type="button"
            onClick={() => setIsMenuOpen(false)}
            title="Закрыть меню"
          >
            <X className="icon" />
          </button>
        )}
        <ul className="threads-list">
          {sortedThreads.map((id) => {
            const settings = threadSettings[id];
            const provider = settings?.chatProvider ?? 'openrouter';
            const indicatorClass = provider === 'openrouter' ? 'openrouter' : 'agentrouter';
            const indicatorIcon = provider === 'openrouter' ? '🌩️' : '🛰️';
            const threadLabel = threadNames[id] ?? 'Без названия';

            return (
              <li key={id} className={id === threadId ? 'active' : ''}>
                <div className="thread-menu-container">
                  <button
                    type="button"
                    className="thread-menu-trigger"
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenMenuId(openMenuId === id ? null : id);
                    }}
                    title="Меню треда"
                  >
                    <MoreVertical className="icon" />
                  </button>
                  {openMenuId === id && (
                    <div className="thread-menu" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="thread-menu-item"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRenameThread(id);
                          setOpenMenuId(null);
                        }}
                      >
                        Переименовать
                      </button>
                      {id !== 'default' && (
                        <button
                          type="button"
                          className="thread-menu-item"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteThread(id);
                            setOpenMenuId(null);
                          }}
                        >
                          Удалить
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setThreadId(id)}
                  className="thread-button"
                  data-thread-name={threadLabel}
                  title={threadLabel}
                >
                  <span className={`thread-model-indicator ${indicatorClass}`}>
                    {indicatorIcon}
                  </span>
                  <span className="thread-name">{threadLabel}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="threads-actions">
          <button type="button" onClick={handleNewThread} className="command-button">
            <Command className="icon" />
            Новый тред
          </button>
          <button
            type="button"
            className="command-button"
            onClick={toggleThreadSortOrder}
            title={threadSortOrder === 'newest-first' ? 'Показать новые треды снизу' : 'Показать новые треды сверху'}
          >
            <ArrowDownWideNarrow className="icon" />
            {threadSortOrder === 'newest-first' ? 'Новые сверху' : 'Новые снизу'}
          </button>
          <button
            type="button"
            className="command-button mobile-settings-button"
            onClick={openSettings}
            title="Настройки"
          >
            <Settings className="icon" />
            Настройки
          </button>
          <button
            className="command-button mobile-only"
            type="button"
            onClick={() => setAudioEnabled(!audioEnabled)}
            title={audioEnabled ? 'Выключить озвучивание' : 'Включить озвучивание'}
          >
            {audioEnabled ? <Volume2 className="icon" /> : <VolumeX className="icon" />}
            {audioEnabled ? 'Озвучка вкл.' : 'Озвучка выкл.'}
          </button>
        </div>
        {/* <div className="mobile-widget">
          <ElevenLabsConvaiWidget />
        </div> */}
      </aside>
    </>
  );
};

export default ThreadsPanel;
