#!/usr/bin/env python3
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

import json
import requests
import uvicorn
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

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    history: list | None = None

class ChatResponse(BaseModel):
    status: str
    response: str
    thread_id: str | None = None

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
print(f"TELEGRAM_BOT_TOKEN: '{TELEGRAM_BOT_TOKEN}'")
if not TELEGRAM_BOT_TOKEN:
    print("TELEGRAM_BOT_TOKEN not set in .env")
    sys.exit(1)

ALLOWED_USER_IDS = {310176382}

# Хранение истории бесед по user_id
user_histories = {}


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-9;]*[mGKF]")
CARRIAGE_RETURN_RE = re.compile(r"\r(?!\n)")


def sanitize_output(text: str) -> str:
    without_cr = CARRIAGE_RETURN_RE.sub("\n", text)
    return ANSI_ESCAPE_RE.sub("", without_cr)


def call_ai_query(prompt: str, history: list = None) -> str:
    """Run mcp-cli ai-query and return textual response."""
    logger.info("call_ai_query: prompt=%s", prompt)

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            data = {"query": prompt, "history": history}
            json.dump(data, f)
            temp_file = f.name

        cmd = [sys.executable, "mcp-cli.py", "ai-query", "--input-file", temp_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            check=False,
            timeout=120,
        )
        os.unlink(temp_file)
    except Exception as exc:  # pragma: no cover - subprocess failure
        raise RuntimeError(f"Не удалось выполнить ai-query: {exc}") from exc

    stdout_raw = result.stdout or ""
    stderr_raw = result.stderr or ""

    stdout = sanitize_output(stdout_raw).strip()
    stderr = sanitize_output(stderr_raw).strip()

    if result.returncode != 0:
        raise RuntimeError(
            f"ai-query завершился с кодом {result.returncode}: {stderr or 'stderr пуст'}"
        )

    if not stdout:
        logger.warning("Получен пустой ответ от ai-query. stderr=%s", stderr)
        return "Получен пустой ответ от клиента"

    if stderr:
        logger.debug("ai-query stderr: %s", stderr_raw)

    logger.info("call_ai_query: response=%s", stdout)
    return stdout


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Получен webhook:", data)
    logger.info("Webhook: raw payload=%s", data)
    if "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        from_user = message.get("from")
        user_id = from_user.get("id") if from_user else None
        if user_id not in ALLOWED_USER_IDS:
            print(f"Игнорируем сообщение от неразрешенного пользователя: {user_id}")
            return {"ok": True}
        text = message.get("text", "")
        print(f"Сообщение от chat_id {chat_id}: {text}")
        logger.info("Webhook: user_id=%s text=%s", user_id, text)

        # Инициализировать историю для пользователя, если не существует
        if user_id not in user_histories:
            user_histories[user_id] = []

        # Добавить сообщение пользователя в историю
        user_histories[user_id].append({"type": "user", "content": text})

        # Ограничить историю 20 сообщениями
        if len(user_histories[user_id]) > 20:
            user_histories[user_id] = user_histories[user_id][-20:]

        # Вызвать ai_query через subprocess с историей
        print("Вызываю ai_query...")
        logger.info("Webhook: invoking ai_query for user_id=%s", user_id)
        try:
            response_text = call_ai_query(text, user_histories[user_id][:-1])  # Исключить текущее сообщение
        except RuntimeError as exc:
            response_text = f"Ошибка обработки: {exc}"
            print(response_text)
            logger.exception("Webhook: ai_query failed")
        else:
            # Добавить ответ бота в историю
            user_histories[user_id].append({"type": "bot", "content": response_text})

        print(f"Ответ для отправки: {response_text}")

        # Отправить ответ в Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": response_text[:4096]}  # Ограничение Telegram
        print(f"Отправка в Telegram: {url}")
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            resp_json = resp.json()
            text_sent = resp_json['result']['text']
            print(f"Отправлено: {text_sent[:100]}...")
        else:
            print(f"Ошибка отправки: {resp.status_code}")

    return {"ok": True}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Пустое сообщение недопустимо")

    current_thread_id = payload.thread_id or str(uuid4())
    logger.info("Web UI запрос: thread_id=%s message=%s", current_thread_id, message)

    try:
        response_text = call_ai_query(message, payload.history)
    except RuntimeError as exc:
        logger.exception("Ошибка при выполнении ai-query")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info("Web UI ответ: thread_id=%s response=%s", current_thread_id, response_text)

    return ChatResponse(
        status="Message processed",
        response=response_text,
        thread_id=current_thread_id,
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8018)