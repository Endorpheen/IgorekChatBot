#!/usr/bin/env python3
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import logging
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
import uvicorn
import requests
import base64
import json
import mimetypes
from uuid import uuid4
from typing import Literal, Dict, List, Optional, Tuple, Deque
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel as LangchainBaseModel, Field as LangchainField
from langchain.tools import tool
from langchain_core.messages import ToolMessage

from image_generation import ImageGenerationError, get_model_capabilities, image_manager

try:
    import multipart  # type: ignore
except ImportError:  # pragma: no cover - fallback when python-multipart не установлен
    multipart = None

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "DEBUG"),  # DEBUG для максимальной детализации
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_bot")

MAX_IMAGE_UPLOAD_MB = int(os.getenv("MAX_IMAGE_UPLOAD_MB", "20"))
MAX_IMAGE_UPLOAD_BYTES = MAX_IMAGE_UPLOAD_MB * 1024 * 1024
os.environ.setdefault("PYTHON_MULTIPART_LIMIT", str(MAX_IMAGE_UPLOAD_BYTES))

if multipart and hasattr(multipart, "multipart"):
    if hasattr(multipart.multipart, "MAX_MEMORY_SIZE"):
        multipart.multipart.MAX_MEMORY_SIZE = MAX_IMAGE_UPLOAD_BYTES
    if hasattr(multipart.multipart, "DEFAULT_MAX_MEMORY_SIZE"):
        multipart.multipart.DEFAULT_MAX_MEMORY_SIZE = MAX_IMAGE_UPLOAD_BYTES

UPLOAD_DIR_NAME = os.getenv("UPLOAD_DIR", "uploads")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR_ABS", Path.cwd() / UPLOAD_DIR_NAME)).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_URL_PREFIX = os.getenv("UPLOAD_URL_PREFIX", "/uploads")
UPLOAD_TTL_DAYS = int(os.getenv("UPLOAD_TTL_DAYS", "7"))
UPLOAD_MAX_TOTAL_MB = int(os.getenv("UPLOAD_MAX_TOTAL_MB", "1024"))
UPLOAD_CLEAN_INTERVAL_SECONDS = int(os.getenv("UPLOAD_CLEAN_INTERVAL_SECONDS", "3600"))
UPLOAD_MAX_TOTAL_BYTES = UPLOAD_MAX_TOTAL_MB * 1024 * 1024

cleanup_task: asyncio.Task | None = None

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
GOOGLE_SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
GOOGLE_SEARCH_MAX_RESULTS = max(1, min(10, int(os.getenv("GOOGLE_SEARCH_MAX_RESULTS", "5"))))
GOOGLE_SEARCH_RATE_LIMIT = max(1, int(os.getenv("GOOGLE_SEARCH_RATE_LIMIT", "5")))
GOOGLE_SEARCH_RATE_WINDOW = max(1, int(os.getenv("GOOGLE_SEARCH_RATE_WINDOW", "60")))
GOOGLE_SEARCH_CACHE_TTL = max(1, int(os.getenv("GOOGLE_SEARCH_CACHE_TTL", "30")))

_google_rate_timestamps: Deque[float] = deque()
_google_cache: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
_google_lock = threading.Lock()


