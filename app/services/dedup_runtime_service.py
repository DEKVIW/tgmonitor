from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.monitor_parser import normalize_url
from app.models.models import DedupStats, Message, engine
from app.services.dedup_runtime_settings import (
    DEFAULT_WAIT_WHEN_BLOCKED_MINUTES,
    ensure_dedup_next_run,
    get_dedup_runtime_config,
    update_dedup_runtime_meta,
)
from app.services.resource_ops import delete_message_resource_data


logger = logging.getLogger(__name__)

DEDUP_RUN_LOCK_KEY = 42025094
DEDUP_SCHEDULER_LOCK_KEY = 42025095
DEDUP_CLOSE_WINDOW_SECONDS = 300


@dataclass(slots=True)
class MessageSnapshot:
    id: int
    timestamp: datetime
    normalized_urls: frozenset[str]
    link_count: int


def extract_urls(links: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(links, str):
        urls.append(links)
    elif isinstance(links, dict):
        for value in links.values():
            urls.extend(extract_urls(value))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict) and "url" in item:
                urls.append(str(item["url"]))
            else:
                urls.extend(extract_urls(item))
    return urls


def _normalize_links_payload(links: Any) -> Any:
    if isinstance(links, str):
        try:
            return json.loads(links)
        except Exception:
            return links
    return links


def _normalize_url_key(url: str | None) -> str:
    normalized = normalize_url(url or "")
    if not normalized:
        return ""
    return normalized


def _build_snapshot(message_id: int, timestamp: datetime, links: Any) -> MessageSnapshot | None:
    normalized_payload = _normalize_links_payload(links)
    normalized_urls = {
        normalized
        for raw_url in extract_urls(normalized_payload)
        if isinstance(raw_url, str)
        for normalized in [_normalize_url_key(raw_url)]
        if normalized
    }
    if not normalized_urls:
        return None
    return MessageSnapshot(
        id=int(message_id),
        timestamp=timestamp,
        normalized_urls=frozenset(normalized_urls),
        link_count=len(normalized_urls),
    )


def _is_close_duplicate(left: MessageSnapshot, right: MessageSnapshot) -> bool:
    return abs((left.timestamp - right.timestamp).total_seconds()) < DEDUP_CLOSE_WINDOW_SECONDS


def _is_newer(left: MessageSnapshot, right: MessageSnapshot) -> bool:
    if left.timestamp != right.timestamp:
        return left.timestamp > right.timestamp
    return left.id > right.id


def _should_prefer_candidate(candidate: MessageSnapshot, current: MessageSnapshot) -> bool:
    if _is_close_duplicate(candidate, current):
        if candidate.link_count != current.link_count:
            return candidate.link_count > current.link_count
    return _is_newer(candidate, current)


def _try_claim_xact_lock(session: Session, lock_key: int) -> bool:
    try:
        return bool(
            session.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": int(lock_key)},
            ).scalar()
        )
    except Exception:
        logger.exception("Failed to claim advisory transaction lock %s", lock_key)
        return False


def _remove_keeper(
    keepers_by_id: dict[int, MessageSnapshot],
    keeper_ids_by_url: dict[str, set[int]],
    keeper_id: int,
) -> None:
    snapshot = keepers_by_id.pop(int(keeper_id), None)
    if snapshot is None:
        return
    for normalized_url in snapshot.normalized_urls:
        ids = keeper_ids_by_url.get(normalized_url)
        if not ids:
            continue
        ids.discard(snapshot.id)
        if not ids:
            keeper_ids_by_url.pop(normalized_url, None)


def _iter_message_snapshots(
    session: Session,
    *,
    scope_mode: str,
    lookback_hours: int,
) -> Any:
    query = (
        session.query(Message.id, Message.timestamp, Message.links)
        .filter(Message.links.isnot(None))
        .order_by(Message.timestamp.desc(), Message.id.desc())
    )
    if scope_mode == "recent_hours":
        cutoff_time = datetime.now() - timedelta(hours=max(1, int(lookback_hours)))
        query = query.filter(Message.timestamp >= cutoff_time)

    for row in query.yield_per(1000):
        snapshot = _build_snapshot(row.id, row.timestamp, row.links)
        if snapshot is not None:
            yield snapshot


