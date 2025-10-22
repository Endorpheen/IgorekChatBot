from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging import get_logger
from app.security_layer.session_manager import SessionManager, get_session_manager


class ServerSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, session_manager: SessionManager | None = None) -> None:  # type: ignore[override]
        super().__init__(app)
        self._session_manager = session_manager or get_session_manager()
        self._logger = get_logger()

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        session_info, new_token = self._session_manager.resolve(request)
        request.state.session_info = session_info
        request.state._new_session_token = new_token

        response: Response = await call_next(request)

        token_to_set = getattr(request.state, "_new_session_token", None)
        if token_to_set:
            secure = request.url.scheme == "https"
            response.set_cookie(
                self._session_manager.cookie_name,
                token_to_set,
                httponly=True,
                secure=secure,
                samesite="Strict",
                max_age=self._session_manager.ttl_seconds,
                path="/",
            )
            self._logger.debug("[SESSION] New session cookie issued")
        return response