def _delete_file(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.warning("[UPLOAD CLEAN] Не удалось удалить файл %s: %s", path, exc)
        return False


def _cleanup_uploads_once() -> tuple[int, int]:
    removed = 0
    now = datetime.utcnow()
    ttl_delta = timedelta(days=UPLOAD_TTL_DAYS) if UPLOAD_TTL_DAYS > 0 else None

    if ttl_delta:
        cutoff = now - ttl_delta
        for path in list(UPLOAD_DIR.rglob("*")):
            if not path.is_file():
                continue
            try:
                mtime = datetime.utcfromtimestamp(path.stat().st_mtime)
            except OSError as exc:
                logger.warning("[UPLOAD CLEAN] Не удалось получить время файла %s: %s", path, exc)
                continue
            if mtime < cutoff:
                if _delete_file(path):
                    removed += 1

    files: list[tuple[Path, int, float]] = []
    total_size = 0
    for path in UPLOAD_DIR.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError as exc:
            logger.warning("[UPLOAD CLEAN] Не удалось получить статистику файла %s: %s", path, exc)
            continue
        files.append((path, stat.st_size, stat.st_mtime))
        total_size += stat.st_size

    if UPLOAD_MAX_TOTAL_BYTES > 0 and total_size > UPLOAD_MAX_TOTAL_BYTES:
        files.sort(key=lambda item: item[2])  # oldest first
        index = 0
        while total_size > UPLOAD_MAX_TOTAL_BYTES and index < len(files):
            path, size, _ = files[index]
            index += 1
            if _delete_file(path):
                removed += 1
                total_size -= size

    logger.info(
        "[UPLOAD CLEAN] removed=%s total_size=%.2f MB",
        removed,
        total_size / (1024 * 1024),
    )

    return removed, total_size


async def _cleanup_uploads_periodically() -> None:
    loop = asyncio.get_running_loop()
    interval = max(UPLOAD_CLEAN_INTERVAL_SECONDS, 60)
    while True:
        try:
            await loop.run_in_executor(None, _cleanup_uploads_once)
        except Exception as exc:  # pragma: no cover
            logger.error("[UPLOAD CLEAN] Ошибка при очистке: %s", exc, exc_info=True)
        await asyncio.sleep(interval)

app = FastAPI(max_request_size=MAX_IMAGE_UPLOAD_BYTES + 1024 * 1024)

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

    @app.get("/favicon.ico")
    async def serve_favicon():
        favicon_path = os.path.join(WEBUI_DIR, "favicon.ico")
        if os.path.isfile(favicon_path):
            return FileResponse(favicon_path)
        raise HTTPException(status_code=404, detail="Not Found")

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

app.mount(UPLOAD_URL_PREFIX, StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

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
    filename: str
    url: str
    content_type: str | None = None


class ImageAnalysisResponse(BaseModel):
    status: str
    response: str
    thread_id: str
    image: ImagePayload | None = None
    images: List[ImagePayload] | None = None


class ImageGenerateRequest(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024
    steps: int = 4

    model_config = ConfigDict(extra="forbid")


class ImageJobCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class ImageJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    provider: str
    prompt: str
    width: int
    height: int
    steps: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class ImageCapabilitiesResponse(BaseModel):
    model: str
    steps_allowed: list[int]
    default_steps: int
    sizes_allowed: list[int]
    default_size: int


def _require_csrf_token(request: Request) -> None:
    cookie_token = request.cookies.get("csrf-token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail={"code": "csrf_failed", "message": "CSRF проверка не пройдена"})


def _require_session_id(request: Request) -> str:
    session_id = (request.headers.get("X-Client-Session") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail={"code": "missing_session", "message": "Не удалось определить сессию клиента"})
    return session_id


def _extract_together_key(request: Request) -> str:
    together_key = (request.headers.get("X-Together-Key") or "").strip()
    if not together_key:
        raise HTTPException(status_code=400, detail={"code": "missing_key", "message": "Заголовок X-Together-Key обязателен"})
    return together_key


def _image_error_to_http(exc: ImageGenerationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.error_code, "message": str(exc)})

# -------------------------------
# LangChain Tools
# -------------------------------


def _log_google_search(status: str, results_count: int, thread_id: Optional[str]) -> None:
    logger.info(
        "[GOOGLE SEARCH] status=%s results=%s thread_id=%s",
        status,
        results_count,
        thread_id or "unknown",
    )


def _normalize_google_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


@tool
def google_search(query: str, thread_id: Optional[str] = None) -> str:
    """Выполняет web-поиск через Google Custom Search API и возвращает JSON с результатами."""
    sanitized_query = (query or "").strip()
    if not sanitized_query:
        _log_google_search("error", 0, thread_id)
        return "Ошибка: поисковый запрос пуст."

    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        _log_google_search("error", 0, thread_id)
        return "Ошибка: сервис поиска недоступен — API ключ не настроен."

    now = time.time()
    cache_key = _normalize_google_query(sanitized_query)

    with _google_lock:
        while _google_rate_timestamps and now - _google_rate_timestamps[0] > GOOGLE_SEARCH_RATE_WINDOW:
            _google_rate_timestamps.popleft()

        if len(_google_rate_timestamps) >= GOOGLE_SEARCH_RATE_LIMIT:
            retry_after = max(int(GOOGLE_SEARCH_RATE_WINDOW - (now - _google_rate_timestamps[0])) + 1, 1)
            _log_google_search("error", 0, thread_id)
            return f"Ошибка: превышен лимит запросов к поиску. Попробуйте через {retry_after} сек."

        _google_rate_timestamps.append(now)

        cached_entry = _google_cache.get(cache_key)
        if cached_entry and now - cached_entry[0] <= GOOGLE_SEARCH_CACHE_TTL:
            cached_results = cached_entry[1]
            _log_google_search("success", len(cached_results), thread_id)
            return json.dumps({
                "query": sanitized_query,
                "cached": True,
                "results": cached_results,
            }, ensure_ascii=False)

    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": sanitized_query,
        "num": GOOGLE_SEARCH_MAX_RESULTS,
    }

    try:
        response = requests.get(GOOGLE_SEARCH_ENDPOINT, params=params, timeout=10)
    except requests.exceptions.RequestException:
        _log_google_search("error", 0, thread_id)
        return "Ошибка: не удалось связаться с сервисом Google Custom Search."

    if response.status_code == 429:
        _log_google_search("error", 0, thread_id)
        return "Ошибка: превышен дневной лимит Google Custom Search. Попробуйте позже."
    if response.status_code == 403:
        _log_google_search("error", 0, thread_id)
        return "Ошибка: доступ к Google Custom Search запрещен. Проверьте квоты и разрешения."

    if not response.ok:
        _log_google_search("error", 0, thread_id)
        return "Ошибка: Google Custom Search вернул ошибку сервера."

    try:
        data = response.json()
    except ValueError:
        _log_google_search("error", 0, thread_id)
        return "Ошибка: некорректный ответ от Google Custom Search."

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        _log_google_search("success", 0, thread_id)
        return json.dumps({
            "query": sanitized_query,
            "cached": False,
            "results": [],
        }, ensure_ascii=False)

    search_results: List[Dict[str, str]] = []
    for item in items[:GOOGLE_SEARCH_MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        title = item.get("title") or item.get("htmlTitle") or ""
        snippet = item.get("snippet") or item.get("htmlSnippet") or ""
        if not link:
            continue
        search_results.append({
            "title": title.strip(),
            "link": link,
            "snippet": re.sub(r"\s+", " ", snippet.strip()),
        })

    with _google_lock:
        now_after_call = time.time()
        _google_cache[cache_key] = (now_after_call, search_results)
        stale_keys = [key for key, (timestamp, _) in _google_cache.items() if now_after_call - timestamp > GOOGLE_SEARCH_CACHE_TTL * 2]
        for stale_key in stale_keys:
            _google_cache.pop(stale_key, None)

    _log_google_search("success", len(search_results), thread_id)

    return json.dumps({
        "query": sanitized_query,
        "cached": False,
        "results": search_results,
    }, ensure_ascii=False)


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


@app.on_event("startup")
async def _startup_cleanup_task() -> None:
    global cleanup_task
    await image_manager.startup()

    if UPLOAD_CLEAN_INTERVAL_SECONDS > 0:
        cleanup_task = asyncio.create_task(_cleanup_uploads_periodically())
        logger.info(
            "[UPLOAD CLEAN] Фоновая очистка запущена: interval=%ss ttl_days=%s max_total_mb=%s",
            UPLOAD_CLEAN_INTERVAL_SECONDS,
            UPLOAD_TTL_DAYS,
            UPLOAD_MAX_TOTAL_MB,
        )


@app.on_event("shutdown")
async def _shutdown_cleanup_task() -> None:
    global cleanup_task
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        cleanup_task = None
    await image_manager.shutdown()

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
                  messages: list[dict[str, str]] | None = None,
                  thread_id: str | None = None) -> str:
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
    llm_with_tools = llm.bind_tools([run_code_in_sandbox, browse_website, google_search])

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
        max_tool_steps = 5
        for step in range(1, max_tool_steps + 1):
            ai_msg = llm_with_tools.invoke(conversation)

            logger.debug(f"[AI QUERY] Ответ модели (step={step}): {ai_msg}")
            logger.debug(f"[AI QUERY] tool_calls={ai_msg.tool_calls}")

            if not ai_msg.tool_calls:
                return ai_msg.content

            conversation.append(ai_msg)

            tool_outputs: List[ToolMessage] = []
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call.get('name') if isinstance(tool_call, dict) else getattr(tool_call, 'name', 'unknown')
                logger.info("[TOOL RECURSION] step=%s call=%s", step, tool_name)
                tool_args = tool_call.get('args') if isinstance(tool_call, dict) else getattr(tool_call, 'args', {})

                if tool_name == 'run_code_in_sandbox':
                    result = run_code_in_sandbox.run(tool_args)
                elif tool_name == 'browse_website':
                    result = browse_website.run(tool_args)
                elif tool_name == 'google_search':
                    prepared_args = tool_args
                    if isinstance(prepared_args, dict):
                        prepared_args = {
                            **prepared_args,
                            **({"thread_id": thread_id} if thread_id and "thread_id" not in prepared_args else {}),
                        }
                    else:
                        prepared_args = {
                            "query": prepared_args,
                            "thread_id": thread_id,
                        }
                    result = google_search.run(prepared_args)
                else:
                    logger.warning("[TOOL RECURSION] step=%s неизвестный инструмент: %s", step, tool_name)
                    result = f"Unsupported tool: {tool_name}"

                tool_outputs.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call.get("id") if isinstance(tool_call, dict) else getattr(tool_call, 'id', None),
                    )
                )

            conversation.extend(tool_outputs)
            logger.debug(f"[AI QUERY] Сообщения после tool_calls шага {step}: {conversation}")

        logger.error("[TOOL RECURSION] Превышен лимит последовательных вызовов инструментов")
        return "Превышен лимит последовательных вызовов инструментов."

    except Exception as e:
        logger.error(f"[AI QUERY] Ошибка LangChain API: {e}", exc_info=True)
        return f"Ошибка API: {e}"


