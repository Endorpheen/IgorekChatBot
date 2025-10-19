from __future__ import annotations

import logging
import re

from .settings import Settings


class MaskSecretsFilter(logging.Filter):
    _patterns = [
        re.compile(r"sk-[a-zA-Z0-9]{5,}", re.IGNORECASE),
        re.compile(r"Bearer\s+[a-zA-Z0-9\-_.]{5,}", re.IGNORECASE),
    ]

    @classmethod
    def _mask(cls, value: str) -> str:
        result = value
        for pattern in cls._patterns:
            result = pattern.sub(lambda match: f"{match.group(0)[:6]}***", result)
        return result

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if isinstance(record.msg, str):
            record.msg = self._mask(record.msg)
        if record.args:
            record.args = tuple(self._mask(arg) if isinstance(arg, str) else arg for arg in record.args)  # type: ignore[assignment]
        return True


class IgnoreScannerAccessFilter(logging.Filter):
    _blocked_prefixes = (
        "/wp-admin",
        "/wordpress",
        "/.env",
        "/phpinfo",
        "/.git",
    )
    _blocked_exact = ("/robots.txt", "robots.txt")

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        path = self._extract_path(record)
        if not path:
            return True

        status_code = self._extract_status_code(record)
        if status_code not in (None, 404):
            return True

        normalized = self._normalize_path(path)
        if self._matches_blocked(normalized):
            return False

        return True

    @staticmethod
    def _extract_path(record: logging.LogRecord) -> str | None:
        args = record.args
        if isinstance(args, dict):
            candidate = args.get("path")
            if candidate:
                return str(candidate)
        elif isinstance(args, tuple) and len(args) >= 3:
            candidate = args[2]
            if candidate:
                return str(candidate)

        msg = record.getMessage() if record.msg else ""
        match = re.search(r'"[A-Z]+\s+([^\s"]+)', msg)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_status_code(record: logging.LogRecord) -> int | None:
        for attr in ("status_code", "status"):
            value = getattr(record, attr, None)
            if isinstance(value, int):
                return value

        args = record.args
        if isinstance(args, dict):
            value = args.get("status_code")
            if isinstance(value, int):
                return value
        elif isinstance(args, tuple) and len(args) >= 5:
            value = args[4]
            if isinstance(value, int):
                return value
        return None

    def _matches_blocked(self, path: str) -> bool:
        if path in self._blocked_exact:
            return True

        return any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in self._blocked_prefixes
        )

    @staticmethod
    def _normalize_path(path: str) -> str:
        result = path.split("?", 1)[0].split("#", 1)[0]
        result = re.sub(r"/{2,}", "/", result.strip())
        if not result.startswith("/"):
            result = f"/{result}"
        return result.lower()


def setup_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("igorek.api")
    logger.setLevel(settings.log_level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        handler.addFilter(MaskSecretsFilter())
        logger.addHandler(handler)
    logger.propagate = False

    _attach_uvicorn_filters(IgnoreScannerAccessFilter())
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("igorek.api")


def _attach_uvicorn_filters(filter_instance: logging.Filter) -> None:
    def _already_has(logger: logging.Logger) -> bool:
        return any(isinstance(existing, filter_instance.__class__) for existing in logger.filters)

    for name in ("uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        if not _already_has(uvicorn_logger):
            uvicorn_logger.addFilter(filter_instance)
