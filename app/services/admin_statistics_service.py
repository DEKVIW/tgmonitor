from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Message, MessageLinkRef, ensure_message_monitor_source_columns


def _safe_days(value: int | None) -> int:
    return max(7, min(int(value or 14), 30))


def _build_date_keys(days: int) -> list[date]:
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    return [start + timedelta(days=offset) for offset in range(days)]


def _row_key(config_id: int | None, channel_key: str | None) -> str:
    if config_id is not None and int(config_id) > 0:
        return f"config:{int(config_id)}"
    return f"key:{(channel_key or '').strip()}"


def get_admin_channel_matrix(session: Session, *, days: int = 14) -> dict[str, Any]:
    ensure_message_monitor_source_columns()

    safe_days = _safe_days(days)
    dates = _build_date_keys(safe_days)
    if not dates:
        return {
            "days": safe_days,
            "dates": [],
            "rows": [],
            "available_since": None,
            "max_daily_messages": 0,
        }

    start_dt = datetime.combine(dates[0], time.min)
    date_labels = [item.isoformat() for item in dates]

    available_since_value = (
        session.query(func.min(Message.timestamp))
        .filter(Message.monitor_channel_key.isnot(None))
        .scalar()
    )

    message_rows = (
        session.query(
            Message.monitor_channel_config_id.label("config_id"),
            Message.monitor_channel_key.label("channel_key"),
            Message.monitor_channel_title.label("channel_title"),
            func.date(Message.timestamp).label("stat_date"),
            func.max(Message.timestamp).label("last_message_at"),
            func.count(Message.id).label("message_count"),
        )
        .filter(
            Message.monitor_channel_key.isnot(None),
            Message.timestamp >= start_dt,
        )
        .group_by(
            Message.monitor_channel_config_id,
            Message.monitor_channel_key,
            Message.monitor_channel_title,
            func.date(Message.timestamp),
        )
        .all()
    )

    link_rows = (
        session.query(
            Message.monitor_channel_config_id.label("config_id"),
            Message.monitor_channel_key.label("channel_key"),
            Message.monitor_channel_title.label("channel_title"),
            func.date(Message.timestamp).label("stat_date"),
            func.max(Message.timestamp).label("last_message_at"),
            func.count(MessageLinkRef.id).label("link_count"),
        )
        .join(MessageLinkRef, MessageLinkRef.message_id == Message.id)
        .filter(
            Message.monitor_channel_key.isnot(None),
            Message.timestamp >= start_dt,
        )
        .group_by(
            Message.monitor_channel_config_id,
            Message.monitor_channel_key,
            Message.monitor_channel_title,
            func.date(Message.timestamp),
        )
        .all()
    )

    rows_by_key: dict[str, dict[str, Any]] = {}

    def ensure_row(config_id: int | None, channel_key: str | None, channel_title: str | None) -> dict[str, Any]:
        normalized_key = (channel_key or "").strip()
        key = _row_key(config_id, normalized_key)
        row = rows_by_key.get(key)
        if row is not None:
            return row
        row = {
            "row_key": key,
            "monitor_channel_config_id": int(config_id) if config_id is not None else None,
            "monitor_channel_key": normalized_key,
            "monitor_channel_title": (channel_title or "").strip() or normalized_key or "Unknown",
            "total_messages": 0,
            "total_links": 0,
            "message_counts": {label: 0 for label in date_labels},
            "link_counts": {label: 0 for label in date_labels},
            "trend": [0 for _ in date_labels],
            "_last_message_at": None,
        }
        rows_by_key[key] = row
        return row

    for raw_row in message_rows:
        stat_date = raw_row.stat_date.isoformat() if raw_row.stat_date is not None else None
        if not stat_date or stat_date not in date_labels:
            continue
        row = ensure_row(raw_row.config_id, raw_row.channel_key, raw_row.channel_title)
        row["message_counts"][stat_date] += int(raw_row.message_count or 0)
        row["total_messages"] += int(raw_row.message_count or 0)
        last_message_at = raw_row.last_message_at
        if last_message_at is not None and (row["_last_message_at"] is None or last_message_at > row["_last_message_at"]):
            row["_last_message_at"] = last_message_at
            row["monitor_channel_title"] = (raw_row.channel_title or "").strip() or row["monitor_channel_key"] or row["monitor_channel_title"]

    for raw_row in link_rows:
        stat_date = raw_row.stat_date.isoformat() if raw_row.stat_date is not None else None
        if not stat_date or stat_date not in date_labels:
            continue
        row = ensure_row(raw_row.config_id, raw_row.channel_key, raw_row.channel_title)
        row["link_counts"][stat_date] += int(raw_row.link_count or 0)
        row["total_links"] += int(raw_row.link_count or 0)
        last_message_at = raw_row.last_message_at
        if last_message_at is not None and (row["_last_message_at"] is None or last_message_at > row["_last_message_at"]):
            row["_last_message_at"] = last_message_at
            row["monitor_channel_title"] = (raw_row.channel_title or "").strip() or row["monitor_channel_key"] or row["monitor_channel_title"]

    max_daily_messages = 0
    rows: list[dict[str, Any]] = []
    for row in rows_by_key.values():
        trend = [int(row["message_counts"].get(label) or 0) for label in date_labels]
        row["trend"] = trend
        if trend:
            max_daily_messages = max(max_daily_messages, max(trend))
        rows.append(
            {
                "row_key": row["row_key"],
                "monitor_channel_config_id": row["monitor_channel_config_id"],
                "monitor_channel_key": row["monitor_channel_key"],
                "monitor_channel_title": row["monitor_channel_title"],
                "total_messages": int(row["total_messages"]),
                "total_links": int(row["total_links"]),
                "message_counts": row["message_counts"],
                "link_counts": row["link_counts"],
                "trend": trend,
            }
        )

    rows.sort(
        key=lambda item: (
            int(item.get("total_messages") or 0),
            int(item.get("total_links") or 0),
            str(item.get("monitor_channel_title") or item.get("monitor_channel_key") or "").lower(),
        ),
        reverse=True,
    )

    available_since = None
    if isinstance(available_since_value, datetime):
        available_since = available_since_value.date().isoformat()

    return {
        "days": safe_days,
        "dates": date_labels,
        "rows": rows,
        "available_since": available_since,
        "max_daily_messages": int(max_daily_messages),
    }
