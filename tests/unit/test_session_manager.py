from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest
from fastapi import Request

from app.security_layer.session_manager import (
    SessionInfo,
    SessionManager,
    UnauthorizedSessionError,
)


pytestmark = pytest.mark.unit


@pytest.fixture
def fixed_secret() -> str:
    return "test-secret-key-for-unit-testing"


@pytest.fixture
def session_manager(fixed_secret: str) -> SessionManager:
    return SessionManager(
        secret=fixed_secret,
        ttl_seconds=3600,
        cookie_name="test_session",
        header_name="X-Test-Session",
        legacy_enabled=False,
        legacy_origins=[],
    )


@pytest.fixture
def legacy_session_manager(fixed_secret: str) -> SessionManager:
    return SessionManager(
        secret=fixed_secret,
        ttl_seconds=3600,
        cookie_name="test_session",
        header_name="X-Test-Session",
        legacy_enabled=True,
        legacy_origins=["https://example.com", "http://localhost:3000"],
    )


class TestSessionManagerTokenIssuance:
    def test_issue_token_creates_valid_format(self, session_manager: SessionManager) -> None:
        token, session_id, issued_at = session_manager._issue_token()

        assert isinstance(token, str)
        assert isinstance(session_id, str)
        assert isinstance(issued_at, int)

        # Формат: session_id.issued_at.signature
        parts = token.split(".")
        assert len(parts) == 3
        assert parts[0] == session_id
        assert parts[1] == str(issued_at)
        assert len(parts[2]) == 64  # SHA256 hex digest

    def test_issue_token_generates_unique_tokens(self, session_manager: SessionManager) -> None:
        tokens = set()
        for _ in range(10):
            token, _, _ = session_manager._issue_token()
            assert token not in tokens
            tokens.add(token)

    def test_issue_token_timestamp_is_current(self, session_manager: SessionManager) -> None:
        before = int(time.time())
        _, _, issued_at = session_manager._issue_token()
        after = int(time.time())

        assert before <= issued_at <= after


class TestSessionManagerTokenVerification:
    def test_verify_valid_token(self, session_manager: SessionManager) -> None:
        token, session_id, issued_at = session_manager._issue_token()

        info = session_manager._verify_token(token)

        assert info is not None
        assert info.session_id == session_id
        assert info.issued_at == issued_at
        assert info.legacy is False
        assert info.token == token

    def test_verify_invalid_format_token(self, session_manager: SessionManager) -> None:
        invalid_tokens = [
            "too-short",
            "only.two.parts",
            "too.many.parts.here",
            "",
            "justdot.",
            ".dotstart",
            "dotend.",
        ]

        for token in invalid_tokens:
            assert session_manager._verify_token(token) is None

    def test_verify_invalid_signature(self, session_manager: SessionManager) -> None:
        # Создаем валидный токен, но меняем подпись
        token, _, _ = session_manager._issue_token()
        parts = token.split(".")
        invalid_token = f"{parts[0]}.{parts[1]}.invalid_signature_here"

        assert session_manager._verify_token(invalid_token) is None

    def test_verify_expired_token(self, session_manager: SessionManager) -> None:
        # Создаем токен с истекшим временем
        past_time = int(time.time()) - session_manager.ttl_seconds - 100
        token, session_id, _ = session_manager._issue_token()

        # Подменяем время на прошлое
        parts = token.split(".")
        expired_token = f"{parts[0]}.{past_time}.{parts[2]}"

        assert session_manager._verify_token(expired_token) is None

    def test_verify_token_with_invalid_timestamp(self, session_manager: SessionManager) -> None:
        token, _, _ = session_manager._issue_token()
        parts = token.split(".")
        invalid_timestamp_token = f"{parts[0]}.not_a_number.{parts[2]}"

        assert session_manager._verify_token(invalid_timestamp_token) is None


