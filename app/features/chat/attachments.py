from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status

from app.settings import ensure_upload_directory, get_settings


ALLOWED_EXTENSIONS = {".md", ".markdown", ".txt", ".json"}
DEFAULT_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
}
MAX_ATTACHMENT_SIZE = 512 * 1024  # 512 KB


@dataclass(slots=True)
class StoredAttachment:
    storage_name: str
    download_name: str
    content_type: str
    size: int


class ChatAttachmentStorage:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        settings = get_settings()
        default_dir = settings.upload_dir_path / "chat"
        self._base_dir = ensure_upload_directory(base_dir or default_dir)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def override_directory(self, new_dir: Path) -> None:
        self._base_dir = ensure_upload_directory(new_dir)

    def create_attachment(self, *, filename: str, content: str, content_type: Optional[str]) -> StoredAttachment:
        safe_name = (Path(filename).name or "attachment").strip()
        extension = Path(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Недопустимое расширение файла. Разрешены: .md, .markdown, .txt, .json",
            )

        encoded = content.encode("utf-8")
        if len(encoded) > MAX_ATTACHMENT_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Превышен максимальный размер вложения",
            )

        storage_name = f"{uuid4().hex}{extension}"
        storage_path = self._base_dir / storage_name
        storage_path.write_bytes(encoded)
        os.chmod(storage_path, 0o600)

        detected_type = (content_type or "").strip()
        if not detected_type:
            detected_type = DEFAULT_CONTENT_TYPES.get(extension) or mimetypes.guess_type(safe_name)[0] or "text/plain"

        return StoredAttachment(
            storage_name=storage_name,
            download_name=safe_name,
            content_type=detected_type,
            size=len(encoded),
        )

    def resolve_attachment(self, storage_name: str) -> Path:
        path = (self._base_dir / storage_name).resolve()
        try:
            path.relative_to(self._base_dir)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ запрещён",
            ) from exc
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вложение не найдено")
        return path


_storage: Optional[ChatAttachmentStorage] = None


def get_storage() -> ChatAttachmentStorage:
    global _storage
    if _storage is None:
        _storage = ChatAttachmentStorage()
    return _storage


def reset_storage_for_tests(new_dir: Path) -> None:
    ensure_upload_directory(new_dir)
    storage = get_storage()
    storage.override_directory(new_dir)
