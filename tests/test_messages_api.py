from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.api import messages as messages_api


class MessagesApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_messages_public_guest_rejects_disallowed_time_range(self) -> None:
        with patch("app.api.messages.is_public_dashboard_enabled", return_value=True):
            with self.assertRaises(HTTPException) as context:
                await messages_api.get_messages(
                    time_range="invalid-range",
                    db=object(),
                    current_user=None,
                )

        self.assertEqual(context.exception.status_code, 403)

    async def test_get_messages_public_guest_keeps_read_only_filters_within_limit(self) -> None:
        fake_db = object()
        allowed_time_range = next(iter(messages_api.PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES))
        with (
            patch("app.api.messages.is_public_dashboard_enabled", return_value=True),
            patch("app.api.messages.get_filtered_messages", return_value=([], 0, 1)) as mocked_get_filtered_messages,
        ):
            response = await messages_api.get_messages(
                search_query="perfect world",
                time_range=allowed_time_range,
                selected_tags=["4K"],
                selected_netdisks=["quark"],
                min_content_length=20,
                has_links_only=True,
                page=2,
                page_size=150,
                db=fake_db,
                current_user=None,
            )

        self.assertEqual(response.total, 0)
        self.assertEqual(response.page, 2)
        self.assertEqual(response.page_size, 150)
        mocked_get_filtered_messages.assert_called_once_with(
            db=fake_db,
            search_query="perfect world",
            time_range=allowed_time_range,
            selected_tags=["4K"],
            selected_netdisks=["quark"],
            min_content_length=20,
            has_links_only=True,
            page=2,
            page_size=150,
        )

    async def test_get_message_public_guest_hides_message_older_than_seven_days(self) -> None:
        old_message = SimpleNamespace(id=9, timestamp=datetime.now() - timedelta(days=8))
        with (
            patch("app.api.messages.is_public_dashboard_enabled", return_value=True),
            patch("app.api.messages.get_message_by_id", return_value=old_message),
        ):
            with self.assertRaises(HTTPException) as context:
                await messages_api.get_message(
                    9,
                    db=object(),
                    current_user=None,
                )

        self.assertEqual(context.exception.status_code, 404)

    async def test_get_tags_stats_public_guest_scopes_stats_to_recent_seven_days(self) -> None:
        before_call = datetime.now() - timedelta(days=7, seconds=2)
        with (
            patch("app.api.messages.is_public_dashboard_enabled", return_value=True),
            patch("app.api.messages.get_tag_stats", return_value=[]) as mocked_get_tag_stats,
        ):
            await messages_api.get_tags_stats(
                limit=20,
                db=object(),
                current_user=None,
            )
        after_call = datetime.now() - timedelta(days=7) + timedelta(seconds=2)

        called_since = mocked_get_tag_stats.call_args.kwargs["since"]
        self.assertGreaterEqual(called_since, before_call)
        self.assertLessEqual(called_since, after_call)
        self.assertEqual(mocked_get_tag_stats.call_args.kwargs["limit"], 20)


if __name__ == "__main__":
    unittest.main()
