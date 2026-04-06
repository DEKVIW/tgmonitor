from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.api import admin_backups
from app.schemas.backup_models import BackupTargetCreate


def _target_response_payload() -> dict:
    return {
        "id": 1,
        "name": "Local backup",
        "target_kind": "local",
        "provider": "local",
        "is_enabled": True,
        "backup_mode": "full",
        "schedule_enabled": False,
        "schedule_kind": "manual",
        "schedule_hour": 3,
        "schedule_minute": 0,
        "schedule_weekday": None,
        "schedule_day": None,
        "timezone": "Asia/Shanghai",
        "retention_count": 10,
        "retention_days": 30,
        "local_dir": "data/backups",
        "webdav_base_url": "",
        "webdav_username": "",
        "webdav_root_path": "",
        "webdav_timeout_seconds": 60,
        "webdav_verify_ssl": True,
        "webdav_password_configured": False,
        "include_database": True,
        "include_users_json": True,
        "include_env_file": False,
        "include_runtime_data": True,
        "export_range_kind": "all",
        "export_range_days": None,
        "last_run_at": None,
        "next_run_at": None,
        "last_status": None,
        "last_error_message": None,
        "has_active_run": False,
        "active_run_id": None,
        "active_run_status": None,
        "extra_json": {},
        "created_at": "2026-04-06T10:00:00",
        "updated_at": "2026-04-06T10:00:00",
        "updated_by": "tester",
    }


def _run_response_payload() -> dict:
    return {
        "id": 9,
        "target_id": 1,
        "target_name": "Local backup",
        "target_kind": "local",
        "provider": "local",
        "backup_mode": "full",
        "trigger_source": "manual",
        "status": "pending",
        "file_name": None,
        "file_format": None,
        "file_size_bytes": None,
        "sha256": None,
        "local_path": None,
        "remote_path": None,
        "remote_url": None,
        "item_count": None,
        "started_at": "2026-04-06T10:00:00",
        "finished_at": None,
        "duration_seconds": None,
        "created_by": "tester",
        "error_message": None,
        "result_json": {},
        "created_at": "2026-04-06T10:00:00",
        "reused_existing": False,
    }


class AdminBackupsApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_create_backup_target_passes_updated_by(self) -> None:
        payload = BackupTargetCreate(
            name="Local backup",
            target_kind="local",
            backup_mode="full",
            local_dir="data/backups",
        )
        expected = payload.model_dump()

        with patch("app.api.admin_backups.create_backup_target", return_value=_target_response_payload()) as mocked_create:
            result = await admin_backups.create_backup_target_api(
                payload,
                current_user={"role": "admin", "username": "tester"},
            )

        mocked_create.assert_called_once_with(expected, updated_by="tester")
        self.assertEqual(result.name, "Local backup")
        self.assertEqual(result.target_kind, "local")

    async def test_run_backup_target_wraps_response(self) -> None:
        with patch("app.api.admin_backups.start_backup_run", return_value=_run_response_payload()) as mocked_start:
            result = await admin_backups.run_backup_target_api(
                1,
                current_user={"role": "admin", "username": "tester"},
            )

        mocked_start.assert_called_once_with(1, trigger_source="manual", created_by="tester")
        self.assertEqual(result.target_name, "Local backup")
        self.assertEqual(result.status, "pending")


if __name__ == "__main__":
    unittest.main()

