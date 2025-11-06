from __future__ import annotations

import base64
import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import uuid4
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict

from app.features.chat.service import THREAD_MODEL_OVERRIDES
from app.features.image_analysis.service import (
    build_image_conversation,
    call_agentrouter_for_image,
    call_openrouter_for_image,
)
from app.logging import get_logger
from app.middlewares.security import _require_csrf_token
from app.security_layer.dependencies import require_session
from app.security_layer.rate_limiter import RateLimitConfig, get_rate_limiter
from app.settings import ensure_upload_directory, get_settings

router = APIRouter()
logger = get_logger()
settings = get_settings()

upload_dir = ensure_upload_directory(settings.upload_dir_path)


class ImagePayload(BaseModel):
    filename: str
    url: str
    content_type: str | None = None


class ImageAnalysisResponse(BaseModel):
    status: str
    response: str
    thread_id: str
    image: ImagePayload | None = None
    images: List[ImagePayload] | None = None

    model_config = ConfigDict(extra="ignore")


@router.post("/image/analyze", response_model=ImageAnalysisResponse, include_in_schema=False)
async def analyze_image_endpoint(
    request: Request,
    files: List[UploadFile] | None = File(default=None),
    thread_id: str = Form(...),
    message: str = Form(""),
    history: str = Form("[]"),
    open_router_api_key: str | None = Form(default=None),
    open_router_model: str | None = Form(default=None),
    agent_router_api_key: str | None = Form(default=None),
    agent_router_model: str | None = Form(default=None),
    agent_router_base_url: str | None = Form(default=None),
    provider_type: str = Form(default="openrouter"),
    system_prompt: str | None = Form(default=None),
    history_message_count: int = Form(default=5),
    session=Depends(require_session),
):
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "image_analyze:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_image_analyze_per_minute, window_seconds=60),
    )
    client_ip = request.client.host if request.client else "unknown"
    limiter.hit(
        "image_analyze:ip",
        client_ip,
        RateLimitConfig(limit=settings.rate_limit_image_analyze_per_minute, window_seconds=60),
    )
    files = files or []

    if not files and not message.strip():
        raise HTTPException(status_code=422, detail="Требуется текст или хотя бы одно изображение")

    logger.info(
        "[IMAGE ANALYSIS] Запрос: thread_id=%s, файлов=%s, has_text=%s",
        thread_id,
        len(files),
        bool(message.strip()),
    )

    try:
        history_payload = json.loads(history) if history else []
        if not isinstance(history_payload, list):
            raise ValueError("history should be a list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("[IMAGE ANALYSIS] Некорректный формат history: %s", exc)
        raise HTTPException(status_code=400, detail="Некорректный формат истории") from exc

    encoded_images: List[str] = []
    response_images: List[ImagePayload] = []

    provider = (provider_type or "openrouter").strip().lower()
    if provider not in {"openrouter", "agentrouter"}:
        provider = "openrouter"

    for upload in files:
        if not upload.content_type or not upload.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"Файл {upload.filename or ''} не является изображением")

        original_name = upload.filename or "image"
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(original_name).stem) or "image"
        stem = stem[:40]
        ext = Path(original_name).suffix
        if not ext:
            guessed = mimetypes.guess_extension(upload.content_type)
            ext = guessed or ""
        if ext and not ext.startswith('.'):
            ext = f".{ext}"
        if not ext:
            ext = ".bin"

        unique_name = f"{datetime.utcnow():%Y%m%d%H%M%S}_{uuid4().hex[:8]}_{stem}{ext}"
        file_path = upload_dir / unique_name

        try:
            file_bytes = await upload.read()
        except Exception as exc:  # pragma: no cover
            logger.error("[IMAGE ANALYSIS] Не удалось прочитать файл %s: %s", upload.filename, exc)
            raise HTTPException(status_code=500, detail="Не удалось прочитать файл изображения") from exc
        finally:
            await upload.close()

        try:
            with open(file_path, "wb") as destination:
                destination.write(file_bytes)
        except OSError as exc:
            logger.error("[IMAGE ANALYSIS] Не удалось сохранить файл %s: %s", file_path, exc)
            raise HTTPException(status_code=500, detail="Не удалось сохранить файл изображения") from exc

        encoded = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{upload.content_type};base64,{encoded}"
        encoded_images.append(data_url)

        response_images.append(
            ImagePayload(
                filename=unique_name,
                url=f"{settings.upload_url_prefix.rstrip('/')}/{unique_name}",
                content_type=upload.content_type,
            )
        )

    origin = request.headers.get("Origin") or request.headers.get("Referer")

    if provider == "agentrouter":
        actual_api_key = (agent_router_api_key or "").strip() or None
        actual_model = (agent_router_model or "").strip() or None
        base_url = (agent_router_base_url or "").strip() or None
        if not actual_api_key:
            raise HTTPException(status_code=400, detail="OpenAI Compatible API ключ не настроен")
        if not base_url:
            raise HTTPException(status_code=400, detail="OpenAI Compatible endpoint не настроен")

        try:
            parsed = urlparse(base_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="OpenAI Compatible endpoint некорректен") from exc
        if parsed.scheme.lower() != "https":
            # Allow HTTP providers for localhost development if enabled
            # Use existing settings from module scope
            is_localhost = parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0") or (
                parsed.hostname and parsed.hostname.startswith("192.168.")
            )
            if not (settings.allow_http_providers and is_localhost):
                raise HTTPException(status_code=400, detail="OpenAI Compatible endpoint должен использовать HTTPS")
        normalized_origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        allowlist = {item.rstrip("/").lower() for item in settings.allowed_agentrouter_base_urls}
        if allowlist and normalized_origin not in allowlist:
            raise HTTPException(status_code=403, detail="OpenAI Compatible endpoint не разрешён")

        if not actual_model:
            raise HTTPException(status_code=400, detail="OpenAI Compatible модель не настроена")
    else:
        actual_api_key = (open_router_api_key or settings.openrouter_api_key or "").strip() or None
        sanitized_model = (open_router_model or "").strip()
        if sanitized_model:
            THREAD_MODEL_OVERRIDES[thread_id] = sanitized_model

        model_from_thread = THREAD_MODEL_OVERRIDES.get(thread_id)
        actual_model = (model_from_thread or settings.openrouter_model or "").strip() or None

        if not actual_api_key:
            raise HTTPException(status_code=400, detail="OpenRouter API ключ не настроен")
        if not actual_model:
            raise HTTPException(status_code=400, detail="OpenRouter модель не настроена")

    messages = build_image_conversation(
        history=history_payload,
        thread_id=thread_id,
        history_limit=history_message_count,
        system_prompt=system_prompt,
        image_data_urls=encoded_images,
        prompt=message,
        provider_base_url=base_url if provider == "agentrouter" else None,
        lmstudio_mode=settings.lmstudio_image_mode,
    )

    try:
        if provider == "agentrouter":
            response_text = call_agentrouter_for_image(
                messages=messages,
                api_key=actual_api_key,
                model=actual_model,
                base_url=base_url,  # type: ignore[arg-type]
            )
        else:
            response_text = call_openrouter_for_image(
                messages=messages,
                api_key=actual_api_key,
                model=actual_model,
                origin=origin,
            )
    except HTTPException as exc:
        if exc.status_code == 502 and "does not support" in str(exc.detail).lower():
            raise HTTPException(status_code=400, detail="Выбранная модель не поддерживает работу с изображениями.") from exc
        raise

    logger.info("[IMAGE ANALYSIS] Ответ модели: %s", response_text)

    payload = ImageAnalysisResponse(
        status="Image processed",
        response=response_text,
        thread_id=thread_id,
        images=response_images or None,
    )

    if payload.images:
        payload.image = payload.images[0]

    return payload
