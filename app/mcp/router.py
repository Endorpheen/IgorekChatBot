from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.mcp import get_mcp_store
from app.mcp.connector import call_tool, list_tools
from app.mcp.schemas import (
    BindRequest,
    Binding,
    ProbeResponse,
    ProbeStatus,
    RunRequest,
    RunResult,
    ServerConfig,
    ServerConfigPublic,
    SSRFBlocker,
    Transport,
)
from app.mcp.settings import get_mcp_settings

router = APIRouter(prefix="/mcp", tags=["MCP"])


async def get_store():
    return get_mcp_store()


@router.post("/servers", response_model=ServerConfigPublic)
async def upsert_server(
    payload: ServerConfig,
    store=Depends(get_store),
):
    settings = get_mcp_settings()
    blocker = SSRFBlocker(settings.allow_internal)
    blocked, is_internal = blocker.classify(payload.url)
    if blocked:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "ssrf_blocked"})

    await store.upsert_server(payload)

    return ServerConfigPublic(
        id=payload.id,
        name=payload.name,
        transport=payload.transport,
        url=payload.url,
        headers=sorted(payload.headers.keys()),
        allow_tools=payload.allow_tools,
        timeout_s=payload.timeout_s,
        max_output_kb=payload.max_output_kb,
        notes=payload.notes,
        max_calls_per_minute_per_thread=payload.max_calls_per_minute_per_thread,
        status=ProbeStatus.OK if not is_internal else None,
    )


@router.get("/servers", response_model=List[ServerConfigPublic])
async def list_servers(store=Depends(get_store)):
    settings = get_mcp_settings()
    blocker = SSRFBlocker(settings.allow_internal)
    servers = await store.list_servers()
    public: List[ServerConfigPublic] = []
    for item in servers:
        blocked, is_internal = blocker.classify(item.config.url)
        status_value = item.last_status
        if blocked:
            status_value = ProbeStatus.SSRF_BLOCKED
        public.append(
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
                status=status_value,
            )
        )
    return public


@router.post("/servers/{server_id}/probe", response_model=ProbeResponse)
async def probe_server(server_id: str, store=Depends(get_store)):
    settings = get_mcp_settings()
    server = await store.get_server(server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")

    blocker = SSRFBlocker(settings.allow_internal)
    blocked, _ = blocker.classify(server.config.url)
    if blocked:
        await store.update_probe_status(server_id, ProbeStatus.SSRF_BLOCKED)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "ssrf_blocked"})

    tools, status_value, error = await list_tools(server.config, settings)
    await store.update_probe_status(server_id, status_value)
    if status_value == ProbeStatus.OK and tools:
        await store.cache_tools(server_id, tools)
        return ProbeResponse(status=status_value, tools=tools, cached=False)

    cached_tools, cache_valid = await store.load_cached_tools(server_id)
    if cached_tools:
        return ProbeResponse(status=status_value, tools=cached_tools, error=error, cached=cache_valid)

    return ProbeResponse(status=status_value, tools=[], error=error, cached=False)


@router.get("/servers/{server_id}/tools", response_model=ProbeResponse)
async def get_server_tools(server_id: str, store=Depends(get_store)):
    settings = get_mcp_settings()
    server = await store.get_server(server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")

    tools, cache_valid = await store.load_cached_tools(server_id)
    if tools:
        status_value = server.last_status or (ProbeStatus.OK if cache_valid else ProbeStatus.ERROR)
        return ProbeResponse(status=status_value, tools=tools, cached=cache_valid)

    tools, status_value, error = await list_tools(server.config, settings)
    if status_value == ProbeStatus.OK:
        await store.cache_tools(server_id, tools)
    await store.update_probe_status(server_id, status_value)
    return ProbeResponse(status=status_value, tools=tools, error=error, cached=False)


@router.post("/bind", response_model=Binding)
async def bind_server(
    payload: BindRequest,
    store=Depends(get_store),
    x_chat_role: str | None = Header(default=None, convert_underscores=True),
):
    role = (x_chat_role or "").lower()
    if role not in {"owner", "moderator"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_privileges")

    server = await store.get_server(payload.server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")

    allowed = set(server.config.allow_tools) if server.config.allow_tools else None
    enabled_clean = []
    for tool in payload.enabled_tools:
        trimmed = tool.strip()
        if not trimmed:
            continue
        if allowed is not None and trimmed not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tool '{trimmed}' is not allowed")
        enabled_clean.append(trimmed)

    binding = Binding(server_id=payload.server_id, thread_id=payload.thread_id, enabled_tools=sorted(set(enabled_clean)))
    await store.set_binding(binding)
    return binding


@router.get("/bindings/{thread_id}", response_model=List[Binding])
async def list_bindings(thread_id: str, store=Depends(get_store)):
    return await store.list_bindings_for_thread(thread_id)


@router.post("/run", response_model=RunResult)
async def run_tool(payload: RunRequest, store=Depends(get_store)):
    settings = get_mcp_settings()
    server = await store.get_server(payload.server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")

    binding = await store.get_binding(payload.server_id, payload.thread_id)
    if binding is None or payload.tool_name not in binding.enabled_tools:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tool is not enabled for this thread")

    tools, _ = await store.load_cached_tools(payload.server_id)
    if tools:
        known_tools = {tool.name for tool in tools}
        if payload.tool_name not in known_tools:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")

    blocker = SSRFBlocker(settings.allow_internal)
    blocked, _ = blocker.classify(server.config.url)
    if blocked:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "ssrf_blocked"})

    result = await call_tool(payload, server.config, settings)
    return result