def _build_image_conversation(history: list[dict],
                              thread_id: str,
                              history_limit: int,
                              system_prompt: str | None,
                              image_data_urls: List[str],
                              prompt: str | None) -> list[dict]:
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

        if role not in {"user", "bot"}:
            continue

        if content_type == "image" and role == "user":
            data_url = None
            if isinstance(content, str) and content.startswith("data:"):
                data_url = content
            else:
                file_name = entry.get("fileName") or entry.get("filename")
                if file_name:
                    file_path = UPLOAD_DIR / file_name
                    if file_path.exists():
                        mime_type = entry.get("mimeType") or entry.get("mime_type") or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                        try:
                            with open(file_path, "rb") as stored_file:
                                encoded = base64.b64encode(stored_file.read()).decode("utf-8")
                                data_url = f"data:{mime_type};base64,{encoded}"
                        except OSError as exc:
                            logger.warning("[IMAGE ANALYSIS] Не удалось прочитать файл истории %s: %s", file_path, exc)

            if data_url:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Анализируй это изображение."},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                })
        elif content_type == "text" and isinstance(content, str):
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content
            })

    user_prompt = (prompt or "").strip() or "Опиши изображения подробно, извлеки весь текст если есть."

    final_content: List[dict] = [{
        "type": "text",
        "text": user_prompt
    }]

    for image_url in image_data_urls:
        final_content.append({
            "type": "image_url",
            "image_url": {"url": image_url}
        })

    messages.append({
        "role": "user",
        "content": final_content
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
            thread_id=current_thread_id,
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
    files: List[UploadFile] | None = File(default=None),
    thread_id: str = Form(...),
    message: str = Form(""),
    history: str = Form("[]"),
    open_router_api_key: str | None = Form(default=None),
    open_router_model: str | None = Form(default=None),
    system_prompt: str | None = Form(default=None),
    history_message_count: int = Form(default=5),
):
    files = files or []

    if not files and not message.strip():
        raise HTTPException(status_code=422, detail="Требуется текст или хотя бы одно изображение")

    logger.info(
        "[IMAGE ANALYSIS] Запрос: thread_id=%s, файлов=%s, has_text=%s",
        thread_id,
        len(files),
        bool(message.strip()),
    )

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

    encoded_images: List[str] = []
    response_images: List[ImagePayload] = []

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
        file_path = UPLOAD_DIR / unique_name

        try:
            file_bytes = await upload.read()
        except Exception as exc:
            logger.error("[IMAGE ANALYSIS] Не удалось прочитать файл %s: %s", upload.filename, exc)
            raise HTTPException(status_code=500, detail="Не удалось прочитать файл") from exc
        finally:
            await upload.close()

        try:
            with open(file_path, "wb") as stored_file:
                stored_file.write(file_bytes)
        except OSError as exc:
            logger.error("[IMAGE ANALYSIS] Не удалось сохранить файл %s: %s", file_path, exc)
            raise HTTPException(status_code=500, detail="Не удалось сохранить файл") from exc

        encoded = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{upload.content_type};base64,{encoded}"
        encoded_images.append(data_url)
        response_images.append(ImagePayload(
            filename=unique_name,
            url=f"{UPLOAD_URL_PREFIX.rstrip('/')}/{unique_name}",
            content_type=upload.content_type,
        ))

    messages = _build_image_conversation(
        history=history_payload,
        thread_id=thread_id,
        history_limit=history_message_count,
        system_prompt=system_prompt,
        image_data_urls=encoded_images,
        prompt=message,
    )

    origin = request.headers.get("Origin") or request.headers.get("Referer")
    try:
        response_text = _call_openrouter_for_image(messages, actual_api_key, actual_model, origin)
    except HTTPException as exc:
        if exc.status_code == 502 and "does not support" in str(exc.detail).lower():
            raise HTTPException(status_code=400, detail="Выбранная модель не поддерживает работу с изображениями.") from exc
        raise

    logger.info("[IMAGE ANALYSIS] Ответ модели: %s", response_text)

    images_payload = response_images or None

    return ImageAnalysisResponse(
        status="Image processed",
        response=response_text,
        thread_id=thread_id,
        image=images_payload[0] if images_payload else None,
        images=images_payload,
    )


@app.post("/image/generate", response_model=ImageJobCreateResponse)
async def create_image_job(request: Request, payload: ImageGenerateRequest) -> ImageJobCreateResponse:
    _require_csrf_token(request)
    session_id = _require_session_id(request)
    together_key = _extract_together_key(request)

    try:
        job_id = await image_manager.enqueue_job(
            prompt=payload.prompt,
            width=payload.width,
            height=payload.height,
            steps=payload.steps,
            session_id=session_id,
            together_key=together_key,
        )
    except ImageGenerationError as exc:
        raise _image_error_to_http(exc)

    return ImageJobCreateResponse(job_id=job_id, status="queued")


@app.get("/image/jobs/{job_id}", response_model=ImageJobStatusResponse)
async def get_image_job(job_id: str, request: Request) -> ImageJobStatusResponse:
    session_id = _require_session_id(request)

    try:
        status = await image_manager.get_job_status(job_id)
    except ImageGenerationError as exc:
        raise _image_error_to_http(exc)

    if not status:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Задача не найдена"})
    if status.session_id != session_id:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ к задаче запрещён"})

    result_url = None
    if status.status == "done" and status.result_path:
        result_url = f"/image/jobs/{job_id}/result"

    return ImageJobStatusResponse(
        job_id=job_id,
        status=status.status,
        provider=status.provider,
        prompt=status.prompt,
        width=status.width,
        height=status.height,
        steps=status.steps,
        created_at=status.created_at,
        updated_at=status.updated_at,
        started_at=status.started_at,
        completed_at=status.completed_at,
        duration_ms=status.duration_ms,
        error_code=status.error_code,
        error_message=status.error_message,
        result_url=result_url,
    )


@app.get("/image/jobs/{job_id}/result")
async def download_image_job_result(job_id: str, request: Request) -> FileResponse:
    session_id = _require_session_id(request)

    try:
        status = await image_manager.get_job_status(job_id)
    except ImageGenerationError as exc:
        raise _image_error_to_http(exc)

    if not status or status.status != "done" or not status.result_path:
        raise HTTPException(status_code=404, detail={"code": "result_unavailable", "message": "Результат ещё не готов"})
    if status.session_id != session_id:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ запрещён"})

    try:
        file_path = Path(status.result_path).resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_path", "message": "Некорректный путь к результату"}) from exc

    output_dir = image_manager.output_dir.resolve()
    try:
        file_path.relative_to(output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ запрещён"}) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Файл результата не найден"})

    return FileResponse(str(file_path), media_type="image/webp")


@app.post("/image/validate")
async def validate_together_key_endpoint(request: Request) -> Dict[str, str]:
    _require_csrf_token(request)
    together_key = _extract_together_key(request)

    try:
        await image_manager.validate_key(together_key)
    except ImageGenerationError as exc:
        raise _image_error_to_http(exc)

    return {"status": "ok"}


@app.get("/image/capabilities", response_model=ImageCapabilitiesResponse)
async def get_image_capabilities_endpoint() -> ImageCapabilitiesResponse:
    data = get_model_capabilities()
    return ImageCapabilitiesResponse(**data)

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
