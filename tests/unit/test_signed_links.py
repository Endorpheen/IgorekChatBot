from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException, status

from app.security_layer.signed_links import (
    SignedLinkManager,
    SignedPayload,
)


pytestmark = pytest.mark.unit


@pytest.fixture
def fixed_secret() -> str:
    return "test-signed-link-secret"


@pytest.fixture
def signed_link_manager(fixed_secret: str) -> SignedLinkManager:
    return SignedLinkManager(
        secret=fixed_secret,
        ttl_seconds=3600,
    )


class TestSignedLinkManagerIssuance:
    def test_issue_creates_valid_format(self, signed_link_manager: SignedLinkManager) -> None:
        resource = "test-resource"
        data = {"user_id": 123, "action": "download"}

        token = signed_link_manager.issue(resource, data)

        assert isinstance(token, str)
        assert "." in token  # Should have signature separator

    def test_issue_includes_all_required_fields(self, signed_link_manager: SignedLinkManager) -> None:
        resource = "test-resource"
        data = {"key": "value"}
        before = int(time.time())

        token = signed_link_manager.issue(resource, data)
        after = int(time.time())

        # Decode and verify payload
        payload_part, signature = token.split(".", 1)
        padded = payload_part + "=" * (-len(payload_part) % 4)

        import base64
        import json
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))

        assert payload["resource"] == resource
        assert payload["data"] == data
        assert before <= payload["exp"] <= after + signed_link_manager._ttl
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest

    def test_issue_with_custom_ttl(self, signed_link_manager: SignedLinkManager) -> None:
        resource = "test-resource"
        data = {"test": True}
        custom_ttl = 1800  # 30 minutes
        before = int(time.time())

        token = signed_link_manager.issue(resource, data, ttl=custom_ttl)

        # Decode and verify expiration
        payload_part, _ = token.split(".", 1)
        padded = payload_part + "=" * (-len(payload_part) % 4)

        import base64
        import json
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))

        expected_exp = before + custom_ttl
        assert payload["exp"] == expected_exp

    def test_issue_enforces_minimum_ttl(self, signed_link_manager: SignedLinkManager) -> None:
        resource = "test-resource"
        data = {"test": True}

        # Try with TTL less than minimum (10)
        token = signed_link_manager.issue(resource, data, ttl=5)

        # Decode and verify expiration uses minimum
        payload_part, _ = token.split(".", 1)
        padded = payload_part + "=" * (-len(payload_part) % 4)

        import base64
        import json
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))

        before = int(time.time())
        min_expected = before + 10
        assert payload["exp"] >= min_expected

    def test_issue_generates_unique_tokens(self, signed_link_manager: SignedLinkManager) -> None:
        resource = "test-resource"
        data = {"test": True}

        tokens = set()
        for i in range(10):
            # Add uniqueness to data to ensure different tokens
            unique_data = {**data, "index": i}
            token = signed_link_manager.issue(resource, unique_data)
            assert token not in tokens
            tokens.add(token)


