import { useRef } from 'react';

interface UseAttachmentUploadProps {
  onFilesSelected: (files: File[]) => Promise<void> | void;
}

export const useImageUpload = ({ onFilesSelected }: UseAttachmentUploadProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }

    try {
      await onFilesSelected(Array.from(files));
    } finally {
      event.target.value = '';
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  return { fileInputRef, handleImageUpload, triggerFileInput };
};
