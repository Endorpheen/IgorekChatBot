import { useCallback, useEffect, useRef, useState } from 'react';

interface UseSpeechRecognitionProps {
  onResult: (transcript: string) => void;
  onError?: (error: string) => void;
}

export const useSpeechRecognition = ({ onResult, onError }: UseSpeechRecognitionProps) => {
  const [isRecording, setIsRecording] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const handlersAttachedRef = useRef(false);

  const detachHandlers = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }
    recognition.onstart = null;
    recognition.onend = null;
    recognition.onresult = null;
    recognition.onerror = null;
    handlersAttachedRef.current = false;
  }, []);

  const handleFinalize = useCallback(() => {
    setIsRecording(false);
    detachHandlers();
  }, [detachHandlers]);

  const ensureRecognition = useCallback(() => {
    if (recognitionRef.current) {
      return recognitionRef.current;
    }

    if (typeof window === 'undefined') {
      return null;
    }

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionCtor) {
      console.warn('Speech Recognition not supported in this browser.');
      return null;
    }

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = 'ru-RU';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognitionRef.current = recognition;
    return recognition;
  }, []);

  const attachHandlers = useCallback(
    (recognition: SpeechRecognition) => {
      if (handlersAttachedRef.current) {
        return;
      }

      recognition.onstart = () => setIsRecording(true);
      recognition.onend = handleFinalize;
      recognition.onresult = (event: SpeechRecognitionEvent) => {
        const firstResult = event.results[0];
        const transcript = firstResult && firstResult[0] ? firstResult[0].transcript.trim() : '';

        if (transcript.length > 0) {
          onResult(transcript);
        }
      };
      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        console.error('Speech recognition error:', event.error);
        onError?.(event.error);
        handleFinalize();
      };

      handlersAttachedRef.current = true;
    },
    [handleFinalize, onError, onResult],
  );

  const startRecognition = useCallback(() => {
    if (isRecording) {
      return;
    }

    const recognition = ensureRecognition();

    if (!recognition) {
      return;
    }

    attachHandlers(recognition);

    try {
      recognition.start();
    } catch (error) {
      console.error('Speech recognition start error:', error);
      onError?.(error instanceof Error ? error.message : String(error));

      if (!(error instanceof DOMException) || error.name !== 'InvalidStateError') {
        handleFinalize();
      }
    }
  }, [attachHandlers, ensureRecognition, handleFinalize, isRecording, onError]);

  const stopRecognition = useCallback(() => {
    const recognition = recognitionRef.current;

    if (!recognition) {
      return;
    }

    if (isRecording) {
      try {
        recognition.stop();
      } catch (error) {
        console.error('Speech recognition stop error:', error);
        onError?.(error instanceof Error ? error.message : String(error));
      }
    } else {
      try {
        recognition.abort();
      } catch (error) {
        console.error('Speech recognition abort error:', error);
      }
    }

    handleFinalize();
  }, [handleFinalize, isRecording, onError]);

  const abortRecognition = useCallback(() => {
    const recognition = recognitionRef.current;

    if (!recognition) {
      return;
    }

    try {
      recognition.abort();
    } catch (error) {
      console.error('Speech recognition abort error:', error);
    }

    handleFinalize();
  }, [handleFinalize]);

  const toggleRecognition = useCallback(() => {
    if (isRecording) {
      stopRecognition();
    } else {
      startRecognition();
    }
  }, [isRecording, startRecognition, stopRecognition]);

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        abortRecognition();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      abortRecognition();
      recognitionRef.current = null;
    };
  }, [abortRecognition]);

  return { isRecording, toggleRecognition, recognition: recognitionRef.current };
};
