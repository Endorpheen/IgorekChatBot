from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Dict, Optional, Tuple

import aiohttp
import httpx
from httpx import HTTPError, TimeoutException

from app.mcp.logger import get_mcp_logger
from app.mcp.schemas import (
    ProbeStatus,
    RunRequest,
    RunResult,
    RunStatus,
    ServerConfig,
    ToolSchema,
    Transport,
)
from app.mcp.settings import MCPSettings

_LIST_TIMEOUT_CAP = 10
_CALL_TIMEOUT_CAP = 30
_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_SEMAPHORE_LOCK = asyncio.Lock()


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[Tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, server_id: str, thread_id: str, limit: Optional[int]) -> bool:
        if limit is None or limit <= 0:
            return True
        cutoff = time.monotonic() - 60
        key = (server_id, thread_id)
        async with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(time.monotonic())
            return True


_rate_limiter = RateLimiter()
_mcp_logger = get_mcp_logger()


def _masked_headers(headers: Dict[str, str]) -> Dict[str, str]:
    masked: Dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if any(sub in lowered for sub in ["authorization", "token", "secret", "api-key", "x-api-key", "password"]):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


async def _get_semaphore(server_id: str, limit: int) -> asyncio.Semaphore:
    async with _SEMAPHORE_LOCK:
        if server_id not in _SEMAPHORES:
            _SEMAPHORES[server_id] = asyncio.Semaphore(limit)
        return _SEMAPHORES[server_id]


def _normalize_timeout(configured: Optional[int], cap: int, fallback: int) -> float:
    if configured is None or configured <= 0:
        return float(min(cap, fallback))
    return float(min(cap, configured))


def _build_payload(method: str, params: Optional[Dict[str, Any]] = None, trace_id: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": trace_id or str(uuid.uuid4()),
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return payload


async def _http_post(
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: float,
) -> Dict[str, Any]:
    final_headers = {"Content-Type": "application/json", **headers}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=final_headers)
        response.raise_for_status()
        return response.json()


async def _ws_call(
    server: ServerConfig,
    payload: Dict[str, Any],
    timeout: float,
) -> Dict[str, Any]:
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=client_timeout, headers=server.headers) as session:
        async with session.ws_connect(server.url) as websocket:
            await websocket.send_json(payload)
            async for message in websocket:
                if message.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(message.data)
                    if data.get("id") == payload["id"]:
                        return data
                elif message.type == aiohttp.WSMsgType.ERROR:
                    raise RuntimeError("WebSocket error: %s" % message.data)
    raise RuntimeError("Не удалось получить ответ по WebSocket")


def _extract_tools(response: Dict[str, Any]) -> list[ToolSchema]:
    result = response.get("result")
    if not isinstance(result, dict):
        return []
    tools_payload = result.get("tools")
    if not isinstance(tools_payload, list):
        return []
    tools: list[ToolSchema] = []
    for entry in tools_payload:
        try:
            tools.append(ToolSchema.model_validate(entry))
        except Exception:  # pragma: no cover
            continue
    return tools


async def list_tools(server: ServerConfig, settings: MCPSettings) -> tuple[list[ToolSchema], ProbeStatus, Optional[str]]:
    timeout = _normalize_timeout(server.timeout_s, _LIST_TIMEOUT_CAP, settings.default_timeout_s)
    payload = _build_payload("tools/list")
    try:
        if server.transport == Transport.HTTP_SSE:
            response = await _http_post(server.url, payload, server.headers, timeout)
        else:
            response = await _ws_call(server, payload, timeout)
    except TimeoutException:
        return [], ProbeStatus.TIMEOUT, "Истек таймаут соединения"
    except HTTPError as exc:
        return [], ProbeStatus.UNREACHABLE, str(exc)
    except Exception as exc:  # pragma: no cover
        return [], ProbeStatus.ERROR, str(exc)

    error = response.get("error")
    if error:
        return [], ProbeStatus.ERROR, json.dumps(error, ensure_ascii=False)

    tools = _extract_tools(response)
    return tools, ProbeStatus.OK, None


