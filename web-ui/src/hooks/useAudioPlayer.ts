import { useRef, useEffect } from 'react';

interface UseAudioPlayerProps {
  musicMuted: boolean;
}

export const useAudioPlayer = ({ musicMuted }: UseAudioPlayerProps) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const sendAudioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    const playAudio = async () => {
      if (audioRef.current && !musicMuted) {
        try {
          audioRef.current.currentTime = 0;
          audioRef.current.volume = 0.3;
          if (window.AudioContext && new window.AudioContext().state === 'suspended') {
            await new window.AudioContext().resume();
          }
          await audioRef.current.play();
        } catch (error) {
          console.log('Audio playback failed:', error);
        }
      }
    };

    const timer = setTimeout(playAudio, 100);

    const handleInteraction = () => {
      if (audioRef.current && audioRef.current.paused && !musicMuted) {
        playAudio();
      }
    };

    document.addEventListener('click', handleInteraction);
    document.addEventListener('keydown', handleInteraction);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('click', handleInteraction);
      document.removeEventListener('keydown', handleInteraction);
    };
  }, [musicMuted]);

  return { audioRef, sendAudioRef };
};
