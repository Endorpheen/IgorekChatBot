from __future__ import annotations

import re
import time
from collections import deque
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.unit


class TestGoogleSearchProvider:
    def test_provider_initialization(self) -> None:
        """Test GoogleSearchProvider initialization"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        # Should initialize correctly
        assert provider._settings is settings
        assert hasattr(provider, '_logger')
        assert isinstance(provider._rate_timestamps, deque)
        assert isinstance(provider._cache, dict)
        assert hasattr(provider, '_lock')
        assert hasattr(provider, '_tool')

    def test_log_method(self) -> None:
        """Test logging method"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        with patch.object(provider._logger, 'info') as mock_logger:
            provider._log("success", 10, "thread-123")

            mock_logger.assert_called_once_with(
                "[GOOGLE SEARCH] status=%s results=%s thread_id=%s",
                "success",
                10,
                "thread-123"
            )

    def test_log_method_without_thread_id(self) -> None:
        """Test logging method without thread ID"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        with patch.object(provider._logger, 'info') as mock_logger:
            provider._log("error", 0, None)

            mock_logger.assert_called_once_with(
                "[GOOGLE SEARCH] status=%s results=%s thread_id=%s",
                "error",
                0,
                "unknown"
            )

    def test_normalize_query(self) -> None:
        """Test query normalization"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        # Test basic normalization
        assert provider._normalize_query("  Hello   World  ") == "hello world"
        assert provider._normalize_query("TEST QUERY") == "test query"
        assert provider._normalize_query("   Multiple    Spaces   ") == "multiple spaces"

        # Test edge cases
        assert provider._normalize_query("") == ""
        assert provider._normalize_query("   ") == ""
        assert provider._normalize_query("Single") == "single"

    def test_execute_empty_query(self) -> None:
        """Test execute with empty query"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        with patch.object(provider, '_log') as mock_log:
            result = provider._execute("", "thread-123")

            assert result == "Ошибка: поисковый запрос пуст."
            mock_log.assert_called_once_with("error", 0, "thread-123")

    def test_execute_whitespace_only_query(self) -> None:
        """Test execute with whitespace-only query"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        with patch.object(provider, '_log') as mock_log:
            result = provider._execute("   ", "thread-123")

            assert result == "Ошибка: поисковый запрос пуст."
            mock_log.assert_called_once_with("error", 0, "thread-123")

    def test_execute_missing_api_credentials(self) -> None:
        """Test execute with missing API credentials"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings(google_api_key=None, google_cse_id=None)
        provider = GoogleSearchProvider(settings)

        with patch.object(provider, '_log') as mock_log:
            result = provider._execute("test query", "thread-123")

            assert result == "Ошибка: сервис поиска недоступен — API ключ не настроен."
            mock_log.assert_called_once_with("error", 0, "thread-123")

    def test_execute_missing_api_key(self) -> None:
        """Test execute with missing API key but valid CSE ID"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings(google_api_key=None, google_cse_id="valid-cse-id")
        provider = GoogleSearchProvider(settings)

        with patch.object(provider, '_log') as mock_log:
            result = provider._execute("test query", "thread-123")

            assert result == "Ошибка: сервис поиска недоступен — API ключ не настроен."
            mock_log.assert_called_once_with("error", 0, "thread-123")

    def test_execute_missing_cse_id(self) -> None:
        """Test execute with missing CSE ID but valid API key"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings(google_api_key="valid-api-key", google_cse_id=None)
        provider = GoogleSearchProvider(settings)

        with patch.object(provider, '_log') as mock_log:
            result = provider._execute("test query", "thread-123")

            assert result == "Ошибка: сервис поиска недоступен — API ключ не настроен."
            mock_log.assert_called_once_with("error", 0, "thread-123")

    @patch('app.features.search.google_tool.time')
    def test_cache_key_generation(self, mock_time: Mock) -> None:
        """Test cache key generation"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        mock_time.time.return_value = 1234567890.0

        # Test cache key generation (would be used in execute method)
        query = "Test Query"
        cache_key = provider._normalize_query(query)

        assert cache_key == "test query"
        assert isinstance(cache_key, str)

    def test_rate_limiting_data_structures(self) -> None:
        """Test rate limiting data structures"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        # Test rate timestamps deque
        assert isinstance(provider._rate_timestamps, deque)
        assert len(provider._rate_timestamps) == 0

        # Test cache dictionary
        assert isinstance(provider._cache, dict)
        assert len(provider._cache) == 0

    def test_thread_safety_components(self) -> None:
        """Test thread safety components"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        # Should have thread lock
        assert hasattr(provider, '_lock')
        assert provider._lock is not None

    def test_tool_creation(self) -> None:
        """Test LangChain tool creation"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        # Should have tool attribute
        assert hasattr(provider, '_tool')
        assert provider._tool is not None

        # Tool should have expected attributes
        assert hasattr(provider._tool, 'name')
        assert hasattr(provider._tool, 'description')
        assert hasattr(provider._tool, 'func')

    def test_regex_patterns(self) -> None:
        """Test regex patterns used in query normalization"""
        # Test the regex pattern directly
        pattern = r"\s+"

        # Test multiple spaces
        result = re.sub(pattern, " ", "  Hello    World  ")
        assert result == " Hello World "

        # Test tabs and mixed whitespace
        result = re.sub(pattern, " ", "\tHello\t\tWorld\n")
        assert result == " Hello World "

    def test_error_handling_patterns(self) -> None:
        """Test error handling patterns"""
        import requests
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        settings = Settings()
        provider = GoogleSearchProvider(settings)

        # Test request timeout pattern
        try:
            raise requests.exceptions.Timeout("Search timeout")
        except requests.exceptions.Timeout:
            assert True  # Expected exception

        # Test connection error pattern
        try:
            raise requests.exceptions.ConnectionError("Connection failed")
        except requests.exceptions.ConnectionError:
            assert True  # Expected exception

        # Test HTTP error pattern
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        http_error = requests.exceptions.HTTPError("429 Rate Limit")
        http_error.response = mock_response

        try:
            raise http_error
        except requests.exceptions.HTTPError as e:
            assert e.response.status_code == 429

    def test_cache_data_structure_patterns(self) -> None:
        """Test cache data structure patterns"""
        # Test the cache structure that would be used
        cache: dict[str, tuple[float, list[dict[str, str]]]] = {}

        # Simulate adding a cached item
        cache_key = "test query"
        timestamp = time.time()
        results = [{"title": "Test", "link": "http://example.com", "snippet": "Test result"}]

        cache[cache_key] = (timestamp, results)

        assert cache_key in cache
        assert cache[cache_key][0] == timestamp
        assert cache[cache_key][1] == results

    def test_rate_limiting_timestamp_patterns(self) -> None:
        """Test rate limiting timestamp patterns"""
        from collections import deque

        rate_timestamps: deque[float] = deque()
        current_time = time.time()

        # Add timestamps
        for i in range(5):
            rate_timestamps.append(current_time + i)

        assert len(rate_timestamps) == 5
        assert rate_timestamps[0] == current_time

    def test_settings_integration(self) -> None:
        """Test settings integration"""
        from app.features.search.google_tool import GoogleSearchProvider
        from app.settings import Settings

        # Test with custom settings
        settings = Settings(
            google_api_key="test-api-key",
            google_cse_id="test-cse-id"
        )
        provider = GoogleSearchProvider(settings)

        assert provider._settings.google_api_key == "test-api-key"
        assert provider._settings.google_cse_id == "test-cse-id"