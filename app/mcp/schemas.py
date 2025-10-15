from __future__ import annotations

import ipaddress
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, FieldValidationInfo, field_validator


class Transport(str, Enum):
    WEBSOCKET = "websocket"
    HTTP_SSE = "http-sse"


_ALLOWED_WS_SCHEMES = {"ws", "wss"}
_ALLOWED_HTTP_SCHEMES = {"http", "https"}
_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class ToolSchema(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = Field(default=None, alias="inputSchema")

    model_config = {"populate_by_name": True, "str_strip_whitespace": True}


class ServerConfig(BaseModel):
    id: str = Field(..., description="Уникальный идентификатор сервера")
    name: str = Field(..., min_length=1, max_length=120)
    transport: Transport
    url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    allow_tools: List[str] = Field(default_factory=list)
    timeout_s: Optional[int] = Field(default=None, ge=1, le=120)
    max_output_kb: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = Field(default=None, max_length=2048)
    max_calls_per_minute_per_thread: Optional[int] = Field(default=None, ge=1, le=120)

    model_config = {"str_strip_whitespace": True}

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _ID_PATTERN.match(value):
            raise ValueError("Некорректный идентификатор сервера")
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str, info: FieldValidationInfo) -> str:
        transport: Transport | None = info.data.get("transport") if info.data else None
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Некорректный URL")
        scheme = parsed.scheme.lower()
        if transport == Transport.WEBSOCKET and scheme not in _ALLOWED_WS_SCHEMES:
            raise ValueError("Для websocket транспорта допустимы только ws:// или wss://")
        if transport == Transport.HTTP_SSE and scheme not in _ALLOWED_HTTP_SCHEMES:
            raise ValueError("Для http-sse транспорта допустимы только http:// или https://")
        return value

    @field_validator("headers")
    @classmethod
    def _normalize_headers(cls, value: Dict[str, str]) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        for key, header_value in value.items():
            if not key or not key.strip():
                raise ValueError("Имя заголовка не может быть пустым")
            normalized[key.strip()] = header_value.strip()
        return normalized

    @field_validator("allow_tools")
    @classmethod
    def _normalize_tools(cls, value: List[str]) -> List[str]:
        deduped: List[str] = []
        for tool in value:
            normalized = tool.strip()
            if not normalized:
                continue
            if normalized not in deduped:
                deduped.append(normalized)
        return deduped


class ServerConfigPublic(BaseModel):
    id: str
    name: str
    transport: Transport
    url: str
    headers: List[str] = Field(default_factory=list)
    allow_tools: List[str] = Field(default_factory=list)
    timeout_s: Optional[int] = None
    max_output_kb: Optional[int] = None
    notes: Optional[str] = None
    max_calls_per_minute_per_thread: Optional[int] = None
    status: Optional[ProbeStatus] = None


class ProbeStatus(str, Enum):
    OK = "ok"
    UNREACHABLE = "unreachable"
    INVALID_URL = "invalid_url"
    TIMEOUT = "timeout"
    SSRF_BLOCKED = "ssrf_blocked"
    ERROR = "error"


class ProbeResponse(BaseModel):
    status: ProbeStatus
    tools: List[ToolSchema] = Field(default_factory=list)
    error: Optional[str] = None
    cached: bool = False


class ToolListResponse(BaseModel):
    tools: List[ToolSchema]
    cached: bool


class BindRequest(BaseModel):
    server_id: str
    thread_id: str
    enabled_tools: List[str]

    @field_validator("thread_id")
    @classmethod
    def _validate_thread_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("thread_id обязателен")
        return value


class Binding(BaseModel):
    server_id: str
    thread_id: str
    enabled_tools: List[str]


class RunRequest(BaseModel):
    server_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    thread_id: str


class RunStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"


class RunResult(BaseModel):
    trace_id: str
    status: RunStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    truncated: bool = False
    duration_ms: Optional[int] = None


class ServerWithSecrets(BaseModel):
    config: ServerConfig
    is_internal: bool = False
    last_status: Optional[ProbeStatus] = None
    last_checked_at: Optional[str] = None


class SSRFBlocker:
    _BLOCKED_HOSTS = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.google.internal.",
    }

    _BLOCKED_SUFFIXES = (".internal", ".local", ".intranet", ".corp")

    def __init__(self, allow_internal: bool) -> None:
        self.allow_internal = allow_internal

    def is_blocked(self, url: str) -> bool:
        blocked, _ = self.classify(url)
        return blocked

    def classify(self, url: str) -> tuple[bool, bool]:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return True, True

        host_part = host.split(":", 1)[0]
        is_internal = self._is_internal_host(host_part)
        blocked = is_internal and not self.allow_internal
        return blocked, is_internal

    def _is_internal_host(self, host: str) -> bool:
        lowered = host.lower()
        if lowered in self._BLOCKED_HOSTS:
            return True

        if lowered.endswith(self._BLOCKED_SUFFIXES):
            return True

        try:
            ip_obj = ipaddress.ip_address(lowered)
        except ValueError:
            if lowered == "localhost":
                return True
            if lowered == "mcp_server":
                return True
            if "." not in lowered:
                return True
            return False

        if any(
            [
                ip_obj.is_loopback,
                ip_obj.is_private,
                ip_obj.is_link_local,
                ip_obj.is_reserved,
                ip_obj.is_multicast,
            ]
        ):
            return True
        return False
