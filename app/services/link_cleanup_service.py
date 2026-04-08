from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from app.core.monitor_parser import normalize_url
from app.models.models import LinkCheckDetails, LinkCheckStats, Message
from app.services.link_check.result import STATUS_INVALID

logger = logging.getLogger(__name__)

CLEANUP_MODE_REMOVE_INVALID_LINKS = "remove_invalid_links"
CLEANUP_MODE_DELETE_MESSAGE_IF_EMPTY = "delete_message_if_empty"
SUPPORTED_CLEANUP_MODES = {
    CLEANUP_MODE_REMOVE_INVALID_LINKS,
    CLEANUP_MODE_DELETE_MESSAGE_IF_EMPTY,
}
_CLEANUP_ELIGIBLE_STATUSES = {STATUS_INVALID}


def _normalize_status(status: str | None) -> str:
    return (status or "").strip().lower()


def _normalize_url_key(url: str | None) -> str:
    normalized = normalize_url(url or "")
    if not normalized:
        return ""
    return normalized


def _normalize_links_payload(links: Any) -> Any:
    if isinstance(links, str):
        try:
            return json.loads(links)
        except Exception:
            return links
    return links


def _is_empty_container(value: Any) -> bool:
    return value is None or value == {} or value == []


def _prune_invalid_links(value: Any, invalid_urls: set[str]) -> Tuple[Any, int]:
    if isinstance(value, dict):
        link_url = value.get("url")
        if isinstance(link_url, str):
            if _normalize_url_key(link_url) in invalid_urls:
                return None, 1

            cleaned_dict: Dict[str, Any] = {}
            removed_count = 0
            for key, item in value.items():
                if key == "url":
                    cleaned_dict[key] = item
                    continue
                cleaned_item, child_removed = _prune_invalid_links(item, invalid_urls)
                removed_count += child_removed
                if cleaned_item is None and isinstance(item, (dict, list)):
                    continue
                cleaned_dict[key] = cleaned_item
            return cleaned_dict, removed_count

        cleaned_dict = {}
        removed_count = 0
        for key, item in value.items():
            cleaned_item, child_removed = _prune_invalid_links(item, invalid_urls)
            removed_count += child_removed
            if _is_empty_container(cleaned_item):
                continue
            cleaned_dict[key] = cleaned_item
        return (cleaned_dict or None), removed_count

    if isinstance(value, list):
        cleaned_list = []
        removed_count = 0
        for item in value:
            cleaned_item, child_removed = _prune_invalid_links(item, invalid_urls)
            removed_count += child_removed
            if _is_empty_container(cleaned_item):
                continue
            cleaned_list.append(cleaned_item)
        return (cleaned_list or None), removed_count

    if isinstance(value, str):
        if _normalize_url_key(value) in invalid_urls:
            return None, 1
        return value, 0

    return value, 0


def _extract_netdisk_types(links: Any) -> list[str]:
    if isinstance(links, dict):
        return [key for key, value in links.items() if not _is_empty_container(value)]
    return []


def _is_cleanup_candidate(detail: LinkCheckDetails) -> bool:
    return (
        not bool(detail.is_valid)
        and detail.message_id is not None
        and int(detail.message_id or 0) > 0
        and _normalize_status(detail.action_taken) in _CLEANUP_ELIGIBLE_STATUSES
    )


def _has_invalid_streak(
    db: Session,
    normalized_url: str,
    *,
    min_consecutive_invalid_runs: int,
) -> bool:
    rows = (
        db.query(LinkCheckDetails.check_time, LinkCheckDetails.is_valid, LinkCheckDetails.action_taken)
        .filter(LinkCheckDetails.normalized_url == normalized_url)
        .order_by(LinkCheckDetails.check_time.desc(), LinkCheckDetails.id.desc())
        .all()
    )

    seen_check_times: set[datetime] = set()
    streak_count = 0
    for check_time, is_valid, action_taken in rows:
        if check_time in seen_check_times:
            continue
        seen_check_times.add(check_time)
        if bool(is_valid) or _normalize_status(action_taken) not in _CLEANUP_ELIGIBLE_STATUSES:
            return False
        streak_count += 1
        if streak_count >= min_consecutive_invalid_runs:
            return True
    return False


