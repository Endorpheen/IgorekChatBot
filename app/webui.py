from __future__ import annotations

from pathlib import Path
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.settings import Settings


def register_webui(app: FastAPI, settings: Settings) -> None:
    webui_dir = settings.webui_dir
    if not webui_dir.is_dir():
        return

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
        # Normalize and verify path_file to prevent path traversal
        base_dir = webui_dir.resolve()
        # Reject absolute paths and normalize
        if os.path.isabs(path_file):
            raise HTTPException(status_code=404, detail="Not Found")
        try:
            file_path = (webui_dir / path_file).resolve()
        except Exception:
            raise HTTPException(status_code=404, detail="Not Found")
        # Only serve files actually inside base_dir (use commonpath for robustness)
        if os.path.commonpath([str(base_dir), str(file_path)]) != str(base_dir):
            raise HTTPException(status_code=404, detail="Not Found")
        if file_path.is_file():
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="Not Found")
