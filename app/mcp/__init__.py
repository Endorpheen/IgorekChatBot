"""Поддержка MCP-серверов для Игорька."""

from __future__ import annotations

from functools import lru_cache

from app.mcp.store import MCPStore
from app.mcp.logger import get_mcp_logger
from app.mcp.settings import get_mcp_settings

__all__ = ["MCPStore", "get_mcp_store", "get_mcp_logger", "get_mcp_settings"]


@lru_cache
def get_mcp_store() -> MCPStore:
    settings = get_mcp_settings()
    return MCPStore(settings)
