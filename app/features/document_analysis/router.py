from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.features.chat.service import THREAD_MODEL_OVERRIDES, call_ai_query
from app.logging import get_logger
from app.middlewares.security import _require_csrf_token
from app.security_layer.dependencies import require_session
from app.security_layer.rate_limiter import RateLimitConfig, get_rate_limiter
from app.settings import get_settings

router = APIRouter()
logger = get_logger()
settings = get_settings()

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
DOCUMENT_TEXT_LIMIT = 120_000
SANDBOX_TIMEOUT = 30

_REDACTED_RESPONSE_MARKERS = (
    "traceback",
    'file "',
    ".py",
    "openai",
    "aws_secret",
    "google",
)

ALLOWED_EXTENSIONS = {'.pdf', '.md', '.txt', '.docx'}
ALLOWED_MIME_TYPES: Dict[str, set[str]] = {
    '.pdf': {'application/pdf', 'application/x-pdf'},
    '.md': {'text/markdown', 'text/plain'},
    '.txt': {'text/plain', 'text/markdown'},
    '.docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
}


def _resolve_sandbox_document_url() -> str:
    base = settings.sandbox_service_url.rstrip('/')
    if base.endswith('/execute'):
        base = base.rsplit('/', 1)[0]
    return f"{base}/analyze/document"


def _is_mime_allowed(extension: str, mime: str) -> bool:
    if not extension:
        return False
    allowed = ALLOWED_MIME_TYPES.get(extension)
    if not allowed:
        return False
    if not mime:
        return True
    lowered = mime.lower()
    if lowered == 'application/octet-stream':
        return True
    return lowered in allowed


def _normalise_history(raw_history: List[Any], limit: int) -> List[Dict[str, str]]:
    if limit <= 0:
        return []

    trimmed = raw_history[-limit:]
    normalised: List[Dict[str, str]] = []
    for entry in trimmed:
        if not isinstance(entry, dict):
            continue
        content = entry.get('content')
        if not isinstance(content, str) or not content.strip():
            continue
        content_type = entry.get('contentType')
        if content_type not in (None, 'text'):
            continue
        message_type = entry.get('type')
        if message_type not in ('user', 'bot'):
            continue
        normalised.append({'type': message_type, 'content': content})
    return normalised


