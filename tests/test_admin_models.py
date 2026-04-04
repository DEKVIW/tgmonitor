from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.admin_models import (
    BulkUsernamesRequest,
    ChannelCreate,
    LinkCheckTaskCreate,
    LinkCleanupApplyRequest,
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

    def test_link_check_task_create_validates_concurrency(self) -> None:
        with self.assertRaises(ValidationError):
            LinkCheckTaskCreate(period="today", max_concurrent=0)

    def test_link_cleanup_request_validates_mode(self) -> None:
        with self.assertRaises(ValidationError):
            LinkCleanupApplyRequest(mode="delete_everything")

    def test_user_create_rejects_space_in_username(self) -> None:
        with self.assertRaises(ValidationError):
            UserCreate(username="bad user", password="secret123")


if __name__ == "__main__":
    unittest.main()
