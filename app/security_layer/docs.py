from __future__ import annotations

from fastapi import APIRouter, Depends, Response, HTTPException, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.utils import get_openapi
import secrets

from app.logging import get_logger
from app.settings import get_settings


logger = get_logger()
http_basic = HTTPBasic()


def _require_docs_auth(credentials: HTTPBasicCredentials = Depends(http_basic)) -> None:
    settings = get_settings()
    if not settings.docs_auth_enabled:
        return
    if not settings.docs_auth_username or not settings.docs_auth_password:
        logger.error("[DOCS AUTH] enabled but credentials not configured")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Docs credentials not configured",
            headers={"WWW-Authenticate": 'Basic realm="IgorekChatBot Docs"'},
        )

    username_correct = secrets.compare_digest(credentials.username, settings.docs_auth_username)
    password_correct = secrets.compare_digest(credentials.password, settings.docs_auth_password)
    if not (username_correct and password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительные учетные данные",
            headers={"WWW-Authenticate": 'Basic realm="IgorekChatBot Docs"'},
        )


def _noindex_headers(response: Response) -> None:
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"


def register_protected_docs(app) -> None:
    router = APIRouter()

    @router.get("/openapi.json", include_in_schema=False)
    async def openapi_route(_: None = Depends(_require_docs_auth)):
        schema = get_openapi(
            title=app.title,
            version="protected",
            routes=[route for route in app.routes if getattr(route, "include_in_schema", True)],
        )
        response = JSONResponse(schema)
        _noindex_headers(response)
        return response

    @router.get("/docs", include_in_schema=False)
    async def swagger_ui(_: None = Depends(_require_docs_auth)):
        response = get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="IgorekChatBot API Docs",
            swagger_ui_parameters={
                "supportedSubmitMethods": [],
                "tryItOutEnabled": False,
                "displayRequestDuration": True,
            },
        )
        _noindex_headers(response)
        return response

    @router.get("/redoc", include_in_schema=False)
    async def redoc_ui(_: None = Depends(_require_docs_auth)):
        response = get_redoc_html(
            openapi_url="/openapi.json",
            title="IgorekChatBot API Reference",
        )
        _noindex_headers(response)
        return response

    app.include_router(router)