def _prune_old_stats(session: Session, *, stats_retention_hours: int) -> None:
    retention_hours = max(10, int(stats_retention_hours or 10))
    cutoff_time = datetime.now() - timedelta(hours=retention_hours)
    (
        session.query(DedupStats)
        .filter(DedupStats.run_time < cutoff_time)
        .delete(synchronize_session=False)
    )


def execute_dedup_run(
    session: Session,
    *,
    scope_mode: str,
    lookback_hours: int,
    stats_retention_hours: int,
    trigger_source: str = "manual",
) -> dict[str, Any]:
    if not _try_claim_xact_lock(session, DEDUP_RUN_LOCK_KEY):
        raise RuntimeError("链接去重任务已在运行，请稍后再试")

    started_at = datetime.now()
    started_perf = time.perf_counter()
    keepers_by_id: dict[int, MessageSnapshot] = {}
    keeper_ids_by_url: dict[str, set[int]] = {}
    deleted_message_ids: set[int] = set()
    duplicate_candidate_count = 0
    duplicate_group_count = 0
    scanned_links = 0
    scanned_messages = 0

    for snapshot in _iter_message_snapshots(
        session,
        scope_mode=scope_mode,
        lookback_hours=lookback_hours,
    ):
        scanned_messages += 1
        scanned_links += snapshot.link_count
        overlapping_keeper_ids = {
            keeper_id
            for normalized_url in snapshot.normalized_urls
            for keeper_id in keeper_ids_by_url.get(normalized_url, set())
            if keeper_id in keepers_by_id
        }
        if overlapping_keeper_ids:
            duplicate_candidate_count += 1

        current_deleted = False
        for keeper_id in sorted(overlapping_keeper_ids, reverse=True):
            keeper = keepers_by_id.get(keeper_id)
            if keeper is None:
                continue
            if snapshot.normalized_urls.issubset(keeper.normalized_urls) and _should_prefer_candidate(keeper, snapshot):
                deleted_message_ids.add(snapshot.id)
                duplicate_group_count += 1
                current_deleted = True
                break

        if current_deleted:
            continue

        losers_to_delete: list[int] = []
        for keeper_id in sorted(overlapping_keeper_ids, reverse=True):
            keeper = keepers_by_id.get(keeper_id)
            if keeper is None:
                continue
            if keeper.normalized_urls.issubset(snapshot.normalized_urls) and _should_prefer_candidate(snapshot, keeper):
                losers_to_delete.append(keeper.id)

        if losers_to_delete:
            duplicate_group_count += 1
            for keeper_id in losers_to_delete:
                deleted_message_ids.add(keeper_id)
                _remove_keeper(keepers_by_id, keeper_ids_by_url, keeper_id)

        keepers_by_id[snapshot.id] = snapshot
        for normalized_url in snapshot.normalized_urls:
            keeper_ids_by_url.setdefault(normalized_url, set()).add(snapshot.id)

    deleted_count = 0
    if deleted_message_ids:
        delete_message_resource_data(session, deleted_message_ids)
        deleted_count = (
            session.query(Message)
            .filter(Message.id.in_(deleted_message_ids))
            .delete(synchronize_session=False)
        )

    unique_links = len(keeper_ids_by_url)
    _prune_old_stats(session, stats_retention_hours=stats_retention_hours)
    session.add(
        DedupStats(
            run_time=started_at,
            inserted=unique_links,
            deleted=int(deleted_count or 0),
        )
    )

    duration_seconds = round(time.perf_counter() - started_perf, 3)
    scope_label = "全量历史" if scope_mode == "all_history" else f"最近 {int(lookback_hours)} 小时"
    return {
        "success": True,
        "status": "completed",
        "run_time": started_at.isoformat(),
        "trigger_source": trigger_source,
        "scope_mode": scope_mode,
        "scope_label": scope_label,
        "lookback_hours": None if scope_mode == "all_history" else int(lookback_hours),
        "scanned_messages": scanned_messages,
        "scanned_links": scanned_links,
        "unique_links": unique_links,
        "kept_messages": len(keepers_by_id),
        "duplicate_candidate_count": duplicate_candidate_count,
        "duplicate_group_count": duplicate_group_count,
        "deleted_count": int(deleted_count or 0),
        "duration_seconds": duration_seconds,
        "error": None,
    }


