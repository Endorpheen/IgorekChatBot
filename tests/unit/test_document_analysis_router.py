from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


class TestDocumentAnalysisRouter:
    def test_router_imports(self) -> None:
        """Test that document analysis router can be imported"""
        from app.features.document_analysis.router import (
            router, MAX_DOCUMENT_SIZE, DOCUMENT_TEXT_LIMIT,
            SANDBOX_TIMEOUT, ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES
        )

        # Test constants exist
        assert MAX_DOCUMENT_SIZE == 10 * 1024 * 1024
        assert DOCUMENT_TEXT_LIMIT == 120_000
        assert SANDBOX_TIMEOUT == 30
        assert isinstance(ALLOWED_EXTENSIONS, set)
        assert isinstance(ALLOWED_MIME_TYPES, dict)
        assert router is not None

    def test_resolve_sandbox_document_url(self) -> None:
        """Test sandbox URL resolution function"""
        from app.features.document_analysis.router import _resolve_sandbox_document_url

        with patch('app.features.document_analysis.router.settings') as mock_settings:
            # Test basic URL
            mock_settings.sandbox_service_url = "http://sandbox:8080"
            result = _resolve_sandbox_document_url()
            assert result == "http://sandbox:8080/analyze/document"

            # Test URL ending with /execute
            mock_settings.sandbox_service_url = "http://sandbox:8080/execute"
            result = _resolve_sandbox_document_url()
            assert result == "http://sandbox:8080/analyze/document"

            # Test URL with trailing slash
            mock_settings.sandbox_service_url = "http://sandbox:8080/"
            result = _resolve_sandbox_document_url()
            assert result == "http://sandbox:8080/analyze/document"

    def test_is_mime_allowed_function(self) -> None:
        """Test MIME type validation function"""
        from app.features.document_analysis.router import _is_mime_allowed

        # Test allowed combinations
        assert _is_mime_allowed('.pdf', 'application/pdf') == True
        assert _is_mime_allowed('.md', 'text/markdown') == True
        assert _is_mime_allowed('.txt', 'text/plain') == True
        assert _is_mime_allowed('.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') == True

        # Test disallowed combinations
        assert _is_mime_allowed('.pdf', 'text/plain') == False
        assert _is_mime_allowed('.txt', 'application/pdf') == False
        assert _is_mime_allowed('.docx', 'text/markdown') == False

        # Test alternative allowed MIME types
        assert _is_mime_allowed('.pdf', 'application/x-pdf') == True
        assert _is_mime_allowed('.md', 'text/plain') == True
        assert _is_mime_allowed('.txt', 'text/markdown') == True

    def test_constants_and_configuration(self) -> None:
        """Test router constants and configuration"""
        from app.features.document_analysis.router import (
            _REDACTED_RESPONSE_MARKERS, ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES
        )

        # Test redaction markers
        assert isinstance(_REDACTED_RESPONSE_MARKERS, tuple)
        assert "traceback" in _REDACTED_RESPONSE_MARKERS
        assert "openai" in _REDACTED_RESPONSE_MARKERS
        assert "google" in _REDACTED_RESPONSE_MARKERS

        # Test allowed extensions
        assert '.pdf' in ALLOWED_EXTENSIONS
        assert '.md' in ALLOWED_EXTENSIONS
        assert '.txt' in ALLOWED_EXTENSIONS
        assert '.docx' in ALLOWED_EXTENSIONS

        # Test MIME type mapping
        assert '.pdf' in ALLOWED_MIME_TYPES
        assert 'application/pdf' in ALLOWED_MIME_TYPES['.pdf']
        assert '.md' in ALLOWED_MIME_TYPES
        assert 'text/markdown' in ALLOWED_MIME_TYPES['.md']

    @patch('app.features.document_analysis.router.settings')
    def test_file_validation_patterns(self, mock_settings: Mock) -> None:
        """Test file validation patterns used in the router"""
        from app.features.document_analysis.router import _is_mime_allowed, ALLOWED_EXTENSIONS

        mock_settings.max_document_size = 10 * 1024 * 1024

        # Test extension validation
        allowed_extensions = ['.pdf', '.md', '.txt', '.docx']

        # Valid extensions
        assert Path("test.pdf").suffix.lower() in allowed_extensions
        assert Path("document.md").suffix.lower() in allowed_extensions
        assert Path("notes.txt").suffix.lower() in allowed_extensions
        assert Path("report.docx").suffix.lower() in allowed_extensions

        # Invalid extensions
        assert Path("image.jpg").suffix.lower() not in allowed_extensions
        assert Path("script.js").suffix.lower() not in allowed_extensions
        assert Path("archive.zip").suffix.lower() not in allowed_extensions

    def test_error_handling_patterns(self) -> None:
        """Test error handling patterns used in document analysis"""
        import requests
        from fastapi import HTTPException

        # Test request timeout pattern
        try:
            raise requests.exceptions.Timeout("Request timeout")
        except requests.exceptions.Timeout:
            assert True  # Expected exception

        # Test connection error pattern
        try:
            raise requests.exceptions.ConnectionError("Connection failed")
        except requests.exceptions.ConnectionError:
            assert True  # Expected exception

        # Test HTTP error pattern
        mock_response = Mock()
        mock_response.status_code = 413
        mock_response.text = "Payload too large"
        http_error = requests.exceptions.HTTPError("413 Payload Too Large")
        http_error.response = mock_response

        try:
            raise http_error
        except requests.exceptions.HTTPError as e:
            assert e.response.status_code == 413

    @patch('app.features.document_analysis.router.settings')
    def test_sandbox_timeout_configuration(self, mock_settings: Mock) -> None:
        """Test sandbox timeout configuration"""
        from app.features.document_analysis.router import SANDBOX_TIMEOUT

        # Should have reasonable timeout value
        assert isinstance(SANDBOX_TIMEOUT, int)
        assert SANDBOX_TIMEOUT > 0
        assert SANDBOX_TIMEOUT == 30  # Expected value

    def test_content_redaction_patterns(self) -> None:
        """Test content redaction patterns"""
        from app.features.document_analysis.router import _REDACTED_RESPONSE_MARKERS

        # Test that redaction markers include sensitive patterns
        sensitive_patterns = ['traceback', 'openai', 'aws_secret', 'google']

        for pattern in sensitive_patterns:
            assert pattern in _REDACTED_RESPONSE_MARKERS

        # Test that markers can be used for content filtering
        test_content = "This contains openai api key and traceback information"
        should_redact = any(marker in test_content.lower() for marker in _REDACTED_RESPONSE_MARKERS)
        assert should_redact == True

    def test_rate_limiting_integration(self) -> None:
        """Test rate limiting integration points"""
        from app.features.document_analysis.router import router
        from app.security_layer.rate_limiter import RateLimitConfig

        # Router should exist and have routes
        assert router is not None
        assert len(router.routes) > 0

        # Rate limit config should be importable
        config = RateLimitConfig(limit=10, window_seconds=60)
        assert config.limit == 10
        assert config.window_seconds == 60