#!/usr/bin/env python3
from fastapi import FastAPI, Request
import requests
import subprocess
import sys
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
print(f"TELEGRAM_BOT_TOKEN: '{TELEGRAM_BOT_TOKEN}'")
if not TELEGRAM_BOT_TOKEN:
    print("TELEGRAM_BOT_TOKEN not set in .env")
    sys.exit(1)

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Получен webhook:", data)
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]
        print(f"Сообщение от chat_id {chat_id}: {text}")

        # Вызвать ai_query через subprocess
        print("Вызываю ai_query...")
        try:
            result = subprocess.run([sys.executable, "mcp-cli.py", "ai-query", text],
                                  capture_output=True, text=True, cwd=os.getcwd())
            response_text = result.stdout.strip()
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
            if not response_text:
                response_text = "Получен пустой ответ от клиента"
        except Exception as e:
            response_text = f"Ошибка обработки: {str(e)}"
            print(f"Exception: {e}")

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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8018)