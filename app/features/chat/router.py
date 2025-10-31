from __future__ import annotations

from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.features.chat.attachments import (
    StoredAttachment,
    consume_thread_attachments,
    get_storage,
)
from app.features.chat.service import THREAD_MODEL_OVERRIDES, call_ai_query
from app.logging import get_logger
from app.middlewares.security import _require_csrf_token
from app.security_layer.dependencies import require_session
from app.security_layer.rate_limiter import RateLimitConfig, get_rate_limiter
from app.security_layer.signed_links import get_signed_link_manager
from app.settings import get_settings

router = APIRouter()
logger = get_logger()
settings = get_settings()
signed_links = get_signed_link_manager()


class ChatMessagePayload(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    model_config = ConfigDict(extra="ignore")


class ChatRequest(BaseModel):
    message: str | None = None
    thread_id: str | None = None
    history: list | None = None

    # OpenRouter (backward-compatible)
    open_router_api_key: str | None = Field(default=None, alias="openRouterApiKey")
    open_router_model: str | None = Field(default=None, alias="openRouterModel")

    # AgentRouter (OpenAI-compatible)
    provider_type: Literal["openrouter", "agentrouter"] | None = Field(default=None, alias="providerType")
    agent_router_base_url: str | None = Field(default=None, alias="agentRouterBaseUrl")
    agent_router_api_key: str | None = Field(default=None, alias="agentRouterApiKey")
    agent_router_model: str | None = Field(default=None, alias="agentRouterModel")

    messages: list[ChatMessagePayload] | None = None

    model_config = ConfigDict(populate_by_name=True)


class ChatResponse(BaseModel):
    status: str
    response: str
    thread_id: str | None = None
    attachments: list["ChatAttachment"] | None = None


class ChatAttachment(BaseModel):
    filename: str
    url: str
    content_type: str
    size: int
    description: str | None = None


class ChatAttachmentCreateRequest(BaseModel):
    filename: str
    content: str
    content_type: str | None = None
    description: str | None = None


class ChatAttachmentResponse(BaseModel):
    status: Literal["created"]
    attachment: ChatAttachment


@router.post("/chat", response_model=ChatResponse, include_in_schema=False)
async def chat_endpoint(
    payload: ChatRequest,
    request: Request,
    session=Depends(require_session),
) -> ChatResponse:
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "chat:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_chat_per_minute, window_seconds=60),
    )
    client_ip = request.client.host if request.client else "unknown"
    limiter.hit(
        "chat:ip",
        client_ip,
        RateLimitConfig(limit=settings.rate_limit_chat_per_minute, window_seconds=60),
    )
    log_payload = payload.model_dump(by_alias=True)
    if log_payload.get("openRouterApiKey"):
        log_payload["openRouterApiKey"] = "***masked***"
    if log_payload.get("agentRouterApiKey"):
        log_payload["agentRouterApiKey"] = "***masked***"
    logger.info(f"[CHAT ENDPOINT] Входящий payload: {log_payload}")

    message = (payload.message or "").strip()
    incoming_messages = None
    if payload.messages:
        incoming_messages = []
        for msg in payload.messages:
            if msg.content is None:
                logger.warning("[CHAT ENDPOINT] Пропущено сообщение без content: %s", msg)
                continue
            incoming_messages.append({"role": msg.role, "content": msg.content})

    if not message and not incoming_messages:
        raise HTTPException(status_code=400, detail="Пустое сообщение недопустимо")

    # Определяем провайдера и параметры
    provider = (payload.provider_type or "openrouter").strip().lower()
    if provider not in ("openrouter", "agentrouter"):
        provider = "openrouter"

    effective_api_key: Optional[str]
    effective_model: Optional[str]
    agent_base_url: Optional[str] = None

    if provider == "agentrouter":
        effective_api_key = payload.agent_router_api_key
        effective_model = payload.agent_router_model
        agent_base_url = (payload.agent_router_base_url or "").strip() or None
    else:
        effective_api_key = payload.open_router_api_key
        effective_model = payload.open_router_model

    current_thread_id = payload.thread_id or str(uuid4())
    try:
        response_text = call_ai_query(
            prompt=message or None,
            history=payload.history,
            user_api_key=effective_api_key,
            user_model=effective_model,
            messages=incoming_messages,
            thread_id=current_thread_id,
            provider_type=provider,
            agent_base_url=agent_base_url,
        )
        sanitized_model: Optional[str] = (effective_model or "").strip() if effective_model else None
        if sanitized_model:
            THREAD_MODEL_OVERRIDES[current_thread_id] = sanitized_model
    except RuntimeError as exc:
        logger.error("[CHAT ENDPOINT] RuntimeError: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    generated_attachments = consume_thread_attachments(current_thread_id)
    attachment_items: list[ChatAttachment] = []
    if generated_attachments:
        path = request.app.url_path_for("signed_chat_attachment")
        for item in generated_attachments:
            token = signed_links.issue(
                "chat-attachment",
                {
                    "file": item.storage_name,
                    "filename": item.filename,
                    "content_type": item.content_type,
                },
            )
            url = f"{path}?token={token}"
            attachment_items.append(
                ChatAttachment(
                    filename=item.filename,
                    url=url,
                    content_type=item.content_type,
                    size=item.size,
                    description=item.description,
                )
            )

    return ChatResponse(
        status="Message processed",
        response=response_text,
        thread_id=current_thread_id,
        attachments=attachment_items or None,
    )


@router.post("/chat/attachments", response_model=ChatAttachmentResponse, include_in_schema=False)
async def create_chat_attachment(
    payload: ChatAttachmentCreateRequest,
    request: Request,
    session=Depends(require_session),
) -> ChatAttachmentResponse:
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "chat_attachment:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_chat_per_minute, window_seconds=60),
    )

    storage = get_storage()
    stored: StoredAttachment = storage.create_attachment(
        filename=payload.filename,
        content=payload.content,
        content_type=payload.content_type,
    )

    token = signed_links.issue(
        "chat-attachment",
        {
            "file": stored.storage_name,
            "filename": stored.download_name,
            "content_type": stored.content_type,
        },
    )
    path = request.app.url_path_for("signed_chat_attachment")
    attachment_url = f"{path}?token={token}"

    attachment = ChatAttachment(
        filename=stored.download_name,
        url=attachment_url,
        content_type=stored.content_type,
        size=stored.size,
        description=payload.description,
    )

    return ChatAttachmentResponse(status="created", attachment=attachment)


@router.get("/signed/chat/attachments", name="signed_chat_attachment", include_in_schema=False)
async def serve_signed_chat_attachment(token: str = Query(...)) -> FileResponse:
    payload = signed_links.verify(token)
    if payload.resource != "chat-attachment":
        raise HTTPException(status_code=403, detail="Некорректный тип ресурса")

    data = payload.data
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Недопустимый токен вложения")

    storage_name = data.get("file")
    download_name = data.get("filename")
    content_type = data.get("content_type") or "application/octet-stream"

    if not isinstance(storage_name, str) or not storage_name:
        raise HTTPException(status_code=400, detail="Недопустимый токен вложения")

    if not isinstance(download_name, str) or not download_name:
        download_name = storage_name

    storage = get_storage()
    file_path = storage.resolve_attachment(storage_name)

    response = FileResponse(str(file_path), media_type=content_type, filename=download_name)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


ChatResponse.model_rebuild()
