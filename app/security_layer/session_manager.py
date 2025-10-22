from __future__ import annotations

import hmac
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

from fastapi import Request

from app.logging import get_logger
from app.settings import get_settings


_logger = get_logger()


@dataclass(slots=True)
class SessionInfo:
    session_id: str
    issued_at: int
    legacy: bool = False
    token: Optional[str] = None


class SessionManager:
    def __init__(
        self,
        *,
        secret: str,
        ttl_seconds: int,
        cookie_name: str,
        header_name: str,
        legacy_enabled: bool,
        legacy_origins: Iterable[str],
    ) -> None:
        if not secret:
            secret = secrets.token_urlsafe(48)
            _logger.warning(
                "[SESSION] session_secret не задан в окружении — сессии будут сбрасываться при перезапуске"
            )

        self._secret = secret.encode("utf-8")
        self._ttl = max(60, ttl_seconds)
        self._cookie_name = cookie_name
        self._header_name = header_name
        self._legacy_enabled = legacy_enabled
        self._legacy_origins = {origin.rstrip("/") for origin in legacy_origins}
        self._logger = logging.getLogger("igorek.session")

    @property
    def cookie_name(self) -> str:
        return self._cookie_name

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def resolve(self, request: Request) -> Tuple[Optional[SessionInfo], Optional[str]]:
        """
        Возвращает SessionInfo и, при необходимости, новый токен, который нужно выставить в cookie.
        """
        token = self._extract_token(request)
        if token:
            info = self._verify_token(token)
            if info:
                return info, None

        if not self._legacy_enabled:
            return None, None

        legacy_id = self._extract_legacy_id(request)
        if not legacy_id:
            return None, None

        new_token, session_id, issued_at = self._issue_token()
        info = SessionInfo(session_id=session_id, issued_at=issued_at, legacy=True, token=new_token)
        self._logger.info(
            "[SESSION] Legacy session accepted: legacy_id=%s origin=%s agent=%s",
            legacy_id,
            self._extract_origin(request) or "unknown",
            request.headers.get("User-Agent", "n/a"),
        )
        return info, new_token

    def require_session(self, request: Request) -> SessionInfo:
        info, _ = self.resolve(request)
        if not info:
            raise UnauthorizedSessionError("Сессия отсутствует или истекла")
        return info

    def _issue_token(self) -> Tuple[str, str, int]:
        session_id = secrets.token_urlsafe(18)
        issued_at = int(time.time())
        payload = f"{session_id}.{issued_at}"
        signature = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}", session_id, issued_at

    def _verify_token(self, token: str) -> Optional[SessionInfo]:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        session_id, issued_str, signature = parts
        expected = hmac.new(self._secret, f"{session_id}.{issued_str}".encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            self._logger.warning("[SESSION] Invalid signature for token (session_id=%s)", session_id)
            return None
        try:
            issued_at = int(issued_str)
        except ValueError:
            return None

        if issued_at + self._ttl < int(time.time()):
            self._logger.info("[SESSION] Token expired: session_id=%s", session_id)
            return None

        return SessionInfo(session_id=session_id, issued_at=issued_at, legacy=False, token=token)

    def _extract_token(self, request: Request) -> Optional[str]:
        header_token = request.headers.get(self._header_name)
        if header_token:
            return header_token.strip()
        cookie_token = request.cookies.get(self._cookie_name)
        if cookie_token:
            return cookie_token.strip()
        return None

    def _extract_legacy_id(self, request: Request) -> Optional[str]:
        legacy_id = request.headers.get("X-Client-Session") or request.cookies.get("client_session")
        if not legacy_id:
            return None
        origin = self._extract_origin(request)
        candidate_origins = []
        if origin:
            candidate_origins.append(origin.rstrip("/"))
        else:
            host = request.headers.get("Host")
            if host:
                candidate_origins.append(f"{request.url.scheme}://{host.rstrip('/')}")

        for candidate in candidate_origins:
            if candidate in self._legacy_origins:
                return legacy_id.strip()
        self._logger.warning(
            "[SESSION] Legacy session rejected: session_id=%s origin=%s",
            legacy_id,
            origin or "unknown",
        )
        return None

    @staticmethod
    def _extract_origin(request: Request) -> Optional[str]:
        origin = request.headers.get("Origin")
        if origin:
            return origin
        referer = request.headers.get("Referer")
        if not referer:
            return None
        parsed = urlparse(referer)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"


class UnauthorizedSessionError(RuntimeError):
    pass


_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        settings = get_settings()
        _session_manager = SessionManager(
            secret=settings.session_secret or "",
            ttl_seconds=settings.session_ttl_seconds,
            cookie_name=settings.session_cookie_name,
            header_name=settings.session_header_name,
            legacy_enabled=settings.legacy_session_compat_enabled,
            legacy_origins=settings.legacy_session_allowed_origins,
        )
    return _session_manager
