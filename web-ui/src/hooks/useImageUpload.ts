import { useRef } from 'react';

interface UseImageUploadProps {
  onImageUpload: (file: File) => Promise<void> | void;
}

export const useImageUpload = ({ onImageUpload }: UseImageUploadProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !file.type.startsWith('image/')) {
      alert('Пожалуйста, выберите изображение.');
      return;
    }

    try {
      await onImageUpload(file);
    } finally {
      event.target.value = '';
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  return { fileInputRef, handleImageUpload, triggerFileInput };
};
