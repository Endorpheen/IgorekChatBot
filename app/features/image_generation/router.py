from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.middlewares.security import _require_csrf_token, verify_client_session
from app.settings import get_settings
from image_generation import ImageGenerationError, image_manager

from .adapters import image_error_to_http

router = APIRouter()
settings = get_settings()


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


@router.post("/image/generate", response_model=ImageJobCreateResponse)
async def create_image_job(request: Request, payload: ImageGenerateRequest) -> ImageJobCreateResponse:
    _require_csrf_token(request)
    session_id = verify_client_session(request)
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


@router.get("/image/jobs/{job_id}", response_model=ImageJobStatusResponse)
async def get_image_job(job_id: str, request: Request) -> ImageJobStatusResponse:
    session_id = verify_client_session(request)

    try:
        status = await image_manager.get_job_status(job_id)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    if not status:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Задача не найдена"})
    if status.session_id != session_id:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ к задаче запрещён"})

    result_url = None
    if status.status == "done" and status.result_path:
        result_url = f"/image/files/{job_id}.webp"

    return ImageJobStatusResponse(
        job_id=job_id,
        status=status.status,
        provider=status.provider,
        model=status.model,
        prompt=status.prompt,
        width=status.width,
        height=status.height,
        steps=status.steps,
        cfg=status.cfg,
        seed=status.seed,
        mode=status.mode,
        created_at=status.created_at,
        updated_at=status.updated_at,
        started_at=status.started_at,
        completed_at=status.completed_at,
        duration_ms=status.duration_ms,
        error_code=status.error_code,
        error_message=status.error_message,
        result_url=result_url,
    )


@router.get("/image/jobs/{job_id}/result")
async def download_image_job_result(job_id: str, request: Request) -> FileResponse:
    session_id = verify_client_session(request)

    try:
        status = await image_manager.get_job_status(job_id)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    if not status or status.status != "done" or not status.result_path:
        raise HTTPException(status_code=404, detail={"code": "result_unavailable", "message": "Результат ещё не готов"})
    if status.session_id != session_id:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ запрещён"})

    try:
        file_path = Path(status.result_path).resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_path", "message": "Некорректный путь к результату"}) from exc

    output_dir = image_manager.output_dir.resolve()
    try:
        file_path.relative_to(output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ запрещён"}) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Файл результата не найден"})

    provider_slug = status.provider.replace("/", "-")
    filename = f"{provider_slug}-{job_id}.webp"
    return FileResponse(str(file_path), media_type="image/webp", filename=filename)


@router.post("/image/validate")
async def validate_image_key(request: Request, payload: ImageKeyValidationRequest) -> Dict[str, str]:
    _require_csrf_token(request)
    api_key = _extract_image_key(request)

    try:
        await image_manager.validate_key(payload.provider, api_key)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    return {"status": "ok"}


@router.get("/image/files/{job_id}.webp")
async def download_image_file(job_id: str):
    try:
        status = await image_manager.get_job_status(job_id)
    except ImageGenerationError as exc:
        raise image_error_to_http(exc)

    if not status or status.status != "done" or not status.result_path:
        raise HTTPException(status_code=404, detail={"code": "result_unavailable", "message": "Результат ещё не готов"})

    try:
        file_path = Path(status.result_path).resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_path", "message": "Некорректный путь к результату"}) from exc

    output_dir = image_manager.output_dir.resolve()
    try:
        file_path.relative_to(output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Доступ запрещён"}) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Файл результата не найден"})

    provider_slug = status.provider.replace("/", "-")
    filename = f"{provider_slug}-{job_id}.webp"
    return FileResponse(str(file_path), media_type="image/webp", filename=filename)


@router.get("/image/providers", response_model=ProviderModelsResponse | ProviderListResponse)
async def get_image_providers(
    request: Request,
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
