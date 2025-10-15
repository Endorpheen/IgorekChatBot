from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.logging import get_logger
from app.mcp.schemas import (
    Binding,
    ProbeStatus,
    ServerConfig,
    ServerConfigPublic,
    ServerWithSecrets,
    ToolSchema,
)
from app.mcp.settings import MCPSettings

_TOOLS_CACHE_TTL = timedelta(minutes=10)


class MCPStore:
    def __init__(self, settings: MCPSettings) -> None:
        self._settings = settings
        self._fernet = Fernet(settings.secret_key)
        self._db_path = str(settings.db_path)
        self._lock = asyncio.Lock()
        self._logger = get_logger()
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterable[sqlite3.Connection]:  # type: ignore[override]
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    id TEXT PRIMARY KEY,
                    data BLOB NOT NULL,
                    last_status TEXT,
                    last_checked_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_server_tools (
                    server_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    schema_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (server_id, tool_name)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_bindings (
                    server_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    enabled_tools TEXT NOT NULL,
                    PRIMARY KEY (server_id, thread_id)
                )
                """
            )
            conn.commit()

    def _encrypt(self, config: ServerConfig) -> bytes:
        data = config.model_dump()
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return self._fernet.encrypt(payload)

    def _decrypt(self, blob: bytes) -> ServerConfig:
        try:
            payload = self._fernet.decrypt(blob)
        except InvalidToken as exc:  # pragma: no cover
            raise RuntimeError("Не удалось расшифровать конфигурацию MCP") from exc
        data = json.loads(payload.decode("utf-8"))
        return ServerConfig.model_validate(data)

    async def upsert_server(self, config: ServerConfig) -> None:
        encrypted = self._encrypt(config)

        async with self._lock:
            await asyncio.to_thread(self._upsert_server_sync, config.id, encrypted)

    def _upsert_server_sync(self, server_id: str, blob: bytes) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mcp_servers (id, data, last_status, last_checked_at)
                VALUES (?, ?, NULL, NULL)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data
                """,
                (server_id, blob),
            )
            conn.commit()

    async def list_servers(self) -> list[ServerWithSecrets]:
        async with self._lock:
            rows = await asyncio.to_thread(self._fetch_servers)
        return rows

    def _fetch_servers(self) -> list[ServerWithSecrets]:
        result: list[ServerWithSecrets] = []
        with self._connect() as conn:
            for row in conn.execute(
                "SELECT id, data, last_status, last_checked_at FROM mcp_servers ORDER BY id"
            ):
                config = self._decrypt(row["data"])
                status = self._to_status(row["last_status"])
                result.append(
                    ServerWithSecrets(
                        config=config,
                        is_internal=False,
                        last_status=status,
                        last_checked_at=row["last_checked_at"],
                    )
                )
        return result

    async def get_server(self, server_id: str) -> ServerWithSecrets | None:
        async with self._lock:
            return await asyncio.to_thread(self._fetch_server_sync, server_id)

    def _fetch_server_sync(self, server_id: str) -> ServerWithSecrets | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data, last_status, last_checked_at FROM mcp_servers WHERE id=?",
                (server_id,),
            ).fetchone()
        if row is None:
            return None
        config = self._decrypt(row["data"])
        status = self._to_status(row["last_status"])
        return ServerWithSecrets(
            config=config,
            is_internal=False,
            last_status=status,
            last_checked_at=row["last_checked_at"],
        )

    @staticmethod
    def _to_status(value: Optional[str]) -> Optional[ProbeStatus]:
        if not value:
            return None
        try:
            return ProbeStatus(value)
        except ValueError:
            return None

    async def update_probe_status(
        self,
        server_id: str,
        status: ProbeStatus,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(self._update_status_sync, server_id, status)

    def _update_status_sync(self, server_id: str, status: ProbeStatus) -> None:
        timestamp = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE mcp_servers SET last_status=?, last_checked_at=? WHERE id=?",
                (status.value, timestamp, server_id),
            )
            conn.commit()

    async def to_public(self) -> list[ServerConfigPublic]:
        servers = await self.list_servers()
        public_configs: list[ServerConfigPublic] = []
        for item in servers:
            public_configs.append(
                ServerConfigPublic(
                    id=item.config.id,
                    name=item.config.name,
                    transport=item.config.transport,
                    url=item.config.url,
                    headers=sorted(item.config.headers.keys()),
                    allow_tools=item.config.allow_tools,
                    timeout_s=item.config.timeout_s,
                    max_output_kb=item.config.max_output_kb,
                    notes=item.config.notes,
                    max_calls_per_minute_per_thread=item.config.max_calls_per_minute_per_thread,
                )
            )
        return public_configs

    async def cache_tools(self, server_id: str, tools: list[ToolSchema]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._cache_tools_sync, server_id, tools)

    def _cache_tools_sync(self, server_id: str, tools: list[ToolSchema]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM mcp_server_tools WHERE server_id=?", (server_id,))
            now = datetime.utcnow().isoformat()
            for tool in tools:
                conn.execute(
                    """
                    INSERT INTO mcp_server_tools (server_id, tool_name, schema_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        server_id,
                        tool.name,
                        json.dumps(tool.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False),
                        now,
                    ),
                )
            conn.commit()

    async def load_cached_tools(self, server_id: str) -> tuple[list[ToolSchema], bool]:
        async with self._lock:
            return await asyncio.to_thread(self._load_cached_tools_sync, server_id)

    def _load_cached_tools_sync(self, server_id: str) -> tuple[list[ToolSchema], bool]:
        tools: list[ToolSchema] = []
        most_recent: Optional[datetime] = None
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tool_name, schema_json, updated_at FROM mcp_server_tools WHERE server_id=?",
                (server_id,),
            ).fetchall()
            for row in rows:
                payload = json.loads(row["schema_json"])
                payload.setdefault("name", row["tool_name"])
                tools.append(ToolSchema.model_validate(payload))
                try:
                    updated_at = datetime.fromisoformat(row["updated_at"])
                except ValueError:
                    updated_at = None
                if updated_at:
                    most_recent = max(most_recent or updated_at, updated_at)
        if not tools:
            return [], False
        if most_recent and datetime.utcnow() - most_recent <= _TOOLS_CACHE_TTL:
            return tools, True
        return tools, False

    async def set_binding(self, binding: Binding) -> None:
        async with self._lock:
            await asyncio.to_thread(self._set_binding_sync, binding)

    def _set_binding_sync(self, binding: Binding) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mcp_bindings (server_id, thread_id, enabled_tools)
                VALUES (?, ?, ?)
                ON CONFLICT(server_id, thread_id) DO UPDATE SET enabled_tools=excluded.enabled_tools
                """,
                (
                    binding.server_id,
                    binding.thread_id,
                    json.dumps(sorted(set(binding.enabled_tools))),
                ),
            )
            conn.commit()

    async def get_binding(self, server_id: str, thread_id: str) -> Binding | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_binding_sync, server_id, thread_id)

    def _get_binding_sync(self, server_id: str, thread_id: str) -> Binding | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT enabled_tools FROM mcp_bindings WHERE server_id=? AND thread_id=?",
                (server_id, thread_id),
            ).fetchone()
        if row is None:
            return None
        enabled = json.loads(row["enabled_tools"])
        return Binding(server_id=server_id, thread_id=thread_id, enabled_tools=list(enabled))

    async def delete_binding(self, server_id: str, thread_id: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._delete_binding_sync, server_id, thread_id)

    def _delete_binding_sync(self, server_id: str, thread_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM mcp_bindings WHERE server_id=? AND thread_id=?",
                (server_id, thread_id),
            )
            conn.commit()

    async def list_bindings_for_thread(self, thread_id: str) -> list[Binding]:
        async with self._lock:
            return await asyncio.to_thread(self._list_bindings_for_thread_sync, thread_id)

    def _list_bindings_for_thread_sync(self, thread_id: str) -> list[Binding]:
        bindings: list[Binding] = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT server_id, enabled_tools FROM mcp_bindings WHERE thread_id=?",
                (thread_id,),
            ).fetchall()
        for row in rows:
            enabled = json.loads(row["enabled_tools"])
            bindings.append(
                Binding(
                    server_id=row["server_id"],
                    thread_id=thread_id,
                    enabled_tools=list(enabled),
                )
            )
        return bindings
