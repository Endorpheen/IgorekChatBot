from __future__ import annotations

import logging
import re
from typing import Any

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


def setup_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("igorek.api")
    logger.setLevel(settings.log_level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        handler.addFilter(MaskSecretsFilter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("igorek.api")