def _format_output(data: Any, max_output_kb: int) -> tuple[Any, bool]:
    if data is None:
        return None, False
    if isinstance(data, (dict, list)):
        raw = json.dumps(data, ensure_ascii=False)
    else:
        raw = str(data)
    encoded = raw.encode("utf-8")
    limit_bytes = max(0, max_output_kb) * 1024
    if limit_bytes and len(encoded) > limit_bytes:
        truncated = encoded[:limit_bytes]
        return truncated.decode("utf-8", errors="ignore"), True
    return raw, False


async def call_tool(
    request: RunRequest,
    server: ServerConfig,
    settings: MCPSettings,
) -> RunResult:
    trace_id = str(uuid.uuid4())
    start = time.perf_counter()
    timeout = _normalize_timeout(server.timeout_s, _CALL_TIMEOUT_CAP, settings.default_timeout_s)
    max_output_kb = server.max_output_kb or settings.max_output_kb
    rate_limit = server.max_calls_per_minute_per_thread or settings.max_calls_per_minute_per_thread

    allowed = await _rate_limiter.allow(server.id, request.thread_id, rate_limit)
    if not allowed:
        duration_ms = int((time.perf_counter() - start) * 1000)
        _mcp_logger.warning(
            "trace=%s server=%s tool=%s status=rate_limited duration_ms=%s",
            trace_id,
            server.id,
            request.tool_name,
            duration_ms,
        )
        return RunResult(trace_id=trace_id, status=RunStatus.RATE_LIMITED, error="Rate limit exceeded", duration_ms=duration_ms)

    semaphore = await _get_semaphore(server.id, settings.concurrency_limit)

    payload = _build_payload(
        "tools/call",
        params={
            "serverId": server.id,
            "toolName": request.tool_name,
            "arguments": request.arguments,
            "threadId": request.thread_id,
        },
        trace_id=trace_id,
    )

    mask_headers = _masked_headers(server.headers)
    _mcp_logger.info(
        "trace=%s server=%s tool=%s transport=%s action=start headers=%s",
        trace_id,
        server.id,
        request.tool_name,
        server.transport.value,
        mask_headers,
    )

    async with semaphore:
        try:
            if server.transport == Transport.HTTP_SSE:
                response = await _http_post(server.url, payload, server.headers, timeout)
            else:
                response = await _ws_call(server, payload, timeout)
        except TimeoutException:
            duration_ms = int((time.perf_counter() - start) * 1000)
            _mcp_logger.warning(
                "trace=%s server=%s tool=%s status=timeout duration_ms=%s",
                trace_id,
                server.id,
                request.tool_name,
                duration_ms,
            )
            return RunResult(trace_id=trace_id, status=RunStatus.TIMEOUT, error="Timeout", duration_ms=duration_ms)
        except HTTPError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            _mcp_logger.error(
                "trace=%s server=%s tool=%s status=error err=%s duration_ms=%s",
                trace_id,
                server.id,
                request.tool_name,
                str(exc),
                duration_ms,
            )
            return RunResult(trace_id=trace_id, status=RunStatus.ERROR, error=str(exc), duration_ms=duration_ms)
        except Exception as exc:  # pragma: no cover
            duration_ms = int((time.perf_counter() - start) * 1000)
            _mcp_logger.error(
                "trace=%s server=%s tool=%s status=error err=%s duration_ms=%s",
                trace_id,
                server.id,
                request.tool_name,
                str(exc),
                duration_ms,
            )
            return RunResult(trace_id=trace_id, status=RunStatus.ERROR, error=str(exc), duration_ms=duration_ms)

    result_payload = response.get("result")
    error_payload = response.get("error")

    duration_ms = int((time.perf_counter() - start) * 1000)

    if error_payload:
        message = error_payload.get("message") if isinstance(error_payload, dict) else str(error_payload)
        _mcp_logger.error(
            "trace=%s server=%s tool=%s status=error duration_ms=%s",
            trace_id,
            server.id,
            request.tool_name,
            duration_ms,
        )
        return RunResult(trace_id=trace_id, status=RunStatus.ERROR, error=message, duration_ms=duration_ms)

    formatted, truncated = _format_output(result_payload, max_output_kb)

    _mcp_logger.info(
        "trace=%s server=%s tool=%s status=ok duration_ms=%s truncated=%s",
        trace_id,
        server.id,
        request.tool_name,
        duration_ms,
        truncated,
    )
    return RunResult(trace_id=trace_id, status=RunStatus.OK, output=formatted, truncated=truncated, duration_ms=duration_ms)
