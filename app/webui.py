from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.settings import Settings


def register_webui(app: FastAPI, settings: Settings) -> None:
    webui_dir = settings.webui_dir
    if not webui_dir.is_dir():
        return

    webui_root = webui_dir.resolve()

    app.mount(
        "/web-ui",
        StaticFiles(directory=str(webui_root), html=True),
        name="web-ui",
    )

    @app.get("/favicon.ico")
    async def serve_favicon():
        favicon_path = webui_root / "favicon.ico"
        if favicon_path.is_file():
            return FileResponse(favicon_path)
        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/sw.js")
    async def serve_root_sw():
        return FileResponse(webui_root / "sw.js")
