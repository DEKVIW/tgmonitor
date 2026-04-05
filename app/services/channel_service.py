"""Service helpers for admin channel management and debugging."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from dataclasses import asdict
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session
from telethon import TelegramClient, events

from app.core.monitor_parser import extract_all_urls, parse_message_records
from app.models.config import settings
from app.models.models import Credential, engine
from app.services.channel_registry import get_runtime_channels

try:
    from telethon.tl.types import KeyboardButtonUrl, MessageEntityTextUrl, MessageEntityUrl
except ImportError:  # pragma: no cover - optional in tests
    KeyboardButtonUrl = MessageEntityTextUrl = MessageEntityUrl = object

logger = logging.getLogger(__name__)


def is_invite_link_hash(channel_name: str) -> bool:
    """Return whether the channel name looks like a Telegram invite hash."""
    return bool(re.match(r"^\+[a-zA-Z0-9_-]{10,}$", channel_name or ""))


def ensure_session_file(session_name: str) -> bool:
    """Ensure a named Telethon session exists by copying the main session if needed."""
    main_session = "tg_monitor_session.session"
    target_session = f"{session_name}.session"

    if os.path.exists(target_session):
        return True

    if not os.path.exists(main_session):
        logger.error("Main session file %s does not exist", main_session)
        return False

    try:
        shutil.copy2(main_session, target_session)
        return True
    except Exception as exc:  # pragma: no cover - filesystem failure
        logger.error("Failed to copy session file: %s", exc)
        return False


def get_api_credentials() -> Tuple[int, str]:
    """Load Telegram API credentials from the database, falling back to settings."""
    with Session(engine) as session:
        credential = session.query(Credential).first()
        if credential:
            return int(credential.api_id), credential.api_hash
    return settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH


def get_channels() -> List[str]:
    """Return runtime channels from the database only."""
    return get_runtime_channels()


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _sanitize_telegram_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"type": "bytes", "length": len(value)}
    if isinstance(value, dict):
        return {str(key): _sanitize_telegram_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_telegram_value(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _sanitize_telegram_value(value.to_dict())
        except Exception:  # pragma: no cover - defensive serialization fallback
            pass
    return str(value)


def _build_raw_message_snapshot(message: Any) -> Dict[str, Any]:
    if hasattr(message, "to_dict") and callable(message.to_dict):
        try:
            snapshot = _sanitize_telegram_value(message.to_dict())
            if isinstance(snapshot, dict):
                return snapshot
        except Exception:  # pragma: no cover - defensive serialization fallback
            logger.debug("Failed to serialize raw Telegram message", exc_info=True)

    return {
        "id": int(getattr(message, "id", 0) or 0),
        "message": str(getattr(message, "message", None) or ""),
        "raw_text": str(getattr(message, "raw_text", None) or ""),
    }


def _infer_media_kind(message: Any) -> str | None:
    media = getattr(message, "media", None)
    if media is None:
        return None

    if getattr(media, "webpage", None) is not None:
        return "webpage"

    return media.__class__.__name__


def _build_message_link(channel_username: str, channel_id: int | None, message_id: int) -> str | None:
    if not message_id:
        return None

    normalized_username = str(channel_username or "").strip()
    if normalized_username and not is_invite_link_hash(normalized_username):
        return f"https://t.me/{normalized_username}/{message_id}"
    if channel_id:
        return f"https://t.me/c/{channel_id}/{message_id}"
    return None


def _extract_message_debug_urls(
    message: Any,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str | None]], Dict[str, str | None] | None]:
    entity_urls: List[Dict[str, str]] = []
    button_links: List[Dict[str, str | None]] = []

    if hasattr(message, "get_entities_text"):
        for entity, text_part in message.get_entities_text():
            if isinstance(entity, MessageEntityTextUrl):
                entity_urls.append(
                    {
                        "type": "text_url",
                        "url": str(getattr(entity, "url", "") or ""),
                        "text": str(text_part or ""),
                    }
                )
            elif isinstance(entity, MessageEntityUrl):
                entity_urls.append(
                    {
                        "type": "url",
                        "url": str(text_part or ""),
                        "text": str(text_part or ""),
                    }
                )

    reply_markup = getattr(message, "reply_markup", None)
    if reply_markup:
        for row in getattr(reply_markup, "rows", []):
            for button in getattr(row, "buttons", []):
                if isinstance(button, KeyboardButtonUrl) and getattr(button, "url", None):
                    button_links.append(
                        {
                            "text": _normalize_optional_text(getattr(button, "text", None)),
                            "url": str(button.url),
                        }
                    )

    media = getattr(message, "media", None)
    webpage = getattr(media, "webpage", None)
    webpage_preview = None
    if webpage is not None:
        preview = {
            "url": _normalize_optional_text(getattr(webpage, "url", None)),
            "title": _normalize_optional_text(getattr(webpage, "title", None)),
            "description": _normalize_optional_text(getattr(webpage, "description", None)),
            "site_name": _normalize_optional_text(getattr(webpage, "site_name", None)),
            "author": _normalize_optional_text(getattr(webpage, "author", None)),
            "type": _normalize_optional_text(getattr(webpage, "type", None)),
            "display_url": _normalize_optional_text(getattr(webpage, "display_url", None)),
        }
        if any(value for value in preview.values()):
            webpage_preview = preview

    deduped_entity_urls: List[Dict[str, str]] = []
    seen_entities = set()
    for item in entity_urls:
        key = (item.get("type"), item.get("url"), item.get("text"))
        if key in seen_entities:
            continue
        seen_entities.add(key)
        deduped_entity_urls.append(item)

    deduped_button_links: List[Dict[str, str | None]] = []
    seen_buttons = set()
    for item in button_links:
        key = (item.get("text"), item.get("url"))
        if not item.get("url") or key in seen_buttons:
            continue
        seen_buttons.add(key)
        deduped_button_links.append(item)

    return deduped_entity_urls, deduped_button_links, webpage_preview


async def _build_channel_message_sample(
    message: Any,
    *,
    channel_username: str,
    channel_id: int | None,
    parser_profile: str | None = None,
) -> Dict[str, Any]:
    message_id = int(getattr(message, "id", 0) or 0)
    text = str(getattr(message, "message", None) or getattr(message, "raw_text", None) or "")
    raw_urls = sorted(extract_all_urls(text, message))
    entity_urls, button_links, webpage_preview = _extract_message_debug_urls(message)
    parsed_records, diagnostics = await parse_message_records(
        text,
        msg_obj=message,
        channel_name=channel_username,
        channel_id=channel_id,
        parser_profile=parser_profile,
    )
    extracted_link_count = sum(
        len(link_items)
        for record in parsed_records
        for link_items in record.get("links", {}).values()
    )

    return {
        "message_id": message_id,
        "timestamp": getattr(message, "date").isoformat() if getattr(message, "date", None) else "",
        "message_link": _build_message_link(channel_username, channel_id, message_id),
        "text": text,
        "text_length": len(text),
        "has_media": bool(getattr(message, "media", None)),
        "media_kind": _infer_media_kind(message),
        "grouped_id": int(getattr(message, "grouped_id", 0) or 0) or None,
        "post_author": _normalize_optional_text(getattr(message, "post_author", None)),
        "raw_urls": raw_urls,
        "entity_urls": entity_urls,
        "button_links": button_links,
        "webpage_preview": webpage_preview,
        "raw_message": _build_raw_message_snapshot(message),
        "extracted_link_count": extracted_link_count,
        "parser_debug": {
            "parsed_records": parsed_records,
            "diagnostics": asdict(diagnostics),
            "extracted_link_count": extracted_link_count,
        },
    }


async def fetch_channel_message_samples(
    channel_username: str,
    *,
    limit: int = 10,
    page: int = 1,
    page_size: int | None = None,
    only_with_links: bool = True,
    parser_profile: str | None = None,
) -> Dict[str, Any]:
    """Fetch recent channel messages plus parser diagnostics for rule tuning."""
    if not ensure_session_file("tg_monitor_session_sample"):
        raise RuntimeError("Telegram session file is missing")

    api_id, api_hash = get_api_credentials()
    client = TelegramClient("tg_monitor_session_sample", api_id, api_hash)

    try:
        await client.start()
        entity = await client.get_entity(f"https://t.me/{channel_username}")
        page = max(1, int(page or 1))
        page_size = max(1, int(page_size or limit or 10))
        required_count = page * page_size + 1
        inspect_limit = min(max(required_count * (4 if only_with_links else 1), required_count), 500)
        collected_samples: List[Dict[str, Any]] = []
        inspected_messages = 0

        async for message in client.iter_messages(entity, limit=inspect_limit):
            inspected_messages += 1
            if getattr(message, "service", None):
                continue

            sample = await _build_channel_message_sample(
                message,
                channel_username=channel_username,
                channel_id=getattr(entity, "id", None),
                parser_profile=parser_profile,
            )
            parser_debug = sample.get("parser_debug", {})
            has_links = bool(sample["raw_urls"]) or bool(parser_debug.get("extracted_link_count"))
            has_content = bool(sample["text"].strip()) or has_links or sample["has_media"]
            if not has_content:
                continue
            if only_with_links and not has_links:
                continue

            collected_samples.append(sample)
            if len(collected_samples) >= required_count:
                break

        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        page_samples = collected_samples[start_index:end_index]
        has_more = len(collected_samples) > end_index

        return {
            "channel_id": int(getattr(entity, "id", 0) or 0),
            "username": channel_username,
            "title": getattr(entity, "title", None),
            "telegram_id": int(getattr(entity, "id", 0) or 0) or None,
            "requested_limit": page_size,
            "page": page,
            "page_size": page_size,
            "sample_count": len(page_samples),
            "has_more": has_more,
            "inspected_count": inspected_messages,
            "only_with_links": only_with_links,
            "samples": page_samples,
        }
    finally:
        await client.disconnect()


async def resolve_channel_runtime_details(
    channel_usernames: List[str] | None = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Resolve live Telegram metadata for configured channels."""
    if not ensure_session_file("tg_monitor_session_diagnose"):
        logger.error("Cannot resolve channel metadata because the Telegram session file is missing")
        return {}, {}

    api_id, api_hash = get_api_credentials()
    resolved_usernames = channel_usernames or get_channels()
    if not resolved_usernames:
        return {}, {}

    client = TelegramClient("tg_monitor_session_diagnose", api_id, api_hash)

    try:
        await client.start()
        valid_map: Dict[str, Dict[str, Any]] = {}
        invalid_map: Dict[str, Dict[str, Any]] = {}

        for channel in resolved_usernames:
            try:
                entity = await client.get_entity(f"https://t.me/{channel}")
                channel_info = await client.get_entity(entity)
                valid_map[channel] = {
                    "username": channel,
                    "title": getattr(channel_info, "title", "未知"),
                    "id": channel_info.id,
                    "type": "invite_link" if is_invite_link_hash(channel) else "standard",
                    "participants_count": getattr(channel_info, "participants_count", None),
                }
            except Exception as exc:
                invalid_map[channel] = {
                    "username": channel,
                    "error": str(exc),
                    "type": "unknown",
                }

        return valid_map, invalid_map
    except Exception as exc:
        logger.error("Failed to resolve channel metadata: %s", exc)
        return {}, {}
    finally:
        await client.disconnect()


