from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.models import (
    MediaWallItem,
    MediaWallLink,
    PanTransferSyncTask,
    engine,
    ensure_runtime_storage_tables,
)
from app.services.link_check.parser import canonical_target_key
from app.services.link_check.validator import LinkValidator


logger = logging.getLogger(__name__)

MAX_LINKS_PER_RUN = 24
CLAIM_TIMEOUT = timedelta(minutes=10)
VALID_INTERVAL = timedelta(days=1)
INVALID_RECHECK_INTERVAL = timedelta(minutes=10)
UNCERTAIN_RECHECK_INTERVAL = timedelta(minutes=30)
RATE_LIMITED_RECHECK_INTERVAL = timedelta(minutes=30)
REQUIRES_CODE_INTERVAL = timedelta(days=1)
OTHER_RECHECK_INTERVAL = timedelta(days=7)
FOLLOW_LINK_RECHECK_INTERVAL = timedelta(hours=1)


def _next_check_at(status: str, checked_at: datetime) -> datetime:
    if status in {"valid", "healthy"}:
        return checked_at + VALID_INTERVAL
    if status == "invalid":
        return checked_at + INVALID_RECHECK_INTERVAL
    if status == "rate_limited":
        return checked_at + RATE_LIMITED_RECHECK_INTERVAL
    if status in {"uncertain", "error", "network_error"}:
        return checked_at + UNCERTAIN_RECHECK_INTERVAL
    if status == "requires_code":
        return checked_at + REQUIRES_CODE_INTERVAL
    return checked_at + OTHER_RECHECK_INTERVAL


def _is_due_link(link: MediaWallLink, now: datetime) -> bool:
    if link.source_type == "sync":
        return False
    if link.next_check_at is None or link.next_check_at <= now:
        return bool(link.is_enabled or int(link.invalid_streak or 0) > 0 or link.last_status == "invalid")
    return False


def _is_follow_current_link(session: Session, link: MediaWallLink) -> bool:
    item = session.get(MediaWallItem, int(link.item_id))
    if item is None or item.sync_task_id is None:
        return False
    task = session.get(PanTransferSyncTask, int(item.sync_task_id))
    if task is None or task.status == "deleted" or not task.current_share_url:
        return False
    return canonical_target_key(str(task.current_share_url)) == canonical_target_key(str(link.url))


def _claim_due_links(limit: int) -> list[tuple[int, str, str]]:
    now = datetime.utcnow()
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        candidates = (
            session.query(MediaWallLink)
            .filter(
                MediaWallLink.source_type != "sync",
                or_(MediaWallLink.next_check_at.is_(None), MediaWallLink.next_check_at <= now),
                or_(
                    MediaWallLink.is_enabled.is_(True),
                    MediaWallLink.invalid_streak > 0,
                    MediaWallLink.last_status == "invalid",
                ),
            )
            .order_by(MediaWallLink.next_check_at.asc().nullsfirst(), MediaWallLink.id.asc())
            .limit(max(limit * 2, limit))
            .all()
        )
        claimed: list[tuple[int, str, str]] = []
        for link in candidates:
            if len(claimed) >= limit or not _is_due_link(link, now):
                continue
            if _is_follow_current_link(session, link):
                link.next_check_at = now + FOLLOW_LINK_RECHECK_INTERVAL
                continue
            link.next_check_at = now + CLAIM_TIMEOUT
            claimed.append((int(link.id), str(link.url), str(link.url_fingerprint)))
        session.commit()
        return claimed


async def _check_urls(urls: list[str]) -> list[dict[str, Any]]:
    validator = LinkValidator(use_history=False, enable_inflight=True)
    return await validator.check_multiple_links(urls, max_concurrent=4)


def _apply_results(
    claimed: list[tuple[int, str, str]],
    results: list[dict[str, Any]],
) -> dict[str, int]:
    now = datetime.utcnow()
    result_by_url = {
        canonical_target_key(str(result.get("url") or "")): result
        for result in results
    }
    summary = {"checked": 0, "deleted": 0, "hidden": 0, "restored": 0}
    with Session(engine) as session:
        for link_id, url, fingerprint in claimed:
            link = session.get(MediaWallLink, link_id)
            if link is None or link.source_type == "sync":
                continue
            if str(link.url_fingerprint) != fingerprint or canonical_target_key(str(link.url)) != canonical_target_key(url):
                continue
            result = result_by_url.get(canonical_target_key(url)) or {
                "status": "uncertain",
                "error": "检测未返回结果",
            }
            status = str(result.get("status") or "uncertain").strip().lower()
            error_message = str(result.get("error") or result.get("reason") or "").strip()[:2000] or None
            summary["checked"] += 1
            link.last_checked_at = now
            link.last_status = status
            link.last_error_message = None if status in {"valid", "healthy"} else error_message
            if status == "invalid":
                link.invalid_streak = int(link.invalid_streak or 0) + 1
                if link.invalid_streak >= 2:
                    session.delete(link)
                    summary["deleted"] += 1
                    continue
                link.is_enabled = False
                link.next_check_at = _next_check_at(status, now)
                summary["hidden"] += 1
                continue

            was_disabled = not bool(link.is_enabled)
            link.invalid_streak = 0
            link.is_enabled = True
            link.next_check_at = _next_check_at(status, now)
            if was_disabled:
                summary["restored"] += 1
        session.commit()
    return summary


def run_due_media_wall_link_checks(*, limit: int = MAX_LINKS_PER_RUN) -> dict[str, int]:
    claimed = _claim_due_links(max(1, min(int(limit), MAX_LINKS_PER_RUN)))
    if not claimed:
        return {"checked": 0, "deleted": 0, "hidden": 0, "restored": 0}

    unique_urls = list(dict.fromkeys(canonical_target_key(url) for _, url, _ in claimed))
    try:
        results = asyncio.run(_check_urls(unique_urls))
    except Exception:
        logger.exception("Media wall link health check failed")
        results = [{"url": url, "status": "uncertain", "error": "检测任务异常"} for url in unique_urls]

    summary = _apply_results(claimed, results)
    if summary["deleted"] or summary["hidden"] or summary["restored"]:
        logger.info(
            "Media wall link health check completed: checked=%s hidden=%s restored=%s deleted=%s",
            summary["checked"],
            summary["hidden"],
            summary["restored"],
            summary["deleted"],
        )
    return summary
