import io
import logging
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import importlib

document_router_module = importlib.import_module("app.features.document_analysis.router")
document_router = document_router_module.router
from app.security_layer.dependencies import require_session
from app.security_layer.session_manager import SessionInfo


class _FakeSandboxResponse:
    status_code = 200
    ok = True
    text = "sandbox-ok"

    @staticmethod
    def json() -> dict:
        return {
            "text": "Документ содержит важную информацию.",
            "metadata": {"mime_type": "text/plain"},
        }


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(document_router)

    app.dependency_overrides[require_session] = lambda: SessionInfo(
        session_id="test-session",
        issued_at=0,
        legacy=False,
        token="session-token",
    )

    monkeypatch.setattr(document_router_module.requests, "post", lambda *args, **kwargs: _FakeSandboxResponse())

    with TestClient(app) as test_client:
        test_client.cookies.set("csrf-token", "test-token")
        yield test_client


def _call_document_analysis(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/file/analyze",
        data={
            "message": "Сделай краткое резюме.",
            "thread_id": "thread-123",
            "history": "[]",
            "history_message_count": "5",
            "provider_type": "openrouter",
        },
        headers=headers,
        files={
            "file": ("document.txt", io.BytesIO(b"example document"), "text/plain"),
        },
    )
    return {"status": response.status_code, "json": response.json(), "text": response.text}


def test_error_response_is_sanitized(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    forbidden_markers = ["Traceback", "app/features", ".py", "OPENAI", "AWS_SECRET", "GOOGLE"]

    def _raise_exception(*_args, **_kwargs):
        raise Exception("Traceback: OPENAI AWS_SECRET GOOGLE failure")

    monkeypatch.setattr(document_router_module, "call_ai_query", _raise_exception)

    result = _call_document_analysis(
        client,
        headers={
            "X-CSRF-Token": "test-token",
            "Origin": "https://igorekchatbot.ru",
        },
    )

    assert result["status"] == 500
    assert result["json"] == {"detail": "Не удалось сформировать ответ"}

    for marker in forbidden_markers:
        assert marker not in result["text"]


def test_stack_only_in_logs(client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def _raise_runtime_error(*_args, **_kwargs):
        raise Exception("Traceback: app/features/router.py failure")

    monkeypatch.setattr(document_router_module, "call_ai_query", _raise_runtime_error)
    caplog.clear()
    analysis_logger = logging.getLogger("igorek.api")
    analysis_logger.addHandler(caplog.handler)
    analysis_logger.setLevel(logging.ERROR)

    try:
        result = _call_document_analysis(
            client,
            headers={
                "X-CSRF-Token": "test-token",
                "Origin": "https://igorekchatbot.ru",
            },
        )
    finally:
        analysis_logger.removeHandler(caplog.handler)

    assert result["status"] == 500
    assert result["json"] == {"detail": "Не удалось сформировать ответ"}

    log_records = [record for record in caplog.records if "Ошибка генерации ответа" in record.getMessage()]
    assert log_records, "Ожидалась запись об ошибке генерации ответа в логах"
    assert all(record.levelno >= logging.ERROR for record in log_records)
    assert any(record.exc_info for record in log_records)

    for marker in ("Traceback", "app/features", ".py"):
        assert marker not in result["text"]
