from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.api import admin, admin_extras_runtime as admin_extras
from app.models.config import settings
from app.schemas.admin_models import LinkCleanupApplyRequest, SystemConfigUpdate


class _FakeQuery:
    def __init__(self, result) -> None:
        self.result = result

    def filter(self, *args, **kwargs):
        del args, kwargs
        return self

    def first(self):
        return self.result


class _FakeDb:
    def __init__(self, channel) -> None:
        self.channel = channel

    def query(self, model):
        del model
        return _FakeQuery(self.channel)


class AdminApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_link_check_result_invalid_time_returns_400(self) -> None:
        with patch("app.api.admin.get_task_result", side_effect=ValueError("Invalid isoformat string")):
            with self.assertRaises(HTTPException) as context:
                await admin.get_link_check_result("bad-time", current_user={"role": "admin"})

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("检测时间格式无效", context.exception.detail)

    async def test_update_system_config_rolls_back_runtime_value_when_env_write_fails(self) -> None:
        original_value = settings.PUBLIC_DASHBOARD_ENABLED
        settings.PUBLIC_DASHBOARD_ENABLED = False
        try:
            with patch("app.api.admin.upsert_env_value", side_effect=OSError("disk full")):
                with self.assertRaises(HTTPException) as context:
                    await admin.update_system_config(
                        SystemConfigUpdate(public_dashboard_enabled=True),
                        current_user={"role": "admin"},
                    )

            self.assertEqual(context.exception.status_code, 500)
            self.assertFalse(settings.PUBLIC_DASHBOARD_ENABLED)
        finally:
            settings.PUBLIC_DASHBOARD_ENABLED = original_value

    async def test_apply_link_check_cleanup_not_found_returns_404(self) -> None:
        with patch("app.api.admin.apply_link_check_cleanup", side_effect=LookupError("链接检测记录不存在")):
            with self.assertRaises(HTTPException) as context:
                await admin.apply_link_check_cleanup_api(
                    "2026-04-04T10:00:00",
                    LinkCleanupApplyRequest(mode="remove_invalid_links"),
                    db=object(),
                    current_user={"role": "admin"},
                )

        self.assertEqual(context.exception.status_code, 404)
        self.assertIn("链接检测记录不存在", context.exception.detail)

    async def test_get_channel_samples_api_returns_404_when_channel_missing(self) -> None:
        with self.assertRaises(HTTPException) as context:
            await admin_extras.get_channel_samples_api(
                123,
                db=_FakeDb(channel=None),
                current_user={"role": "admin"},
            )

        self.assertEqual(context.exception.status_code, 404)
        self.assertIn("频道 123 不存在", context.exception.detail)

    async def test_get_link_check_date_range_api_returns_service_payload(self) -> None:
        with patch(
            "app.api.admin_extras_runtime.get_link_check_date_range",
            return_value={
                "min_date": "2026-04-01",
                "max_date": "2026-04-04",
                "latest_message_date": "2026-04-03",
            },
        ):
            result = await admin_extras.get_link_check_date_range_api(current_user={"role": "admin"})

        self.assertEqual(result.min_date, "2026-04-01")
        self.assertEqual(result.max_date, "2026-04-04")
        self.assertEqual(result.latest_message_date, "2026-04-03")

    async def test_get_active_link_check_task_api_returns_404_when_none(self) -> None:
        with patch("app.api.admin_extras_runtime.get_active_task_snapshot", return_value=None):
            with self.assertRaises(HTTPException) as context:
                await admin_extras.get_active_link_check_task_api(current_user={"role": "admin"})

        self.assertEqual(context.exception.status_code, 404)

    async def test_stop_link_check_task_api_wraps_status_payload(self) -> None:
        with patch(
            "app.api.admin_extras_runtime.request_task_stop",
            return_value={"status": "stopping", "progress": 42, "logs": [], "stop_requested": True},
        ):
            result = await admin_extras.stop_link_check_task_api("task-1", current_user={"role": "admin"})

        self.assertEqual(result.task_id, "task-1")
        self.assertEqual(result.status, "stopping")
        self.assertTrue(result.stop_requested)

    async def test_get_channel_samples_api_wraps_runtime_error(self) -> None:
        channel = SimpleNamespace(id=9, username="demo_channel")
        with patch("app.api.admin_extras_runtime.fetch_channel_message_samples", side_effect=RuntimeError("session missing")):
            with self.assertRaises(HTTPException) as context:
                await admin_extras.get_channel_samples_api(
                    9,
                    limit=None,
                    page=1,
                    page_size=10,
                    db=_FakeDb(channel=channel),
                    current_user={"role": "admin"},
                )

        self.assertEqual(context.exception.status_code, 503)
        self.assertIn("session missing", context.exception.detail)

    async def test_delete_link_check_history_api_returns_404_when_missing(self) -> None:
        with patch("app.api.admin_extras_runtime.delete_task_history_entry", side_effect=LookupError("链接检测记录不存在")):
            with self.assertRaises(HTTPException) as context:
                await admin_extras.delete_link_check_history_api(
                    "2026-04-04T10:00:00",
                    current_user={"role": "admin"},
                )

        self.assertEqual(context.exception.status_code, 404)

    async def test_delete_link_check_histories_api_wraps_batch_delete_result(self) -> None:
        with patch(
            "app.api.admin_extras_runtime.delete_task_history_entries",
            return_value={
                "success": True,
                "requested_count": 2,
                "deleted_runs": 2,
                "deleted_details": 10,
                "deleted_stats": 2,
                "missing_check_times": [],
            },
        ):
            result = await admin_extras.delete_link_check_histories_api(
                SimpleNamespace(check_times=["2026-04-04T10:00:00", "2026-04-04T11:00:00"]),
                current_user={"role": "admin"},
            )

        self.assertTrue(result.success)
        self.assertEqual(result.deleted_runs, 2)
        self.assertEqual(result.deleted_details, 10)


if __name__ == "__main__":
    unittest.main()
