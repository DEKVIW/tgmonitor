from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Message

SELECTION_MODE_TIME_RANGE = "time_range"
SELECTION_MODE_SMART_COUNT = "smart_count"
TRAVERSAL_NEWEST_FIRST = "newest_first"
TRAVERSAL_OLDEST_FIRST = "oldest_first"
ALLOWED_SELECTION_MODES = {SELECTION_MODE_TIME_RANGE, SELECTION_MODE_SMART_COUNT}
ALLOWED_TRAVERSAL_ORDERS = {TRAVERSAL_NEWEST_FIRST, TRAVERSAL_OLDEST_FIRST}
MESSAGE_PAGE_SIZE = 200


def extract_urls_from_links(links: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(links, str):
        urls.append(links)
    elif isinstance(links, dict):
        for value in links.values():
            urls.extend(extract_urls_from_links(value))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict) and "url" in item:
                urls.append(str(item["url"]))
            else:
                urls.extend(extract_urls_from_links(item))
    return [url.strip() for url in urls if isinstance(url, str) and url.strip()]


def _normalize_selection_mode(value: str | None) -> str:
    normalized = str(value or SELECTION_MODE_SMART_COUNT).strip().lower()
    if normalized not in ALLOWED_SELECTION_MODES:
        raise ValueError("selection_mode must be smart_count or time_range")
    return normalized


def _normalize_traversal_order(value: str | None) -> str:
    normalized = str(value or TRAVERSAL_NEWEST_FIRST).strip().lower()
    if normalized not in ALLOWED_TRAVERSAL_ORDERS:
        raise ValueError("direction must be newest_first or oldest_first")
    return normalized


def _parse_date_input(value: str | None, field_name: str) -> date:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from exc


def _to_range_datetimes(range_start: str, range_end: str) -> tuple[datetime, datetime]:
    start_date = _parse_date_input(range_start, "range_start")
    end_date = _parse_date_input(range_end, "range_end")
    if end_date < start_date:
        raise ValueError("range_end must be on or after range_start")
    start_time = datetime.combine(start_date, datetime.min.time())
    end_time = datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)
    return start_time, end_time


