from __future__ import annotations

import io
from typing import Any, Dict, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.integration._tool_stub import stub_langchain_tool

with stub_langchain_tool():
    from app.features.image_analysis import router as image_router_module
    from app.security_layer.dependencies import require_session
    from app.security_layer.session_manager import SessionInfo

pytestmark = pytest.mark.integration


@pytest.fixture()
def image_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(image_router_module.router)

    session = SessionInfo(
        session_id="img-session",
        issued_at=0,
        legacy=False,
        token="session-token",
    )
    app.dependency_overrides[require_session] = lambda: session

    monkeypatch.setattr(image_router_module, "upload_dir", tmp_path)
    monkeypatch.setattr(image_router_module.settings, "upload_dir_abs", tmp_path, raising=False)
    monkeypatch.setattr(image_router_module.settings, "upload_url_prefix", "/uploads", raising=False)
    monkeypatch.setattr(image_router_module.settings, "openrouter_api_key", "base-openrouter", raising=False)
    monkeypatch.setattr(image_router_module.settings, "openrouter_model", "openai/gpt-4o-mini", raising=False)
    monkeypatch.setattr(image_router_module.settings, "allowed_agentrouter_base_urls", ["https://agent.example.com"], raising=False)

    image_router_module.THREAD_MODEL_OVERRIDES.clear()
    try:
        with TestClient(app) as client:
            client.cookies.set("csrf-token", "test-token")
            yield client
    finally:
        image_router_module.THREAD_MODEL_OVERRIDES.clear()


def _make_image_payload() -> Dict[str, tuple[str, io.BytesIO, str]]:
    return {
        "files": (
            "photo.png",
            io.BytesIO(b"\x89PNG\r\n\x1a\n"),
            "image/png",
        )
    }


def test_openrouter_provider_uses_openrouter_client(image_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    def _fake_call_openrouter_for_image(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "Описываю изображение через OpenRouter."

    monkeypatch.setattr(image_router_module, "call_openrouter_for_image", _fake_call_openrouter_for_image)

    response = image_client.post(
        "/image/analyze",
        data={
            "thread_id": "thread-openrouter",
            "message": "Что на фото?",
            "history": "[]",
            "history_message_count": "5",
            "provider_type": "openrouter",
            "open_router_api_key": "user-openrouter",
            "open_router_model": "openai/gpt-4o-mini",
        },
        headers={"X-CSRF-Token": "test-token"},
        files=_make_image_payload(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Описываю изображение через OpenRouter."
    assert payload["thread_id"] == "thread-openrouter"

    assert captured["api_key"] == "user-openrouter"
    assert captured["model"] == "openai/gpt-4o-mini"
    assert isinstance(captured["messages"], list)


def test_agentrouter_provider_uses_agent_client(image_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    def _fake_call_agentrouter_for_image(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "Описываю изображение через OpenAI Compatible."

    monkeypatch.setattr(image_router_module, "call_agentrouter_for_image", _fake_call_agentrouter_for_image)

    response = image_client.post(
        "/image/analyze",
        data={
            "thread_id": "thread-agentrouter",
            "message": "Опиши картинку",
            "history": "[]",
            "history_message_count": "5",
            "provider_type": "agentrouter",
            "agent_router_api_key": "agent-key",
            "agent_router_model": "gpt-4o-mini",
            "agent_router_base_url": "https://agent.example.com/v1",
        },
        headers={"X-CSRF-Token": "test-token"},
        files=_make_image_payload(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Описываю изображение через OpenAI Compatible."
    assert payload["thread_id"] == "thread-agentrouter"

    assert captured["api_key"] == "agent-key"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["base_url"] == "https://agent.example.com/v1"
    assert isinstance(captured["messages"], list)


def test_agentrouter_rejects_non_vision_model(image_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _should_not_be_called(**_kwargs: Any) -> str:
        raise AssertionError("call_agentrouter_for_image must not be invoked for non-vision model")

    monkeypatch.setattr(image_router_module, "call_agentrouter_for_image", _should_not_be_called)

    response = image_client.post(
        "/image/analyze",
        data={
            "thread_id": "thread-block",
            "message": "Опиши картинку",
            "history": "[]",
            "history_message_count": "5",
            "provider_type": "agentrouter",
            "agent_router_api_key": "agent-key",
            "agent_router_model": "gpt-3.5-turbo",
            "agent_router_base_url": "https://agent.example.com/v1",
        },
        headers={"X-CSRF-Token": "test-token"},
        files=_make_image_payload(),
    )

    assert response.status_code == 400
    assert "не поддерживает анализ изображений" in response.json().get("detail", "")
