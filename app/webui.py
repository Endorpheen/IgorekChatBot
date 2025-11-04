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

    assets_dir = webui_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/web-ui/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/web-ui")
    @app.get("/web-ui/")
    async def serve_index():
        return FileResponse(webui_dir / "index.html")

    @app.get("/web-ui/manifest.json")
    async def serve_manifest():
        return FileResponse(webui_dir / "manifest.json")

    @app.get("/web-ui/icon-192.png")
    async def serve_icon192():
        return FileResponse(webui_dir / "icon-192.png")

    @app.get("/web-ui/icon-512.png")
    async def serve_icon512():
        return FileResponse(webui_dir / "icon-512.png")

    @app.get("/favicon.ico")
    async def serve_favicon():
        favicon_path = webui_dir / "favicon.ico"
        if favicon_path.is_file():
            return FileResponse(favicon_path)
        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/sw.js")
    async def serve_root_sw():
        return FileResponse(webui_dir / "sw.js")

    @app.get("/web-ui/{path_file}")
    async def serve_root_files(path_file: str):
        requested = Path(path_file)
        if requested.is_absolute() or ".." in requested.parts:
            raise HTTPException(status_code=404, detail="Not Found")

        file_path = (webui_dir / requested).resolve(strict=False)
        if file_path.is_file() and file_path.is_relative_to(webui_root):
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="Not Found")
