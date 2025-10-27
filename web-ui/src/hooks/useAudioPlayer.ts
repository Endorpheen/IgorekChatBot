import { useRef, useEffect, useCallback } from 'react';

interface UseAudioPlayerProps {
  musicMuted: boolean;
}

export const useAudioPlayer = ({ musicMuted }: UseAudioPlayerProps) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const sendAudioRef = useRef<HTMLAudioElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);

  const ensureAudioContext = useCallback(async () => {
    if (typeof window === 'undefined' || typeof window.AudioContext === 'undefined') {
      return null;
    }

    let context = audioContextRef.current;

    if (!context || context.state === 'closed') {
      try {
        context = new window.AudioContext();
        audioContextRef.current = context;
      } catch (error) {
        console.log('AudioContext init failed:', error);
        audioContextRef.current = null;
        return null;
      }
    }

    if (context.state === 'suspended') {
      try {
        await context.resume();
      } catch (error) {
        console.log('AudioContext resume failed:', error);
        return null;
      }
    }

    return context;
  }, []);

  useEffect(() => {
    const playAudio = async () => {
      if (document.visibilityState !== 'visible') {
        return;
      }
      if (audioRef.current && !musicMuted) {
        try {
          const context = await ensureAudioContext();
          if (context) {
            audioRef.current.currentTime = 0;
            audioRef.current.volume = 0.3;
            await audioRef.current.play();
          }
        } catch (error) {
          console.log('Audio playback failed:', error);
        }
      }
    };

    const timer = setTimeout(playAudio, 100);

    const handleInteraction = () => {
      if (audioRef.current && audioRef.current.paused && !musicMuted && document.visibilityState === 'visible') {
        playAudio();
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        if (audioRef.current && !audioRef.current.paused) {
          audioRef.current.pause();
          audioRef.current.currentTime = 0;
        }
        const context = audioContextRef.current;
        if (context && context.state !== 'closed') {
          void context.close().catch((error) => {
            console.log('AudioContext close failed:', error);
          });
        }
        audioContextRef.current = null;
      } else if (!musicMuted && audioRef.current?.paused) {
        void playAudio();
      }
    };

    document.addEventListener('click', handleInteraction);
    document.addEventListener('keydown', handleInteraction);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('click', handleInteraction);
      document.removeEventListener('keydown', handleInteraction);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      const context = audioContextRef.current;
      if (context && context.state !== 'closed') {
        void context.close().catch((error) => {
          console.log('AudioContext close failed:', error);
        });
      }
      audioContextRef.current = null;
    };
  }, [ensureAudioContext, musicMuted]);

  return { audioRef, sendAudioRef };
};
