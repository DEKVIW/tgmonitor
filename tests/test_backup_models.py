from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.backup_models import BackupTargetCreate


class BackupModelsTestCase(unittest.TestCase):
    def test_local_backup_target_defaults_are_valid(self) -> None:
        model = BackupTargetCreate(
            name="Local backup",
            target_kind="local",
            backup_mode="full",
            local_dir="data/backups",
        )

        self.assertEqual(model.target_kind, "local")
        self.assertEqual(model.provider, "local")
        self.assertEqual(model.local_dir, "data/backups")

    def test_webdav_target_requires_base_url(self) -> None:
        with self.assertRaises(ValidationError):
            BackupTargetCreate(
                name="Remote backup",
                target_kind="webdav",
                backup_mode="full",
                webdav_base_url="",
            )

    def test_weekly_schedule_requires_weekday(self) -> None:
        with self.assertRaises(ValidationError):
            BackupTargetCreate(
                name="Scheduled backup",
                target_kind="local",
                backup_mode="full",
                local_dir="data/backups",
                schedule_enabled=True,
                schedule_kind="weekly",
                schedule_weekday=None,
            )

    def test_export_days_requires_day_count(self) -> None:
        with self.assertRaises(ValidationError):
            BackupTargetCreate(
                name="Export backup",
                target_kind="local",
                backup_mode="media_export",
                local_dir="data/backups",
                export_range_kind="days",
                export_range_days=None,
            )

    def test_full_backup_requires_at_least_one_source(self) -> None:
        with self.assertRaises(ValidationError):
            BackupTargetCreate(
                name="Invalid full backup",
                target_kind="local",
                backup_mode="full",
                local_dir="data/backups",
                include_database=False,
                include_users_json=False,
                include_env_file=False,
                include_runtime_data=False,
            )


if __name__ == "__main__":
    unittest.main()

