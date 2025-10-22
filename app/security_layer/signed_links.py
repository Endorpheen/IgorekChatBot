from __future__ import annotations

import base64
import binascii
import json
import secrets
import hmac
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.logging import get_logger
from app.settings import get_settings


_logger = get_logger()


@dataclass(slots=True)
class SignedPayload:
    resource: str
    data: Dict[str, Any]
    expires_at: int


class SignedLinkManager:
    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        if not secret:
            secret = secrets.token_urlsafe(48)
            _logger.warning(
                "[SIGNED-LINK] secret не задан — ссылки будут недействительны после перезапуска процесса"
            )
        self._secret = secret.encode("utf-8")
        self._ttl = max(30, ttl_seconds)

    def issue(self, resource: str, data: Dict[str, Any], *, ttl: Optional[int] = None) -> str:
        lifetime = max(10, ttl or self._ttl)
        payload = {
            "resource": resource,
            "data": data,
            "exp": int(time.time()) + lifetime,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = self._sign(raw)
        token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
        return f"{token}.{signature}"

    def verify(self, token: str) -> SignedPayload:
        try:
            payload_segment, signature = token.split(".", 1)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная ссылка") from exc

        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        try:
            raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        except (ValueError, binascii.Error) as exc:  # type: ignore[name-defined]
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная ссылка") from exc

        expected_signature = self._sign(raw)
        if not hmac.compare_digest(expected_signature, signature):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Подпись недействительна")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная ссылка") from exc

        expires = int(payload.get("exp", 0))
        if expires < int(time.time()):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Ссылка истекла")

        resource = payload.get("resource")
        data = payload.get("data")
        if not isinstance(resource, str) or not isinstance(data, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная ссылка")

        return SignedPayload(resource=resource, data=data, expires_at=expires)

    def _sign(self, raw: bytes) -> str:
        import hashlib

        return hmac.new(self._secret, raw, hashlib.sha256).hexdigest()


_signed_manager: Optional[SignedLinkManager] = None


def get_signed_link_manager() -> SignedLinkManager:
    global _signed_manager
    if _signed_manager is None:
        settings = get_settings()
        _signed_manager = SignedLinkManager(
            secret=settings.signed_link_secret or "",
            ttl_seconds=settings.signed_link_ttl_seconds,
        )
    return _signed_manager
