from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import requests
from fastapi import HTTPException

from app.logging import get_logger
from app.settings import get_settings

logger = get_logger()
settings = get_settings()


def build_image_conversation(
    history: list[dict],
    thread_id: str,
    history_limit: int,
    system_prompt: str | None,
    image_data_urls: List[str],
    prompt: str | None,
    provider_base_url: str | None = None,
    lmstudio_mode: str = "auto",
) -> list[dict]:
    base_prompt = system_prompt or "You are a helpful AI assistant. You can analyze images when provided."
    messages = [{"role": "system", "content": base_prompt}]

    filtered_history = [msg for msg in history if isinstance(msg, dict) and msg.get("threadId") == thread_id]
    filtered_history.sort(key=lambda item: item.get("createdAt", ""))

    history_limit = max(1, min(50, history_limit))
    if len(filtered_history) > history_limit:
        filtered_history = filtered_history[-history_limit:]

    upload_dir = settings.upload_dir_path

    for entry in filtered_history:
        role = entry.get("type")
        content_type = entry.get("contentType")
        content = entry.get("content")

        if role not in {"user", "bot"}:
            continue

        if content_type == "image" and role == "user":
            data_url = None
            if isinstance(content, str) and content.startswith("data:"):
                data_url = content
            else:
                file_name = entry.get("fileName") or entry.get("filename")
                if file_name:
                    file_path = upload_dir / file_name
                    if file_path.exists():
                        mime_type = (
                            entry.get("mimeType")
                            or entry.get("mime_type")
                            or mimetypes.guess_type(file_path.name)[0]
                            or "application/octet-stream"
                        )
                        try:
                            with open(file_path, "rb") as stored_file:
                                encoded = base64.b64encode(stored_file.read()).decode("utf-8")
                                data_url = f"data:{mime_type};base64,{encoded}"
                        except OSError as exc:  # pragma: no cover
                            logger.warning("[IMAGE ANALYSIS] Не удалось прочитать файл истории %s: %s", file_path, exc)

            if data_url:
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Анализируй это изображение."},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                )
        elif content_type == "text" and isinstance(content, str):
            messages.append({"role": "user" if role == "user" else "assistant", "content": content})

    user_prompt = (prompt or "").strip() or "Опиши изображения подробно, извлеки весь текст если есть."

    final_content: List[dict] = [{"type": "text", "text": user_prompt}]

    # Determine if we should use base64 format for LM Studio
    use_base64_format = False
    logger.info("[IMAGE ANALYSIS] LM Studio mode: %s, provider_base_url: %s", lmstudio_mode, provider_base_url)

    if lmstudio_mode == "base64":
        use_base64_format = True
        logger.info("[IMAGE ANALYSIS] Forced base64 mode enabled")
    elif lmstudio_mode == "auto" and provider_base_url:
        # Auto-detect LM Studio by port 8010 or common LM Studio patterns
        parsed = urlparse(provider_base_url)
        is_lmstudio = (
            ":8010" in provider_base_url or
            parsed.port == 8010 or
            "192.168.0.155" in parsed.hostname or
            parsed.hostname and parsed.hostname.startswith("192.168.")
        )
        use_base64_format = is_lmstudio
        logger.info("[IMAGE ANALYSIS] Auto-detected LM Studio: %s, use_base64: %s", is_lmstudio, use_base64_format)
    else:
        logger.info("[IMAGE ANALYSIS] Base64 conversion disabled")

    logger.info("[IMAGE ANALYSIS] Processing %d image URLs", len(image_data_urls))
    for i, image_url in enumerate(image_data_urls):
        logger.info("[IMAGE ANALYSIS] Processing image %d: %s", i, image_url)
        if use_base64_format:
            # Convert to base64 for LM Studio
            logger.info("[IMAGE ANALYSIS] Converting image to base64...")
            try:
                if image_url.startswith("http"):
                    # Handle external URLs - download and convert
                    response = requests.get(image_url, timeout=10)
                    if response.ok:
                        mime_type = response.headers.get('content-type', 'image/jpeg')
                        encoded = base64.b64encode(response.content).decode('utf-8')
                        base64_url = f"data:{mime_type};base64,{encoded}"
                        final_content.append({"type": "image_url", "image_url": {"url": base64_url}})
                    else:
                        logger.warning("[IMAGE ANALYSIS] Failed to download image for base64 conversion: %s", response.status_code)
                        final_content.append({"type": "image_url", "image_url": {"url": image_url}})
                elif image_url.startswith("data:"):
                    # Already base64 encoded - use as-is
                    final_content.append({"type": "image_url", "image_url": {"url": image_url}})
                else:
                    # Handle local file URLs or relative paths
                    if image_url.startswith("/uploads/") or "uploads/" in image_url:
                        logger.info("[IMAGE ANALYSIS] Detected local file URL: %s", image_url)
                        # Extract filename from URL and convert local file
                        filename = image_url.split("/")[-1].split("?")[0]  # Remove query params
                        file_path = upload_dir / filename
                        logger.info("[IMAGE ANALYSIS] Looking for file: %s", file_path)
                        if file_path.exists():
                            logger.info("[IMAGE ANALYSIS] File found, converting to base64...")
                            mime_type = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
                            with open(file_path, "rb") as f:
                                encoded = base64.b64encode(f.read()).decode('utf-8')
                                base64_url = f"data:{mime_type};base64,{encoded}"
                                logger.info("[IMAGE ANALYSIS] Successfully converted to base64, length: %d", len(encoded))
                                final_content.append({"type": "image_url", "image_url": {"url": base64_url}})
                        else:
                            logger.warning("[IMAGE ANALYSIS] Local file not found: %s", file_path)
                            final_content.append({"type": "image_url", "image_url": {"url": image_url}})
                    else:
                        logger.info("[IMAGE ANALYSIS] Unknown format, using as-is: %s", image_url)
                        # Unknown format - use as-is
                        final_content.append({"type": "image_url", "image_url": {"url": image_url}})
            except Exception as exc:
                logger.warning("[IMAGE ANALYSIS] Error converting image to base64: %s", exc)
                final_content.append({"type": "image_url", "image_url": {"url": image_url}})
        else:
            logger.info("[IMAGE ANALYSIS] Base64 disabled, using original URL: %s", image_url)
            # Use original URL format
            final_content.append({"type": "image_url", "image_url": {"url": image_url}})

    messages.append({"role": "user", "content": final_content})
    return messages


