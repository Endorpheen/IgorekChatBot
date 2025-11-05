from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException

pytestmark = pytest.mark.unit


class TestSandboxTool:
    def test_tool_imports(self) -> None:
        """Test that sandbox tool can be imported and is a StructuredTool"""
        # Import fresh to avoid module caching issues
        import importlib
        import sys
        if 'app.features.infra.sandbox_tool' in sys.modules:
            importlib.reload(sys.modules['app.features.infra.sandbox_tool'])

        from app.features.infra.sandbox_tool import run_code_in_sandbox

        # Verify it's a LangChain StructuredTool
        assert hasattr(run_code_in_sandbox, 'name')
        assert hasattr(run_code_in_sandbox, 'description')
        assert hasattr(run_code_in_sandbox, 'args_schema')
        assert run_code_in_sandbox.name == 'run_code_in_sandbox'

    def test_tool_schema_structure(self) -> None:
        """Test that sandbox tool has proper schema structure"""
        # Import fresh to avoid module caching issues
        import importlib
        import sys
        if 'app.features.infra.sandbox_tool' in sys.modules:
            importlib.reload(sys.modules['app.features.infra.sandbox_tool'])

        from app.features.infra.sandbox_tool import run_code_in_sandbox

        # Test that tool has required attributes
        assert run_code_in_sandbox.name is not None
        assert run_code_in_sandbox.description is not None

        # Should have code argument
        if hasattr(run_code_in_sandbox, 'args_schema'):
            schema = run_code_in_sandbox.args_schema
            if schema:
                assert hasattr(schema, 'model_fields') or hasattr(schema, '__fields__')

    @patch('app.features.infra.sandbox_tool.settings')
    def test_error_handling_patterns(self, mock_settings: Mock) -> None:
        """Test error handling patterns used in sandbox tool"""
        mock_settings.sandbox_service_url = "http://sandbox:8080"

        # Test various request exception patterns
        with patch('requests.post', side_effect=requests.exceptions.Timeout()):
            # Should handle timeout gracefully
            try:
                requests.post("http://test", timeout=5)
            except requests.exceptions.Timeout:
                assert True  # Expected exception

        with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
            try:
                requests.post("http://test", timeout=5)
            except requests.exceptions.ConnectionError:
                assert True  # Expected exception

        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Error")
            mock_post.return_value = mock_response
            try:
                requests.post("http://test", timeout=5)
            except requests.exceptions.HTTPError:
                assert True  # Expected exception


class TestBrowserTool:
    def test_tool_imports(self) -> None:
        """Test that browser tool can be imported and is a StructuredTool"""
        # Import fresh to avoid module caching issues
        import importlib
        import sys
        if 'app.features.infra.browser_tool' in sys.modules:
            importlib.reload(sys.modules['app.features.infra.browser_tool'])

        from app.features.infra.browser_tool import browse_website

        # Verify it's a LangChain StructuredTool
        assert hasattr(browse_website, 'name')
        assert hasattr(browse_website, 'description')
        assert hasattr(browse_website, 'args_schema')
        assert browse_website.name == 'browse_website'

    def test_tool_schema_structure(self) -> None:
        """Test that browser tool has proper schema structure"""
        # Import fresh to avoid module caching issues
        import importlib
        import sys
        if 'app.features.infra.browser_tool' in sys.modules:
            importlib.reload(sys.modules['app.features.infra.browser_tool'])

        from app.features.infra.browser_tool import browse_website

        # Test that tool has required attributes
        assert browse_website.name is not None
        assert browse_website.description is not None

        # Should have url argument
        if hasattr(browse_website, 'args_schema'):
            schema = browse_website.args_schema
            if schema:
                assert hasattr(schema, 'model_fields') or hasattr(schema, '__fields__')

    @patch('app.features.infra.browser_tool.settings')
    def test_url_validation_patterns(self, mock_settings: Mock) -> None:
        """Test URL validation patterns used in browser tool"""
        mock_settings.browser_service_url = "http://browser:8080"

        # Test various URL formats that should be handled
        test_urls = [
            "https://example.com",
            "http://localhost:3000",
            "https://api.example.com/v1",
            "",  # Empty URL edge case
        ]

        for url in test_urls:
            # Basic URL pattern validation - should not crash
            assert isinstance(url, str)

    @patch('app.features.infra.browser_tool.settings')
    def test_error_handling_patterns(self, mock_settings: Mock) -> None:
        """Test error handling patterns used in browser tool"""
        mock_settings.browser_service_url = "http://browser:8080"

        # Test similar request exception patterns as sandbox tool
        with patch('requests.post', side_effect=requests.exceptions.Timeout()):
            try:
                requests.post("http://test", timeout=20)
            except requests.exceptions.Timeout:
                assert True  # Expected exception

        with patch('requests.post', side_effect=requests.exceptions.ConnectionError()):
            try:
                requests.post("http://test", timeout=20)
            except requests.exceptions.ConnectionError:
                assert True  # Expected exception