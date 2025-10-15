from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from app.logging import get_logger
from app.settings import get_settings


@dataclass(frozen=True)
class MCPSettings:
    enabled: bool
    secret_key: bytes
    allow_internal: bool
    default_timeout_s: int
    max_output_kb: int
    max_calls_per_minute_per_thread: int
    db_path: Path
    log_path: Path
    concurrency_limit: int


def _decode_secret(raw_value: str | None) -> bytes:
    if not raw_value:
        raise RuntimeError("MCP secret key is not configured")

    prepared = raw_value.strip()
    if prepared.startswith("base64:"):
        prepared = prepared.split(":", 1)[1]

    try:
        decoded = base64.urlsafe_b64decode(prepared)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise RuntimeError("Invalid MCP secret key") from exc

    if len(decoded) < 32:
        raise RuntimeError("MCP secret key is too short")

    return prepared.encode()


def get_mcp_settings() -> MCPSettings:
    settings = get_settings()
    logger = get_logger()

    db_path = settings.mcp_db_path
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    log_path = settings.mcp_log_path
    if not log_path.is_absolute():
        log_path = (Path.cwd() / log_path).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not settings.mcp_feature_enabled:
        logger.info("[MCP] MCP feature is disabled via MCP_FEATURE_ENABLED flag")

    secret = _decode_secret(settings.mcp_secret_key)

    return MCPSettings(
        enabled=settings.mcp_feature_enabled,
        secret_key=secret,
        allow_internal=settings.mcp_allow_internal,
        default_timeout_s=settings.mcp_default_timeout_s,
        max_output_kb=settings.mcp_max_output_kb,
        max_calls_per_minute_per_thread=settings.mcp_max_calls_per_minute_per_thread,
        db_path=db_path,
        log_path=log_path,
        concurrency_limit=max(1, settings.mcp_concurrency_limit),
    )
