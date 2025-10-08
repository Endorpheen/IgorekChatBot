#!/usr/bin/env python3
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging
import os
import re
import uvicorn
import requests
import base64
import json
from uuid import uuid4
from typing import Literal, Dict
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel as LangchainBaseModel, Field as LangchainField
from langchain.tools import tool
from langchain_core.messages import ToolMessage

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "DEBUG"),  # DEBUG для максимальной детализации
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_bot")

app = FastAPI()

ALLOW_ORIGINS = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
    "https://igorek.end0databox.duckdns.org",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# WebUI static files (Vite build)
# -------------------------------
WEBUI_DIR = "/app/web-ui"

if os.path.isdir(WEBUI_DIR):
    app.mount(
        "/web-ui/assets",
        StaticFiles(directory=os.path.join(WEBUI_DIR, "assets")),
        name="assets",
    )

    @app.get("/web-ui")
    @app.get("/web-ui/")
    async def serve_index():
        return FileResponse(os.path.join(WEBUI_DIR, "index.html"))

    # Service Worker и манифест/иконки через /web-ui
    @app.get("/web-ui/manifest.json")
    async def serve_manifest():
        return FileResponse(os.path.join(WEBUI_DIR, "manifest.json"))

    @app.get("/web-ui/icon-192.png")
    async def serve_icon192():
        return FileResponse(os.path.join(WEBUI_DIR, "icon-192.png"))

    @app.get("/web-ui/icon-512.png")
    async def serve_icon512():
        return FileResponse(os.path.join(WEBUI_DIR, "icon-512.png"))

    # Service Worker из корня (чтобы точно не ломался)
    @app.get("/sw.js")
    async def serve_root_sw():
        return FileResponse(os.path.join(WEBUI_DIR, "sw.js"))

    @app.get("/web-ui/{path_file}")
    async def serve_root_files(path_file: str):
        file_path = os.path.join(WEBUI_DIR, path_file)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="Not Found")

# -------------------------------
# Models
# -------------------------------


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


class ImagePayload(BaseModel):
    content: str
    content_type: str


class ImageAnalysisResponse(BaseModel):
    status: str
    response: str
    thread_id: str
    image: ImagePayload

# -------------------------------
# LangChain Tools
# -------------------------------
@tool
def run_code_in_sandbox(code: str):
    """
    Выполняет код в песочнице.
    """
    logger.info(f"[TOOL] Вызов run_code_in_sandbox с кодом: {code}")
    try:
        response = requests.post(
            "http://sandbox_executor:8000/execute",
            json={"language": "python", "code": code, "timeout": 5},
            timeout=7
        )
        response.raise_for_status()
        data = response.json()
        if data["exit_code"] == 0:
            return f"Результат выполнения:\n{data['stdout']}"
        else:
            return f"Ошибка выполнения:\n{data['stderr']}"
    except requests.exceptions.RequestException as e:
        logger.error(f"[TOOL] Ошибка при обращении к песочнице: {e}")
        return "Ошибка: не удалось связаться с сервисом выполнения кода."


@tool
def browse_website(url: str) -> str:
    """
    Открывает указанный URL в браузере и возвращает его текстовое содержимое.
    """
    logger.info(f"[TOOL] Вызов browse_website с URL: {url}")
    try:
        response = requests.post(
            "http://browser:8000/browse",
            json={"url": url},
            timeout=20
        )
        response.raise_for_status()
        data = response.json()
        if data["error"]:
            return f"Ошибка при просмотре сайта: {data['error']}"
        return f"Содержимое страницы {url}:\n\n{data['content']}"
    except requests.exceptions.RequestException as e:
        logger.error(f"[TOOL] Ошибка при обращении к браузеру: {e}")
        return "Ошибка: не удалось связаться с сервисом браузера."

# -------------------------------
# LangChain
# -------------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

THREAD_MODEL_OVERRIDES: Dict[str, str] = {}

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY не задан — чат работать не будет")

