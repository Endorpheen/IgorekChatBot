import pytest
from unittest.mock import Mock, patch, mock_open
from app.features.image_analysis.service import build_image_conversation


pytestmark = pytest.mark.unit


@pytest.fixture
def mock_settings() -> Mock:
    settings = Mock()
    settings.lmstudio_image_mode = "auto"
    return settings


class TestLMStudioImageSupport:
    """Test LM Studio base64 image support"""

    def test_lmstudio_auto_detection_port_8010(self, mock_settings: Mock) -> None:
        """Test auto-detection of LM Studio by port 8010"""
        mock_settings.lmstudio_image_mode = "auto"

        result = build_image_conversation(
            history=[],
            thread_id="test-thread",
            history_limit=5,
            system_prompt=None,
            image_data_urls=["data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/8A8A"],
            prompt="Test prompt",
            provider_base_url="http://192.168.0.155:8010/v1",
            lmstudio_mode="auto",
        )

        # Should process data URL format
        user_message = result[-1]
        assert user_message["role"] == "user"
        assert len(user_message["content"]) > 1  # text + image

        # Check if image content is data URL format (already base64)
        image_content = user_message["content"][1]
        assert image_content["type"] == "image_url"
        assert "data:image/" in image_content["image_url"]["url"]
        assert ";base64," in image_content["image_url"]["url"]

    def test_lmstudio_auto_detection_ip_pattern(self, mock_settings: Mock) -> None:
        """Test auto-detection of LM Studio by IP pattern"""
        mock_settings.lmstudio_image_mode = "auto"

        result = build_image_conversation(
            history=[],
            thread_id="test-thread",
            history_limit=5,
            system_prompt=None,
            image_data_urls=["data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/8A8A"],
            prompt="Test prompt",
            provider_base_url="http://192.168.1.100:8010/v1",
            lmstudio_mode="auto",
        )

        # Should process data URL format
        user_message = result[-1]
        image_content = user_message["content"][1]
        assert "data:image/" in image_content["image_url"]["url"]

    def test_lmstudio_force_base64_mode(self, mock_settings: Mock) -> None:
        """Test force base64 mode"""
        mock_settings.lmstudio_image_mode = "base64"

        result = build_image_conversation(
            history=[],
            thread_id="test-thread",
            history_limit=5,
            system_prompt=None,
            image_data_urls=["data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/8A8A"],
            prompt="Test prompt",
            provider_base_url="https://api.openai.com/v1",
            lmstudio_mode="base64",
        )

        # Should process data URL format even for non-LM Studio providers
        user_message = result[-1]
        image_content = user_message["content"][1]
        assert "data:image/" in image_content["image_url"]["url"]

    def test_lmstudio_url_mode_unchanged(self, mock_settings: Mock) -> None:
        """Test that URL mode leaves images unchanged"""
        mock_settings.lmstudio_image_mode = "url"

        original_url = "http://localhost:3010/uploads/test.jpg"
        result = build_image_conversation(
            history=[],
            thread_id="test-thread",
            history_limit=5,
            system_prompt=None,
            image_data_urls=[original_url],
            prompt="Test prompt",
            provider_base_url="http://192.168.0.155:8010/v1",
            lmstudio_mode="url",
        )

        # Should keep original URL format
        user_message = result[-1]
        image_content = user_message["content"][1]
        assert image_content["image_url"]["url"] == original_url

    def test_non_lmstudio_provider_unchanged(self, mock_settings: Mock) -> None:
        """Test that non-LM Studio providers are unchanged in auto mode"""
        mock_settings.lmstudio_image_mode = "auto"

        original_url = "http://localhost:3010/uploads/test.jpg"
        result = build_image_conversation(
            history=[],
            thread_id="test-thread",
            history_limit=5,
            system_prompt=None,
            image_data_urls=[original_url],
            prompt="Test prompt",
            provider_base_url="https://api.openai.com/v1",
            lmstudio_mode="auto",
        )

        # Should keep original URL format for non-LM Studio providers
        user_message = result[-1]
        image_content = user_message["content"][1]
        assert image_content["image_url"]["url"] == original_url

    def test_base64_images_unchanged(self, mock_settings: Mock) -> None:
        """Test that already base64-encoded images are unchanged"""
        mock_settings.lmstudio_image_mode = "auto"

        base64_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD"
        result = build_image_conversation(
            history=[],
            thread_id="test-thread",
            history_limit=5,
            system_prompt=None,
            image_data_urls=[base64_url],
            prompt="Test prompt",
            provider_base_url="http://192.168.0.155:8010/v1",
            lmstudio_mode="auto",
        )

        # Should keep base64 format as-is
        user_message = result[-1]
        image_content = user_message["content"][1]
        assert image_content["image_url"]["url"] == base64_url

    def test_local_file_base64_conversion(self, mock_settings: Mock) -> None:
        """Test conversion of local uploaded files to base64"""
        mock_settings.lmstudio_image_mode = "auto"

        # Create a temporary test image file
        test_image_data = b"fake_image_data_for_testing"

        with patch('pathlib.Path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=test_image_data)), \
             patch('mimetypes.guess_type', return_value=('image/jpeg', None)):

            result = build_image_conversation(
                history=[],
                thread_id="test-thread",
                history_limit=5,
                system_prompt=None,
                image_data_urls=["/uploads/test_image.jpg"],
                prompt="Test prompt",
                provider_base_url="http://192.168.0.155:8010/v1",
                lmstudio_mode="auto",
            )

            # Should convert local file to base64
            user_message = result[-1]
            image_content = user_message["content"][1]
            assert "data:image/jpeg;base64," in image_content["image_url"]["url"]
            assert "ZmFrZV9pbWFnZV9kYXRhX2Zvcl90ZXN0aW5n" in image_content["image_url"]["url"]  # base64 of test data

    @patch('app.features.image_analysis.service.requests.get')
    def test_base64_conversion_error_handling(self, mock_get: Mock, mock_settings: Mock) -> None:
        """Test error handling when base64 conversion fails"""
        mock_settings.lmstudio_image_mode = "auto"

        # Mock failed request
        mock_get.return_value = Mock()
        mock_get.return_value.ok = False
        mock_get.return_value.status_code = 404

        original_url = "http://localhost:3010/uploads/test.jpg"
        result = build_image_conversation(
            history=[],
            thread_id="test-thread",
            history_limit=5,
            system_prompt=None,
            image_data_urls=[original_url],
            prompt="Test prompt",
            provider_base_url="http://192.168.0.155:8010/v1",
            lmstudio_mode="auto",
        )

        # Should fall back to original URL on error
        user_message = result[-1]
        image_content = user_message["content"][1]
        assert image_content["image_url"]["url"] == original_url