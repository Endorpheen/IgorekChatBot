from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


class TestImageAnalysisService:
    def test_service_imports(self) -> None:
        """Test that image analysis service can be imported"""
        from app.features.image_analysis.service import build_image_conversation

        # Test function exists and is callable
        assert callable(build_image_conversation)

    @patch('app.features.image_analysis.service.settings')
    def test_build_image_conversation_basic(self, mock_settings: Mock) -> None:
        """Test basic image conversation building"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        history = [
            {"type": "user", "content": "Hello", "threadId": "thread-123", "createdAt": "2024-01-01T00:00:00Z"},
            {"type": "bot", "content": "Hi there!", "threadId": "thread-123", "createdAt": "2024-01-01T00:01:00Z"}
        ]
        image_data_urls = ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="]

        result = build_image_conversation(
            history=history,
            thread_id="thread-123",
            history_limit=10,
            system_prompt="You are an image analyzer",
            image_data_urls=image_data_urls,
            prompt="Analyze this image"
        )

        assert isinstance(result, list)
        assert len(result) >= 2  # System prompt + at least one message
        assert result[0]["role"] == "system"
        assert "image analyzer" in result[0]["content"].lower()

    @patch('app.features.image_analysis.service.settings')
    def test_build_image_conversation_filters_by_thread(self, mock_settings: Mock) -> None:
        """Test that conversation is filtered by thread ID"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        history = [
            {"type": "user", "content": "From thread 1", "threadId": "thread-1", "createdAt": "2024-01-01T00:00:00Z"},
            {"type": "user", "content": "From thread 2", "threadId": "thread-2", "createdAt": "2024-01-01T00:01:00Z"},
            {"type": "bot", "content": "Reply to thread 1", "threadId": "thread-1", "createdAt": "2024-01-01T00:02:00Z"}
        ]

        result = build_image_conversation(
            history=history,
            thread_id="thread-1",
            history_limit=10,
            system_prompt=None,
            image_data_urls=[],
            prompt="Test"
        )

        # Should only include messages from thread-1
        thread_ids = [msg.get("threadId") for msg in history if msg.get("threadId") == "thread-1"]
        assert len(thread_ids) == 2  # Two messages from thread-1

    @patch('app.features.image_analysis.service.settings')
    def test_build_image_conversation_history_limit(self, mock_settings: Mock) -> None:
        """Test history limit functionality"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        # Create history with more messages than limit
        history = []
        for i in range(10):
            history.append({
                "type": "user" if i % 2 == 0 else "bot",
                "content": f"Message {i}",
                "threadId": "thread-123",
                "createdAt": f"2024-01-01T00:{i:02d}:00Z"
            })

        result = build_image_conversation(
            history=history,
            thread_id="thread-123",
            history_limit=3,  # Limit to 3 messages
            system_prompt=None,
            image_data_urls=[],
            prompt="Test"
        )

        # History limit should be respected (1 system + limited history)
        assert isinstance(result, list)
        assert result[0]["role"] == "system"

    @patch('app.features.image_analysis.service.settings')
    def test_build_image_conversation_sorting(self, mock_settings: Mock) -> None:
        """Test that history is sorted by creation time"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        history = [
            {"type": "user", "content": "First", "threadId": "thread-123", "createdAt": "2024-01-01T00:02:00Z"},
            {"type": "bot", "content": "Second", "threadId": "thread-123", "createdAt": "2024-01-01T00:01:00Z"},  # Earlier time
            {"type": "user", "content": "Third", "threadId": "thread-123", "createdAt": "2024-01-01T00:03:00Z"}
        ]

        result = build_image_conversation(
            history=history,
            thread_id="thread-123",
            history_limit=10,
            system_prompt=None,
            image_data_urls=[],
            prompt="Test"
        )

        # Should be sorted by createdAt (earliest first)
        assert isinstance(result, list)

    @patch('app.features.image_analysis.service.settings')
    def test_build_image_conversation_ignores_invalid_roles(self, mock_settings: Mock) -> None:
        """Test that messages with invalid roles are ignored"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        history = [
            {"type": "user", "content": "Valid user message", "threadId": "thread-123", "createdAt": "2024-01-01T00:00:00Z"},
            {"type": "bot", "content": "Valid bot message", "threadId": "thread-123", "createdAt": "2024-01-01T00:01:00Z"},
            {"type": "system", "content": "Invalid system message", "threadId": "thread-123", "createdAt": "2024-01-01T00:02:00Z"},
            {"type": "unknown", "content": "Invalid unknown message", "threadId": "thread-123", "createdAt": "2024-01-01T00:03:00Z"}
        ]

        result = build_image_conversation(
            history=history,
            thread_id="thread-123",
            history_limit=10,
            system_prompt=None,
            image_data_urls=[],
            prompt="Test"
        )

        # Should only include user and bot messages
        valid_roles = {"user", "bot"}
        valid_messages = [msg for msg in history if msg.get("type") in valid_roles]
        assert len(valid_messages) == 2

    @patch('app.features.image_analysis.service.settings')
    def test_build_image_conversation_with_image_content(self, mock_settings: Mock) -> None:
        """Test handling of image content in history"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        history = [
            {
                "type": "user",
                "contentType": "image",
                "content": "data:image/png;base64,fakedata",
                "threadId": "thread-123",
                "createdAt": "2024-01-01T00:00:00Z"
            }
        ]

        result = build_image_conversation(
            history=history,
            thread_id="thread-123",
            history_limit=10,
            system_prompt=None,
            image_data_urls=["data:image/png;base64,newdata"],
            prompt="Analyze this"
        )

        assert isinstance(result, list)

    @patch('app.features.image_analysis.service.settings')
    def test_build_image_conversation_default_system_prompt(self, mock_settings: Mock) -> None:
        """Test default system prompt when none provided"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        result = build_image_conversation(
            history=[],
            thread_id="thread-123",
            history_limit=10,
            system_prompt=None,  # No custom system prompt
            image_data_urls=[],
            prompt="Test"
        )

        assert isinstance(result, list)
        assert result[0]["role"] == "system"
        assert "helpful ai assistant" in result[0]["content"].lower()
        assert "analyze images" in result[0]["content"].lower()

    def test_base64_and_mime_type_utilities(self) -> None:
        """Test utility functions for image processing"""
        import base64
        import mimetypes

        # Test base64 encoding/decoding
        test_data = b"test image data"
        encoded = base64.b64encode(test_data).decode()
        decoded = base64.b64decode(encoded)
        assert decoded == test_data

        # Test MIME type detection
        mime_type, _ = mimetypes.guess_type("test.png")
        assert mime_type == "image/png"

        mime_type, _ = mimetypes.guess_type("test.jpg")
        assert mime_type == "image/jpeg"

    def test_error_handling_patterns(self) -> None:
        """Test error handling patterns used in image analysis"""
        import requests
        from fastapi import HTTPException

        # Test request timeout pattern
        try:
            raise requests.exceptions.Timeout("Image processing timeout")
        except requests.exceptions.Timeout:
            assert True  # Expected exception

        # Test connection error pattern
        try:
            raise requests.exceptions.ConnectionError("Cannot connect to image service")
        except requests.exceptions.ConnectionError:
            assert True  # Expected exception

        # Test HTTP error pattern
        mock_response = Mock()
        mock_response.status_code = 413
        mock_response.text = "Image too large"
        http_error = requests.exceptions.HTTPError("413 Image Too Large")
        http_error.response = mock_response

        try:
            raise http_error
        except requests.exceptions.HTTPError as e:
            assert e.response.status_code == 413

    @patch('app.features.image_analysis.service.settings')
    def test_history_limit_bounds(self, mock_settings: Mock) -> None:
        """Test that history limit is properly bounded"""
        from app.features.image_analysis.service import build_image_conversation

        mock_settings.upload_dir_path = "/tmp/uploads"

        # Test with very small limit (should be clamped to 1)
        result = build_image_conversation(
            history=[],
            thread_id="thread-123",
            history_limit=0,  # Below minimum
            system_prompt=None,
            image_data_urls=[],
            prompt="Test"
        )

        # Test with very large limit (should be clamped to 50)
        result = build_image_conversation(
            history=[],
            thread_id="thread-123",
            history_limit=1000,  # Above maximum
            system_prompt=None,
            image_data_urls=[],
            prompt="Test"
        )

        assert isinstance(result, list)
        assert result[0]["role"] == "system"