def call_openrouter_for_image(messages: list[dict], api_key: str, model: str, origin: str | None) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": origin or "http://localhost",
        "X-Title": "IgorekChatBot",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": settings.max_completion_tokens,
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        logger.error("[IMAGE ANALYSIS] Ошибка запроса к OpenRouter: %s", exc)
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {exc}") from exc

    if not response.ok:
        try:
            error_payload = response.json()
            error_detail = error_payload.get("error", {}).get("message") or error_payload.get("message")
        except ValueError:
            error_detail = response.text

        logger.error(
            "[IMAGE ANALYSIS] OpenRouter non-OK response: status=%s detail=%s",
            response.status_code,
            error_detail,
        )
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter error ({response.status_code}): {error_detail or 'Unknown error'}",
        )

    data = response.json()
    return _extract_image_description(data)


def call_agentrouter_for_image(messages: list[dict], api_key: str, model: str, base_url: str) -> str:
    if not base_url:
        raise HTTPException(status_code=400, detail="OpenAI Compatible endpoint не настроен")

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": settings.max_completion_tokens,
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        logger.error("[IMAGE ANALYSIS] Ошибка запроса к OpenAI Compatible: %s", exc)
        raise HTTPException(status_code=502, detail=f"OpenAI Compatible error: {exc}") from exc

    if not response.ok:
        try:
            payload = response.json()
            error_detail = payload.get("error") or payload.get("message")
        except ValueError:
            error_detail = response.text

        logger.error(
            "[IMAGE ANALYSIS] OpenAI Compatible non-OK response: status=%s detail=%s",
            response.status_code,
            error_detail,
        )
        status = response.status_code
        if status < 400 or status > 499:
            status = 502
        raise HTTPException(
            status_code=status,
            detail=f"OpenAI Compatible error ({response.status_code}): {error_detail or 'Unknown error'}",
        )

    data = response.json()
    return _extract_image_description(data)


def _extract_image_description(data: dict) -> str:
    message = data.get("choices", [{}])[0].get("message") or {}
    content = message.get("content")
    if not content:
        logger.warning("[IMAGE ANALYSIS] Пустой ответ модели: %s", data)
        return "Не удалось получить описание изображения."

    if isinstance(content, list):
        return "".join(chunk.get("text", "") for chunk in content if isinstance(chunk, dict)) or "Не удалось получить описание изображения."

    return str(content)
