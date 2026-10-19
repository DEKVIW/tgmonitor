from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from app.models.models import BackupTarget
from app.schemas.backup_models import BackupTargetCreate
from app.services.backup_service import (
    _confirm_webdav_upload,
    _is_target_backup_file,
    _retained_remote_paths,
    _upload_file_to_webdav,
)


class BackupRetentionDefaultTests(unittest.TestCase):
    def test_new_backup_targets_keep_one_backup_by_default(self) -> None:
        target = BackupTargetCreate(name="test", local_dir="/tmp/backups")
        self.assertEqual(target.retention_count, 1)
        self.assertEqual(BackupTarget.retention_count.property.columns[0].default.arg, 1)

    def test_retention_keeps_the_latest_remote_files_and_current_upload(self) -> None:
        remote_files = [
            {"remote_path": "movie-data-target-all-20261019-005018.xlsx", "backup_time": "2026-10-19T00:50:18"},
            {"remote_path": "movie-data-target-all-20261018-005018.xlsx", "backup_time": "2026-10-18T00:50:18"},
            {"remote_path": "movie-data-target-all-20261017-005010.xlsx", "backup_time": "2026-10-17T00:50:10"},
            {"remote_path": "movie-data-target-all-20261016-005026.xlsx", "backup_time": "2026-10-16T00:50:26"},
        ]

        retained = _retained_remote_paths(
            remote_files,
            retention_count=3,
            current_remote_path="movie-data-target-all-20261016-005026.xlsx",
        )

        self.assertEqual(
            retained,
            {
                "movie-data-target-all-20261019-005018.xlsx",
                "movie-data-target-all-20261018-005018.xlsx",
                "movie-data-target-all-20261016-005026.xlsx",
            },
        )

    def test_upload_confirmation_requires_matching_remote_size(self) -> None:
        target = BackupTarget(
            name="target",
            target_kind="webdav",
            backup_mode="media_export",
            webdav_timeout_seconds=60,
        )
        with NamedTemporaryFile() as local_file:
            local_path = Path(local_file.name)
            local_file.write(b"backup")
            local_file.flush()
            with patch(
                "app.services.backup_service._list_webdav_files",
                return_value=[
                    {
                        "remote_path": "movie-data-target-all-20261019-005018.xlsx",
                        "size_bytes": 6,
                    }
                ],
            ), patch("app.services.backup_service.time.sleep"):
                confirmed = _confirm_webdav_upload(
                    target,
                    local_path,
                    "movie-data-target-all-20261019-005018.xlsx",
                )

        self.assertTrue(confirmed)

    def test_retention_only_matches_the_current_target_prefix(self) -> None:
        target = BackupTarget(name="target", backup_mode="media_export")

        self.assertTrue(
            _is_target_backup_file(
                target,
                {"name": "movie-data-target-all-20261019-005018.xlsx"},
            )
        )

    def test_upload_timeout_is_successful_when_remote_file_is_confirmed(self) -> None:
        class TimeoutConnection:
            def request(self, *args, **kwargs) -> None:
                return None

            def getresponse(self):
                raise TimeoutError("The read operation timed out")

            def close(self) -> None:
                return None

        target = BackupTarget(
            name="target",
            target_kind="webdav",
            backup_mode="media_export",
            webdav_base_url="https://example.com/dav",
            webdav_timeout_seconds=60,
        )
        with NamedTemporaryFile() as local_file:
            local_path = Path(local_file.name)
            local_file.write(b"backup")
            local_file.flush()
            with patch("app.services.backup_service._ensure_webdav_directories"), patch(
                "app.services.backup_service._build_webdav_connection",
                return_value=(TimeoutConnection(), "/dav/movie-data-target-all.xlsx"),
            ), patch("app.services.backup_service._confirm_webdav_upload", return_value=True):
                remote_url = _upload_file_to_webdav(
                    target,
                    local_path,
                    "movie-data-target-all.xlsx",
                )

        self.assertEqual(remote_url, "https://example.com/dav/movie-data-target-all.xlsx")
        self.assertFalse(
            _is_target_backup_file(
                target,
                {"name": "movie-data-other-all-20261019-005018.xlsx"},
            )
        )


if __name__ == "__main__":
    unittest.main()
