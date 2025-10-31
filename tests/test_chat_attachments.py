from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.chat import attachments as attachments_module
from app.features.chat import router as chat_router_module
from app.security_layer.dependencies import require_session
from app.security_layer.session_manager import SessionInfo


@pytest.fixture()
def chat_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(chat_router_module.router)

    attachments_module.reset_storage_for_tests(tmp_path)
    monkeypatch.setattr(chat_router_module.settings, "signed_link_compat_enabled", True, raising=False)

    app.dependency_overrides[require_session] = lambda: SessionInfo(
        session_id="test-session",
        issued_at=0,
        legacy=False,
        token="session-token",
    )

    with TestClient(app) as client:
        client.cookies.set("csrf-token", "test-token")
        yield client


def test_chat_attachment_creation_and_download(chat_client: TestClient) -> None:
    payload = {
        "filename": "summary.md",
        "content": "# Итог\n\nЭто тестовое вложение.",
        "description": "Автоматически сгенерированный файл",
    }
    headers = {"X-CSRF-Token": "test-token"}

    response = chat_client.post("/chat/attachments", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "created"
    attachment = data["attachment"]
    assert attachment["filename"] == "summary.md"
    assert attachment["content_type"] == "text/markdown"
    assert attachment["size"] > 0

    download_response = chat_client.get(attachment["url"])
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith("text/markdown")
    assert download_response.text == payload["content"]


def test_chat_attachment_rejects_invalid_extension(chat_client: TestClient) -> None:
    payload = {
        "filename": "report.exe",
        "content": "binary???",
    }
    headers = {"X-CSRF-Token": "test-token"}

    response = chat_client.post("/chat/attachments", json=payload, headers=headers)

    assert response.status_code == 415
    assert response.json()["detail"].startswith("Недопустимое расширение файла")
