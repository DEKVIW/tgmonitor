from __future__ import annotations

import os
import unittest
from datetime import datetime
from types import SimpleNamespace

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.models.models import LinkCheckDetails, LinkCheckStats, Message
from app.services.link_cleanup_service import (
    CLEANUP_MODE_DELETE_MESSAGE_IF_EMPTY,
    CLEANUP_MODE_REMOVE_INVALID_LINKS,
    _extract_netdisk_types,
    _normalize_url_key,
    _prune_invalid_links,
    apply_link_check_cleanup,
)


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if isinstance(self.rows, list):
            return self.rows[0] if self.rows else None
        return self.rows

    def all(self):
        if isinstance(self.rows, list):
            return list(self.rows)
        return [self.rows] if self.rows is not None else []


class _FakeSession:
    def __init__(self, stats, details, messages):
        self._queries = {
            LinkCheckStats: _FakeQuery(stats),
            LinkCheckDetails: _FakeQuery(details),
            Message: _FakeQuery(messages),
        }
        self.deleted_messages = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def query(self, model):
        return self._queries[model]

    def delete(self, message):
        self.deleted_messages.append(message)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


class LinkCleanupServiceTestCase(unittest.TestCase):
    def test_prune_invalid_links_removes_only_dead_urls(self) -> None:
        links = {
            "百度网盘": [
                {"label": "主链", "url": "https://pan.baidu.com/s/bad"},
                {"label": "备链", "url": "https://pan.baidu.com/s/good"},
            ],
            "夸克网盘": {
                "items": [
                    {"label": "主链", "url": "https://pan.quark.cn/s/dead"},
                ]
            },
        }

        cleaned, removed_count = _prune_invalid_links(
            links,
            {
                _normalize_url_key("https://pan.baidu.com/s/bad"),
                _normalize_url_key("https://pan.quark.cn/s/dead"),
            },
        )

        self.assertEqual(removed_count, 2)
        self.assertEqual(
            cleaned,
            {
                "百度网盘": [
                    {"label": "备链", "url": "https://pan.baidu.com/s/good"},
                ]
            },
        )
        self.assertEqual(_extract_netdisk_types(cleaned), ["百度网盘"])

    def test_apply_cleanup_updates_message_links(self) -> None:
        check_time = datetime(2026, 4, 4, 10, 0, 0)
        stats = SimpleNamespace(check_time=check_time, updated_messages=0, deleted_messages=0)
        details = [
            SimpleNamespace(
                check_time=check_time,
                message_id=1,
                netdisk_type="百度网盘",
                url="https://pan.baidu.com/s/bad",
                is_valid=False,
                action_taken="invalid",
            ),
            SimpleNamespace(
                check_time=check_time,
                message_id=1,
                netdisk_type="百度网盘",
                url="https://pan.baidu.com/s/uncertain",
                is_valid=False,
                action_taken="uncertain",
            ),
        ]
        message = SimpleNamespace(
            id=1,
            links={
                "百度网盘": [
                    {"label": "主链", "url": "https://pan.baidu.com/s/bad"},
                    {"label": "备链", "url": "https://pan.baidu.com/s/good"},
                ],
                "夸克网盘": [
                    {"label": "主链", "url": "https://pan.quark.cn/s/keep"},
                ],
            },
            netdisk_types=["百度网盘", "夸克网盘"],
        )
        db = _FakeSession(stats, details, [message])

        result = apply_link_check_cleanup(
            db,
            check_time.isoformat(),
            mode=CLEANUP_MODE_REMOVE_INVALID_LINKS,
            dry_run=False,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["updated_messages"], 1)
        self.assertEqual(result["deleted_messages"], 0)
        self.assertEqual(result["removed_links"], 1)
        self.assertEqual(
            message.links,
            {
                "百度网盘": [
                    {"label": "备链", "url": "https://pan.baidu.com/s/good"},
                ],
                "夸克网盘": [
                    {"label": "主链", "url": "https://pan.quark.cn/s/keep"},
                ],
            },
        )
        self.assertEqual(message.netdisk_types, ["百度网盘", "夸克网盘"])
        self.assertEqual(stats.updated_messages, 1)
        self.assertEqual(stats.deleted_messages, 0)
        self.assertEqual(db.commit_calls, 1)

    def test_apply_cleanup_can_delete_message_when_no_links_remain(self) -> None:
        check_time = datetime(2026, 4, 4, 11, 0, 0)
        stats = SimpleNamespace(check_time=check_time, updated_messages=0, deleted_messages=0)
        details = [
            SimpleNamespace(
                check_time=check_time,
                message_id=2,
                netdisk_type="百度网盘",
                url="https://pan.baidu.com/s/bad",
                is_valid=False,
                action_taken="invalid",
            )
        ]
        message = SimpleNamespace(
            id=2,
            links={"百度网盘": [{"label": "主链", "url": "https://pan.baidu.com/s/bad"}]},
            netdisk_types=["百度网盘"],
        )
        db = _FakeSession(stats, details, [message])

        result = apply_link_check_cleanup(
            db,
            check_time.isoformat(),
            mode=CLEANUP_MODE_DELETE_MESSAGE_IF_EMPTY,
            dry_run=False,
        )

        self.assertEqual(result["updated_messages"], 0)
        self.assertEqual(result["deleted_messages"], 1)
        self.assertEqual(result["removed_links"], 1)
        self.assertEqual(db.deleted_messages, [message])
        self.assertEqual(stats.deleted_messages, 1)


if __name__ == "__main__":
    unittest.main()
