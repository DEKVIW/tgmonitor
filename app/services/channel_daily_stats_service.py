from __future__ import annotations

from datetime import date, datetime, timedelta
import threading
from typing import Any, Iterable

from sqlalchemy import func, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.models import ChannelDailyStat, Message, engine, ensure_runtime_storage_tables
from app.services.resource_ops.catalog import flatten_message_links


CHANNEL_DAILY_STATS_RETENTION_DAYS = 30

_retention_lock = threading.RLock()
_retention_pruned_on: date | None = None
_recent_backfill_lock = threading.RLock()
_recent_backfill_completed = False


def _normalize_channel_key(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_channel_title(channel_key: str, value: Any) -> str:
    text = str(value or "").strip()
    return text or channel_key


def _normalize_positive_ids(values: Iterable[int]) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw_value in values:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _safe_retention_days(value: int | None = None) -> int:
    return max(1, min(int(value or CHANNEL_DAILY_STATS_RETENTION_DAYS), CHANNEL_DAILY_STATS_RETENTION_DAYS))


def _retention_cutoff(keep_days: int) -> date:
    return datetime.now().date() - timedelta(days=keep_days - 1)


def _count_message_links(links: Any) -> int:
    try:
        return len(flatten_message_links(links))
    except Exception:
        return 0


def _build_stat_row(message: Message) -> tuple[tuple[date, str], dict[str, Any]] | None:
    timestamp = getattr(message, "timestamp", None)
    channel_key = _normalize_channel_key(getattr(message, "monitor_channel_key", None))
    if not isinstance(timestamp, datetime) or not channel_key:
        return None

    stat_date = timestamp.date()
    row_key = (stat_date, channel_key)
    config_id = getattr(message, "monitor_channel_config_id", None)
    return (
        row_key,
        {
            "stat_date": stat_date,
            "monitor_channel_config_id": int(config_id) if config_id is not None else None,
            "monitor_channel_key": channel_key,
            "monitor_channel_title": _normalize_channel_title(channel_key, getattr(message, "monitor_channel_title", None)),
            "message_count": 1,
            "link_count": _count_message_links(getattr(message, "links", None)),
            "last_message_at": timestamp,
        },
    )


def _collapse_messages(
    messages: Iterable[Message],
    *,
    allowed_pairs: set[tuple[date, str]] | None = None,
    cutoff_date: date | None = None,
) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[date, str], dict[str, Any]] = {}
    for message in messages:
        built = _build_stat_row(message)
        if built is None:
            continue
        row_key, row_payload = built
        if cutoff_date is not None and row_payload["stat_date"] < cutoff_date:
            continue
        if allowed_pairs is not None and row_key not in allowed_pairs:
            continue

        current = rows_by_key.get(row_key)
        if current is None:
            rows_by_key[row_key] = row_payload
            continue

        current["message_count"] += int(row_payload["message_count"] or 0)
        current["link_count"] += int(row_payload["link_count"] or 0)
        next_last_message_at = row_payload.get("last_message_at")
        if isinstance(next_last_message_at, datetime) and (
            current.get("last_message_at") is None or next_last_message_at > current["last_message_at"]
        ):
            current["last_message_at"] = next_last_message_at
            current["monitor_channel_title"] = row_payload["monitor_channel_title"]
        if current.get("monitor_channel_config_id") is None and row_payload.get("monitor_channel_config_id") is not None:
            current["monitor_channel_config_id"] = row_payload["monitor_channel_config_id"]

    return list(rows_by_key.values())


def _prune_channel_daily_stats(session: Session, *, keep_days: int = CHANNEL_DAILY_STATS_RETENTION_DAYS) -> None:
    global _retention_pruned_on

    today = datetime.now().date()
    with _retention_lock:
        if _retention_pruned_on == today:
            return

        cutoff = _retention_cutoff(_safe_retention_days(keep_days))
        (
            session.query(ChannelDailyStat)
            .filter(ChannelDailyStat.stat_date < cutoff)
            .delete(synchronize_session=False)
        )
        _retention_pruned_on = today


def _upsert_accumulate_rows(session: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    stmt = pg_insert(ChannelDailyStat.__table__).values(rows)
    excluded = stmt.excluded
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["stat_date", "monitor_channel_key"],
            set_={
                "monitor_channel_config_id": func.coalesce(
                    excluded.monitor_channel_config_id,
                    ChannelDailyStat.monitor_channel_config_id,
                ),
                "monitor_channel_title": func.coalesce(
                    func.nullif(excluded.monitor_channel_title, ""),
                    ChannelDailyStat.monitor_channel_title,
                ),
                "message_count": ChannelDailyStat.message_count + excluded.message_count,
                "link_count": ChannelDailyStat.link_count + excluded.link_count,
                "last_message_at": func.coalesce(
                    func.greatest(ChannelDailyStat.last_message_at, excluded.last_message_at),
                    ChannelDailyStat.last_message_at,
                    excluded.last_message_at,
                ),
                "updated_at": func.now(),
            },
        )
    )


