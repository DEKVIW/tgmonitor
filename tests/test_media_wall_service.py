from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "test-hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:password@127.0.0.1:5432/tg_monitor")
os.environ.setdefault("DEFAULT_CHANNELS", "test")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.models.models import AiProviderConfig, MediaWallItem, MediaWallLink, PanTransferSyncTask
from app.services.media_wall import (
    MEDIA_WALL_METADATA_NOT_SYNCED,
    MEDIA_WALL_VISIBILITIES,
    _build_import_preview,
    _fingerprint_url,
    _invalidate_metadata_cache,
    _metadata_cache,
    _normalize_title,
    _public_link_exists_filter,
    _serialize_item,
    _serialize_link_health,
)
from app.services.media_wall_link_health import _next_check_at


class MediaWallServiceTests(unittest.TestCase):
    def test_media_wall_has_no_draft_state_and_ai_provider_tracks_operator(self) -> None:
        self.assertEqual(MEDIA_WALL_VISIBILITIES, {"public", "hidden"})
        self.assertEqual(MediaWallItem.__table__.c.visibility.default.arg, "public")
        self.assertEqual(MediaWallItem.__table__.c.metadata_status.default.arg, MEDIA_WALL_METADATA_NOT_SYNCED)
        self.assertIn("metadata_json", MediaWallItem.__table__.c)
        self.assertIn("metadata_last_synced_at", MediaWallItem.__table__.c)
        self.assertIn("metadata_last_error", MediaWallItem.__table__.c)
        self.assertTrue(hasattr(AiProviderConfig, "updated_by"))

    def test_serializing_public_item_uses_stored_metadata_without_external_fetch(self) -> None:
        class EmptyQuery:
            def join(self, *args, **kwargs):
                return self

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def all(self):
                return []

        class EmptySession:
            def get(self, model, item_id):
                return None

            def query(self, model):
                return EmptyQuery()

        item = SimpleNamespace(
            id=1,
            display_title="黑岛监狱",
            metadata_query_title="黑岛监狱",
            visibility="public",
            sort_order=0,
            custom_poster_url=None,
            metadata_json={"poster_url": "https://img.example/poster.jpg", "year": "2026"},
            metadata_status="ready",
            metadata_last_synced_at=None,
            metadata_last_error=None,
            sync_task_id=None,
            updated_at=None,
            created_at=None,
        )

        with patch("app.services.media_wall._fetch_metadata", side_effect=AssertionError("should not fetch")):
            result = _serialize_item(EmptySession(), item, public=True, include_metadata=True)

        self.assertEqual(result["poster_url"], "https://img.example/poster.jpg")
        self.assertEqual(result["year"], "2026")
        self.assertEqual(result["metadata_status"], "ready")

    def test_metadata_cache_can_be_invalidated_for_a_retry(self) -> None:
        _metadata_cache["黑岛监狱"] = (0.0, {})
        _invalidate_metadata_cache("黑岛监狱")
        self.assertNotIn("黑岛监狱", _metadata_cache)

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

    def test_media_wall_link_health_distinguishes_statuses(self) -> None:
        health = _serialize_link_health([
            {"is_enabled": True, "last_status": "valid"},
            {"is_enabled": False, "last_status": "invalid"},
            {"is_enabled": True, "last_status": "unknown"},
        ])

        self.assertEqual(health["total"], 3)
        self.assertEqual(health["enabled"], 2)
        self.assertEqual(health["valid"], 1)
        self.assertEqual(health["invalid"], 1)
        self.assertEqual(health["pending"], 1)
        self.assertEqual(health["status"], "valid")

    def test_media_wall_link_health_has_recheck_fields_and_intervals(self) -> None:
        self.assertIn("invalid_streak", MediaWallLink.__table__.c)
        self.assertIn("next_check_at", MediaWallLink.__table__.c)
        self.assertIn("last_error_message", MediaWallLink.__table__.c)

        checked_at = datetime(2026, 10, 17, 12, 0, 0)
        self.assertEqual(_next_check_at("invalid", checked_at), checked_at + timedelta(minutes=10))
        self.assertEqual(_next_check_at("valid", checked_at), checked_at + timedelta(days=1))

    def test_public_link_filter_compiles_with_sync_task_join(self) -> None:
        statement = (
            select(MediaWallItem)
            .outerjoin(PanTransferSyncTask, PanTransferSyncTask.id == MediaWallItem.sync_task_id)
            .where(_public_link_exists_filter())
        )
        compiled = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("FROM media_wall_links", compiled)
        self.assertIn("FROM pan_transfer_sync_tasks", compiled)


if __name__ == "__main__":
    unittest.main()
