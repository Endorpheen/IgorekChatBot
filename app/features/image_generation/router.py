from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from urllib.parse import urlencode

from app.middlewares.security import _require_csrf_token
from app.settings import get_settings
from image_generation import ImageGenerationError, image_manager

from .adapters import image_error_to_http
from app.security_layer.dependencies import require_session
from app.security_layer.rate_limiter import RateLimitConfig, get_rate_limiter
from app.security_layer.signed_links import get_signed_link_manager

router = APIRouter()
settings = get_settings()
signed_links = get_signed_link_manager()


class ImageGenerateRequest(BaseModel):
    provider: str
    model: str
    prompt: str
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    cfg: Optional[float] = None
    seed: Optional[int] = None
    mode: Optional[str] = None
    extras: Dict[str, Any] | None = Field(default=None)

    model_config = ConfigDict(extra="forbid")


class ImageJobCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class ImageJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    provider: str
    model: str
    prompt: str
    width: int
    height: int
    steps: int
    cfg: float | None = None
    seed: int | None = None
    mode: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProviderSummary(BaseModel):
    id: str
    label: str
    enabled: bool = True
    description: str | None = None
    recommended_models: list[str]


class ProviderModelSpecResponse(BaseModel):
    id: str
    display_name: str
    recommended: bool
    capabilities: Dict[str, Any]
    limits: Dict[str, Any]
    defaults: Dict[str, Any]
    metadata: Dict[str, Any] | None = None


class ProviderModelsResponse(BaseModel):
    provider: str
    models: list[ProviderModelSpecResponse]


class ProviderListResponse(BaseModel):
    providers: list[ProviderSummary]


class ImageKeyValidationRequest(BaseModel):
    provider: str


def _extract_image_key(request: Request) -> str:
    image_key = (request.headers.get("X-Image-Key") or "").strip()
    if not image_key:
        raise HTTPException(status_code=400, detail={"code": "missing_key", "message": "Заголовок X-Image-Key обязателен"})
    return image_key


@router.post("/image/generate", response_model=ImageJobCreateResponse, include_in_schema=False)
async def create_image_job(
    request: Request,
    payload: ImageGenerateRequest,
    session=Depends(require_session),
) -> ImageJobCreateResponse:
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "image_generate:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_image_generate_per_minute, window_seconds=60),
    )
    client_ip = request.client.host if request.client else "unknown"
    limiter.hit(
        "image_generate:ip",
        client_ip,
        RateLimitConfig(limit=settings.rate_limit_image_generate_per_minute, window_seconds=60),
    )
    session_id = session.session_id
    api_key = _extract_image_key(request)

    params: Dict[str, Any] = {}
    if payload.width is not None:
        params["width"] = payload.width
    if payload.height is not None:
        params["height"] = payload.height
    if payload.steps is not None:
        params["steps"] = payload.steps
    if payload.cfg is not None:
        params["cfg"] = payload.cfg
    if payload.seed is not None:
        params["seed"] = payload.seed
    if payload.mode is not None:
        params["mode"] = payload.mode
    if payload.extras:
        params.update(payload.extras)

    try:
        job_id = await image_manager.enqueue_job(
            provider_id=payload.provider,
            model_id=payload.model,
            prompt=payload.prompt,
            params=params,
            session_id=session_id,
            api_key=api_key,
        )
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    return ImageJobCreateResponse(job_id=job_id, status="queued")


@router.get("/image/jobs/{job_id}", include_in_schema=False)
async def get_image_job(job_id: str, request: Request, session=Depends(require_session)) -> RedirectResponse:
    if not settings.signed_link_compat_enabled:
        raise HTTPException(status_code=403, detail="Прямой доступ отключён")
    limiter = get_rate_limiter()
    limiter.hit(
        "image_generate_status:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_image_generate_per_minute, window_seconds=60),
    )
    token = signed_links.issue(
        "image-job-status",
        {"job_id": job_id, "session": session.session_id},
    )
    path = request.app.url_path_for("signed_image_job_status")
    redirect_url = f"{path}?{urlencode({'token': token})}"
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/image/jobs/{job_id}/result", include_in_schema=False)
async def download_image_job_result(job_id: str, request: Request, session=Depends(require_session)) -> RedirectResponse:
    if not settings.signed_link_compat_enabled:
        raise HTTPException(status_code=403, detail="Прямой доступ отключён")
    token = signed_links.issue(
        "image-job-result",
        {"job_id": job_id, "session": session.session_id},
    )
    path = request.app.url_path_for("signed_image_job_result")
    redirect_url = f"{path}?{urlencode({'token': token})}"
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/image/validate", include_in_schema=False)
async def validate_image_key(
    request: Request,
    payload: ImageKeyValidationRequest,
    session=Depends(require_session),
) -> Dict[str, str]:
    _require_csrf_token(request)
    limiter = get_rate_limiter()
    limiter.hit(
        "image_validate:session",
        session.session_id,
        RateLimitConfig(limit=settings.rate_limit_image_generate_per_minute, window_seconds=60),
    )
    api_key = _extract_image_key(request)

    try:
        await image_manager.validate_key(payload.provider, api_key)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    return {"status": "ok"}