def call_ai_query(prompt: str | None = None,
                  history: list | None = None,
                  user_api_key: str | None = None,
                  user_model: str | None = None,
                  messages: list[dict[str, str]] | None = None) -> str:
    """
    Вызов модели через LangChain с поддержкой function-calling
    """
    actual_api_key = user_api_key or OPENROUTER_API_KEY
    actual_model = user_model or OPENROUTER_MODEL

    logger.debug(f"[AI QUERY] prompt={prompt}")
    logger.debug(f"[AI QUERY] history={history}")
    logger.debug(f"[AI QUERY] incoming_messages={messages}")
    logger.debug(f"[AI QUERY] actual_model={actual_model}")
    logger.debug(f"[AI QUERY] actual_api_key={'***masked***' if actual_api_key else None}")

    if not actual_api_key:
        raise RuntimeError("Нет доступного OpenRouter API ключа")

    # Создаём LLM и биндим инструменты каждый раз заново
    llm = ChatOpenAI(
        model=actual_model,
        api_key=actual_api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.7,
        max_tokens=int(os.getenv("MAX_COMPLETION_TOKENS", 4096)),
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "IgorekChatBot",
        },
    )
    llm_with_tools = llm.bind_tools([run_code_in_sandbox, browse_website])

    conversation = []

    if messages:
        for entry in messages:
            role = entry.get("role") if isinstance(entry, dict) else None
            content = entry.get("content") if isinstance(entry, dict) else None
            if content is None or role is None:
                logger.warning(f"[AI QUERY] Пропущено сообщение без role/content: {entry}")
                continue

            if role == "system":
                conversation.append(("system", content))
            elif role == "user":
                conversation.append(("human", content))
            elif role == "assistant":
                conversation.append(("ai", content))
            else:
                logger.warning(f"[AI QUERY] Неизвестная роль сообщения: {role}")
    else:
        conversation = [("system", "You are a helpful AI assistant.")]
        if history:
            for msg in history:
                role = "human" if msg["type"] == "user" else "ai"
                conversation.append((role, msg["content"]))
        if prompt is not None:
            conversation.append(("human", prompt))

    if not conversation:
        raise RuntimeError("Не удалось сформировать сообщения для модели")

    logger.debug(f"[AI QUERY] Отправляем messages={conversation}")

    try:
        ai_msg = llm_with_tools.invoke(conversation)

        logger.debug(f"[AI QUERY] Ответ модели: {ai_msg}")
        logger.debug(f"[AI QUERY] tool_calls={ai_msg.tool_calls}")

        if not ai_msg.tool_calls:
            return ai_msg.content

        # Если есть вызовы инструментов, обрабатываем их
        tool_outputs = []
        for tool_call in ai_msg.tool_calls:
            logger.info(f"[AI QUERY] Вызов функции: {tool_call['name']} args={tool_call['args']}")
            if tool_call['name'] == 'run_code_in_sandbox':
                result = run_code_in_sandbox.run(tool_call['args'])
                tool_outputs.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )
            elif tool_call['name'] == 'browse_website':
                result = browse_website.run(tool_call['args'])
                tool_outputs.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )

        conversation.append(ai_msg)
        conversation.extend(tool_outputs)

        logger.debug(f"[AI QUERY] Сообщения после tool_calls: {conversation}")

        final_response = llm_with_tools.invoke(conversation)
        logger.debug(f"[AI QUERY] Итоговый ответ: {final_response}")
        return final_response.content

    except Exception as e:
        logger.error(f"[AI QUERY] Ошибка LangChain API: {e}", exc_info=True)
        return f"Ошибка API: {e}"


def _build_image_conversation(history: list[dict],
                              thread_id: str,
                              history_limit: int,
                              system_prompt: str | None,
                              image_data_url: str) -> list[dict]:
    """
    Формирует набор сообщений для OpenRouter, включая историю треда и новое изображение.
    """
    base_prompt = system_prompt or "You are a helpful AI assistant. You can analyze images when provided."
    messages = [{"role": "system", "content": base_prompt}]

    filtered_history = [
        msg for msg in history
        if isinstance(msg, dict) and msg.get("threadId") == thread_id
    ]

    filtered_history.sort(key=lambda item: item.get("createdAt", ""))

    history_limit = max(1, min(50, history_limit))
    if len(filtered_history) > history_limit:
        filtered_history = filtered_history[-history_limit:]

    for entry in filtered_history:
        role = entry.get("type")
        content_type = entry.get("contentType")
        content = entry.get("content")
        if not content or role not in {"user", "bot"}:
            continue

        if content_type == "image" and role == "user":
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "Анализируй это изображение."},
                    {"type": "image_url", "image_url": {"url": content}}
                ]
            })
        elif content_type == "text":
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content
            })

    messages.append({
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Опиши это изображение подробно, извлеки весь текст если есть."
            },
            {"type": "image_url", "image_url": {"url": image_data_url}}
        ]
    })

    return messages


def _call_openrouter_for_image(messages: list[dict],
                               api_key: str,
                               model: str,
                               origin: str | None) -> str:
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
        "max_tokens": int(os.getenv("MAX_COMPLETION_TOKENS", 4096)),
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
    message = data.get("choices", [{}])[0].get("message") or {}
    content = message.get("content")
    if not content:
        logger.warning("[IMAGE ANALYSIS] Пустой ответ от OpenRouter: %s", data)
        return "Не удалось получить описание изображения."

    if isinstance(content, list):
        return "".join(chunk.get("text", "") for chunk in content if isinstance(chunk, dict)) or \
            "Не удалось получить описание изображения."

    return str(content)

