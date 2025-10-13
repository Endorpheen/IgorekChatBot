from __future__ import annotations

import requests
from langchain.tools import tool

from app.logging import get_logger
from app.settings import get_settings

logger = get_logger()
settings = get_settings()


def _ensure_tool():
    @tool
    def run_code_in_sandbox(code: str):
        """Выполняет код в песочнице."""
        logger.info("[TOOL] Вызов run_code_in_sandbox с кодом: %s", code)
        try:
            response = requests.post(
                settings.sandbox_service_url,
                json={"language": "python", "code": code, "timeout": 5},
                timeout=7,
            )
            response.raise_for_status()
            data = response.json()
            if data["exit_code"] == 0:
                return f"Результат выполнения\n{data['stdout']}"
            return f"Ошибка выполнения\n{data['stderr']}"
        except requests.exceptions.RequestException as exc:
            logger.error("[TOOL] Ошибка при обращении к песочнице: %s", exc)
            return "Ошибка: не удалось связаться с сервисом выполнения кода."

    return run_code_in_sandbox


_sandbox_tool = None


def get_sandbox_tool():
    global _sandbox_tool
    if _sandbox_tool is None:
        _sandbox_tool = _ensure_tool()
    return _sandbox_tool
