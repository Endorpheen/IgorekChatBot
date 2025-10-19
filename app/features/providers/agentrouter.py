from __future__ import annotations

from typing import Any, List, Dict

import requests
from fastapi import APIRouter, HTTPException, Request, Query

from app.logging import get_logger

router = APIRouter(prefix="/api/providers/agentrouter", tags=["AgentRouter"])
logger = get_logger()


def _normalize_models(payload: Any) -> List[str]:
    models: List[str] = []
    try:
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                for item in payload["data"]:
                    mid = (item.get("id") if isinstance(item, dict) else None)
                    if isinstance(mid, str):
                        models.append(mid)
            elif isinstance(payload.get("models"), list):
                for item in payload["models"]:
                    if isinstance(item, str):
                        models.append(item)
                    elif isinstance(item, dict):
                        mid = item.get("id")
                        if isinstance(mid, str):
                            models.append(mid)
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, str):
                    models.append(item)
                elif isinstance(item, dict):
                    mid = item.get("id")
                    if isinstance(mid, str):
                        models.append(mid)
    except Exception:
        pass
    return sorted(set(models))


@router.get("/models")
async def list_models(request: Request, base_url: str = Query(..., description="AgentRouter base URL")) -> Dict[str, List[str]]:
    auth = (request.headers.get("Authorization") or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail={"code": "missing_base_url", "message": "Query param base_url is required"})
    if not auth:
        raise HTTPException(status_code=400, detail={"code": "missing_key", "message": "Authorization: Bearer <api_key> header is required"})

    target = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": auth, "Accept": "application/json"}
    logger.info("[AgentRouter] Prepared request url=%s headers=%s", target, headers)
    try:
        resp = requests.get(target, headers=headers, timeout=15, allow_redirects=False)
        logger.info(
            "[AgentRouter] Response status=%s url=%s history=%s sent_headers=%s",
            resp.status_code,
            getattr(resp.request, "url", None),
            [(r.status_code, getattr(r, "url", None)) for r in resp.history],
            dict(getattr(resp.request, "headers", {})),
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail={"code": "agentrouter_timeout", "message": "Timeout fetching models"})
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail={"code": "agentrouter_unreachable", "message": "Cannot connect to AgentRouter endpoint"})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "agentrouter_error", "message": str(exc)})

    if resp.status_code != 200:
        # Attempt to extract error message
        try:
            data = resp.json()
            msg = data.get("error") or data.get("message") or resp.reason
        except Exception:
            msg = resp.text or resp.reason
        raise HTTPException(status_code=resp.status_code, detail={"code": "agentrouter_bad_response", "message": msg})

    try:
        payload = resp.json()
    except Exception:
        payload = None

    models = _normalize_models(payload)
    if not models:
        # Fallback: log raw payload length
        try:
            text = resp.text
            logger.warning("[AgentRouter] Empty models parsed; raw length=%s", len(text))
        except Exception:
            pass
    return {"models": models}
