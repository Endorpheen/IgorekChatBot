import React from 'react';
import { Settings, Github } from 'lucide-react';
import ElevenLabsConvaiWidget from './ElevenLabsConvaiWidget';

interface FooterProps {
  openSettings: () => void;
}

const Footer: React.FC<FooterProps> = ({ openSettings }) => {
  return (
    <footer className="app-footer">
      <div className="footer-primary">
        <div className="footer-center">
          <div>
            Code by <span className="accent">GPT-5, GEMINI 2.5, GROK 4</span>
          </div>
          <div>
            CODE ORCHESTRATION by <span className="accent">end0</span>
          </div>
          <div>
            <span className="version">V1.2.1</span>
          </div>
        </div>
        <a
          className="settings-button"
          href="https://github.com/Endorpheen/IgorekChatBot"
          target="_blank"
          rel="noreferrer noopener"
        >
          <Github className="icon" />
          <span>GitHub</span>
        </a>
        <button
          type="button"
          className="settings-button footer-settings-hide-mobile"
          title="Настройки"
          onClick={openSettings}
        >
          <Settings className="icon" />
          Настройки
        </button>
      </div>

      <div className="footer-secondary">
        <div className="desktop-widget">
          <ElevenLabsConvaiWidget />
        </div>
        <div className="support-project">
          <img src="/web-ui/metamaskqr.png" alt="MetaMask QR" className="support-icon" />
          <span
            className="support-text"
            onClick={() => {
              navigator.clipboard.writeText('0x5d36725941870C927473d2ba3eEBDe6613185b78');
              alert('Адрес крипто кошелька MetaMask скопирован в буфер, будем рады Вашей поддержке 😊');
            }}
          >
            Поддержать проект
          </span>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
