from __future__ import annotations

from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.features.chat.service import THREAD_MODEL_OVERRIDES, call_ai_query
from app.logging import get_logger

router = APIRouter()
logger = get_logger()


class ChatMessagePayload(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    model_config = ConfigDict(extra="ignore")


class ChatRequest(BaseModel):
    message: str | None = None
    thread_id: str | None = None
    history: list | None = None
    open_router_api_key: str | None = Field(default=None, alias="openRouterApiKey")
    open_router_model: str | None = Field(default=None, alias="openRouterModel")
    messages: list[ChatMessagePayload] | None = None

    model_config = ConfigDict(populate_by_name=True)


class ChatResponse(BaseModel):
    status: str
    response: str
    thread_id: str | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    log_payload = payload.model_dump(by_alias=True)
    if log_payload.get("openRouterApiKey"):
        log_payload["openRouterApiKey"] = "***masked***"
    logger.info("[CHAT ENDPOINT] Входящий payload: %s", log_payload)

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

    current_thread_id = payload.thread_id or str(uuid4())
    try:
        response_text = call_ai_query(
            prompt=message or None,
            history=payload.history,
            user_api_key=payload.open_router_api_key,
            user_model=payload.open_router_model,
            messages=incoming_messages,
            thread_id=current_thread_id,
        )
        sanitized_model: Optional[str] = (payload.open_router_model or "").strip() if payload.open_router_model else None
        if sanitized_model:
            THREAD_MODEL_OVERRIDES[current_thread_id] = sanitized_model
    except RuntimeError as exc:
        logger.error("[CHAT ENDPOINT] RuntimeError: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(status="Message processed", response=response_text, thread_id=current_thread_id)
