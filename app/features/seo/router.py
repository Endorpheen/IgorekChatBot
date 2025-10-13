from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.settings import get_settings

router = APIRouter()
settings = get_settings()


def _serve_webui_file(path: Path):
    if path.is_file():
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="Not Found")


@router.get("/google{rest_of_path:path}")
async def serve_google_verification(rest_of_path: str):
    return _serve_webui_file(settings.webui_dir / f"google{rest_of_path}")


@router.get("/sitemap.xml")
async def serve_sitemap():
    return _serve_webui_file(settings.webui_dir / "sitemap.xml")


@router.get("/robots.txt")
async def serve_robots():
    return _serve_webui_file(settings.webui_dir / "robots.txt")