def apply_link_check_cleanup(
    db: Session,
    check_time_str: str,
    *,
    mode: str = CLEANUP_MODE_REMOVE_INVALID_LINKS,
    dry_run: bool = False,
    min_consecutive_invalid_runs: int = 1,
) -> Dict[str, Any]:
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in SUPPORTED_CLEANUP_MODES:
        raise ValueError(f"Unsupported cleanup mode: {mode}")
    if int(min_consecutive_invalid_runs or 1) < 1:
        raise ValueError("min_consecutive_invalid_runs must be at least 1")

    check_time = datetime.fromisoformat(check_time_str)
    stats = db.query(LinkCheckStats).filter(LinkCheckStats.check_time == check_time).first()
    if stats is None:
        raise LookupError("链接检测记录不存在")

    invalid_details = (
        db.query(LinkCheckDetails)
        .filter(LinkCheckDetails.check_time == check_time)
        .all()
    )

    message_invalid_urls: Dict[int, set[str]] = {}
    cleanup_candidates = 0
    for detail in invalid_details:
        if not _is_cleanup_candidate(detail):
            continue
        normalized_url = _normalize_url_key(detail.url)
        if not normalized_url:
            continue
        if int(min_consecutive_invalid_runs or 1) > 1 and not _has_invalid_streak(
            db,
            normalized_url,
            min_consecutive_invalid_runs=int(min_consecutive_invalid_runs or 1),
        ):
            continue
        message_invalid_urls.setdefault(int(detail.message_id), set()).add(normalized_url)
        cleanup_candidates += 1

    if not message_invalid_urls:
        return {
            "success": True,
            "check_time": check_time.isoformat(),
            "mode": normalized_mode,
            "dry_run": dry_run,
            "total_invalid_details": sum(1 for detail in invalid_details if not bool(detail.is_valid)),
            "cleanup_candidates": 0,
            "matched_messages": 0,
            "updated_messages": 0,
            "deleted_messages": 0,
            "removed_links": 0,
            "skipped_messages": 0,
        }

    messages = (
        db.query(Message)
        .filter(Message.id.in_(list(message_invalid_urls.keys())))
        .all()
    )
    message_by_id = {message.id: message for message in messages}

    matched_messages = 0
    updated_messages = 0
    deleted_messages = 0
    removed_links = 0
    skipped_messages = 0

    try:
        for message_id, invalid_urls in message_invalid_urls.items():
            message = message_by_id.get(message_id)
            if message is None:
                skipped_messages += 1
                continue

            matched_messages += 1
            original_links = _normalize_links_payload(message.links)
            cleaned_links, message_removed_links = _prune_invalid_links(original_links, invalid_urls)
            cleaned_links = None if _is_empty_container(cleaned_links) else cleaned_links
            next_netdisk_types = _extract_netdisk_types(cleaned_links)
            links_changed = cleaned_links != original_links
            should_delete_message = (
                normalized_mode == CLEANUP_MODE_DELETE_MESSAGE_IF_EMPTY
                and not next_netdisk_types
            )

            if should_delete_message:
                removed_links += message_removed_links
                deleted_messages += 1
                if not dry_run:
                    db.delete(message)
                continue

            if not links_changed:
                skipped_messages += 1
                continue

            removed_links += message_removed_links
            updated_messages += 1
            if not dry_run:
                message.links = cleaned_links
                message.netdisk_types = next_netdisk_types

        if not dry_run:
            stats.updated_messages = int(stats.updated_messages or 0) + updated_messages
            stats.deleted_messages = int(stats.deleted_messages or 0) + deleted_messages
            db.commit()
            if (updated_messages or deleted_messages) and hasattr(db, "get_bind") and db.get_bind() is not None:
                try:
                    from app.services.link_check_plan_service import mark_link_check_plan_overview_stale

                    mark_link_check_plan_overview_stale(getattr(stats, "plan_id", None))
                except Exception:
                    logger.exception("failed to mark link check plan overview stale after cleanup")
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        logger.error("failed to apply link cleanup for %s: %s", check_time_str, exc, exc_info=True)
        raise

    return {
        "success": True,
        "check_time": check_time.isoformat(),
        "mode": normalized_mode,
        "dry_run": dry_run,
        "total_invalid_details": sum(1 for detail in invalid_details if not bool(detail.is_valid)),
        "cleanup_candidates": cleanup_candidates,
        "matched_messages": matched_messages,
        "updated_messages": updated_messages,
        "deleted_messages": deleted_messages,
        "removed_links": removed_links,
        "skipped_messages": skipped_messages,
    }
