from fastapi import HTTPException, Request, status

from app.settings import get_settings
from app.security_layer.session_manager import UnauthorizedSessionError, get_session_manager


def _require_csrf_token(request: Request) -> None:
    cookie_token = request.cookies.get("csrf-token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_failed", "message": "CSRF проверка не пройдена"},
        )

    origin = request.headers.get("Origin")
    if origin:
        settings = get_settings()
        if origin.rstrip("/") not in {host.rstrip("/") for host in settings.allow_origins}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недопустимый источник запроса")


def verify_client_session(request: Request) -> str:
    manager = get_session_manager()
    info = getattr(request.state, "session_info", None)
    if info is None:
        try:
            info = manager.require_session(request)
        except UnauthorizedSessionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "missing_session", "message": "Доступ запрещён"},
            ) from exc
        request.state.session_info = info
    return info.session_id
