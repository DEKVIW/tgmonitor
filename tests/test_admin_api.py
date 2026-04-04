from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.api import admin
from app.models.config import settings
from app.schemas.admin_models import SystemConfigUpdate


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


if __name__ == "__main__":
    unittest.main()
