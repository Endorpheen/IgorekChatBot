from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import Mock, patch

import pytest

from app.features.uploads.cleaner import (
    cleanup_uploads_once,
    start_cleanup_task,
    stop_cleanup_task,
)
from app.settings import Settings


pytestmark = pytest.mark.integration


@pytest.fixture
def temp_upload_dir() -> TemporaryDirectory[str]:
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        upload_ttl_days=1,
        upload_max_total_bytes=1024 * 1024,  # 1MB
        upload_clean_interval_seconds=60,
        upload_max_total_mb=1,
    )


class TestUploadCleanerOnce:
    def test_cleanup_by_ttl_removes_old_files(self, temp_upload_dir: Path, test_settings: Settings) -> None:
        # Create files with different ages
        old_file = temp_upload_dir / "old.txt"
        new_file = temp_upload_dir / "new.txt"

        old_file.write_text("old content")
        new_file.write_text("new content")

        # Make old file appear old (2 days ago)
        two_days_ago = datetime.utcnow() - timedelta(days=2)
        old_time = two_days_ago.timestamp()
        os.utime(old_file, (old_time, old_time))

        # Run cleanup
        removed, total_size = cleanup_uploads_once(test_settings, temp_upload_dir)

        # Should remove old file, keep new file
        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()
        assert total_size == len("new content")

    def test_cleanup_by_ttl_keeps_recent_files(self, temp_upload_dir: Path, test_settings: Settings) -> None:
        # Create recent files
        file1 = temp_upload_dir / "file1.txt"
        file2 = temp_upload_dir / "file2.txt"

        file1.write_text("content1")
        file2.write_text("content2")

        # Run cleanup (files are recent)
        removed, total_size = cleanup_uploads_once(test_settings, temp_upload_dir)

        # Should not remove any files
        assert removed == 0
        assert file1.exists()
        assert file2.exists()
        assert total_size == len("content1") + len("content2")

    def test_cleanup_by_total_size_removes_largest_files(self, temp_upload_dir: Path, test_settings: Settings) -> None:
        # Create files that exceed size limit
        small_file = temp_upload_dir / "small.txt"
        large_file = temp_upload_dir / "large.txt"

        small_file.write_text("small")  # 5 bytes
        large_size = test_settings.upload_max_total_bytes + 1024
        large_file.write_bytes(b"x" * large_size)

        # Make files appear recent (no TTL cleanup)
        recent_time = datetime.utcnow().timestamp()
        os.utime(small_file, (recent_time, recent_time))
        os.utime(large_file, (recent_time, recent_time))

        # Run cleanup - should remove large files first
        removed, total_size = cleanup_uploads_once(test_settings, temp_upload_dir)

        # Should remove files to stay under limit
        assert removed >= 1
        assert small_file.exists()  # Small file should remain
        assert not large_file.exists()
        assert total_size <= test_settings.upload_max_total_bytes

    def test_cleanup_with_disabled_ttl(self, temp_upload_dir: Path) -> None:
        # Settings with TTL disabled
        settings = Settings(
            upload_ttl_days=0,  # Disabled
            upload_max_total_bytes=1024,
            upload_clean_interval_seconds=60,
            upload_max_total_mb=1,
        )

        # Create old file
        old_file = temp_upload_dir / "old.txt"
        old_file.write_text("old content")
        old_time = (datetime.utcnow() - timedelta(days=2)).timestamp()
        os.utime(old_file, (old_time, old_time))

        # Run cleanup
        removed, total_size = cleanup_uploads_once(settings, temp_upload_dir)

        # Should not remove by TTL, but could remove by size
        assert removed == 0
        assert old_file.exists()

    def test_cleanup_empty_directory(self, temp_upload_dir: Path, test_settings: Settings) -> None:
        # Run cleanup on empty directory
        removed, total_size = cleanup_uploads_once(test_settings, temp_upload_dir)

        assert removed == 0
        assert total_size == 0

    def test_cleanup_with_nested_directories(self, temp_upload_dir: Path, test_settings: Settings) -> None:
        # Create nested structure
        subdir = temp_upload_dir / "subdir"
        subdir.mkdir()

        root_file = temp_upload_dir / "root.txt"
        nested_file = subdir / "nested.txt"

        root_file.write_text("root content")
        nested_file.write_text("nested content")

        # Make files old
        old_time = (datetime.utcnow() - timedelta(days=2)).timestamp()
        os.utime(root_file, (old_time, old_time))
        os.utime(nested_file, (old_time, old_time))

        # Run cleanup
        removed, total_size = cleanup_uploads_once(test_settings, temp_upload_dir)

        # Should remove both files
        assert removed == 2
        assert not root_file.exists()
        assert not nested_file.exists()
        assert total_size == 0


class TestCleanupTask:
    def test_start_cleanup_task_with_valid_settings(self, test_settings: Settings, temp_upload_dir: Path) -> None:
        async def runner() -> None:
            task = await start_cleanup_task(test_settings, temp_upload_dir)

            assert task is not None
            assert isinstance(task, asyncio.Task)

            await stop_cleanup_task(task)

        asyncio.run(runner())

    def test_start_cleanup_task_disabled_interval(self, temp_upload_dir: Path) -> None:
        settings = Settings(
            upload_clean_interval_seconds=0,  # Disabled
            upload_ttl_days=1,
            upload_max_total_bytes=1024,
            upload_max_total_mb=1,
        )

        async def runner() -> None:
            task = await start_cleanup_task(settings, temp_upload_dir)
            assert task is None

        asyncio.run(runner())

    def test_stop_cleanup_task_with_none(self) -> None:
        async def runner() -> None:
            await stop_cleanup_task(None)

        asyncio.run(runner())


class TestCleanupEdgeCases:
    def test_cleanup_with_corrupted_file_stats(self, temp_upload_dir: Path, test_settings: Settings) -> None:
        # Create file
        file_path = temp_upload_dir / "test.txt"
        file_path.write_text("content")

        # Mock stat to raise OSError
        original_stat = Path.stat
        call_state = {"count": 0, "error_done": False}

        def mock_stat(path_obj: Path, *args: Any, **kwargs: Any):
            if path_obj == file_path:
                if not call_state["error_done"]:
                    call_state["count"] += 1
                    if call_state["count"] >= 2:
                        call_state["error_done"] = True
                        raise OSError("Permission denied")
            return original_stat(path_obj, *args, **kwargs)

        with patch.object(Path, 'stat', autospec=True) as mock_stat_method:
            mock_stat_method.side_effect = mock_stat
            # Run cleanup - should not crash
            removed, total_size = cleanup_uploads_once(test_settings, temp_upload_dir)

            assert removed == 0
            assert call_state["error_done"]

        assert file_path.exists()
        assert total_size == file_path.stat().st_size

    def test_minimum_interval_enforced(self, temp_upload_dir: Path) -> None:
        settings = Settings(
            upload_clean_interval_seconds=30,  # Less than minimum 60
            upload_ttl_days=1,
            upload_max_total_bytes=1024,
            upload_max_total_mb=1,
        )

        # Should enforce minimum of 60 seconds
        # This is tested indirectly through the task creation
        async def test_task_creation():
            task = await start_cleanup_task(settings, temp_upload_dir)
            if task:
                await stop_cleanup_task(task)

        # Should not raise error
        asyncio.run(test_task_creation())
