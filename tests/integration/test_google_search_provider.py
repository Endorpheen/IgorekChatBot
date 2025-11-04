from __future__ import annotations

import json
import time
from unittest.mock import Mock, patch

import pytest
import requests

from app.features.search.google_tool import GoogleSearchProvider
from app.settings import Settings


pytestmark = pytest.mark.integration


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        google_api_key="test-api-key",
        google_cse_id="test-cse-id",
        google_search_endpoint="https://www.googleapis.com/customsearch/v1",
        google_search_rate_limit=5,
        google_search_rate_window=60,
        google_search_cache_ttl=300,
        google_search_max_results=5,
    )


@pytest.fixture
def search_provider(test_settings: Settings) -> GoogleSearchProvider:
    return GoogleSearchProvider(test_settings)


class TestGoogleSearchProviderHappyPath:
    def test_successful_search_returns_results(self, search_provider: GoogleSearchProvider) -> None:
        mock_response_data = {
            "items": [
                {
                    "title": "Test Result 1",
                    "link": "https://example.com/1",
                    "snippet": "This is a test result"
                },
                {
                    "title": "Test Result 2",
                    "link": "https://example.com/2",
                    "snippet": "Another test result"
                }
            ]
        }

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_get.return_value = mock_response

            result = search_provider._execute("test query")

            result_data = json.loads(result)
            assert result_data["query"] == "test query"
            assert result_data["cached"] is False
            assert len(result_data["results"]) == 2
            assert result_data["results"][0]["title"] == "Test Result 1"

    def test_search_caches_results(self, search_provider: GoogleSearchProvider) -> None:
        mock_response_data = {
            "items": [{"title": "Cached Result", "link": "https://example.com", "snippet": "Cached"}]
        }

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_get.return_value = mock_response

            # First call
            result1 = search_provider._execute("test query")
            result1_data = json.loads(result1)
            assert result1_data["cached"] is False

            # Second call should use cache
            result2 = search_provider._execute("test query")
            result2_data = json.loads(result2)
            assert result2_data["cached"] is True

            # Should only make one API call
            mock_get.assert_called_once()

    def test_search_handles_empty_results(self, search_provider: GoogleSearchProvider) -> None:
        mock_response_data = {"items": []}

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_get.return_value = mock_response

            result = search_provider._execute("test query")
            result_data = json.loads(result)

            assert result_data["cached"] is False
            assert result_data["results"] == []
            assert result_data["query"] == "test query"


class TestGoogleSearchProviderErrorHandling:
    def test_empty_query_returns_error(self, search_provider: GoogleSearchProvider) -> None:
        result = search_provider._execute("")
        assert "поисковый запрос пуст" in result

        result = search_provider._execute("   ")
        assert "поисковый запрос пуст" in result

    def test_missing_api_key_returns_error(self, search_provider: GoogleSearchProvider) -> None:
        search_provider._settings.google_api_key = ""
        result = search_provider._execute("test query")
        assert "сервис поиска недоступен" in result

    def test_missing_cse_id_returns_error(self, search_provider: GoogleSearchProvider) -> None:
        search_provider._settings.google_cse_id = ""
        result = search_provider._execute("test query")
        assert "сервис поиска недоступен" in result

    def test_rate_limiting_returns_retry_after(self, search_provider: GoogleSearchProvider) -> None:
        # Fill rate limit
        now = time.time()
        for _ in range(search_provider._settings.google_search_rate_limit):
            search_provider._rate_timestamps.append(now)

        result = search_provider._execute("test query")
        assert "превышен лимит запросов" in result
        assert "Попробуйте через" in result

    def test_network_error_returns_graceful_message(self, search_provider: GoogleSearchProvider) -> None:
        with patch('requests.get', side_effect=requests.exceptions.ConnectionError("Network error")):
            result = search_provider._execute("test query")
            assert "не удалось связаться с сервисом" in result

    def test_http_429_daily_limit_error(self, search_provider: GoogleSearchProvider) -> None:
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 429
            mock_get.return_value = mock_response

            result = search_provider._execute("test query")
            assert "превышен дневной лимит" in result

    def test_http_403_permission_error(self, search_provider: GoogleSearchProvider) -> None:
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 403
            mock_get.return_value = mock_response

            result = search_provider._execute("test query")
            assert "доступ к Google Custom Search запрещен" in result

    def test_malformed_response_data(self, search_provider: GoogleSearchProvider) -> None:
        # Response without items field
        mock_response_data = {"something": "else"}

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_get.return_value = mock_response

            result = search_provider._execute("test query")
            result_data = json.loads(result)

            assert result_data["results"] == []


class TestGoogleSearchProviderConcurrency:
    def test_thread_safety_of_cache(self, search_provider: GoogleSearchProvider) -> None:
        import threading

        mock_response_data = {
            "items": [{"title": "Thread Test", "link": "https://example.com", "snippet": "Test"}]
        }

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_get.return_value = mock_response

            results = []

            def worker():
                result = search_provider._execute("test query")
                results.append(json.loads(result))

            # Create multiple threads
            threads = [threading.Thread(target=worker) for _ in range(3)]

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            assert len(results) == 3
            assert mock_get.call_count == 1

            reference_results = results[0]["results"]
            assert all(result["results"] == reference_results for result in results)
            assert all(result["query"] == "test query" for result in results)

            cached_flags = [result["cached"] for result in results]
            assert cached_flags.count(False) == 1
            assert cached_flags.count(True) == len(results) - 1
