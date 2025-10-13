from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from app.middlewares.security import _require_csrf_token, verify_client_session
from app.settings import get_settings
from image_generation import ImageGenerationError, get_model_capabilities, image_manager

from .adapters import image_error_to_http

router = APIRouter()
settings = get_settings()


class ImageGenerateRequest(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024
    steps: int = 4

    model_config = ConfigDict(extra="forbid")


class ImageJobCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class ImageJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    provider: str
    prompt: str
    width: int
    height: int
    steps: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class ImageCapabilitiesResponse(BaseModel):
    model: str
    steps_allowed: list[int]
    default_steps: int
    sizes_allowed: list[int]
    default_size: int


def _extract_together_key(request: Request) -> str:
    together_key = (request.headers.get("X-Together-Key") or "").strip()
    if not together_key:
        raise HTTPException(status_code=400, detail={"code": "missing_key", "message": "Заголовок X-Together-Key обязателен"})
    return together_key


@router.post("/image/generate", response_model=ImageJobCreateResponse)
async def create_image_job(request: Request, payload: ImageGenerateRequest) -> ImageJobCreateResponse:
    _require_csrf_token(request)
    session_id = verify_client_session(request)
    together_key = _extract_together_key(request)

    try:
        job_id = await image_manager.enqueue_job(
            prompt=payload.prompt,
            width=payload.width,
            height=payload.height,
            steps=payload.steps,
            session_id=session_id,
            together_key=together_key,
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
        prompt=status.prompt,
        width=status.width,
        height=status.height,
        steps=status.steps,
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

    return FileResponse(str(file_path), media_type="image/webp")


@router.post("/image/validate")
async def validate_together_key(request: Request) -> Dict[str, str]:
    _require_csrf_token(request)
    together_key = _extract_together_key(request)

    try:
        await image_manager.validate_key(together_key)
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

    filename = f"together-flux-{job_id}.webp"
    return FileResponse(str(file_path), media_type="image/webp", filename=filename)


@router.get("/image/capabilities", response_model=ImageCapabilitiesResponse)
async def get_image_capabilities() -> ImageCapabilitiesResponse:
    data = get_model_capabilities()
    return ImageCapabilitiesResponse(**data)