class TestSessionManagerTokenExtraction:
    def test_extract_token_from_header(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Test-Session": "header-token"}
        request.cookies = {}

        token = session_manager._extract_token(request)
        assert token == "header-token"

    def test_extract_token_from_cookie(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {"test_session": "cookie-token"}

        token = session_manager._extract_token(request)
        assert token == "cookie-token"

    def test_extract_token_header_priority_over_cookie(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Test-Session": "header-token"}
        request.cookies = {"test_session": "cookie-token"}

        token = session_manager._extract_token(request)
        assert token == "header-token"

    def test_extract_token_strips_whitespace(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Test-Session": "  spaced-token  "}
        request.cookies = {}

        token = session_manager._extract_token(request)
        assert token == "spaced-token"

    def test_extract_token_no_token_present(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {}

        token = session_manager._extract_token(request)
        assert token is None


class TestSessionManagerResolution:
    def test_resolve_valid_token_from_header(self, session_manager: SessionManager) -> None:
        token, _, _ = session_manager._issue_token()
        request = Mock(spec=Request)
        request.headers = {"X-Test-Session": token}
        request.cookies = {}

        info, new_token = session_manager.resolve(request)

        assert info is not None
        assert info.token == token
        assert new_token is None

    def test_resolve_valid_token_from_cookie(self, session_manager: SessionManager) -> None:
        token, _, _ = session_manager._issue_token()
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {"test_session": token}

        info, new_token = session_manager.resolve(request)

        assert info is not None
        assert info.token == token
        assert new_token is None

    def test_resolve_invalid_token_returns_none(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Test-Session": "invalid-token"}
        request.cookies = {}

        info, new_token = session_manager.resolve(request)

        assert info is None
        assert new_token is None

    def test_resolve_no_token_returns_none_when_legacy_disabled(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {}

        info, new_token = session_manager.resolve(request)

        assert info is None
        assert new_token is None


class TestSessionManagerLegacyMode:
    def test_resolve_legacy_id_creates_new_session(self, legacy_session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Client-Session": "legacy-session-123"}
        request.cookies = {}
        request.headers.update({"Origin": "https://example.com"})
        request.url = Mock()
        request.url.scheme = "https"

        info, new_token = legacy_session_manager.resolve(request)

        assert info is not None
        assert info.legacy is True
        assert info.token == new_token
        assert new_token is not None
        assert len(new_token.split(".")) == 3

    def test_resolve_legacy_id_rejected_for_wrong_origin(self, legacy_session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Client-Session": "legacy-session-123"}
        request.cookies = {}
        request.headers.update({"Origin": "https://evil.com"})
        request.url = Mock()
        request.url.scheme = "https"

        info, new_token = legacy_session_manager.resolve(request)

        assert info is None
        assert new_token is None

    def test_resolve_legacy_id_from_cookie(self, legacy_session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {"client_session": "legacy-session-456"}
        request.headers.update({"Referer": "http://localhost:3000/page"})
        request.url = Mock()
        request.url.scheme = "http"

        info, new_token = legacy_session_manager.resolve(request)

        assert info is not None
        assert info.legacy is True
        assert new_token is not None

    def test_legacy_disabled_ignores_legacy_id(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Client-Session": "legacy-session-123"}
        request.cookies = {}
        request.headers.update({"Origin": "https://example.com"})
        request.url = Mock()
        request.url.scheme = "https"

        info, new_token = session_manager.resolve(request)

        assert info is None
        assert new_token is None


class TestSessionManagerRequireSession:
    def test_require_session_with_valid_token(self, session_manager: SessionManager) -> None:
        token, _, _ = session_manager._issue_token()
        request = Mock(spec=Request)
        request.headers = {"X-Test-Session": token}
        request.cookies = {}

        info = session_manager.require_session(request)

        assert info is not None
        assert info.token == token

    def test_require_session_with_no_token_raises_error(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {}
        request.cookies = {}

        with pytest.raises(UnauthorizedSessionError, match="Сессия отсутствует или истекла"):
            session_manager.require_session(request)

    def test_require_session_with_invalid_token_raises_error(self, session_manager: SessionManager) -> None:
        request = Mock(spec=Request)
        request.headers = {"X-Test-Session": "invalid-token"}
        request.cookies = {}

        with pytest.raises(UnauthorizedSessionError, match="Сессия отсутствует или истекла"):
            session_manager.require_session(request)


class TestSessionManagerProperties:
    def test_cookie_name_property(self, session_manager: SessionManager) -> None:
        assert session_manager.cookie_name == "test_session"

    def test_ttl_seconds_property(self, session_manager: SessionManager) -> None:
        assert session_manager.ttl_seconds == 3600

    def test_minimum_ttl_enforced(self) -> None:
        manager = SessionManager(
            secret="test",
            ttl_seconds=30,  # Less than minimum 60
            cookie_name="test",
            header_name="test",
            legacy_enabled=False,
            legacy_origins=[],
        )
        assert manager.ttl_seconds == 60  # Should be enforced to minimum


class TestSessionManagerInitWithoutSecret:
    def test_init_without_secret_generates_warning(self) -> None:
        with patch("app.security_layer.session_manager._logger") as mock_logger:
            manager = SessionManager(
                secret="",
                ttl_seconds=3600,
                cookie_name="test",
                header_name="test",
                legacy_enabled=False,
                legacy_origins=[],
            )

            assert manager._secret  # Should have generated a secret
            mock_logger.warning.assert_called_once()


class TestSessionInfoDataclass:
    def test_session_info_creation(self) -> None:
        info = SessionInfo(
            session_id="test-session",
            issued_at=1234567890,
            legacy=False,
            token="test-token"
        )

        assert info.session_id == "test-session"
        assert info.issued_at == 1234567890
        assert info.legacy is False
        assert info.token == "test-token"

    def test_session_info_defaults(self) -> None:
        info = SessionInfo(
            session_id="test-session",
            issued_at=1234567890
        )

        assert info.legacy is False
        assert info.token is None