def _replace_pairs(session: Session, normalized_pairs: set[tuple[date, str]], rows: list[dict[str, Any]]) -> None:
    if normalized_pairs:
        (
            session.query(ChannelDailyStat)
            .filter(tuple_(ChannelDailyStat.stat_date, ChannelDailyStat.monitor_channel_key).in_(list(normalized_pairs)))
            .delete(synchronize_session=False)
        )
    if rows:
        session.execute(ChannelDailyStat.__table__.insert(), rows)


def accumulate_channel_daily_stats_for_message_ids(
    session: Session,
    message_ids: Iterable[int],
    *,
    keep_days: int = CHANNEL_DAILY_STATS_RETENTION_DAYS,
) -> int:
    ensure_runtime_storage_tables()

    normalized_ids = _normalize_positive_ids(message_ids)
    if not normalized_ids:
        return 0

    cutoff = _retention_cutoff(_safe_retention_days(keep_days))
    messages = (
        session.query(Message)
        .filter(Message.id.in_(normalized_ids))
        .all()
    )
    rows = _collapse_messages(messages, cutoff_date=cutoff)
    _upsert_accumulate_rows(session, rows)
    _prune_channel_daily_stats(session, keep_days=keep_days)
    return len(rows)


def rebuild_channel_daily_stats_for_pairs(
    session: Session,
    pairs: Iterable[tuple[date, str]],
    *,
    keep_days: int = CHANNEL_DAILY_STATS_RETENTION_DAYS,
) -> int:
    ensure_runtime_storage_tables()

    cutoff = _retention_cutoff(_safe_retention_days(keep_days))
    normalized_pairs = {
        (stat_date, channel_key)
        for stat_date, raw_key in pairs
        for channel_key in [_normalize_channel_key(raw_key)]
        if isinstance(stat_date, date) and channel_key and stat_date >= cutoff
    }
    if not normalized_pairs:
        _prune_channel_daily_stats(session, keep_days=keep_days)
        return 0

    min_date = min(stat_date for stat_date, _ in normalized_pairs)
    max_date = max(stat_date for stat_date, _ in normalized_pairs)
    channel_keys = sorted({channel_key for _, channel_key in normalized_pairs})
    start_dt = datetime.combine(min_date, datetime.min.time())
    end_dt = datetime.combine(max_date + timedelta(days=1), datetime.min.time())
    messages = (
        session.query(Message)
        .filter(
            Message.monitor_channel_key.in_(channel_keys),
            Message.timestamp >= start_dt,
            Message.timestamp < end_dt,
        )
        .all()
    )
    rows = _collapse_messages(messages, allowed_pairs=normalized_pairs, cutoff_date=cutoff)
    _replace_pairs(session, normalized_pairs, rows)
    _prune_channel_daily_stats(session, keep_days=keep_days)
    return len(rows)


def rebuild_recent_channel_daily_stats_window(
    session: Session,
    *,
    days: int = CHANNEL_DAILY_STATS_RETENTION_DAYS,
) -> int:
    ensure_runtime_storage_tables()

    safe_days = _safe_retention_days(days)
    cutoff = _retention_cutoff(safe_days)
    start_dt = datetime.combine(cutoff, datetime.min.time())
    end_dt = datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time())
    messages = (
        session.query(Message)
        .filter(
            Message.monitor_channel_key.isnot(None),
            Message.timestamp >= start_dt,
            Message.timestamp < end_dt,
        )
        .all()
    )
    rows = _collapse_messages(messages, cutoff_date=cutoff)
    (
        session.query(ChannelDailyStat)
        .filter(ChannelDailyStat.stat_date >= cutoff)
        .delete(synchronize_session=False)
    )
    if rows:
        session.execute(ChannelDailyStat.__table__.insert(), rows)
    _prune_channel_daily_stats(session, keep_days=safe_days)
    return len(rows)


def backfill_recent_channel_daily_stats_window_once(
    *,
    days: int = CHANNEL_DAILY_STATS_RETENTION_DAYS,
) -> bool:
    global _recent_backfill_completed

    if _recent_backfill_completed:
        return False

    with _recent_backfill_lock:
        if _recent_backfill_completed:
            return False
        with Session(engine) as session:
            rebuild_recent_channel_daily_stats_window(session, days=days)
            session.commit()
        _recent_backfill_completed = True
        return True
