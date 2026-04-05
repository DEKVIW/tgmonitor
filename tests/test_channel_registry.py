from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services import channel_registry


class _FakeQuery:
    def __init__(self, channels) -> None:
        self.channels = list(channels)

    def all(self):
        return list(self.channels)


class _FakeSession:
    def __init__(self, channels) -> None:
        self.channels = list(channels)
        self.added = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def query(self, model):
        del model
        return _FakeQuery(self.channels)

    def add(self, channel):
        self.added.append(channel)

    def commit(self):
        self.committed = True


class ChannelRegistryTestCase(unittest.TestCase):
    def test_get_runtime_channels_prefers_database_when_present(self) -> None:
        fake_session = _FakeSession([SimpleNamespace(username="alpha", parser_profile="movie_default")])

        with (
            patch("app.services.channel_registry.ensure_channel_parser_profile_column"),
            patch("app.services.channel_registry.Session", return_value=fake_session),
            patch.object(channel_registry.settings, "DEFAULT_CHANNELS", "alpha,BaiduCloudDisk"),
        ):
            result = channel_registry.get_runtime_channels()

        self.assertEqual(result, ["alpha"])
        self.assertEqual(fake_session.added, [])
        self.assertFalse(fake_session.committed)

    def test_get_runtime_channels_ignores_env_when_database_is_empty(self) -> None:
        fake_session = _FakeSession([])

        with (
            patch("app.services.channel_registry.ensure_channel_parser_profile_column"),
            patch("app.services.channel_registry.Session", return_value=fake_session),
            patch.object(channel_registry.settings, "DEFAULT_CHANNELS", "alpha,+Invite123456"),
        ):
            result = channel_registry.get_runtime_channels()

        self.assertEqual(result, [])
        self.assertFalse(fake_session.committed)
        self.assertEqual(fake_session.added, [])

    def test_get_runtime_channel_parser_profiles_ignores_env_overrides_when_db_exists(self) -> None:
        fake_session = _FakeSession([SimpleNamespace(username="alpha", parser_profile="movie_default")])

        with (
            patch("app.services.channel_registry.ensure_channel_parser_profile_column"),
            patch("app.services.channel_registry.Session", return_value=fake_session),
            patch.object(channel_registry.settings, "DEFAULT_CHANNELS", "alpha,BaiduCloudDisk"),
        ):
            result = channel_registry.get_runtime_channel_parser_profiles()

        self.assertEqual(result, {"alpha": "movie_default"})


if __name__ == "__main__":
    unittest.main()
