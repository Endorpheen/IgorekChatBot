from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.security_layer.session_manager import (
    SessionInfo,
    SessionManager,
    UnauthorizedSessionError,
    get_session_manager,
)


def _resolve_session(request: Request, manager: SessionManager) -> SessionInfo:
    info = getattr(request.state, "session_info", None)
    if info:
        return info
    try:
        info = manager.require_session(request)
    except UnauthorizedSessionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недоступна") from exc
    request.state.session_info = info
    return info


def require_session(request: Request, manager: SessionManager = Depends(get_session_manager)) -> SessionInfo:
    """
    Обязательная серверная сессия (legacy будет принят, но помечен в SessionInfo.legacy).
    """
    return _resolve_session(request, manager)


def require_non_legacy_session(
    session: SessionInfo = Depends(require_session),
) -> SessionInfo:
    if session.legacy:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуется обновлённая серверная сессия",
        )
    return session