class TestSignedLinkManagerVerification:
    def test_verify_valid_token(self, signed_link_manager: SignedLinkManager) -> None:
        resource = "test-resource"
        data = {"user_id": 123}
        token = signed_link_manager.issue(resource, data)

        payload = signed_link_manager.verify(token)

        assert isinstance(payload, SignedPayload)
        assert payload.resource == resource
        assert payload.data == data
        assert payload.expires_at > int(time.time())

    def test_verify_token_with_invalid_format(self, signed_link_manager: SignedLinkManager) -> None:
        invalid_tokens = [
            "no-separator",
            "multiple.separators.here",
            "",
            "justdot.",
            ".dotstart",
        ]

        for token in invalid_tokens:
            with pytest.raises(HTTPException) as exc_info:
                signed_link_manager.verify(token)
            # Should be 400 for format errors or 403 for signature errors
            assert exc_info.value.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN]

    def test_verify_token_with_invalid_base64(self, signed_link_manager: SignedLinkManager) -> None:
        # Valid format but invalid base64
        token = "invalid-base64-content.signature"

        with pytest.raises(HTTPException) as exc_info:
            signed_link_manager.verify(token)
        # Should be 400 for base64 errors or 403 for signature errors
        assert exc_info.value.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN]

    def test_verify_token_with_invalid_signature(self, signed_link_manager: SignedLinkManager) -> None:
        # Create valid token then modify signature
        token = signed_link_manager.issue("test", {"data": True})
        payload_part, _ = token.split(".", 1)
        invalid_token = f"{payload_part}.invalid_signature"

        with pytest.raises(HTTPException) as exc_info:
            signed_link_manager.verify(invalid_token)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Подпись недействительна" in str(exc_info.value.detail)

    def test_verify_expired_token(self, signed_link_manager: SignedLinkManager) -> None:
        # Create token with past expiration
        resource = "test-resource"
        data = {"test": True}

        # Manually create expired token
        past_time = int(time.time()) - 100  # 100 seconds ago
        payload = {
            "resource": resource,
            "data": data,
            "exp": past_time,
        }

        import json
        import base64
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = signed_link_manager._sign(raw)
        token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
        expired_token = f"{token}.{signature}"

        with pytest.raises(HTTPException) as exc_info:
            signed_link_manager.verify(expired_token)
        assert exc_info.value.status_code == status.HTTP_410_GONE
        assert "Ссылка истекла" in str(exc_info.value.detail)

    def test_verify_token_with_invalid_json(self, signed_link_manager: SignedLinkManager) -> None:
        # Create token with invalid JSON in payload
        import base64
        invalid_json = b'{"invalid": json}'
        signature = signed_link_manager._sign(invalid_json)
        token = base64.urlsafe_b64encode(invalid_json).decode("utf-8").rstrip("=")
        invalid_token = f"{token}.{signature}"

        with pytest.raises(HTTPException) as exc_info:
            signed_link_manager.verify(invalid_token)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Некорректная ссылка" in str(exc_info.value.detail)

    def test_verify_token_missing_required_fields(self, signed_link_manager: SignedLinkManager) -> None:
        # Test missing resource field
        import json
        import base64

        payload_data = {"data": {"test": True}, "exp": int(time.time()) + 3600}
        raw = json.dumps(payload_data, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = signed_link_manager._sign(raw)
        token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
        invalid_token = f"{token}.{signature}"

        with pytest.raises(HTTPException) as exc_info:
            signed_link_manager.verify(invalid_token)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

        # Test missing data field
        payload_data = {"resource": "test", "exp": int(time.time()) + 3600}
        raw = json.dumps(payload_data, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = signed_link_manager._sign(raw)
        token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
        invalid_token = f"{token}.{signature}"

        with pytest.raises(HTTPException) as exc_info:
            signed_link_manager.verify(invalid_token)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


class TestSignedLinkManagerProperties:
    def test_minimum_ttl_enforced(self) -> None:
        manager = SignedLinkManager(secret="test", ttl_seconds=10)  # Less than minimum 30
        assert manager._ttl == 30  # Should be enforced to minimum

    def test_ttl_property(self, signed_link_manager: SignedLinkManager) -> None:
        assert signed_link_manager._ttl == 3600


class TestSignedLinkManagerInitWithoutSecret:
    def test_init_without_secret_generates_warning(self) -> None:
        with patch("app.security_layer.signed_links._logger") as mock_logger:
            manager = SignedLinkManager(secret="", ttl_seconds=3600)

            assert manager._secret  # Should have generated a secret
            mock_logger.warning.assert_called_once()


class TestSignedPayloadDataclass:
    def test_signed_payload_creation(self) -> None:
        payload = SignedPayload(
            resource="test-resource",
            data={"key": "value"},
            expires_at=1234567890
        )

        assert payload.resource == "test-resource"
        assert payload.data == {"key": "value"}
        assert payload.expires_at == 1234567890


class TestSignedLinkManagerSignature:
    def test_signature_is_deterministic(self, signed_link_manager: SignedLinkManager) -> None:
        # Same data should produce same signature
        import json
        import base64

        payload = {
            "resource": "test",
            "data": {"key": "value"},
            "exp": int(time.time()) + 3600,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

        signature1 = signed_link_manager._sign(raw)
        signature2 = signed_link_manager._sign(raw)

        assert signature1 == signature2
        assert len(signature1) == 64  # SHA256 hex digest

    def test_signature_changes_with_different_data(self, signed_link_manager: SignedLinkManager) -> None:
        import json

        payload1 = {"resource": "test1", "data": {"key": "value"}, "exp": 1234567890}
        payload2 = {"resource": "test2", "data": {"key": "value"}, "exp": 1234567890}

        raw1 = json.dumps(payload1, separators=(",", ":"), sort_keys=True).encode("utf-8")
        raw2 = json.dumps(payload2, separators=(",", ":"), sort_keys=True).encode("utf-8")

        signature1 = signed_link_manager._sign(raw1)
        signature2 = signed_link_manager._sign(raw2)

        assert signature1 != signature2


class TestSignedLinkManagerComplexData:
    def test_issue_verify_with_complex_data(self, signed_link_manager: SignedLinkManager) -> None:
        complex_data = {
            "user_id": 123,
            "permissions": ["read", "write"],
            "metadata": {
                "source": "web",
                "timestamp": 1234567890,
                "nested": {"deep": {"value": True}}
            },
            "active": True,
            "count": 42,
        }

        token = signed_link_manager.issue("complex-resource", complex_data)
        payload = signed_link_manager.verify(token)

        assert payload.resource == "complex-resource"
        assert payload.data == complex_data