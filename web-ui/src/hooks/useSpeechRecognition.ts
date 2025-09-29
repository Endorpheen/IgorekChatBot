import { useState, useEffect } from 'react';

interface UseSpeechRecognitionProps {
  onResult: (transcript: string) => void;
  onError?: (error: string) => void;
}

export const useSpeechRecognition = ({ onResult, onError }: UseSpeechRecognitionProps) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recognition, setRecognition] = useState<SpeechRecognition | null>(null);

  useEffect(() => {
    if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const rec = new SpeechRecognition();
      rec.lang = 'ru-RU';
      rec.continuous = false;
      rec.interimResults = false;

      rec.onstart = () => setIsRecording(true);
      rec.onend = () => setIsRecording(false);
      rec.onresult = (event: SpeechRecognitionEvent) => {
        const transcript = event.results[0][0].transcript;
        onResult(transcript);
      };
      rec.onerror = (event: SpeechRecognitionErrorEvent) => {
        console.error('Speech recognition error:', event.error);
        onError?.(event.error);
        setIsRecording(false);
      };
      setRecognition(rec);
    } else {
      console.warn('Speech Recognition not supported in this browser.');
    }
  }, [onResult, onError]);

  const startRecognition = () => {
    if (recognition && !isRecording) {
      recognition.start();
    }
  };

  const stopRecognition = () => {
    if (recognition && isRecording) {
      recognition.stop();
    }
  };

  const toggleRecognition = () => {
    if (isRecording) {
      stopRecognition();
    } else {
      startRecognition();
    }
  };

  return { isRecording, toggleRecognition, recognition };
};