# -------------------------------
# Public chat API for WebUI
# -------------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
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
            incoming_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

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
        )
        sanitized_model = (payload.open_router_model or "").strip() if payload.open_router_model else None
        if sanitized_model:
            THREAD_MODEL_OVERRIDES[current_thread_id] = sanitized_model
    except RuntimeError as exc:
        logger.error("[CHAT ENDPOINT] RuntimeError: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        status="Message processed",
        response=response_text,
        thread_id=current_thread_id,
    )


@app.post("/image/analyze", response_model=ImageAnalysisResponse)
async def analyze_image_endpoint(
    request: Request,
    file: UploadFile = File(...),
    thread_id: str = Form(...),
    history: str = Form("[]"),
    open_router_api_key: str | None = Form(default=None),
    open_router_model: str | None = Form(default=None),
    system_prompt: str | None = Form(default=None),
    history_message_count: int = Form(default=5),
):
    logger.info(
        "[IMAGE ANALYSIS] Получен запрос: thread_id=%s, filename=%s, content_type=%s",
        thread_id,
        file.filename,
        file.content_type,
    )

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Поддерживаются только изображения")

    actual_api_key = open_router_api_key or OPENROUTER_API_KEY
    sanitized_model = (open_router_model or "").strip()
    if sanitized_model:
        THREAD_MODEL_OVERRIDES[thread_id] = sanitized_model

    model_from_thread = THREAD_MODEL_OVERRIDES.get(thread_id)
    actual_model = model_from_thread or OPENROUTER_MODEL

    if not actual_api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API ключ не настроен")
    if not actual_model:
        raise HTTPException(status_code=400, detail="OpenRouter модель не настроена")

    try:
        history_payload = json.loads(history) if history else []
        if not isinstance(history_payload, list):
            raise ValueError("history should be a list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("[IMAGE ANALYSIS] Некорректный формат history: %s", exc)
        raise HTTPException(status_code=400, detail="Некорректный формат истории") from exc

    try:
        file_bytes = await file.read()
    except Exception as exc:
        logger.error("[IMAGE ANALYSIS] Не удалось прочитать файл: %s", exc)
        raise HTTPException(status_code=500, detail="Не удалось прочитать файл") from exc

    encoded = base64.b64encode(file_bytes).decode("utf-8")
    data_url = f"data:{file.content_type};base64,{encoded}"

    messages = _build_image_conversation(
        history=history_payload,
        thread_id=thread_id,
        history_limit=history_message_count,
        system_prompt=system_prompt,
        image_data_url=data_url,
    )

    origin = request.headers.get("Origin") or request.headers.get("Referer")
    response_text = _call_openrouter_for_image(messages, actual_api_key, actual_model, origin)

    return ImageAnalysisResponse(
        status="Image processed",
        response=response_text,
        thread_id=thread_id,
        image=ImagePayload(content=data_url, content_type=file.content_type or "image/*"),
    )

# -------------------------------
# ✅ Google Search Console верификация
# -------------------------------
@app.get("/google{rest_of_path:path}")
async def serve_google_verification(rest_of_path: str):
    """
    Отдаёт HTML-файлы верификации Google (googleXXXX.html)
    """
    file_path = os.path.join(WEBUI_DIR, f"google{rest_of_path}")
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Not Found")

# -------------------------------
# Sitemap для Google и других поисковиков
# -------------------------------
@app.get("/sitemap.xml")
async def serve_sitemap():
    """
    Отдаёт sitemap.xml для поисковых систем
    """
    file_path = os.path.join(WEBUI_DIR, "sitemap.xml")
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Not Found")

# -------------------------------
# Robots.txt для поисковиков
# -------------------------------
@app.get("/robots.txt")
async def serve_robots():
    """
    Отдаёт robots.txt для поисковых систем
    """
    file_path = os.path.join(WEBUI_DIR, "robots.txt")
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Not Found")

# -------------------------------
# ✅ Новый безопасный маршрут
# -------------------------------
@app.get("/")
async def root_redirect():
    """
    Главная страница — перенаправляем на WebUI.
    """
    if os.path.exists(os.path.join(WEBUI_DIR, "index.html")):
        return FileResponse(os.path.join(WEBUI_DIR, "index.html"))
    return {"service": "IgorekChatBot API", "status": "alive"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