@router.post("/file/analyze", include_in_schema=False)
async def analyze_document_endpoint(
    request: Request,
    file: UploadFile = File(...),
    message: str = Form(...),
    thread_id: str = Form(...),
    history: str = Form("[]"),
    history_message_count: int = Form(default=5),
    provider_type: str = Form(default='openrouter'),
    open_router_api_key: Optional[str] = Form(default=None),
    open_router_model: Optional[str] = Form(default=None),
    agent_router_api_key: Optional[str] = Form(default=None),
    agent_router_model: Optional[str] = Form(default=None),
    agent_router_base_url: Optional[str] = Form(default=None),
    system_prompt: Optional[str] = Form(default=None),
    session=Depends(require_session),
):
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "file_analyze:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_file_analyze_per_hour, window_seconds=3600),
    )
    client_ip = request.client.host if request.client else "unknown"
    limiter.hit(
        "file_analyze:ip",
        client_ip,
        RateLimitConfig(limit=settings.rate_limit_file_analyze_per_hour, window_seconds=3600),
    )
    filename = file.filename or 'document'
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported or unsafe file type")

    file_bytes = await file.read()
    await file.close()
    size = len(file_bytes)

    if size > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="Payload Too Large")

    mime_type = (file.content_type or '').lower()
    if not _is_mime_allowed(extension, mime_type):
        raise HTTPException(status_code=415, detail="Unsupported or unsafe file type")

    logger.info(
        "[DOCUMENT ANALYSIS] Получен файл name=%s size=%s mime=%s",
        filename,
        size,
        mime_type or 'unknown',
    )

    sandbox_url = _resolve_sandbox_document_url()

    try:
        sandbox_response = requests.post(
            sandbox_url,
            files={'file': (filename, file_bytes, mime_type or 'application/octet-stream')},
            timeout=SANDBOX_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:  # pragma: no cover - network failure
        logger.error("[DOCUMENT ANALYSIS] Ошибка обращения к песочнице: %s", exc)
        raise HTTPException(status_code=502, detail="Не удалось обработать документ") from exc

    if sandbox_response.status_code == 413:
        raise HTTPException(status_code=413, detail="Payload Too Large")
    if sandbox_response.status_code == 415:
        raise HTTPException(status_code=415, detail="Unsupported or unsafe file type")
    if not sandbox_response.ok:
        logger.error(
            "[DOCUMENT ANALYSIS] Песочница вернула ошибку %s: %s",
            sandbox_response.status_code,
            sandbox_response.text,
        )
        raise HTTPException(status_code=502, detail="Ошибка обработки документа")

    try:
        sandbox_payload = sandbox_response.json()
    except ValueError as exc:  # pragma: no cover - invalid response
        logger.error("[DOCUMENT ANALYSIS] Некорректный ответ песочницы: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка обработки документа") from exc

    document_text = sandbox_payload.get('text') or ''
    metadata = sandbox_payload.get('metadata') or {}

    truncated_text = document_text[:DOCUMENT_TEXT_LIMIT]
    if len(document_text) > DOCUMENT_TEXT_LIMIT:
        truncated_text += "\n\n[Текст документа был сокращён для анализа.]"

    if not truncated_text.strip():
        truncated_text = "[Документ не содержит извлекаемого текста.]"

    try:
        history_payload = json.loads(history) if history else []
        if not isinstance(history_payload, list):
            raise ValueError("history must be a list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("[DOCUMENT ANALYSIS] Некорректный формат history: %s", exc)
        raise HTTPException(status_code=400, detail="Некорректный формат истории") from exc

    history_limit = max(1, min(50, history_message_count))
    history_messages = _normalise_history(history_payload, history_limit)

    provider = (provider_type or 'openrouter').strip().lower()
    if provider not in ('openrouter', 'agentrouter'):
        provider = 'openrouter'

    sanitized_model: Optional[str]
    agent_base_url: Optional[str] = None

    if provider == 'openrouter':
        sanitized_model = (open_router_model or '').strip() or None
        if sanitized_model:
            THREAD_MODEL_OVERRIDES[thread_id] = sanitized_model
    else:
        sanitized_model = (agent_router_model or '').strip() or None
        agent_base_url = (agent_router_base_url or '').strip() or None

    instructions = (system_prompt.strip() + "\n\n") if system_prompt and system_prompt.strip() else ""
    document_intro = (
        f"Пользователь загрузил документ «{filename}» "
        f"({mime_type or metadata.get('mime_type') or 'неизвестный тип'}, {size} байт).\n"
    )

    user_prompt = message.strip() if message and message.strip() else 'Сформулируй краткое содержание документа.'

    prompt_payload = (
        f"{instructions}{document_intro}"
        f"Ниже приведено содержимое документа:\n\"\"\"\n{truncated_text}\n\"\"\"\n\n"
        f"Вопрос пользователя: {user_prompt}\n"
        "Ответь информативно, ссылаясь на содержание документа."
    )

    try:
        response_text = call_ai_query(
            prompt=prompt_payload,
            history=history_messages,
            user_api_key=open_router_api_key if provider == 'openrouter' else agent_router_api_key,
            user_model=sanitized_model,
            thread_id=thread_id,
            provider_type=provider,
            agent_base_url=agent_base_url,
        )
    except RuntimeError as exc:
        logger.error("[DOCUMENT ANALYSIS] RuntimeError: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Обработка запроса временно недоступна",
        )
    except Exception:  # pragma: no cover
        logger.exception("[DOCUMENT ANALYSIS] Ошибка генерации ответа")
        raise HTTPException(
            status_code=500,
            detail="Не удалось сформировать ответ",
        )

    if isinstance(response_text, str):
        # If our internal marker for API failure is present, do NOT expose any error details
        if response_text == "API_ERROR_GENERATING_RESPONSE":
            logger.warning("[DOCUMENT ANALYSIS] Не удалось сформировать ответ: внутренняя ошибка API получена из call_ai_query")
            raise HTTPException(
                status_code=500,
                detail="Не удалось сформировать ответ",
            )
        normalised_response = response_text.lower()
        if any(marker in normalised_response for marker in _REDACTED_RESPONSE_MARKERS):
            logger.warning("[DOCUMENT ANALYSIS] Ответ не прошёл постобработку, возвращаем общий код ошибки")
            raise HTTPException(
                status_code=500,
                detail="Не удалось сформировать ответ",
            )

    return {
        'status': 'Document processed',
        'response': response_text,
        'thread_id': thread_id,
        'document': {
            'filename': filename,
            'mime_type': mime_type or metadata.get('mime_type') or 'application/octet-stream',
            'size': size,
        },
    }
