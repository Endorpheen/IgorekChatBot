from fastapi import HTTPException, Request


def _require_csrf_token(request: Request) -> None:
    cookie_token = request.cookies.get("csrf-token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(
            status_code=403,
            detail={"code": "csrf_failed", "message": "CSRF проверка не пройдена"},
        )


def verify_client_session(request: Request) -> str:
    session_id = (request.headers.get("X-Client-Session") or request.cookies.get("client_session") or "").strip()
    if not session_id:
        raise HTTPException(status_code=403, detail={"code": "missing_session", "message": "Доступ запрещён"})
    return session_id
