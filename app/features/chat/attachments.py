from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status

from langchain.tools import tool

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


@dataclass(slots=True)
class GeneratedAttachment:
    storage_name: str
    filename: str
    content_type: str
    size: int
    description: str | None = None


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
_thread_attachments: dict[str, list[GeneratedAttachment]] = {}


def get_storage() -> ChatAttachmentStorage:
    global _storage
    if _storage is None:
        _storage = ChatAttachmentStorage()
    return _storage


def reset_storage_for_tests(new_dir: Path) -> None:
    ensure_upload_directory(new_dir)
    storage = get_storage()
    storage.override_directory(new_dir)
    _thread_attachments.clear()


def record_thread_attachment(thread_id: str, stored: StoredAttachment, description: Optional[str]) -> GeneratedAttachment:
    attachment = GeneratedAttachment(
        storage_name=stored.storage_name,
        filename=stored.download_name,
        content_type=stored.content_type,
        size=stored.size,
        description=description,
    )
    _thread_attachments.setdefault(thread_id, []).append(attachment)
    return attachment


def consume_thread_attachments(thread_id: Optional[str]) -> list[GeneratedAttachment]:
    if not thread_id:
        return []
    return _thread_attachments.pop(thread_id, [])


def clear_thread_attachments(thread_id: Optional[str]) -> None:
    if not thread_id:
        return
    _thread_attachments.pop(thread_id, None)


@tool("create_chat_attachment")
def create_chat_attachment_tool(
    filename: str,
    content: str,
    description: str | None = None,
    content_type: str | None = None,
    thread_id: str | None = None,
) -> str:
    """Создаёт вложение из переданного текста и возвращает краткое описание."""
    if not thread_id:
        return "Ошибка: не удалось сохранить вложение — отсутствует идентификатор треда."

    storage = get_storage()
    try:
        stored = storage.create_attachment(
            filename=filename,
            content=content,
            content_type=content_type,
        )
    except HTTPException as exc:
        return f"Ошибка создания вложения: {exc.detail}"

    record_thread_attachment(thread_id, stored, description)
    metadata = {
        "filename": stored.download_name,
        "size": stored.size,
        "content_type": stored.content_type,
        "description": description,
    }
    return f"Вложение создано: {json.dumps(metadata, ensure_ascii=False)}"
