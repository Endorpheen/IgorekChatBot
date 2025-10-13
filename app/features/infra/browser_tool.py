from __future__ import annotations

import requests
from langchain.tools import tool

from app.logging import get_logger
from app.settings import get_settings

logger = get_logger()
settings = get_settings()


@tool
def browse_website(url: str) -> str:
    """
    Открывает указанный URL в браузере и возвращает его текстовое содержимое.
    """
    logger.info("[TOOL] Вызов browse_website с URL: %s", url)
    try:
        response = requests.post(
            settings.browser_service_url,
            json={"url": url},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if data["error"]:
            return f"Ошибка при просмотре сайта: {data['error']}"
        return f"Содержимое страницы {url}:\n\n{data['content']}"
    except requests.exceptions.RequestException as exc:
        logger.error("[TOOL] Ошибка при обращении к браузеру: %s", exc)
        return "Ошибка: не удалось связаться с сервисом браузера."