@router.get("/image/files/{job_id}.webp", include_in_schema=False)
async def download_image_file(job_id: str, request: Request, session=Depends(require_session)) -> RedirectResponse:
    if not settings.signed_link_compat_enabled:
        raise HTTPException(status_code=403, detail="Прямой доступ отключён")
    token = signed_links.issue(
        "image-file",
        {"job_id": job_id, "session": session.session_id},
    )
    path = request.app.url_path_for("signed_image_job_result")
    redirect_url = f"{path}?{urlencode({'token': token})}"
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/image/providers", response_model=ProviderModelsResponse | ProviderListResponse, include_in_schema=False)
async def get_image_providers(
    request: Request,
    session=Depends(require_session),
    provider: str | None = Query(default=None),
    force: int | None = Query(default=None),
) -> ProviderModelsResponse | ProviderListResponse:
    if not provider:
        providers = image_manager.list_providers()
        return ProviderListResponse(providers=[ProviderSummary(**item) for item in providers])

    api_key = _extract_image_key(request)
    try:
        models = await image_manager.get_provider_models(provider, api_key, force=bool(force))
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    response_models = [ProviderModelSpecResponse(**model) for model in models]
    return ProviderModelsResponse(provider=provider, models=response_models)


@router.get("/image/providers/search", response_model=ProviderModelsResponse, include_in_schema=False)
async def search_image_provider_models(
    request: Request,
    session=Depends(require_session),
    query: str = Query(..., min_length=1, description="Строка поиска по моделям провайдера"),
    provider: str = Query("replicate", description="Идентификатор провайдера (по умолчанию replicate)"),
    limit: int = Query(50, ge=1, le=200, description="Ограничение на количество результатов"),
) -> ProviderModelsResponse:
    api_key = _extract_image_key(request)
    try:
        models = await image_manager.search_provider_models(provider, api_key, query, limit=limit)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    response_models = [ProviderModelSpecResponse(**model) for model in models]
    return ProviderModelsResponse(provider=provider.lower().strip(), models=response_models)


@router.get("/signed/image/jobs/status", name="signed_image_job_status", include_in_schema=False)
async def serve_signed_job_status(token: str = Query(...)) -> ImageJobStatusResponse:
    payload = signed_links.verify(token)
    if payload.resource != "image-job-status":
        raise HTTPException(status_code=403, detail="Некорректный тип ресурса")
    job_id = payload.data.get("job_id")
    if not isinstance(job_id, str):
        raise HTTPException(status_code=400, detail="Некорректная ссылка")

    try:
        status_info = await image_manager.get_job_status(job_id)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    if not status_info:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Задача не найдена"})

    result_url = None
    if status_info.status == "done" and status_info.result_path:
        result_url = f"/image/files/{job_id}.webp"

    payload = ImageJobStatusResponse(
        job_id=job_id,
        status=status_info.status,
        provider=status_info.provider,
        model=status_info.model,
        prompt=status_info.prompt,
        width=status_info.width,
        height=status_info.height,
        steps=status_info.steps,
        cfg=status_info.cfg,
        seed=status_info.seed,
        mode=status_info.mode,
        created_at=status_info.created_at,
        updated_at=status_info.updated_at,
        started_at=status_info.started_at,
        completed_at=status_info.completed_at,
        duration_ms=status_info.duration_ms,
        error_code=status_info.error_code,
        error_message=status_info.error_message,
        result_url=result_url,
    )
    response = JSONResponse(payload.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@router.get("/signed/image/jobs/result", name="signed_image_job_result", include_in_schema=False)
async def serve_signed_job_result(token: str = Query(...)) -> FileResponse:
    payload = signed_links.verify(token)
    if payload.resource not in {"image-job-result", "image-file"}:
        raise HTTPException(status_code=403, detail="Некорректный тип ресурса")

    job_id = payload.data.get("job_id")
    if not isinstance(job_id, str):
        raise HTTPException(status_code=400, detail="Некорректная ссылка")

    try:
        status_info = await image_manager.get_job_status(job_id)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    if not status_info or status_info.status != "done" or not status_info.result_path:
        raise HTTPException(status_code=404, detail={"code": "result_unavailable", "message": "Результат ещё не готов"})

    try:
        file_path = Path(status_info.result_path).resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_path", "message": "Некорректный путь к результату"}) from exc

    output_dir = image_manager.output_dir.resolve()
    try:
        file_path.relative_to(output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ запрещён"}) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Файл результата не найден"})

    provider_slug = status_info.provider.replace("/", "-")
    filename = f"{provider_slug}-{job_id}.webp"
    response = FileResponse(str(file_path), media_type="image/webp", filename=filename)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response
