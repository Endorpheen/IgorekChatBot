#!/usr/bin/env python3
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging
import os
import re
import requests
import uvicorn
from uuid import uuid4
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_bot")

app = FastAPI()

ALLOW_ORIGINS = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
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

class ChatResponse(BaseModel):
    status: str
    response: str
    thread_id: str | None = None

# -------------------------------
# OpenRouter API
# -------------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY не задан — чат работать не будет")

def call_ai_query(prompt: str, history: list = None) -> str:
    """
    Упрощённый вызов модели напрямую через OpenRouter API
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY отсутствует")

    messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
    if history:
        for msg in history:
            role = "user" if msg["type"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "IgorekChatBot",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Ошибка OpenRouter API: {e}")
        return f"Ошибка API: {e}"

# -------------------------------
# Public chat API for WebUI
# -------------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Пустое сообщение недопустимо")

    current_thread_id = payload.thread_id or str(uuid4())
    try:
        response_text = call_ai_query(message, payload.history)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        status="Message processed",
        response=response_text,
        thread_id=current_thread_id,
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