def run_dedup_with_session(
    session: Session,
    *,
    trigger_source: str = "manual",
    updated_by: str | None = None,
    advance_next_run: bool = False,
) -> dict[str, Any]:
    config = get_dedup_runtime_config(session)
    scope_mode = str(config.get("scope_mode") or "all_history")
    lookback_hours = int(config.get("lookback_hours") or 72)
    stats_retention_hours = int(config.get("stats_retention_hours") or 240)

    try:
        result = execute_dedup_run(
            session,
            scope_mode=scope_mode,
            lookback_hours=lookback_hours,
            stats_retention_hours=stats_retention_hours,
            trigger_source=trigger_source,
        )
        update_dedup_runtime_meta(
            session,
            last_status="completed",
            last_error_message="",
            last_run_summary=result,
            advance_next_run=advance_next_run,
            updated_by=updated_by,
        )
        session.commit()
        return result
    except RuntimeError as exc:
        session.rollback()
        error_message = str(exc)
        if trigger_source == "scheduled":
            update_dedup_runtime_meta(
                session,
                last_status="waiting",
                last_error_message=error_message,
                wait_minutes=DEFAULT_WAIT_WHEN_BLOCKED_MINUTES,
                updated_by=updated_by,
            )
            session.commit()
        return {
            "success": False,
            "status": "busy",
            "trigger_source": trigger_source,
            "scope_mode": scope_mode,
            "scope_label": "全量历史" if scope_mode == "all_history" else f"最近 {lookback_hours} 小时",
            "lookback_hours": None if scope_mode == "all_history" else lookback_hours,
            "deleted_count": 0,
            "scanned_messages": 0,
            "scanned_links": 0,
            "unique_links": 0,
            "kept_messages": 0,
            "duplicate_candidate_count": 0,
            "duplicate_group_count": 0,
            "duration_seconds": 0,
            "error": error_message,
        }
    except Exception as exc:
        logger.exception("Dedup runtime run failed")
        session.rollback()
        failure_result = {
            "success": False,
            "status": "failed",
            "trigger_source": trigger_source,
            "scope_mode": scope_mode,
            "scope_label": "全量历史" if scope_mode == "all_history" else f"最近 {lookback_hours} 小时",
            "lookback_hours": None if scope_mode == "all_history" else lookback_hours,
            "deleted_count": 0,
            "scanned_messages": 0,
            "scanned_links": 0,
            "unique_links": 0,
            "kept_messages": 0,
            "duplicate_candidate_count": 0,
            "duplicate_group_count": 0,
            "duration_seconds": 0,
            "error": str(exc),
        }
        update_dedup_runtime_meta(
            session,
            last_status="failed",
            last_error_message=str(exc),
            last_run_summary=failure_result,
            advance_next_run=advance_next_run,
            updated_by=updated_by,
        )
        session.commit()
        return failure_result


def run_dedup_now(*, updated_by: str | None = None) -> dict[str, Any]:
    with Session(engine) as session:
        return run_dedup_with_session(
            session,
            trigger_source="manual",
            updated_by=updated_by,
            advance_next_run=False,
        )


def run_due_scheduled_dedup() -> dict[str, Any] | None:
    with Session(engine) as session:
        if not _try_claim_xact_lock(session, DEDUP_SCHEDULER_LOCK_KEY):
            return None

        config = get_dedup_runtime_config(session)
        if not bool(config.get("enabled")):
            return None

        next_run_at = config.get("next_run_at")
        if next_run_at is None:
            ensure_dedup_next_run(session, updated_by="system")
            session.commit()
            return None

        if next_run_at > datetime.utcnow():
            return None

        return run_dedup_with_session(
            session,
            trigger_source="scheduled",
            updated_by="system",
            advance_next_run=True,
        )
