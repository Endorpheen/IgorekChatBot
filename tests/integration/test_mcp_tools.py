from __future__ import annotations

import os
from unittest.mock import Mock, patch

import pytest
import requests

from app.features.mcp.client import ObsidianClient

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_settings() -> None:
    """Mock environment variables for testing"""
    with patch.dict(os.environ, {
        "MCP_VAULT_URL": "http://test-vault-url:3000",
        "MCP_SECRET": "test-secret"
    }):
        yield


class TestObsidianClient:
    def test_client_initialization_with_valid_env(self, mock_settings: None) -> None:
        client = ObsidianClient()
        assert client.base_url == "http://test-vault-url:3000"
        assert client.secret == "test-secret"

    def test_client_initialization_without_url_raises_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="MCP_VAULT_URL environment variable not set"):
                ObsidianClient()

    def test_search_successful_request(self, mock_settings: None) -> None:
        client = ObsidianClient()
        mock_response_data = {"results": [{"title": "Test Note", "content": "Test content"}]}

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = mock_response_data
            mock_post.return_value = mock_response

            payload = {"query": "test query"}
            result = client.search(payload)

            assert result == mock_response_data
            mock_post.assert_called_once()

    def test_request_timeout_error(self, mock_settings: None) -> None:
        client = ObsidianClient()
        with patch('requests.post', side_effect=requests.exceptions.Timeout()):
            with pytest.raises(RuntimeError, match="Request timed out"):
                client.search({"query": "test"})


class TestInfraTools:
    def test_run_code_service_unavailable(self) -> None:
        with patch('app.features.infra.sandbox_tool.settings') as mock_settings:
            mock_settings.sandbox_service_url = "http://sandbox:8080"

            with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
                # Import fresh to ensure we get the StructuredTool version
                import importlib
                import sys
                if 'app.features.infra.sandbox_tool' in sys.modules:
                    importlib.reload(sys.modules['app.features.infra.sandbox_tool'])

                from app.features.infra.sandbox_tool import run_code_in_sandbox
                result = run_code_in_sandbox.invoke('print("test")')

                assert "Ошибка: не удалось связаться с сервисом выполнения кода" in result

    def test_browse_website_service_unavailable(self) -> None:
        with patch('app.features.infra.browser_tool.settings') as mock_settings:
            mock_settings.browser_service_url = "http://browser:8080"

            with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
                # Import fresh to ensure we get the StructuredTool version
                import importlib
                import sys
                if 'app.features.infra.browser_tool' in sys.modules:
                    importlib.reload(sys.modules['app.features.infra.browser_tool'])

                from app.features.infra.browser_tool import browse_website
                result = browse_website.invoke("https://example.com")

                assert "Ошибка: не удалось связаться с сервисом браузера" in result
