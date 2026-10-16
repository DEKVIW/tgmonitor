from __future__ import annotations

import os
import unittest

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "test-hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:password@127.0.0.1:5432/tg_monitor")
os.environ.setdefault("DEFAULT_CHANNELS", "test")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services.media_wall import _build_import_preview, _fingerprint_url, _normalize_title


class MediaWallServiceTests(unittest.TestCase):
    def test_import_preview_groups_duplicate_titles_and_links(self) -> None:
        preview = _build_import_preview([
            ["影视名称", "夸克链接", "备用链接"],
            ["黑岛监狱", "https://pan.quark.cn/s/example", "https://pan.baidu.com/s/example"],
            ["黑岛监狱", "https://pan.quark.cn/s/example", "https://pan.quark.cn/s/backup"],
            ["无效条目", "not-a-url"],
        ])

        self.assertEqual(preview["total_records"], 1)
        self.assertEqual(preview["total_links"], 3)
        self.assertEqual(preview["invalid_count"], 1)
        self.assertEqual(preview["records"][0]["display_title"], "黑岛监狱")

    def test_title_and_url_normalization_are_stable(self) -> None:
        self.assertEqual(_normalize_title("  黑岛监狱（2026）  "), "黑岛监狱2026")
        self.assertEqual(
            _fingerprint_url("https://pan.quark.cn/s/example#fragment"),
            _fingerprint_url("https://pan.quark.cn/s/example"),
        )


if __name__ == "__main__":
    unittest.main()
