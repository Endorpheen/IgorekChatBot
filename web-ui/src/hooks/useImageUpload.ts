import { useRef } from 'react';

interface UseImageUploadProps {
  onImageUpload: (dataUrl: string) => void;
}

export const useImageUpload = ({ onImageUpload }: UseImageUploadProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !file.type.startsWith('image/')) {
      alert('Пожалуйста, выберите изображение.');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      if (dataUrl) {
        onImageUpload(dataUrl);
      }
    };
    reader.readAsDataURL(file);
    event.target.value = '';
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  return { fileInputRef, handleImageUpload, triggerFileInput };
};
