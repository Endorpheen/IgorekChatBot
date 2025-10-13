from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import requests
from langchain.tools import tool

from app.logging import get_logger
from app.settings import Settings, get_settings


class GoogleSearchProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger()
        self._rate_timestamps: Deque[float] = deque()
        self._cache: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
        self._lock = threading.Lock()
        self._tool = tool(self._execute)

    def _log(self, status: str, results_count: int, thread_id: Optional[str]) -> None:
        self._logger.info(
            "[GOOGLE SEARCH] status=%s results=%s thread_id=%s",
            status,
            results_count,
            thread_id or "unknown",
        )

    def _normalize_query(self, query: str) -> str:
        return re.sub(r"\s+", " ", query.strip().lower())

    def _execute(self, query: str, thread_id: Optional[str] = None) -> str:
        """Выполняет web-поиск через Google Custom Search API и возвращает JSON с результатами."""
        sanitized_query = (query or "").strip()
        if not sanitized_query:
            self._log("error", 0, thread_id)
            return "Ошибка: поисковый запрос пуст."

        if not self._settings.google_api_key or not self._settings.google_cse_id:
            self._log("error", 0, thread_id)
            return "Ошибка: сервис поиска недоступен — API ключ не настроен."

        now = time.time()
        cache_key = self._normalize_query(sanitized_query)

        with self._lock:
            while self._rate_timestamps and now - self._rate_timestamps[0] > self._settings.google_search_rate_window:
                self._rate_timestamps.popleft()

            if len(self._rate_timestamps) >= self._settings.google_search_rate_limit:
                retry_after = max(
                    int(
                        self._settings.google_search_rate_window
                        - (now - self._rate_timestamps[0])
                    )
                    + 1,
                    1,
                )
                self._log("error", 0, thread_id)
                return f"Ошибка: превышен лимит запросов к поиску. Попробуйте через {retry_after} сек."

            self._rate_timestamps.append(now)

            cached_entry = self._cache.get(cache_key)
            if cached_entry and now - cached_entry[0] <= self._settings.google_search_cache_ttl:
                cached_results = cached_entry[1]
                self._log("success", len(cached_results), thread_id)
                return json.dumps(
                    {
                        "query": sanitized_query,
                        "cached": True,
                        "results": cached_results,
                    },
                    ensure_ascii=False,
                )

        params = {
            "key": self._settings.google_api_key,
            "cx": self._settings.google_cse_id,
            "q": sanitized_query,
            "num": self._settings.google_search_max_results,
        }

        try:
            response = requests.get(
                self._settings.google_search_endpoint,
                params=params,
                timeout=10,
            )
        except requests.exceptions.RequestException:
            self._log("error", 0, thread_id)
            return "Ошибка: не удалось связаться с сервисом Google Custom Search."

        if response.status_code == 429:
            self._log("error", 0, thread_id)
            return "Ошибка: превышен дневной лимит Google Custom Search. Попробуйте позже."
        if response.status_code == 403:
            self._log("error", 0, thread_id)
            return "Ошибка: доступ к Google Custom Search запрещен. Проверьте квоты и разрешения."

        if not response.ok:
            self._log("error", 0, thread_id)
            return "Ошибка: Google Custom Search вернул ошибку сервера."

        try:
            data = response.json()
        except ValueError:
            self._log("error", 0, thread_id)
            return "Ошибка: некорректный ответ от Google Custom Search."

        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            self._log("success", 0, thread_id)
            return json.dumps(
                {
                    "query": sanitized_query,
                    "cached": False,
                    "results": [],
                },
                ensure_ascii=False,
            )

        search_results: List[Dict[str, str]] = []
        for item in items[: self._settings.google_search_max_results]:
            if not isinstance(item, dict):
                continue
            link = item.get("link")
            title = item.get("title") or item.get("htmlTitle") or ""
            snippet = item.get("snippet") or item.get("htmlSnippet") or ""
            if not link:
                continue
            search_results.append(
                {
                    "title": title.strip(),
                    "link": link,
                    "snippet": re.sub(r"\s+", " ", snippet.strip()),
                }
            )

        with self._lock:
            now_after_call = time.time()
            self._cache[cache_key] = (now_after_call, search_results)
            stale_keys = [
                key
                for key, (timestamp, _value) in self._cache.items()
                if now_after_call - timestamp > self._settings.google_search_cache_ttl * 2
            ]
            for stale_key in stale_keys:
                self._cache.pop(stale_key, None)

        self._log("success", len(search_results), thread_id)
        return json.dumps(
            {
                "query": sanitized_query,
                "cached": False,
                "results": search_results,
            },
            ensure_ascii=False,
        )

    def get_tool(self):
        return self._tool


_provider: Optional[GoogleSearchProvider] = None


def get_google_search_tool() -> Any:
    global _provider
    if _provider is None:
        _provider = GoogleSearchProvider(get_settings())
    return _provider.get_tool()
