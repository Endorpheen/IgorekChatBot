#!/usr/bin/env python3
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging
import os
import re
import uvicorn
import requests
from uuid import uuid4
from dotenv import load_dotenv
from pydantic import BaseModel, Field
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
class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    history: list | None = None
    open_router_api_key: str | None = Field(default=None, alias="openRouterApiKey")
    open_router_model: str | None = Field(default=None, alias="openRouterModel")

    class Config:
        allow_population_by_field_name = True

class ChatResponse(BaseModel):
    status: str
    response: str
    thread_id: str | None = None

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
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "x-ai/grok-4-fast:free")

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY не задан — чат работать не будет")

def call_ai_query(prompt: str, history: list = None,
                  user_api_key: str | None = None,
                  user_model: str | None = None) -> str:
    """
    Вызов модели через LangChain с поддержкой function-calling
    """
    actual_api_key = user_api_key or OPENROUTER_API_KEY
    actual_model = user_model or OPENROUTER_MODEL

    logger.debug(f"[AI QUERY] prompt={prompt}")
    logger.debug(f"[AI QUERY] history={history}")
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

    messages = [("system", "You are a helpful AI assistant.")]
    if history:
        for msg in history:
            role = "human" if msg["type"] == "user" else "ai"
            messages.append((role, msg["content"]))
    messages.append(("human", prompt))

    logger.debug(f"[AI QUERY] Отправляем messages={messages}")

    try:
        ai_msg = llm_with_tools.invoke(messages)

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

        messages.append(ai_msg)
        messages.extend(tool_outputs)

        logger.debug(f"[AI QUERY] Сообщения после tool_calls: {messages}")

        final_response = llm_with_tools.invoke(messages)
        logger.debug(f"[AI QUERY] Итоговый ответ: {final_response}")
        return final_response.content

    except Exception as e:
        logger.error(f"[AI QUERY] Ошибка LangChain API: {e}", exc_info=True)
        return f"Ошибка API: {e}"

# -------------------------------
# Public chat API for WebUI
# -------------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    log_payload = payload.dict(by_alias=True)
    if log_payload.get("openRouterApiKey"):
        log_payload["openRouterApiKey"] = "***masked***"
    logger.info("[CHAT ENDPOINT] Входящий payload: %s", log_payload)

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Пустое сообщение недопустимо")

    current_thread_id = payload.thread_id or str(uuid4())
    try:
        response_text = call_ai_query(
            message,
            payload.history,
            payload.open_router_api_key,
            payload.open_router_model
        )
    except RuntimeError as exc:
        logger.error("[CHAT ENDPOINT] RuntimeError: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        status="Message processed",
        response=response_text,
        thread_id=current_thread_id,
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
