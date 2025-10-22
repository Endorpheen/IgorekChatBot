from __future__ import annotations

from typing import Any, List, Dict
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Query

from app.logging import get_logger
from app.security_layer.dependencies import require_session
from app.settings import get_settings

router = APIRouter(prefix="/api/providers/agentrouter", tags=["OpenAI Compatible"], include_in_schema=False)
logger = get_logger()
settings = get_settings()


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
async def list_models(
    request: Request,
    base_url: str = Query(..., description="OpenAI Compatible base URL"),
    session=Depends(require_session),
) -> Dict[str, List[str]]:
    auth = (request.headers.get("Authorization") or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail={"code": "missing_base_url", "message": "Query param base_url is required"})
    if not auth:
        raise HTTPException(status_code=400, detail={"code": "missing_key", "message": "Authorization: Bearer <api_key> header is required"})

    try:
        parsed = urlparse(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "agentrouter_bad_url", "message": "Некорректный base_url"}) from exc

    if parsed.scheme.lower() != "https":
        raise HTTPException(status_code=400, detail={"code": "agentrouter_insecure", "message": "Допускаются только HTTPS endpoints"})

    normalized_origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    allowlist = {item.rstrip("/").lower() for item in settings.allowed_agentrouter_base_urls}
    if allowlist and normalized_origin not in allowlist:
        raise HTTPException(status_code=403, detail={"code": "agentrouter_forbidden", "message": "Провайдер не разрешён"})

    target = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": auth, "Accept": "application/json"}
    logger.info("[OpenAI Compatible] Prepared request url=%s headers=%s", target, headers)
    try:
        resp = requests.get(target, headers=headers, timeout=15, allow_redirects=False)
        logger.info(
            "[OpenAI Compatible] Response status=%s url=%s history=%s sent_headers=%s",
            resp.status_code,
            getattr(resp.request, "url", None),
            [(r.status_code, getattr(r, "url", None)) for r in resp.history],
            dict(getattr(resp.request, "headers", {})),
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail={"code": "agentrouter_timeout", "message": "Timeout fetching models"})
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail={"code": "agentrouter_unreachable", "message": "Cannot connect to OpenAI Compatible endpoint"})
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
            logger.warning("[OpenAI Compatible] Empty models parsed; raw length=%s", len(text))
        except Exception:
            pass
    return {"models": models}
