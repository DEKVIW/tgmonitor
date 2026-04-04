from __future__ import annotations

import os
import unittest

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services import link_check_service


class LinkCheckServiceTestCase(unittest.TestCase):
    def test_get_task_status_returns_deep_copy(self) -> None:
        task_id = "copy-status-task"
        link_check_service.init_task_status(task_id, "today", 3)

        status = link_check_service.get_task_status(task_id)
        self.assertIsNotNone(status)

        status["logs"].append("mutated")
        latest_status = link_check_service.get_task_status(task_id)
        self.assertEqual(latest_status["logs"], [])

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


if __name__ == "__main__":
    unittest.main()