async def diagnose_channels() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    channel_usernames = get_channels()
    if not channel_usernames:
        return [], []

    valid_map, invalid_map = await resolve_channel_runtime_details(channel_usernames)
    valid_channels = [valid_map[channel] for channel in channel_usernames if channel in valid_map]
    invalid_channels = [invalid_map[channel] for channel in channel_usernames if channel in invalid_map]
    return valid_channels, invalid_channels


async def test_monitor() -> Dict[str, Any]:
    """Run a lightweight listener registration test for configured channels."""
    if not ensure_session_file("tg_monitor_session_test"):
        return {
            "success": False,
            "error": "无法进行测试，缺少必要的 session 文件",
        }

    api_id, api_hash = get_api_credentials()
    channel_usernames = get_channels()
    if not channel_usernames:
        return {
            "success": False,
            "error": "没有有效的频道可供监听",
        }

    client = TelegramClient("tg_monitor_session_test", api_id, api_hash)
    message_received = False

    try:
        await client.start()

        @client.on(events.NewMessage(chats=channel_usernames))
        async def test_handler(event: Any) -> None:
            del event
            nonlocal message_received
            message_received = True

        await asyncio.sleep(5)

        return {
            "success": True,
            "channels_tested": len(channel_usernames),
            "message_received": message_received,
            "message": "测试完成，事件处理器已注册",
        }
    except Exception as exc:
        logger.error("Monitor test failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
        }
    finally:
        try:
            await client.disconnect()
        except Exception:  # pragma: no cover - defensive cleanup
            pass
