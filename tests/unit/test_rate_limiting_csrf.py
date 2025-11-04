from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, Request

from app.security_layer.rate_limiter import RateLimiter, RateLimitConfig, get_rate_limiter


pytestmark = pytest.mark.unit


@pytest.fixture
def rate_limiter() -> RateLimiter:
    return RateLimiter()


class TestRateLimiter:
    def test_hit_within_limit_allows_request(self, rate_limiter: RateLimiter) -> None:
        config = RateLimitConfig(limit=5, window_seconds=60)

        # Should allow up to limit
        for i in range(5):
            rate_limiter.hit("test_key", "test_id", config)

    def test_hit_exceeding_limit_raises_exception(self, rate_limiter: RateLimiter) -> None:
        config = RateLimitConfig(limit=2, window_seconds=60)

        # First two hits should be allowed
        rate_limiter.hit("test_key", "test_id", config)
        rate_limiter.hit("test_key", "test_id", config)

        # Third hit should raise exception
        with pytest.raises(HTTPException) as exc_info:
            rate_limiter.hit("test_key", "test_id", config)

        assert exc_info.value.status_code == 429
        assert "Превышен лимит обращений" in str(exc_info.value.detail)

    def test_different_keys_have_separate_limits(self, rate_limiter: RateLimiter) -> None:
        config = RateLimitConfig(limit=2, window_seconds=60)

        # Hit limit for key1
        rate_limiter.hit("key1", "test_id", config)
        rate_limiter.hit("key1", "test_id", config)

        # Should still allow hits for key2
        rate_limiter.hit("key2", "test_id", config)
        rate_limiter.hit("key2", "test_id", config)

        # But key1 should still be limited
        with pytest.raises(HTTPException):
            rate_limiter.hit("key1", "test_id", config)

    def test_window_cleanup_allows_new_requests(self, rate_limiter: RateLimiter) -> None:
        config = RateLimitConfig(limit=2, window_seconds=1)

        # Hit limit
        rate_limiter.hit("test_key", "test_id", config)
        rate_limiter.hit("test_key", "test_id", config)

        # Should be limited
        with pytest.raises(HTTPException):
            rate_limiter.hit("test_key", "test_id", config)

        # Wait for window to pass
        time.sleep(1.1)

        # Should allow new requests
        rate_limiter.hit("test_key", "test_id", config)

    def test_get_rate_limiter_returns_singleton(self) -> None:
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2
        assert isinstance(limiter1, RateLimiter)


class TestCSRFProtection:
    def test_valid_csrf_tokens_allow_request(self) -> None:
        from app.middlewares.security import _require_csrf_token

        mock_request = Mock(spec=Request)
        mock_request.cookies = {"csrf-token": "valid-token"}
        mock_request.headers = {"X-CSRF-Token": "valid-token"}

        # Should not raise exception
        _require_csrf_token(mock_request)

    def test_missing_cookie_token_blocks_request(self) -> None:
        from app.middlewares.security import _require_csrf_token

        mock_request = Mock(spec=Request)
        mock_request.cookies = {}
        mock_request.headers = {"X-CSRF-Token": "some-token"}

        with pytest.raises(HTTPException) as exc_info:
            _require_csrf_token(mock_request)

        assert exc_info.value.status_code == 403
        assert "csrf_failed" in str(exc_info.value.detail)

    def test_missing_header_token_blocks_request(self) -> None:
        from app.middlewares.security import _require_csrf_token

        mock_request = Mock(spec=Request)
        mock_request.cookies = {"csrf-token": "some-token"}
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            _require_csrf_token(mock_request)

        assert exc_info.value.status_code == 403
        assert "csrf_failed" in str(exc_info.value.detail)

    def test_mismatched_tokens_block_request(self) -> None:
        from app.middlewares.security import _require_csrf_token

        mock_request = Mock(spec=Request)
        mock_request.cookies = {"csrf-token": "cookie-token"}
        mock_request.headers = {"X-CSRF-Token": "header-token"}

        with pytest.raises(HTTPException) as exc_info:
            _require_csrf_token(mock_request)

        assert exc_info.value.status_code == 403
        assert "csrf_failed" in str(exc_info.value.detail)

    @patch('app.middlewares.security.get_settings')
    def test_valid_origin_allows_request(self, mock_get_settings: Mock) -> None:
        from app.middlewares.security import _require_csrf_token

        mock_get_settings.return_value.allow_origins = ["https://example.com"]
        mock_request = Mock(spec=Request)
        mock_request.cookies = {"csrf-token": "valid-token"}
        mock_request.headers = {"X-CSRF-Token": "valid-token", "Origin": "https://example.com"}

        # Should not raise exception
        _require_csrf_token(mock_request)

    @patch('app.middlewares.security.get_settings')
    def test_invalid_origin_blocks_request(self, mock_get_settings: Mock) -> None:
        from app.middlewares.security import _require_csrf_token

        mock_get_settings.return_value.allow_origins = ["https://example.com"]
        mock_request = Mock(spec=Request)
        mock_request.cookies = {"csrf-token": "valid-token"}
        mock_request.headers = {"X-CSRF-Token": "valid-token", "Origin": "https://evil.com"}

        with pytest.raises(HTTPException) as exc_info:
            _require_csrf_token(mock_request)

        assert exc_info.value.status_code == 403
        assert "Недопустимый источник запроса" in str(exc_info.value.detail)