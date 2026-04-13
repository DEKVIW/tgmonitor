from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session, aliased

from app.models.models import (
    LinkCheckDetails,
    LinkTarget,
    Message,
    MessageLinkRef,
    ResourceWork,
    ResourceWorkBinding,
)

from .accounts import get_recommended_accounts_by_platform
from .constants import (
    ALLOWED_TRANSFER_HEALTH_FILTERS,
    ALLOWED_TRANSFER_DIRECTIONS,
    ALLOWED_TRANSFER_SELECTION_MODES,
    TRANSFER_LINK_HEALTH_LABELS,
    normalize_transfer_platform,
)


PAN_TRANSFER_PREVIEW_MAX_MESSAGE_SCAN = 3000


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _normalize_direction(value: Any) -> str:
    normalized = _normalize_text(value or "newest_first", max_length=32).lower()
    if normalized not in ALLOWED_TRANSFER_DIRECTIONS:
        raise ValueError("direction must be newest_first or oldest_first")
    return normalized


def _normalize_selection_mode(value: Any) -> str:
    normalized = _normalize_text(value or "recent_messages", max_length=32).lower()
    if normalized not in ALLOWED_TRANSFER_SELECTION_MODES:
        raise ValueError("selection_mode must be recent_messages or time_range")
    return normalized


def _normalize_health_filter(value: Any, *, only_healthy: bool = False) -> str:
    if bool(only_healthy):
        return "healthy_only"
    normalized = _normalize_text(value or "all", max_length=32).lower()
    if normalized not in ALLOWED_TRANSFER_HEALTH_FILTERS:
        raise ValueError("health_filter must be one of: all, healthy_only, exclude_invalid")
    return normalized


