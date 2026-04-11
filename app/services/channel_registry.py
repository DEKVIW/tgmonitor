"""Helpers for loading runtime channel configuration."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import Channel, engine, ensure_channel_parser_profile_column
from app.utils.channel_utils import dedupe_preserve_order, normalize_channel_username


logger = logging.getLogger(__name__)


def load_default_channels_from_settings() -> List[str]:
    channels: List[str] = []
    raw_channels = getattr(settings, "DEFAULT_CHANNELS", "") or ""
    for raw_channel in raw_channels.split(","):
        if not raw_channel.strip():
            continue
        try:
            channels.append(normalize_channel_username(raw_channel))
        except ValueError:
            logger.warning("Skipping invalid channel from settings: %s", raw_channel)
    return dedupe_preserve_order(channels)


def get_runtime_channels() -> List[str]:
    """Return channels from the database only."""
    db_channels: List[str] = []

    ensure_channel_parser_profile_column()
    with Session(engine) as session:
        for channel in session.query(Channel).all():
            try:
                db_channels.append(normalize_channel_username(channel.username))
            except ValueError:
                logger.warning("Skipping invalid channel from database: %s", channel.username)

        db_channels = dedupe_preserve_order(db_channels)
        return db_channels


def get_runtime_channel_parser_profiles() -> Dict[str, str | None]:
    """Return parser profile overrides for the active runtime channels."""
    profile_map: Dict[str, str | None] = {}

    ensure_channel_parser_profile_column()
    with Session(engine) as session:
        for channel in session.query(Channel).all():
            try:
                normalized = normalize_channel_username(channel.username)
            except ValueError:
                logger.warning("Skipping invalid channel from database for parser profile: %s", channel.username)
                continue
            profile_map[normalized] = getattr(channel, "parser_profile", None)

    return profile_map


def get_runtime_channel_metadata() -> Dict[str, Dict[str, Any]]:
    """Return runtime channel metadata keyed by normalized channel username."""
    metadata: Dict[str, Dict[str, Any]] = {}

    ensure_channel_parser_profile_column()
    with Session(engine) as session:
        for channel in session.query(Channel).all():
            try:
                normalized = normalize_channel_username(channel.username)
            except ValueError:
                logger.warning("Skipping invalid channel from database for metadata: %s", channel.username)
                continue
            metadata[normalized] = {
                "config_id": int(channel.id),
                "parser_profile": getattr(channel, "parser_profile", None),
            }

    return metadata
