from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.settings import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/")
async def root_redirect():
    index_path = settings.webui_dir / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return {"service": "IgorekChatBot API", "status": "alive"}


@router.get("/images")
@router.get("/images/")
async def images_spa_route():
    index_path = settings.webui_dir / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not Found")
