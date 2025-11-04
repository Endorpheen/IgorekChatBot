from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.integration._tool_stub import stub_langchain_tool

with stub_langchain_tool():
    from app.features.chat import attachments as attachments_module
    from app.features.chat import router as chat_router_module
    from app.features.chat import service as chat_service_module
    from app.security_layer.dependencies import require_session
    from app.security_layer.session_manager import SessionInfo


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def reset_thread_overrides() -> Iterator[None]:
    chat_service_module.THREAD_MODEL_OVERRIDES.clear()
    try:
        yield
    finally:
        chat_service_module.THREAD_MODEL_OVERRIDES.clear()


@pytest.fixture()
def chat_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    attachments_module.reset_storage_for_tests(tmp_path)

    app = FastAPI()
    app.include_router(chat_router_module.router)

    monkeypatch.setattr(chat_router_module.settings, "signed_link_compat_enabled", True, raising=False)

    session = SessionInfo(
        session_id="test-session",
        issued_at=0,
        legacy=False,
        token="session-token",
    )
    app.dependency_overrides[require_session] = lambda: session

    with TestClient(app) as client:
        client.cookies.set("csrf-token", "test-token")
        yield client


def test_chat_endpoint_openrouter_records_override(chat_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    def _fake_call_ai_query(**kwargs: Any) -> str:
        captured["args"] = kwargs
        return "Готово."

    monkeypatch.setattr(chat_router_module, "call_ai_query", _fake_call_ai_query)

    payload = {
        "message": "Привет!",
        "openRouterApiKey": "user-key",
        "openRouterModel": "   anthropic/claude-3   ",
    }
    headers = {"X-CSRF-Token": "test-token"}

    response = chat_client.post("/chat", json=payload, headers=headers)
    assert response.status_code == 200

    body = response.json()
    thread_id = body["thread_id"]
    assert body["response"] == "Готово."
    assert body["status"] == "Message processed"
    assert body["attachments"] is None

    args = captured["args"]
    assert args["thread_id"] == thread_id
    assert args["provider_type"] == "openrouter"
    assert args["user_api_key"] == "user-key"
    assert args["user_model"] == "   anthropic/claude-3   "
    assert chat_service_module.THREAD_MODEL_OVERRIDES[thread_id] == "anthropic/claude-3"


def test_chat_endpoint_agentrouter_passes_provider_args(chat_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    def _fake_call_ai_query(**kwargs: Any) -> str:
        captured["args"] = kwargs
        return "Agent router ответил."

    monkeypatch.setattr(chat_router_module, "call_ai_query", _fake_call_ai_query)

    payload = {
        "message": "Сменить провайдера",
        "providerType": "agentrouter",
        "agentRouterApiKey": "agent-key",
        "agentRouterModel": "router-model",
        "agentRouterBaseUrl": "https://agent.internal/api",
    }
    headers = {"X-CSRF-Token": "test-token"}

    response = chat_client.post("/chat", json=payload, headers=headers)
    assert response.status_code == 200

    body = response.json()
    thread_id = body["thread_id"]
    assert body["response"] == "Agent router ответил."
    assert body["status"] == "Message processed"

    args = captured["args"]
    assert args["thread_id"] == thread_id
    assert args["provider_type"] == "agentrouter"
    assert args["user_api_key"] == "agent-key"
    assert args["user_model"] == "router-model"
    assert args["agent_base_url"] == "https://agent.internal/api"
    assert chat_service_module.THREAD_MODEL_OVERRIDES[thread_id] == "router-model"


def test_call_ai_query_tool_failure_returns_marker(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    attachments_module.reset_storage_for_tests(tmp_path)
    monkeypatch.setattr(chat_service_module.settings, "openrouter_api_key", "base-key", raising=False)
    monkeypatch.setattr(chat_service_module.settings, "openrouter_model", "openai/gpt-4o-mini", raising=False)

    thread_id = "thread-tool-error"
    tool_payloads: List[Dict[str, Any]] = []

    class _FakeAIMessage:
        content = "intermediate"
        tool_calls = [
            {
                "id": "call-1",
                "name": "run_code_in_sandbox",
                "args": {"code": "print('hello')", "thread_id": thread_id},
            }
        ]

    class _FakeLLMWithTools:
        def invoke(self, conversation: List[Any]) -> _FakeAIMessage:
            return _FakeAIMessage()

    class _FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def bind_tools(self, tools: List[Any]) -> _FakeLLMWithTools:
            return _FakeLLMWithTools()

    class _FailingTool:
        def run(self, args: Dict[str, Any]) -> None:
            tool_payloads.append(args)
            storage = attachments_module.get_storage()
            stored = storage.create_attachment(
                filename="tool.json",
                content='{"status":"error"}',
                content_type="application/json",
            )
            attachments_module.record_thread_attachment(args.get("thread_id", thread_id), stored, "sandbox failure")
            raise RuntimeError("sandbox failure")

    _failing_tool = _FailingTool()
    monkeypatch.setattr(chat_service_module, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setattr(chat_service_module, "run_code_in_sandbox", _failing_tool)

    result = chat_service_module.call_ai_query(
        prompt="Сгенерируй ответ",
        thread_id=thread_id,
        provider_type="openrouter",
        user_api_key="user-key",
        user_model="preferred-model",
    )

    assert result == "API_ERROR_GENERATING_RESPONSE"
    assert tool_payloads and tool_payloads[0]["thread_id"] == thread_id
    assert attachments_module.consume_thread_attachments(thread_id) == []