def _message_query(
    session: Session,
    *,
    direction: str,
    cursor_message_id: int | None = None,
    min_message_id: int | None = None,
    max_message_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    query = session.query(Message).filter(Message.links.isnot(None))
    if min_message_id is not None:
        query = query.filter(Message.id > int(min_message_id))
    if max_message_id is not None:
        query = query.filter(Message.id <= int(max_message_id))
    if start_time is not None:
        query = query.filter(Message.timestamp >= start_time)
    if end_time is not None:
        query = query.filter(Message.timestamp < end_time)

    if direction == TRAVERSAL_NEWEST_FIRST:
        if cursor_message_id is not None:
            query = query.filter(Message.id < cursor_message_id)
        return query.order_by(Message.id.desc())

    if cursor_message_id is not None:
        query = query.filter(Message.id > cursor_message_id)
    return query.order_by(Message.id.asc())


def _build_scope_label(
    *,
    selection_mode: str,
    direction: str | None,
    requested_target_link_count: int | None,
    range_start: str | None,
    range_end: str | None,
    first_message_time: datetime | None,
    last_message_time: datetime | None,
) -> str:
    if selection_mode == SELECTION_MODE_TIME_RANGE:
        return f"{range_start} 至 {range_end}"

    direction_label = "最新" if direction == TRAVERSAL_NEWEST_FIRST else "最早"
    if first_message_time is None or last_message_time is None:
        return f"{direction_label}约 {requested_target_link_count or 0} 链接"

    start_label = min(first_message_time, last_message_time).strftime("%Y-%m-%d")
    end_label = max(first_message_time, last_message_time).strftime("%Y-%m-%d")
    return f"{direction_label}约 {requested_target_link_count or 0} 链接 · {start_label} 至 {end_label}"


def _serialize_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _empty_preview(
    *,
    selection_mode: str,
    task_link_limit: int,
    direction: str | None = None,
    requested_target_link_count: int | None = None,
    range_start: str | None = None,
    range_end: str | None = None,
) -> dict[str, Any]:
    return {
        "selection_mode": selection_mode,
        "direction": direction,
        "scope_label": _build_scope_label(
            selection_mode=selection_mode,
            direction=direction,
            requested_target_link_count=requested_target_link_count,
            range_start=range_start,
            range_end=range_end,
            first_message_time=None,
            last_message_time=None,
        ),
        "estimated_messages": 0,
        "estimated_links": 0,
        "range_start": range_start,
        "range_end": range_end,
        "first_message_time": None,
        "last_message_time": None,
        "requested_target_link_count": requested_target_link_count,
        "effective_target_link_count": requested_target_link_count,
        "task_link_limit": task_link_limit,
        "recommended_batch_count": 0,
        "recommended_target_link_count": min(task_link_limit, requested_target_link_count or task_link_limit),
        "can_start": False,
        "exceeds_task_limit": False,
        "warnings": ["当前范围内没有可检测的网盘链接。"],
        "message_ids": [],
        "link_records": [],
        "next_cursor_message_id": None,
        "has_more_messages": False,
    }


def get_link_check_dataset_summary(session: Session) -> dict[str, Any]:
    query = session.query(Message).filter(Message.links.isnot(None)).order_by(Message.id.asc())
    total_messages = 0
    total_links = 0
    first_message_time: datetime | None = None
    last_message_time: datetime | None = None

    for message in query.yield_per(300):
        urls = extract_urls_from_links(message.links)
        if not urls:
            continue
        total_messages += 1
        total_links += len(urls)
        if first_message_time is None:
            first_message_time = message.timestamp
        last_message_time = message.timestamp

    return {
        "total_messages_with_links": total_messages,
        "total_links": total_links,
        "first_message_time": _serialize_timestamp(first_message_time),
        "last_message_time": _serialize_timestamp(last_message_time),
    }


def get_latest_message_id_with_links(session: Session) -> int | None:
    latest_message = session.query(Message.id).filter(Message.links.isnot(None)).order_by(Message.id.desc()).first()
    if latest_message is None:
        return None
    return int(latest_message[0])


def preview_time_range_selection(
    session: Session,
    *,
    range_start: str,
    range_end: str,
    task_link_limit: int,
) -> dict[str, Any]:
    start_time, end_time = _to_range_datetimes(range_start, range_end)
    query = (
        session.query(Message)
        .filter(
            Message.links.isnot(None),
            Message.timestamp >= start_time,
            Message.timestamp < end_time,
        )
        .order_by(Message.id.desc())
    )

    message_ids: list[int] = []
    link_records: list[dict[str, Any]] = []
    first_message_time: datetime | None = None
    last_message_time: datetime | None = None

    for message in query.yield_per(300):
        urls = extract_urls_from_links(message.links)
        if not urls:
            continue
        message_ids.append(int(message.id))
        if first_message_time is None:
            first_message_time = message.timestamp
        last_message_time = message.timestamp
        for url in urls:
            link_records.append({"message_id": int(message.id), "url": url})

    if not link_records:
        return _empty_preview(
            selection_mode=SELECTION_MODE_TIME_RANGE,
            task_link_limit=task_link_limit,
            range_start=range_start,
            range_end=range_end,
        )

    estimated_links = len(link_records)
    recommended_batch_count = max(1, math.ceil(estimated_links / max(1, task_link_limit)))
    recommended_target_link_count = max(1, math.ceil(estimated_links / recommended_batch_count))
    warnings: list[str] = []
    exceeds_task_limit = estimated_links > task_link_limit
    if exceeds_task_limit:
        warnings.append(
            f"当前时间范围约有 {estimated_links} 个链接，超过单任务上限 {task_link_limit}，建议拆成 {recommended_batch_count} 批。"
        )

    return {
        "selection_mode": SELECTION_MODE_TIME_RANGE,
        "direction": None,
        "scope_label": _build_scope_label(
            selection_mode=SELECTION_MODE_TIME_RANGE,
            direction=None,
            requested_target_link_count=None,
            range_start=range_start,
            range_end=range_end,
            first_message_time=first_message_time,
            last_message_time=last_message_time,
        ),
        "estimated_messages": len(message_ids),
        "estimated_links": estimated_links,
        "range_start": range_start,
        "range_end": range_end,
        "first_message_time": _serialize_timestamp(first_message_time),
        "last_message_time": _serialize_timestamp(last_message_time),
        "requested_target_link_count": None,
        "effective_target_link_count": estimated_links,
        "task_link_limit": task_link_limit,
        "recommended_batch_count": recommended_batch_count,
        "recommended_target_link_count": min(task_link_limit, recommended_target_link_count),
        "can_start": not exceeds_task_limit,
        "exceeds_task_limit": exceeds_task_limit,
        "warnings": warnings,
        "message_ids": message_ids,
        "link_records": link_records,
        "next_cursor_message_id": None,
        "has_more_messages": False,
    }


def preview_smart_count_selection(
    session: Session,
    *,
    target_link_count: int,
    direction: str,
    task_link_limit: int,
    cursor_message_id: int | None = None,
    min_message_id: int | None = None,
    max_message_id: int | None = None,
) -> dict[str, Any]:
    normalized_direction = _normalize_traversal_order(direction)
    requested_target_link_count = int(target_link_count or 0)
    if requested_target_link_count <= 0:
        raise ValueError("target_link_count must be greater than 0")

    if requested_target_link_count > task_link_limit:
        return {
            **_empty_preview(
                selection_mode=SELECTION_MODE_SMART_COUNT,
                task_link_limit=task_link_limit,
                direction=normalized_direction,
                requested_target_link_count=requested_target_link_count,
            ),
            "warnings": [
                f"目标链接数 {requested_target_link_count} 超过单任务上限 {task_link_limit}，请降低后再试。",
            ],
            "recommended_target_link_count": task_link_limit,
            "exceeds_task_limit": True,
        }

    message_ids: list[int] = []
    link_records: list[dict[str, Any]] = []
    first_message_time: datetime | None = None
    last_message_time: datetime | None = None
    query_cursor = cursor_message_id
    last_selected_message_id: int | None = None
    has_more_messages = False

    while True:
        page = _message_query(
            session,
            direction=normalized_direction,
            cursor_message_id=query_cursor,
            min_message_id=min_message_id,
            max_message_id=max_message_id,
        ).limit(MESSAGE_PAGE_SIZE).all()
        if not page:
            break

        query_cursor = int(page[-1].id)
        reached_target = False
        for message in page:
            urls = extract_urls_from_links(message.links)
            if not urls:
                continue
            message_ids.append(int(message.id))
            last_selected_message_id = int(message.id)
            if first_message_time is None:
                first_message_time = message.timestamp
            last_message_time = message.timestamp
            for url in urls:
                link_records.append({"message_id": int(message.id), "url": url})
            if len(link_records) >= requested_target_link_count:
                reached_target = True
                break

        if reached_target:
            break

    if not link_records:
        return _empty_preview(
            selection_mode=SELECTION_MODE_SMART_COUNT,
            task_link_limit=task_link_limit,
            direction=normalized_direction,
            requested_target_link_count=requested_target_link_count,
        )

    if last_selected_message_id is not None:
        has_more_messages = (
            _message_query(
                session,
                direction=normalized_direction,
                cursor_message_id=last_selected_message_id,
                min_message_id=min_message_id,
                max_message_id=max_message_id,
            )
            .limit(1)
            .first()
            is not None
        )

    estimated_links = len(link_records)
    warnings: list[str] = []
    exceeds_task_limit = estimated_links > task_link_limit
    if exceeds_task_limit:
        warnings.append(
            f"本批实际命中了 {estimated_links} 个链接，超过单任务上限 {task_link_limit}，请调小目标链接数。"
        )

    return {
        "selection_mode": SELECTION_MODE_SMART_COUNT,
        "direction": normalized_direction,
        "scope_label": _build_scope_label(
            selection_mode=SELECTION_MODE_SMART_COUNT,
            direction=normalized_direction,
            requested_target_link_count=requested_target_link_count,
            range_start=None,
            range_end=None,
            first_message_time=first_message_time,
            last_message_time=last_message_time,
        ),
        "estimated_messages": len(message_ids),
        "estimated_links": estimated_links,
        "range_start": None,
        "range_end": None,
        "first_message_time": _serialize_timestamp(first_message_time),
        "last_message_time": _serialize_timestamp(last_message_time),
        "requested_target_link_count": requested_target_link_count,
        "effective_target_link_count": estimated_links,
        "task_link_limit": task_link_limit,
        "recommended_batch_count": 1,
        "recommended_target_link_count": requested_target_link_count,
        "can_start": not exceeds_task_limit,
        "exceeds_task_limit": exceeds_task_limit,
        "warnings": warnings,
        "message_ids": message_ids,
        "link_records": link_records,
        "next_cursor_message_id": last_selected_message_id if has_more_messages else None,
        "has_more_messages": has_more_messages,
    }


def build_manual_selection_preview(
    session: Session,
    *,
    selection_mode: str,
    task_link_limit: int,
    range_start: str | None = None,
    range_end: str | None = None,
    target_link_count: int | None = None,
    direction: str | None = None,
) -> dict[str, Any]:
    normalized_mode = _normalize_selection_mode(selection_mode)
    if normalized_mode == SELECTION_MODE_TIME_RANGE:
        if not range_start or not range_end:
            raise ValueError("range_start and range_end are required for time_range mode")
        return preview_time_range_selection(
            session,
            range_start=range_start,
            range_end=range_end,
            task_link_limit=task_link_limit,
        )

    return preview_smart_count_selection(
        session,
        target_link_count=int(target_link_count or 0),
        direction=direction or TRAVERSAL_NEWEST_FIRST,
        task_link_limit=task_link_limit,
    )


def build_manual_selection_snapshot(
    session: Session,
    *,
    selection_mode: str,
    task_link_limit: int,
    range_start: str | None = None,
    range_end: str | None = None,
    target_link_count: int | None = None,
    direction: str | None = None,
) -> dict[str, Any]:
    preview = build_manual_selection_preview(
        session,
        selection_mode=selection_mode,
        task_link_limit=task_link_limit,
        range_start=range_start,
        range_end=range_end,
        target_link_count=target_link_count,
        direction=direction,
    )
    if not preview["can_start"]:
        warning = preview["warnings"][0] if preview["warnings"] else "当前条件下无法启动检测任务。"
        raise ValueError(warning)
    return preview


def build_plan_batch_selection_snapshot(
    session: Session,
    *,
    batch_link_target: int,
    direction: str,
    task_link_limit: int,
    cursor_message_id: int | None = None,
    min_message_id: int | None = None,
    max_message_id: int | None = None,
) -> dict[str, Any]:
    return preview_smart_count_selection(
        session,
        target_link_count=min(task_link_limit, batch_link_target),
        direction=direction,
        task_link_limit=task_link_limit,
        cursor_message_id=cursor_message_id,
        min_message_id=min_message_id,
        max_message_id=max_message_id,
    )
