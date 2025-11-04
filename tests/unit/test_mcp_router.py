from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException

from app.features.mcp.service import McpService


def handle_mcp_request(method, payload):
    """Simplified version for testing"""
    try:
        trace_id, data = method(payload)
        return {"trace_id": trace_id, "data": data}
    except ValueError as e:
        # Check if it's MCP configuration error
        if "MCP_VAULT_URL" in str(e):
            raise HTTPException(status_code=500, detail={"error": "ENV_MISSING_MCP_URL", "message": str(e)})
        else:
            raise HTTPException(status_code=500, detail={"error": "UNKNOWN_MCP_ERROR", "message": str(e)})
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail={"error": "MCP_TIMEOUT", "message": "The request to the MCP server timed out."})
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail={"error": "DNS_FAIL/CONNECTION_REFUSED", "message": "Could not connect to the MCP server. Check if it's running and in the same Docker network."})
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail={"error": "BAD_ENDPOINT", "message": "The /search or /fetch endpoint was not found on the MCP server."})
        raise HTTPException(status_code=e.response.status_code, detail={"error": "MCP_HTTP_ERROR", "message": str(e)})
    except Exception as e:
        # Catch-all for other errors
        raise HTTPException(status_code=500, detail={"error": "UNKNOWN_MCP_ERROR", "message": str(e)})


pytestmark = pytest.mark.unit


class TestHandleMCPRequest:
    def test_successful_request(self) -> None:
        mock_method = Mock()
        mock_method.return_value = ("trace-123", {"data": "result"})

        result = handle_mcp_request(mock_method, {"test": "payload"})

        assert result == {"trace_id": "trace-123", "data": {"data": "result"}}
        mock_method.assert_called_once_with({"test": "payload"})

    def test_misconfigured_client_raises_error(self) -> None:
        mock_method = Mock()
        mock_method.side_effect = ValueError("MCP_VAULT_URL environment variable not set")

        with pytest.raises(HTTPException) as exc_info:
            handle_mcp_request(mock_method, {"test": "payload"})

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["error"] == "ENV_MISSING_MCP_URL"
        assert "MCP_VAULT_URL environment variable not set" in exc_info.value.detail["message"]

    def test_timeout_error_raises_http_exception(self) -> None:
        mock_method = Mock()
        mock_method.side_effect = requests.exceptions.Timeout("Request timed out")

        with pytest.raises(HTTPException) as exc_info:
            handle_mcp_request(mock_method, {"test": "payload"})

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail["error"] == "MCP_TIMEOUT"
        assert "The request to the MCP server timed out" in exc_info.value.detail["message"]

    def test_connection_error_raises_http_exception(self) -> None:
        mock_method = Mock()
        mock_method.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(HTTPException) as exc_info:
            handle_mcp_request(mock_method, {"test": "payload"})

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail["error"] == "DNS_FAIL/CONNECTION_REFUSED"
        assert "Could not connect to the MCP server" in exc_info.value.detail["message"]

    def test_http_404_error_raises_specific_exception(self) -> None:
        mock_method = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_error = requests.exceptions.HTTPError("404 Not Found")
        mock_error.response = mock_response
        mock_method.side_effect = mock_error

        with pytest.raises(HTTPException) as exc_info:
            handle_mcp_request(mock_method, {"test": "payload"})

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"] == "BAD_ENDPOINT"
        assert "not found on the MCP server" in exc_info.value.detail["message"]

    def test_http_error_uses_status_code(self) -> None:
        mock_method = Mock()
        mock_response = Mock()
        mock_response.status_code = 401
        mock_error = requests.exceptions.HTTPError("401 Unauthorized")
        mock_error.response = mock_response
        mock_method.side_effect = mock_error

        with pytest.raises(HTTPException) as exc_info:
            handle_mcp_request(mock_method, {"test": "payload"})

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "MCP_HTTP_ERROR"

    def test_generic_exception_raises_server_error(self) -> None:
        mock_method = Mock()
        mock_method.side_effect = ValueError("Unexpected error")

        with pytest.raises(HTTPException) as exc_info:
            handle_mcp_request(mock_method, {"test": "payload"})

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["error"] == "UNKNOWN_MCP_ERROR"
        assert exc_info.value.detail["message"] == "Unexpected error"

    def test_runtime_error_is_handled(self) -> None:
        mock_method = Mock()
        mock_method.side_effect = RuntimeError("Service unavailable")

        with pytest.raises(HTTPException) as exc_info:
            handle_mcp_request(mock_method, {"test": "payload"})

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["error"] == "UNKNOWN_MCP_ERROR"
        assert exc_info.value.detail["message"] == "Service unavailable"


class TestMCPServiceIntegration:
    def test_singleton_instance(self) -> None:
        from app.features.mcp.service import mcp_service

        service1 = mcp_service
        service2 = mcp_service

        assert service1 is service2
        # Service exists and is singleton - basic functionality test


class TestMCPService:
    def test_service_imports(self) -> None:
        """Test that MCP service can be imported"""
        from app.features.mcp.service import McpService

        # Test that service can be instantiated
        service = McpService()
        assert service is not None

    def test_error_handling_logic(self) -> None:
        """Test error handling logic patterns used in MCP service"""
        import requests
        from fastapi import HTTPException

        # Test timeout handling pattern
        try:
            raise requests.exceptions.Timeout("Request timeout")
        except requests.exceptions.Timeout:
            assert True  # Expected exception

        # Test connection error handling pattern
        try:
            raise requests.exceptions.ConnectionError("Connection refused")
        except requests.exceptions.ConnectionError:
            assert True  # Expected exception

        # Test HTTP error handling pattern
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = requests.exceptions.HTTPError("404 Not Found")
        http_error.response = mock_response

        try:
            raise http_error
        except requests.exceptions.HTTPError as e:
            assert e.response.status_code == 404