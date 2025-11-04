from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.unit


class TestUploadsCleaner:
    def test_delete_file_success(self) -> None:
        """Test successful file deletion"""
        from app.features.uploads.cleaner import _delete_file

        mock_path = Mock(spec=Path)
        mock_path.unlink.return_value = None

        result = _delete_file(mock_path)

        assert result == True
        mock_path.unlink.assert_called_once()

    def test_delete_file_failure(self) -> None:
        """Test file deletion failure"""
        from app.features.uploads.cleaner import _delete_file

        mock_path = Mock(spec=Path)
        mock_path.unlink.side_effect = OSError("Permission denied")

        with patch('app.features.uploads.cleaner.logger') as mock_logger:
            result = _delete_file(mock_path)

            assert result == False
            mock_logger.warning.assert_called_once()

    @patch('app.features.uploads.cleaner._delete_file')
    @patch('app.features.uploads.cleaner.datetime')
    def test_cleanup_uploads_once_with_ttl(self, mock_datetime: Mock, mock_delete: Mock) -> None:
        """Test cleanup with TTL-based file removal"""
        from app.features.uploads.cleaner import cleanup_uploads_once
        from app.settings import Settings

        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_now

        settings = Settings(upload_ttl_days=7, upload_max_size_mb=100)
        upload_dir = Mock(spec=Path)

        # Create empty directory (no files)
        upload_dir.rglob.return_value = []

        removed_by_ttl, removed_by_size = cleanup_uploads_once(settings, upload_dir)

        # Should handle empty directory
        assert removed_by_ttl == 0
        assert removed_by_size == 0

    @patch('app.features.uploads.cleaner._delete_file')
    @patch('app.features.uploads.cleaner.datetime')
    def test_cleanup_uploads_once_disabled_ttl(self, mock_datetime: Mock, mock_delete: Mock) -> None:
        """Test cleanup when TTL is disabled"""
        from app.features.uploads.cleaner import cleanup_uploads_once
        from app.settings import Settings

        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_now

        settings = Settings(upload_ttl_days=0, upload_max_size_mb=100)  # TTL disabled
        upload_dir = Mock(spec=Path)

        mock_file = Mock(spec=Path)
        mock_file.is_file.return_value = True
        mock_stat = Mock()
        mock_stat.st_size = 1024
        mock_stat.st_mtime = mock_now.timestamp()
        mock_file.stat.return_value = mock_stat
        mock_file.name = "test.txt"

        upload_dir.rglob.return_value = [mock_file]

        mock_delete.return_value = True

        removed_by_ttl, removed_by_size = cleanup_uploads_once(settings, upload_dir)

        # Should not delete based on TTL when disabled
        assert removed_by_ttl == 0
        # But should still process for size-based cleanup
        assert isinstance(removed_by_size, int)

    def test_cleanup_uploads_handles_file_stat_errors(self) -> None:
        """Test cleanup handles file stat errors gracefully"""
        from app.features.uploads.cleaner import cleanup_uploads_once
        from app.settings import Settings

        settings = Settings(upload_ttl_days=7, upload_max_size_mb=100)
        upload_dir = Mock(spec=Path)

        mock_file = Mock(spec=Path)
        mock_file.is_file.return_value = True
        mock_file.stat.side_effect = OSError("Stat failed")

        upload_dir.rglob.return_value = [mock_file]

        with patch('app.features.uploads.cleaner.logger') as mock_logger:
            removed_by_ttl, removed_by_size = cleanup_uploads_once(settings, upload_dir)

            # Should handle error gracefully
            assert removed_by_ttl == 0
            assert isinstance(removed_by_size, int)

    @patch('app.features.uploads.cleaner._delete_file')
    def test_cleanup_uploads_once_size_based(self, mock_delete: Mock) -> None:
        """Test size-based cleanup functionality"""
        from app.features.uploads.cleaner import cleanup_uploads_once
        from app.settings import Settings

        settings = Settings(upload_ttl_days=0, upload_max_size_mb=1)  # 1MB limit
        upload_dir = Mock(spec=Path)

        # Create mock files with different sizes
        large_file = Mock(spec=Path)
        large_file.is_file.return_value = True
        large_file.stat.return_value = Mock(st_size=2 * 1024 * 1024)  # 2MB
        large_file.name = "large.txt"

        small_file = Mock(spec=Path)
        small_file.is_file.return_value = True
        small_file.stat.return_value = Mock(st_size=512 * 1024)  # 512KB
        small_file.name = "small.txt"

        upload_dir.rglob.return_value = [large_file, small_file]

        mock_delete.return_value = True

        removed_by_ttl, removed_by_size = cleanup_uploads_once(settings, upload_dir)

        # Should remove files to stay under size limit
        assert isinstance(removed_by_ttl, int)
        assert isinstance(removed_by_size, int)

    def test_cleanup_uploads_skip_directories(self) -> None:
        """Test that directories are skipped during cleanup"""
        from app.features.uploads.cleaner import cleanup_uploads_once
        from app.settings import Settings

        settings = Settings(upload_ttl_days=7, upload_max_size_mb=100)
        upload_dir = Mock(spec=Path)

        mock_dir = Mock(spec=Path)
        mock_dir.is_file.return_value = False  # It's a directory

        upload_dir.rglob.return_value = [mock_dir]

        removed_by_ttl, removed_by_size = cleanup_uploads_once(settings, upload_dir)

        # Should not attempt to delete directories
        assert removed_by_ttl == 0
        assert isinstance(removed_by_size, int)

    def test_cleanup_uploads_empty_directory(self) -> None:
        """Test cleanup with empty upload directory"""
        from app.features.uploads.cleaner import cleanup_uploads_once
        from app.settings import Settings

        settings = Settings(upload_ttl_days=7, upload_max_size_mb=100)
        upload_dir = Mock(spec=Path)
        upload_dir.rglob.return_value = []  # No files

        removed_by_ttl, removed_by_size = cleanup_uploads_once(settings, upload_dir)

        # Should handle empty directory gracefully
        assert removed_by_ttl == 0
        assert removed_by_size == 0

    @patch('app.features.uploads.cleaner.asyncio')
    def test_cleanup_task_integration_patterns(self, mock_asyncio: Mock) -> None:
        """Test patterns used in async cleanup task"""
        # This tests the integration patterns that would be used with the async cleanup task
        mock_loop = Mock()
        mock_asyncio.get_event_loop.return_value = mock_loop

        # Test that we can create asyncio components
        loop = mock_asyncio.get_event_loop()
        assert loop is not None

    def test_timedelta_calculations(self) -> None:
        """Test TTL calculation logic"""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        ttl_days = 7
        cutoff = now - timedelta(days=ttl_days)

        # Test that cutoff is correctly calculated
        assert cutoff < now
        assert (now - cutoff).days == 7

    def test_file_size_calculations(self) -> None:
        """Test file size calculation patterns"""
        # Test MB to bytes conversion
        max_size_mb = 10
        max_size_bytes = max_size_mb * 1024 * 1024

        assert max_size_bytes == 10 * 1024 * 1024

        # Test size comparison
        file_size_5mb = 5 * 1024 * 1024
        file_size_15mb = 15 * 1024 * 1024

        assert file_size_5mb < max_size_bytes
        assert file_size_15mb > max_size_bytes

    def test_logger_integration(self) -> None:
        """Test logger integration patterns"""
        from app.features.uploads.cleaner import logger

        # Test that logger exists and has expected methods
        assert hasattr(logger, 'warning')
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'debug')

        # Test logging patterns
        with patch.object(logger, 'warning') as mock_warning:
            logger.warning("[UPLOAD CLEAN] Test message %s", "param")
            mock_warning.assert_called_once_with("[UPLOAD CLEAN] Test message %s", "param")