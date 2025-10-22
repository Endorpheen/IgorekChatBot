from fastapi import APIRouter, Body, Depends, HTTPException, Request
from typing import Dict, Any
import requests

from app.features.mcp.service import mcp_service
from app.middlewares.security import _require_csrf_token
from app.security_layer.dependencies import require_session
from app.security_layer.rate_limiter import RateLimitConfig, get_rate_limiter
from app.settings import get_settings

router = APIRouter(
    prefix="/api/mcp", 
    tags=["MCP"], 
    include_in_schema=False,
)

settings = get_settings()

async def handle_mcp_request(method, payload):
    try:
        trace_id, data = await method(payload)
        return {"trace_id": trace_id, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail={"error": "ENV_MISSING_MCP_URL", "message": str(e)})
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail={"error": "MCP_TIMEOUT", "message": "The request to the MCP server timed out."})
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail={"error": "DNS_FAIL/CONNECTION_REFUSED", "message": "Could not connect to the MCP server. Check if it's running and in the same Docker network."})
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail={"error": "BAD_ENDPOINT", "message": "The /search or /fetch endpoint was not found on the MCP server."})
        raise HTTPException(status_code=e.response.status_code, detail={"error": "MCP_HTTP_ERROR", "message": str(e)})
    except Exception as e:
        # Catch-all for other errors
        raise HTTPException(status_code=500, detail={"error": "UNKNOWN_MCP_ERROR", "message": str(e)})

@router.post("/search")
async def search(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    session=Depends(require_session),
):
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "mcp:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_mcp_per_minute, window_seconds=60),
    )
    return await handle_mcp_request(mcp_service.search, payload)

@router.post("/fetch")
async def fetch(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    session=Depends(require_session),
):
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "mcp:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_mcp_per_minute, window_seconds=60),
    )
    return await handle_mcp_request(mcp_service.fetch, payload)
