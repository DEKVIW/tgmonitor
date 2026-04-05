from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.admin_models import (
    BulkUsernamesRequest,
    ChannelCreate,
    LinkCheckTaskCreate,
    LinkCleanupApplyRequest,
    SystemConfigUpdate,
    UserCreate,
)


class AdminModelsTestCase(unittest.TestCase):
    def test_channel_create_normalizes_telegram_urls(self) -> None:
        model = ChannelCreate(username=" https://t.me/+AbCdEf123456 ")
        self.assertEqual(model.username, "+AbCdEf123456")

        model = ChannelCreate(username="@example_channel")
        self.assertEqual(model.username, "example_channel")

    def test_bulk_usernames_request_trims_and_deduplicates(self) -> None:
        model = BulkUsernamesRequest(usernames=[" alice ", "bob", "alice", "bob "])
        self.assertEqual(model.usernames, ["alice", "bob"])

    def test_channel_create_accepts_supported_parser_profile(self) -> None:
        model = ChannelCreate(username="@movie_channel", parser_profile="movie_default")
        self.assertEqual(model.username, "movie_channel")
        self.assertEqual(model.parser_profile, "movie_default")

    def test_channel_create_treats_auto_parser_profile_as_none(self) -> None:
        model = ChannelCreate(username="demo", parser_profile=" auto ")
        self.assertIsNone(model.parser_profile)

    def test_channel_create_rejects_unknown_parser_profile(self) -> None:
        with self.assertRaises(ValidationError):
            ChannelCreate(username="demo", parser_profile="unknown_profile")

    def test_link_check_task_create_validates_concurrency(self) -> None:
        with self.assertRaises(ValidationError):
            LinkCheckTaskCreate(period="today", max_concurrent=0)

    def test_link_cleanup_request_validates_mode(self) -> None:
        with self.assertRaises(ValidationError):
            LinkCleanupApplyRequest(mode="delete_everything")

    def test_system_config_update_rejects_default_concurrency_above_max(self) -> None:
        with self.assertRaises(ValidationError):
            SystemConfigUpdate(
                public_dashboard_enabled=True,
                link_check_default_max_concurrent=6,
                link_check_max_allowed_concurrent=5,
                link_check_max_allowed_links=1000,
                link_check_poll_interval_seconds=2,
                monitor_channel_refresh_interval_seconds=60,
                monitor_db_write_max_retries=3,
                monitor_db_write_retry_delay_seconds=1.0,
            )

    def test_user_create_rejects_space_in_username(self) -> None:
        with self.assertRaises(ValidationError):
            UserCreate(username="bad user", password="secret123")


if __name__ == "__main__":
    unittest.main()
