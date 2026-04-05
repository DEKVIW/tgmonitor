from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services import channel_service
from app.core.monitor_parser import ParseDiagnostics


class _DummyEvent:
    def __init__(self, chats):
        self.chats = chats


class _DummyClient:
    def __init__(self) -> None:
        self.captured_chats = None

    async def start(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def on(self, event):
        self.captured_chats = list(event.chats)

        def decorator(func):
            return func

        return decorator


class _DummyEntity:
    id = 123456
    title = "Sample Channel"


class _DummyMessage:
    def __init__(self, message_id: int, text: str, *, media=None, post_author: str | None = None) -> None:
        self.id = message_id
        self.message = text
        self.raw_text = text
        self.date = datetime(2026, 4, 4, 12, 0, 0)
        self.media = media
        self.reply_markup = None
        self.grouped_id = None
        self.post_author = post_author

    def get_entities_text(self):
        return []

    def to_dict(self):
        return {
            "_": "Message",
            "id": self.id,
            "message": self.message,
            "raw_text": self.raw_text,
            "date": self.date.isoformat(),
            "post_author": self.post_author,
            "media": None,
        }


class _DummyWebpage:
    def __init__(self, *, url: str, title: str | None = None, description: str | None = None) -> None:
        self.url = url
        self.title = title
        self.description = description
        self.site_name = "Telegraph"
        self.author = "tester"
        self.type = "article"
        self.display_url = "telegra.ph/sample"


class _DummyMedia:
    def __init__(self, webpage=None) -> None:
        self.webpage = webpage


class _DummySampleClient:
    def __init__(self, messages) -> None:
        self.messages = messages

    async def start(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def get_entity(self, target):
        return _DummyEntity()

    def iter_messages(self, entity, limit: int = 10):
        async def generator():
            for message in self.messages[:limit]:
                yield message

        return generator()


class ChannelServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_test_monitor_uses_normalized_merged_channels(self) -> None:
        dummy_client = _DummyClient()

        with (
            patch("app.services.channel_service.ensure_session_file", return_value=True),
            patch("app.services.channel_service.get_api_credentials", return_value=(1, "hash")),
            patch("app.services.channel_service.get_channels", return_value=["alpha", "+Invite123456"]),
            patch("app.services.channel_service.TelegramClient", return_value=dummy_client),
            patch("app.services.channel_service.events.NewMessage", side_effect=lambda chats: _DummyEvent(chats)),
            patch("app.services.channel_service.asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await channel_service.test_monitor()

        self.assertTrue(result["success"])
        self.assertEqual(result["channels_tested"], 2)
        self.assertEqual(dummy_client.captured_chats, ["alpha", "+Invite123456"])

    async def test_fetch_channel_message_samples_can_filter_non_link_messages(self) -> None:
        dummy_client = _DummySampleClient(
            [
                _DummyMessage(1, "first https://pan.baidu.com/s/abc"),
                _DummyMessage(2, "second plain text"),
            ]
        )
        parse_results = [
            (
                [{"title": "first", "description": "", "links": {"百度网盘": [{"url": "https://pan.baidu.com/s/abc"}]}, "tags": [], "source": "", "channel": "", "group_name": "", "bot": ""}],
                ParseDiagnostics(profile_name="alpha", extracted_link_count=1),
            ),
            (
                [{"title": "second", "description": "", "links": {}, "tags": [], "source": "", "channel": "", "group_name": "", "bot": ""}],
                ParseDiagnostics(profile_name="alpha", extracted_link_count=0),
            ),
        ]

        with (
            patch("app.services.channel_service.ensure_session_file", return_value=True),
            patch("app.services.channel_service.get_api_credentials", return_value=(1, "hash")),
            patch("app.services.channel_service.TelegramClient", return_value=dummy_client),
            patch("app.services.channel_service.parse_message_records", new=AsyncMock(side_effect=parse_results)),
        ):
            result = await channel_service.fetch_channel_message_samples("alpha", limit=5, only_with_links=True)

        self.assertEqual(result["sample_count"], 1)
        self.assertEqual(result["samples"][0]["message_id"], 1)
        self.assertEqual(result["title"], "Sample Channel")
        self.assertEqual(result["requested_limit"], 5)
        self.assertIn("parser_debug", result["samples"][0])
        self.assertEqual(result["samples"][0]["parser_debug"]["extracted_link_count"], 1)

    async def test_fetch_channel_message_samples_supports_page_slicing(self) -> None:
        dummy_client = _DummySampleClient(
            [
                _DummyMessage(1, "first https://pan.baidu.com/s/abc"),
                _DummyMessage(2, "second https://pan.baidu.com/s/def"),
                _DummyMessage(3, "third https://pan.baidu.com/s/ghi"),
            ]
        )
        parse_results = [
            (
                [{"title": "first", "description": "", "links": {"百度网盘": [{"url": "https://pan.baidu.com/s/abc"}]}, "tags": [], "source": "", "channel": "", "group_name": "", "bot": ""}],
                ParseDiagnostics(profile_name="alpha", extracted_link_count=1),
            ),
            (
                [{"title": "second", "description": "", "links": {"百度网盘": [{"url": "https://pan.baidu.com/s/def"}]}, "tags": [], "source": "", "channel": "", "group_name": "", "bot": ""}],
                ParseDiagnostics(profile_name="alpha", extracted_link_count=1),
            ),
            (
                [{"title": "third", "description": "", "links": {"百度网盘": [{"url": "https://pan.baidu.com/s/ghi"}]}, "tags": [], "source": "", "channel": "", "group_name": "", "bot": ""}],
                ParseDiagnostics(profile_name="alpha", extracted_link_count=1),
            ),
        ]

        with (
            patch("app.services.channel_service.ensure_session_file", return_value=True),
            patch("app.services.channel_service.get_api_credentials", return_value=(1, "hash")),
            patch("app.services.channel_service.TelegramClient", return_value=dummy_client),
            patch("app.services.channel_service.parse_message_records", new=AsyncMock(side_effect=parse_results)),
        ):
            result = await channel_service.fetch_channel_message_samples(
                "alpha",
                page=2,
                page_size=1,
                only_with_links=True,
            )

        self.assertEqual(result["page"], 2)
        self.assertEqual(result["sample_count"], 1)
        self.assertEqual(result["samples"][0]["message_id"], 2)
        self.assertTrue(result["has_more"])

    async def test_fetch_channel_message_samples_includes_raw_snapshot_and_preview_fields(self) -> None:
        message = _DummyMessage(
            7,
            "sample https://telegra.ph/test-page",
            media=_DummyMedia(
                _DummyWebpage(
                    url="https://telegra.ph/test-page",
                    title="网页预览标题",
                    description="网页预览描述",
                )
            ),
            post_author="Author",
        )
        dummy_client = _DummySampleClient([message])
        parse_result = (
            [{"title": "sample", "description": "", "links": {}, "tags": [], "source": "", "channel": "", "group_name": "", "bot": ""}],
            ParseDiagnostics(profile_name="alpha", extracted_link_count=0),
        )

        with (
            patch("app.services.channel_service.ensure_session_file", return_value=True),
            patch("app.services.channel_service.get_api_credentials", return_value=(1, "hash")),
            patch("app.services.channel_service.TelegramClient", return_value=dummy_client),
            patch("app.services.channel_service.parse_message_records", new=AsyncMock(return_value=parse_result)),
        ):
            result = await channel_service.fetch_channel_message_samples("alpha", limit=5, only_with_links=False)

        sample = result["samples"][0]
        self.assertEqual(sample["message_link"], "https://t.me/alpha/7")
        self.assertEqual(sample["media_kind"], "webpage")
        self.assertEqual(sample["post_author"], "Author")
        self.assertEqual(sample["webpage_preview"]["title"], "网页预览标题")
        self.assertEqual(sample["webpage_preview"]["description"], "网页预览描述")
        self.assertEqual(sample["raw_message"]["_"], "Message")
        self.assertEqual(sample["parser_debug"]["parsed_records"][0]["title"], "sample")


if __name__ == "__main__":
    unittest.main()
