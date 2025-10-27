import { useEffect, useRef } from 'react';

const SCRIPT_SRC = 'https://elevenlabs.io/convai-widget/index.js';
const SCRIPT_ATTR = 'data-elevenlabs-widget';

let scriptLoadPromise: Promise<void> | null = null;

const loadWidgetScript = () => {
  if (typeof document === 'undefined') {
    return Promise.reject(new Error('Document is not available'));
  }

  if (scriptLoadPromise) {
    return scriptLoadPromise;
  }

  const existing = document.querySelector<HTMLScriptElement>(`script[${SCRIPT_ATTR}]`);
  if (existing && existing.dataset.loaded === 'true') {
    scriptLoadPromise = Promise.resolve();
    return scriptLoadPromise;
  }

  scriptLoadPromise = new Promise<void>((resolve, reject) => {
    const targetScript = existing ?? document.createElement('script');

    if (!existing) {
      targetScript.src = SCRIPT_SRC;
      targetScript.async = true;
      targetScript.type = 'text/javascript';
      targetScript.setAttribute(SCRIPT_ATTR, 'true');
      document.body.appendChild(targetScript);
    }

    const handleLoad = () => {
      targetScript.dataset.loaded = 'true';
      resolve();
    };

    const handleError = (event: Event) => {
      targetScript.removeEventListener('load', handleLoad);
      targetScript.removeEventListener('error', handleError);
      reject(new Error(`Failed to load ElevenLabs widget: ${event.type}`));
    };

    if (targetScript.dataset.loaded === 'true') {
      resolve();
      return;
    }

    targetScript.addEventListener('load', handleLoad, { once: true });
    targetScript.addEventListener('error', handleError, { once: true });
  });

  return scriptLoadPromise;
};

interface ElevenLabsConvaiWidgetProps {
  active: boolean;
  agentId?: string;
}

const ElevenLabsConvaiWidget = ({ active, agentId = 'Yfxp2vAkqHQT469GVM4p' }: ElevenLabsConvaiWidgetProps) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!active) {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
      return;
    }

    let cancelled = false;
    let widgetElement: HTMLElement | null = null;

    loadWidgetScript()
      .then(() => {
        if (cancelled || !containerRef.current) {
          return;
        }
        widgetElement = document.createElement('elevenlabs-convai');
        widgetElement.setAttribute('agent-id', agentId);
        containerRef.current.appendChild(widgetElement);
      })
      .catch((error) => {
        console.error(error);
      });

    return () => {
      cancelled = true;
      if (widgetElement && containerRef.current?.contains(widgetElement)) {
        containerRef.current.removeChild(widgetElement);
      } else if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [active, agentId]);

  return <div className="convai-widget" ref={containerRef} />;
};

export default ElevenLabsConvaiWidget;
