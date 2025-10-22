from __future__ import annotations

import os
import asyncio

try:
    import multipart  # type: ignore
except ImportError:  # pragma: no cover
    multipart = None

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.features.chat.router import router as chat_router
from app.features.image_analysis.router import router as image_analysis_router
from app.features.document_analysis import router as document_router
from app.features.image_generation.router import router as image_generation_router
from app.features.mcp.router import router as mcp_router
from app.features.root.router import router as root_router
from app.features.seo.router import router as seo_router
from app.features.uploads.cleaner import start_cleanup_task, stop_cleanup_task
from app.features.uploads.router import router as uploads_router
from app.features.providers.openai_compatible import router as openai_compatible_router
from app.logging import get_logger, setup_logging
from app.middlewares.cors import setup_cors
from app.middlewares.session import ServerSessionMiddleware
from app.security_layer.docs import register_protected_docs
from app.settings import Settings, ensure_upload_directory, get_settings
from app.webui import register_webui
from image_generation import image_manager


def _lifespan(settings: Settings):
    @asynccontextmanager
    async def manager(_: FastAPI) -> AsyncIterator[None]:
        ensure_upload_directory(settings.upload_dir_path)
        cleanup_task: Optional[asyncio.Task]
        cleanup_task = await start_cleanup_task(settings, settings.upload_dir_path)
        await image_manager.startup()
        try:
            yield
        finally:
            await stop_cleanup_task(cleanup_task)
            await image_manager.shutdown()

    return manager


def create_app() -> FastAPI:
    settings = get_settings()
    os.environ.setdefault("PYTHON_MULTIPART_LIMIT", str(settings.max_image_upload_bytes))
    ensure_upload_directory(settings.upload_dir_path)

    if multipart and hasattr(multipart, "multipart"):
        if hasattr(multipart.multipart, "MAX_MEMORY_SIZE"):
            multipart.multipart.MAX_MEMORY_SIZE = settings.max_image_upload_bytes
        if hasattr(multipart.multipart, "DEFAULT_MAX_MEMORY_SIZE"):
            multipart.multipart.DEFAULT_MAX_MEMORY_SIZE = settings.max_image_upload_bytes

    setup_logging(settings)
    logger = get_logger()
    logger.debug("[APP] Инициализация приложения FastAPI")

    app = FastAPI(
        max_request_size=settings.max_request_size,
        lifespan=_lifespan(settings),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    setup_cors(app, settings)
    app.add_middleware(ServerSessionMiddleware)

    docs_build_path = Path("/app/docs/build")
    if docs_build_path.is_dir():
        app.mount("/guide", StaticFiles(directory=str(docs_build_path), html=True), name="guide")

    app.include_router(chat_router)
    app.include_router(image_analysis_router)
    app.include_router(document_router)
    app.include_router(image_generation_router)
    app.include_router(uploads_router)
    app.include_router(seo_router)
    app.include_router(mcp_router)
    app.include_router(openai_compatible_router)
    app.include_router(root_router)
    register_protected_docs(app)

    register_webui(app, settings)

    return app


app = create_app()
