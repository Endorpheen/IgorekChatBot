from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security_layer.dependencies import require_session
from app.security_layer.session_manager import SessionInfo

image_router_module = importlib.import_module("app.features.image_generation.router")
image_router = image_router_module.router


class _DummyLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def hit(self, key: str, identifier: str, _config: object) -> None:
        self.calls.append((key, identifier))


@pytest.fixture()
def image_router_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, TestClient]]:
    limiter = _DummyLimiter()
    monkeypatch.setattr(image_router_module, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(image_router_module.signed_links, "issue", lambda *_args, **_kwargs: "test-token")
    monkeypatch.setattr(
        image_router_module.settings,
        "signed_link_compat_enabled",
        True,
        raising=False,
    )

    app = FastAPI()
    app.include_router(image_router)

    app.dependency_overrides[require_session] = lambda: SessionInfo(
        session_id="test-session",
        issued_at=0,
        legacy=False,
        token="session-token",
    )

    with TestClient(app) as client:
        yield app, client


@pytest.mark.parametrize(
    ("path", "expected_location"),
    [
        ("/image/jobs/job-123", "/signed/image/jobs/status?token=test-token"),
        ("/image/jobs/job-123/result", "/signed/image/jobs/result?token=test-token"),
        ("/image/files/job-123.webp", "/signed/image/jobs/result?token=test-token"),
    ],
)
def test_redirects_are_relative(image_router_client: tuple[FastAPI, TestClient], path: str, expected_location: str) -> None:
    app, client = image_router_client

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == expected_location


@pytest.mark.parametrize(
    "path",
    [
        "/image/jobs/job-123",
        "/image/jobs/job-123/result",
        "/image/files/job-123.webp",
    ],
)
def test_redirects_reject_external_urls(
    image_router_client: tuple[FastAPI, TestClient],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    app, client = image_router_client

    monkeypatch.setattr(app, "url_path_for", lambda *_args, **_kwargs: "https://evil.example/path")

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 400
    assert response.json() == {"detail": "Неверный адрес перенаправления"}
