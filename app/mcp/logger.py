from __future__ import annotations

import logging

from app.logging import MaskSecretsFilter
from app.mcp.settings import MCPSettings, get_mcp_settings


def get_mcp_logger(settings: MCPSettings | None = None) -> logging.Logger:
    resolved_settings = settings or get_mcp_settings()
    logger = logging.getLogger("igorek.mcp")
    if not logger.handlers:
        handler = logging.FileHandler(resolved_settings.log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s")
        )
        handler.addFilter(MaskSecretsFilter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
