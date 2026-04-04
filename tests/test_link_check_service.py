from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services import link_check_service
from app.services import link_check_runtime


class LinkCheckServiceTestCase(unittest.TestCase):
    def test_get_task_status_returns_deep_copy(self) -> None:
        task_id = "copy-status-task"
        with TemporaryDirectory() as temp_dir:
            with patch.object(link_check_runtime, "TASK_STATUS_DIR", Path(temp_dir)), patch.object(
                link_check_runtime,
                "ACTIVE_TASK_FILE",
                Path(temp_dir) / "_active_task.json",
            ):
                link_check_runtime._task_status.clear()
                link_check_service.init_task_status(task_id, "today", 3)

                status = link_check_service.get_task_status(task_id)
                self.assertIsNotNone(status)
                original_logs = list(status["logs"])

                status["logs"].append("mutated")
                latest_status = link_check_service.get_task_status(task_id)
                self.assertEqual(latest_status["logs"], original_logs)

        link_check_runtime._task_status.clear()

    def test_extract_urls_supports_nested_link_payloads(self) -> None:
        payload = {
            "百度网盘": [{"label": "主链", "url": "https://pan.baidu.com/s/abc"}],
            "夸克网盘": {
                "items": [
                    {"url": "https://pan.quark.cn/s/def"},
                    {"url": "https://pan.quark.cn/s/ghi"},
                ]
            },
        }

        urls = link_check_service.extract_urls(payload)
        self.assertIn("https://pan.baidu.com/s/abc", urls)
        self.assertIn("https://pan.quark.cn/s/def", urls)
        self.assertIn("https://pan.quark.cn/s/ghi", urls)

    def test_get_task_status_can_load_persisted_snapshot(self) -> None:
        task_id = "persisted-status-task"

        with TemporaryDirectory() as temp_dir:
            with patch.object(link_check_runtime, "TASK_STATUS_DIR", Path(temp_dir)), patch.object(
                link_check_runtime,
                "ACTIVE_TASK_FILE",
                Path(temp_dir) / "_active_task.json",
            ):
                link_check_runtime._task_status.clear()
                link_check_service.init_task_status(task_id, "today", 2)
                link_check_runtime._task_status.clear()

                status = link_check_service.get_task_status(task_id)

                self.assertIsNotNone(status)
                self.assertEqual(status["status"], "running")
                self.assertEqual(status["max_concurrent"], 2)

        link_check_runtime._task_status.clear()

    def test_start_or_reuse_task_returns_existing_running_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(link_check_runtime, "TASK_STATUS_DIR", Path(temp_dir)), patch.object(
                link_check_runtime,
                "ACTIVE_TASK_FILE",
                Path(temp_dir) / "_active_task.json",
            ):
                link_check_runtime._task_status.clear()
                first_task_id, _, created = link_check_service.start_or_reuse_task("today", 2)
                second_task_id, second_status, created_again = link_check_service.start_or_reuse_task("week", 5)

                self.assertTrue(created)
                self.assertFalse(created_again)
                self.assertEqual(first_task_id, second_task_id)
                self.assertTrue(second_status.get("reused_existing"))


if __name__ == "__main__":
    unittest.main()