def _normalize_platform_filters(values: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        platform = normalize_transfer_platform(raw_value)
        if platform in seen:
            continue
        seen.add(platform)
        normalized.append(platform)
    return normalized


def _parse_date(value: Any, *, field_name: str) -> date:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from exc


def _classify_link_health(is_valid: bool | None) -> str:
    if is_valid is True:
        return "healthy"
    if is_valid is False:
        return "invalid"
    return "unknown"


def _build_manual_candidate_items(
    session: Session,
    *,
    selected_message_ids: list[int] | None = None,
    link_target_ids: list[int] | None = None,
    platforms: list[str] | None = None,
    health_filter: str = "all",
) -> list[dict[str, Any]]:
    normalized_link_target_ids = [int(value) for value in (link_target_ids or []) if int(value) > 0]
    normalized_platforms = list(platforms or [])

    ref_summary_query = session.query(
        MessageLinkRef.link_target_id.label("link_target_id"),
        func.count(distinct(MessageLinkRef.message_id)).label("impact_message_count"),
        func.count(MessageLinkRef.id).label("source_ref_count"),
        func.max(MessageLinkRef.message_timestamp).label("latest_message_time"),
    )
    latest_ref_id_query = session.query(
        MessageLinkRef.link_target_id.label("link_target_id"),
        func.max(MessageLinkRef.id).label("latest_ref_id"),
    )
    if selected_message_ids:
        ref_summary_query = ref_summary_query.filter(MessageLinkRef.message_id.in_(selected_message_ids))
        latest_ref_id_query = latest_ref_id_query.filter(MessageLinkRef.message_id.in_(selected_message_ids))
    if normalized_link_target_ids:
        ref_summary_query = ref_summary_query.filter(MessageLinkRef.link_target_id.in_(normalized_link_target_ids))
        latest_ref_id_query = latest_ref_id_query.filter(MessageLinkRef.link_target_id.in_(normalized_link_target_ids))
    ref_summary_subquery = ref_summary_query.group_by(MessageLinkRef.link_target_id).subquery()
    latest_ref_id_subquery = latest_ref_id_query.group_by(MessageLinkRef.link_target_id).subquery()

    latest_ref = aliased(MessageLinkRef)
    latest_message = aliased(Message)
    latest_health_id_subquery = (
        session.query(
            LinkCheckDetails.normalized_url.label("normalized_url"),
            func.max(LinkCheckDetails.id).label("latest_detail_id"),
        )
        .filter(LinkCheckDetails.normalized_url.isnot(None))
        .group_by(LinkCheckDetails.normalized_url)
        .subquery()
    )
    latest_health = aliased(LinkCheckDetails)
    binding = aliased(ResourceWorkBinding)
    work = aliased(ResourceWork)

    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.platform.label("platform"),
            LinkTarget.original_url.label("original_url"),
            LinkTarget.share_key.label("share_key"),
            ref_summary_subquery.c.impact_message_count.label("impact_message_count"),
            ref_summary_subquery.c.source_ref_count.label("source_ref_count"),
            ref_summary_subquery.c.latest_message_time.label("latest_message_time"),
            latest_ref.display_text.label("display_text"),
            latest_message.title.label("latest_message_title"),
            latest_message.description.label("latest_message_description"),
            latest_health.is_valid.label("latest_is_valid"),
            latest_health.error_reason.label("latest_health_reason"),
            work.canonical_title.label("work_title"),
        )
        .join(ref_summary_subquery, ref_summary_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref_id_subquery, latest_ref_id_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_id_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .outerjoin(latest_health_id_subquery, latest_health_id_subquery.c.normalized_url == LinkTarget.normalized_url)
        .outerjoin(latest_health, latest_health.id == latest_health_id_subquery.c.latest_detail_id)
        .outerjoin(binding, binding.link_target_id == LinkTarget.id)
        .outerjoin(work, work.id == binding.work_id)
    )
    if normalized_platforms:
        query = query.filter(LinkTarget.platform.in_(normalized_platforms))
    if normalized_link_target_ids:
        query = query.filter(LinkTarget.id.in_(normalized_link_target_ids))

    account_map = get_recommended_accounts_by_platform(session)
    items: list[dict[str, Any]] = []
    for row in query.all():
        latest_link_health = _classify_link_health(row.latest_is_valid)
        if health_filter == "healthy_only" and latest_link_health != "healthy":
            continue
        if health_filter == "exclude_invalid" and latest_link_health == "invalid":
            continue
        recommended_account = account_map.get(row.platform)
        short_title = (
            _normalize_text(row.work_title, max_length=255)
            or _normalize_text(row.latest_message_title, max_length=255)
            or _normalize_text(row.display_text, max_length=255)
            or _normalize_text(row.latest_message_description, max_length=255)
            or _normalize_text(row.share_key, max_length=255)
            or f"资源 {int(row.link_target_id)}"
        )
        items.append(
            {
                "link_target_id": int(row.link_target_id),
                "platform": _normalize_text(row.platform, max_length=64),
                "short_title": short_title,
                "original_url": _normalize_text(row.original_url),
                "share_key": _normalize_text(row.share_key, max_length=255) or None,
                "latest_link_health": latest_link_health,
                "latest_link_health_label": TRANSFER_LINK_HEALTH_LABELS[latest_link_health],
                "latest_link_health_reason": _normalize_text(row.latest_health_reason, max_length=255) or None,
                "impact_message_count": int(row.impact_message_count or 0),
                "source_ref_count": int(row.source_ref_count or 0),
                "latest_message_time": row.latest_message_time,
                "latest_message_title": _normalize_text(row.latest_message_title, max_length=255) or None,
                "work_title": _normalize_text(row.work_title, max_length=255) or None,
                "recommended_account_id": recommended_account.get("id") if recommended_account else None,
                "recommended_account_name": recommended_account.get("account_name") if recommended_account else None,
            }
        )

    items.sort(
        key=lambda item: (
            -int(item["impact_message_count"]),
            -(item["latest_message_time"].timestamp()) if item["latest_message_time"] is not None else float("inf"),
            int(item["link_target_id"]),
        ),
    )
    return items


def collect_manual_pan_transfer_candidates_for_link_targets(
    session: Session,
    *,
    link_target_ids: list[int],
) -> list[dict[str, Any]]:
    return _build_manual_candidate_items(
        session,
        link_target_ids=link_target_ids,
        platforms=[],
        health_filter="all",
    )


