import { useRef } from 'react';

interface UseImageUploadProps {
  onImageUpload: (files: File[]) => Promise<void> | void;
}

export const useImageUpload = ({ onImageUpload }: UseImageUploadProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }

    const images = Array.from(files).filter(file => file.type.startsWith('image/'));
    if (images.length === 0) {
      alert('Пожалуйста, выберите изображение.');
      event.target.value = '';
      return;
    }

    try {
      await onImageUpload(images);
    } finally {
      event.target.value = '';
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  return { fileInputRef, handleImageUpload, triggerFileInput };
};
