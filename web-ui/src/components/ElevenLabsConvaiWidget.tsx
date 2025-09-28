import { useEffect, useRef } from 'react';

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

export default ElevenLabsConvaiWidget;