def _collect_selected_message_ids(session: Session, payload: dict[str, Any]) -> tuple[list[int], dict[str, Any]]:
    selection_mode = _normalize_selection_mode(payload.get("selection_mode"))
    direction = _normalize_direction(payload.get("direction"))
    order_column = Message.id.desc() if direction == "newest_first" else Message.id.asc()
    query = session.query(Message.id).filter(Message.links.isnot(None))
    summary: dict[str, Any] = {
        "selection_mode": selection_mode,
        "direction": direction,
        "requested_message_count": None,
        "effective_message_count": 0,
        "truncated": False,
        "range_start": None,
        "range_end": None,
    }

    if selection_mode == "recent_messages":
        try:
            requested_count = int(payload.get("recent_message_count") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("recent_message_count must be an integer") from exc
        if requested_count <= 0 or requested_count > PAN_TRANSFER_PREVIEW_MAX_MESSAGE_SCAN:
            raise ValueError(f"recent_message_count must be between 1 and {PAN_TRANSFER_PREVIEW_MAX_MESSAGE_SCAN}")
        rows = query.order_by(order_column).limit(requested_count).all()
        message_ids = [int(message_id) for (message_id,) in rows]
        summary["requested_message_count"] = requested_count
        summary["effective_message_count"] = len(message_ids)
        return message_ids, summary

    range_start = _parse_date(payload.get("range_start"), field_name="range_start")
    range_end = _parse_date(payload.get("range_end"), field_name="range_end")
    if range_end < range_start:
        raise ValueError("range_end must be on or after range_start")
    start_dt = datetime.combine(range_start, datetime.min.time())
    end_dt = datetime.combine(range_end, datetime.min.time()) + timedelta(days=1)
    scoped_query = query.filter(Message.timestamp >= start_dt, Message.timestamp < end_dt)
    total_count = int(scoped_query.count() or 0)
    rows = scoped_query.order_by(order_column).limit(PAN_TRANSFER_PREVIEW_MAX_MESSAGE_SCAN).all()
    message_ids = [int(message_id) for (message_id,) in rows]
    summary["range_start"] = range_start.isoformat()
    summary["range_end"] = range_end.isoformat()
    summary["requested_message_count"] = total_count
    summary["effective_message_count"] = len(message_ids)
    summary["truncated"] = total_count > len(message_ids)
    return message_ids, summary


def collect_manual_pan_transfer_candidates(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    selected_message_ids, selection_summary = _collect_selected_message_ids(session, payload)
    platforms = _normalize_platform_filters(payload.get("platforms"))
    health_filter = _normalize_health_filter(payload.get("health_filter"), only_healthy=bool(payload.get("only_healthy")))
    only_healthy = health_filter == "healthy_only"

    empty_payload = {
        **selection_summary,
        "platforms": platforms,
        "health_filter": health_filter,
        "only_healthy": only_healthy,
        "matched_link_ref_count": 0,
        "unique_link_target_count": 0,
        "healthy_count": 0,
        "invalid_count": 0,
        "unknown_count": 0,
        "total": 0,
        "can_start": False,
        "items": [],
    }
    if not selected_message_ids:
        return empty_payload

    items = _build_manual_candidate_items(
        session,
        selected_message_ids=selected_message_ids,
        platforms=platforms,
        health_filter=health_filter,
    )

    healthy_count = sum(1 for item in items if item["latest_link_health"] == "healthy")
    invalid_count = sum(1 for item in items if item["latest_link_health"] == "invalid")
    unknown_count = sum(1 for item in items if item["latest_link_health"] == "unknown")

    return {
        **selection_summary,
        "platforms": platforms,
        "health_filter": health_filter,
        "only_healthy": only_healthy,
        "matched_link_ref_count": sum(int(item["source_ref_count"]) for item in items),
        "unique_link_target_count": len(items),
        "healthy_count": healthy_count,
        "invalid_count": invalid_count,
        "unknown_count": unknown_count,
        "total": len(items),
        "can_start": bool(items),
        "items": items,
    }


def preview_manual_pan_transfer_selection(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    page = max(1, int(payload.get("page") or 1))
    page_size = int(payload.get("page_size") or 50)
    if page_size < 1 or page_size > 200:
        raise ValueError("page_size must be between 1 and 200")

    result = collect_manual_pan_transfer_candidates(session, payload)
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    return {
        **result,
        "page": page,
        "page_size": page_size,
        "items": list(result.get("items") or [])[start_index:end_index],
    }
