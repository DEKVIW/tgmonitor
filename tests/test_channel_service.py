from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services import channel_service


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


if __name__ == "__main__":
    unittest.main()
