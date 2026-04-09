from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import String, case, cast, distinct, func, or_
from sqlalchemy.orm import Session, aliased

from app.models.models import LinkClickEvent, LinkTarget, LinkTargetDailyStat, Message, MessageLinkRef
from app.services.resource_ops.catalog import get_catalog_sync_status


DEFAULT_LOOKBACK_DAYS = 30


def _utcnow() -> datetime:
    return datetime.utcnow()


def _start_date(days: int) -> date:
    safe_days = max(1, min(int(days or DEFAULT_LOOKBACK_DAYS), 90))
    return date.today() - timedelta(days=safe_days - 1)


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_keyword(value: str | None) -> str | None:
    normalized = " ".join((value or "").split()).strip().lower()
    if not normalized:
        return None
    return normalized[:120]


def _build_session_identity_expr():
    return func.coalesce(
        LinkClickEvent.session_key,
        case(
            (LinkClickEvent.user_id.isnot(None), func.concat("user:", cast(LinkClickEvent.user_id, String))),
            else_=None,
        ),
        case(
            (LinkClickEvent.event_token.isnot(None), func.concat("event:", LinkClickEvent.event_token)),
            else_=None,
        ),
        func.concat("row:", cast(LinkClickEvent.id, String)),
    )


def _compute_heat_metrics(item: dict[str, Any]) -> dict[str, Any]:
    clicks_1d = _to_int(item.get("clicks_1d"))
    clicks_3d = _to_int(item.get("clicks_3d"))
    clicks_7d = _to_int(item.get("clicks_7d"))
    clicks_30d = _to_int(item.get("clicks_30d"))
    unique_sessions = _to_int(item.get("unique_sessions_30d"))
    unique_users = _to_int(item.get("unique_users_30d"))
    search_clicks = _to_int(item.get("search_clicks_30d"))
    active_days = _to_int(item.get("active_days_30d"))
    message_count = _to_int(item.get("message_count"))

    burst_ratio = clicks_3d / max(clicks_30d, 1)
    sustained_ratio = active_days / 30

    if clicks_30d >= 24 and active_days >= 7 and clicks_7d >= 8:
        heat_type = "sustained"
        heat_label = "持续热"
    elif clicks_3d >= max(8, math.ceil(clicks_30d * 0.65)) or (clicks_1d >= 10 and burst_ratio >= 0.4):
        heat_type = "burst"
        heat_label = "短期爆发"
    elif clicks_30d >= 8 or active_days >= 3:
        heat_type = "watch"
        heat_label = "持续观察"
    else:
        heat_type = "cold"
        heat_label = "低活跃"

    score = round(
        clicks_1d * 2.2
        + clicks_3d * 1.6
        + clicks_7d * 1.1
        + clicks_30d * 0.5
        + unique_sessions * 1.4
        + unique_users * 1.8
        + search_clicks * 1.2
        + active_days * 2.5
        + min(message_count, 12) * 1.1
        + (16 if heat_type == "sustained" else 10 if heat_type == "burst" else 0),
        1,
    )

    if heat_type == "sustained" and (unique_sessions >= 15 or clicks_30d >= 30):
        priority = "high"
        recommendation = "优先转存"
    elif heat_type == "burst" and (clicks_1d >= 10 or unique_sessions >= 8):
        priority = "high"
        recommendation = "优先跟进"
    elif score >= 30 or clicks_30d >= 10 or active_days >= 4:
        priority = "medium"
        recommendation = "重点观察"
    else:
        priority = "watch"
        recommendation = "继续观察"

    item.update(
        {
            "clicks_1d": clicks_1d,
            "clicks_3d": clicks_3d,
            "clicks_7d": clicks_7d,
            "clicks_30d": clicks_30d,
            "unique_sessions_30d": unique_sessions,
            "unique_users_30d": unique_users,
            "search_clicks_30d": search_clicks,
            "active_days_30d": active_days,
            "message_count": message_count,
            "burst_ratio": round(burst_ratio, 3),
            "sustained_ratio": round(sustained_ratio, 3),
            "heat_type": heat_type,
            "heat_label": heat_label,
            "priority": priority,
            "recommendation": recommendation,
            "score": score,
        }
    )
    return item


def _load_candidate_rows(
    session: Session,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    platform: str | None = None,
    keyword: str | None = None,
    link_target_id: int | None = None,
) -> list[dict[str, Any]]:
    start = _start_date(days)
    day_7 = date.today() - timedelta(days=6)
    day_3 = date.today() - timedelta(days=2)
    day_1 = date.today()
    keyword_value = _normalize_keyword(keyword)
    session_identity = _build_session_identity_expr()

    click_subquery = (
        session.query(
            LinkClickEvent.link_target_id.label("link_target_id"),
            func.count(LinkClickEvent.id).label("clicks_30d"),
            func.count(distinct(session_identity)).label("unique_sessions_30d"),
            func.count(distinct(LinkClickEvent.user_id)).label("unique_users_30d"),
            func.sum(case((LinkClickEvent.stat_date >= day_7, 1), else_=0)).label("clicks_7d"),
            func.sum(case((LinkClickEvent.stat_date >= day_3, 1), else_=0)).label("clicks_3d"),
            func.sum(case((LinkClickEvent.stat_date >= day_1, 1), else_=0)).label("clicks_1d"),
            func.sum(case((LinkClickEvent.search_query.isnot(None), 1), else_=0)).label("search_clicks_30d"),
            func.count(distinct(LinkClickEvent.stat_date)).label("active_days_30d"),
            func.max(LinkClickEvent.clicked_at).label("last_clicked_at"),
        )
        .filter(LinkClickEvent.stat_date >= start)
        .group_by(LinkClickEvent.link_target_id)
        .subquery()
    )

    ref_stats_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.count(MessageLinkRef.id).label("message_ref_count"),
            func.count(distinct(MessageLinkRef.message_id)).label("message_count"),
            func.max(MessageLinkRef.message_timestamp).label("last_message_time"),
        )
        .group_by(MessageLinkRef.link_target_id)
        .subquery()
    )

    latest_ref_id_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.max(MessageLinkRef.id).label("latest_ref_id"),
        )
        .group_by(MessageLinkRef.link_target_id)
        .subquery()
    )
    latest_ref = aliased(MessageLinkRef)

    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.platform.label("platform"),
            LinkTarget.original_url.label("original_url"),
            LinkTarget.share_key.label("share_key"),
            LinkTarget.first_seen_at.label("first_seen_at"),
            LinkTarget.last_seen_at.label("last_seen_at"),
            click_subquery.c.clicks_30d,
            click_subquery.c.unique_sessions_30d,
            click_subquery.c.unique_users_30d,
            click_subquery.c.clicks_7d,
            click_subquery.c.clicks_3d,
            click_subquery.c.clicks_1d,
            click_subquery.c.search_clicks_30d,
            click_subquery.c.active_days_30d,
            click_subquery.c.last_clicked_at,
            ref_stats_subquery.c.message_ref_count,
            ref_stats_subquery.c.message_count,
            ref_stats_subquery.c.last_message_time,
            latest_ref.display_text.label("display_text"),
            latest_ref.provider_label.label("provider_label"),
            latest_ref.target_url.label("target_url"),
        )
        .join(click_subquery, click_subquery.c.link_target_id == LinkTarget.id)
        .join(ref_stats_subquery, ref_stats_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref_id_subquery, latest_ref_id_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_id_subquery.c.latest_ref_id)
    )

    if platform:
        query = query.filter(LinkTarget.platform == platform)
    if link_target_id is not None:
        query = query.filter(LinkTarget.id == int(link_target_id))
    if keyword_value:
        like_pattern = f"%{keyword_value}%"
        query = query.filter(
            or_(
                func.lower(func.coalesce(latest_ref.display_text, "")).like(like_pattern),
                func.lower(func.coalesce(LinkTarget.share_key, "")).like(like_pattern),
                func.lower(func.coalesce(LinkTarget.original_url, "")).like(like_pattern),
            )
        )

    items: list[dict[str, Any]] = []
    for row in query.all():
        item = {
            "link_target_id": _to_int(row.link_target_id),
            "platform": row.platform or "未知网盘",
            "display_text": row.display_text or row.provider_label or row.share_key or f"资源 #{row.link_target_id}",
            "target_url": row.target_url or row.original_url or "",
            "share_key": row.share_key,
            "message_ref_count": _to_int(row.message_ref_count),
            "message_count": _to_int(row.message_count),
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
            "last_message_time": row.last_message_time,
            "last_clicked_at": row.last_clicked_at,
            "clicks_30d": _to_int(row.clicks_30d),
            "unique_sessions_30d": _to_int(row.unique_sessions_30d),
            "unique_users_30d": _to_int(row.unique_users_30d),
            "clicks_7d": _to_int(row.clicks_7d),
            "clicks_3d": _to_int(row.clicks_3d),
            "clicks_1d": _to_int(row.clicks_1d),
            "search_clicks_30d": _to_int(row.search_clicks_30d),
            "active_days_30d": _to_int(row.active_days_30d),
        }
        items.append(_compute_heat_metrics(item))
    return items


def get_resource_ops_overview(session: Session, *, days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    start = _start_date(days)
    session_identity = _build_session_identity_expr()

    overview_row = (
        session.query(
            func.count(LinkClickEvent.id).label("clicks"),
            func.count(distinct(session_identity)).label("unique_sessions"),
            func.count(distinct(LinkClickEvent.user_id)).label("unique_users"),
            func.count(distinct(LinkClickEvent.link_target_id)).label("clicked_targets"),
            func.sum(case((LinkClickEvent.search_query.isnot(None), 1), else_=0)).label("search_clicks"),
        )
        .filter(LinkClickEvent.stat_date >= start)
        .first()
    )

    catalog_status = get_catalog_sync_status(session)
    candidates = _load_candidate_rows(session, days=days)
    high_priority_count = sum(1 for item in candidates if item["priority"] == "high")

    return {
        "clicks_last_30_days": _to_int(getattr(overview_row, "clicks", 0)),
        "unique_sessions_last_30_days": _to_int(getattr(overview_row, "unique_sessions", 0)),
        "unique_users_last_30_days": _to_int(getattr(overview_row, "unique_users", 0)),
        "clicked_targets_last_30_days": _to_int(getattr(overview_row, "clicked_targets", 0)),
        "search_clicks_last_30_days": _to_int(getattr(overview_row, "search_clicks", 0)),
        "unique_link_targets": _to_int(session.query(func.count(distinct(MessageLinkRef.link_target_id))).scalar()),
        "indexed_link_refs": _to_int(session.query(func.count(MessageLinkRef.id)).scalar()),
        "indexed_messages": _to_int(catalog_status["indexed_messages"]),
        "total_messages_with_links": _to_int(catalog_status["total_messages_with_links"]),
        "high_priority_candidates": high_priority_count,
        "generated_at": _utcnow(),
    }


def get_resource_ops_trend(session: Session, *, days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    safe_days = max(3, min(int(days or DEFAULT_LOOKBACK_DAYS), 90))
    start = _start_date(safe_days)

    rows = (
        session.query(
            LinkClickEvent.stat_date.label("stat_date"),
            func.count(LinkClickEvent.id).label("click_count"),
            func.count(distinct(_build_session_identity_expr())).label("unique_sessions"),
            func.count(distinct(LinkClickEvent.link_target_id)).label("clicked_targets"),
        )
        .filter(LinkClickEvent.stat_date >= start)
        .group_by(LinkClickEvent.stat_date)
        .order_by(LinkClickEvent.stat_date.asc())
        .all()
    )
    row_map = {
        row.stat_date: {
            "click_count": _to_int(row.click_count),
            "unique_sessions": _to_int(row.unique_sessions),
            "clicked_targets": _to_int(row.clicked_targets),
        }
        for row in rows
    }

    points: list[dict[str, Any]] = []
    current_day = start
    while current_day <= date.today():
        current = row_map.get(current_day, {})
        points.append(
            {
                "date": current_day.isoformat(),
                "click_count": _to_int(current.get("click_count")),
                "unique_sessions": _to_int(current.get("unique_sessions")),
                "clicked_targets": _to_int(current.get("clicked_targets")),
            }
        )
        current_day += timedelta(days=1)

    return {
        "days": points,
        "days_window": safe_days,
        "generated_at": _utcnow(),
    }


def get_resource_ops_platform_distribution(session: Session, *, days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    start = _start_date(days)

    rows = (
        session.query(
            LinkTarget.platform.label("platform"),
            func.sum(LinkTargetDailyStat.click_count).label("click_count"),
            func.sum(LinkTargetDailyStat.unique_sessions).label("unique_sessions"),
            func.count(distinct(LinkTargetDailyStat.link_target_id)).label("active_targets"),
        )
        .join(LinkTarget, LinkTarget.id == LinkTargetDailyStat.link_target_id)
        .filter(LinkTargetDailyStat.stat_date >= start)
        .group_by(LinkTarget.platform)
        .order_by(func.sum(LinkTargetDailyStat.click_count).desc(), LinkTarget.platform.asc())
        .all()
    )

    total_clicks = sum(_to_int(row.click_count) for row in rows)
    items = [
        {
            "platform": row.platform or "未知网盘",
            "click_count": _to_int(row.click_count),
            "unique_sessions": _to_int(row.unique_sessions),
            "active_targets": _to_int(row.active_targets),
            "percentage": round((_to_int(row.click_count) / total_clicks) * 100, 2) if total_clicks else 0.0,
        }
        for row in rows
    ]
    return {
        "items": items,
        "days_window": max(1, min(int(days or DEFAULT_LOOKBACK_DAYS), 90)),
        "generated_at": _utcnow(),
    }


def list_resource_op_candidates(
    session: Session,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    page: int = 1,
    page_size: int = 20,
    platform: str | None = None,
    heat_type: str | None = None,
    keyword: str | None = None,
    sort_by: str = "score",
    sort_order: str = "desc",
) -> dict[str, Any]:
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    normalized_heat_type = (heat_type or "").strip().lower() or None

    items = _load_candidate_rows(
        session,
        days=days,
        platform=platform,
        keyword=keyword,
    )
    if normalized_heat_type:
        items = [item for item in items if item.get("heat_type") == normalized_heat_type]

    allowed_sort_fields = {
        "score",
        "clicks_30d",
        "clicks_7d",
        "clicks_1d",
        "unique_sessions_30d",
        "active_days_30d",
        "last_clicked_at",
        "message_count",
    }
    sort_field = sort_by if sort_by in allowed_sort_fields else "score"
    reverse = (sort_order or "desc").lower() != "asc"
    items.sort(
        key=lambda item: (
            item.get(sort_field) is None,
            item.get(sort_field) or 0,
            item.get("score") or 0,
            item.get("clicks_30d") or 0,
        ),
        reverse=reverse,
    )

    total = len(items)
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size
    return {
        "items": items[start_index:end_index],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


def get_resource_op_candidate_detail(
    session: Session,
    *,
    link_target_id: int,
    days: int = 14,
) -> dict[str, Any]:
    items = _load_candidate_rows(
        session,
        days=DEFAULT_LOOKBACK_DAYS,
        link_target_id=link_target_id,
    )
    if not items:
        raise LookupError(f"link_target {link_target_id} not found")

    safe_days = max(7, min(int(days or 14), 30))
    start = _start_date(safe_days)

    trend_rows = (
        session.query(
            LinkTargetDailyStat.stat_date.label("stat_date"),
            LinkTargetDailyStat.click_count.label("click_count"),
            LinkTargetDailyStat.unique_sessions.label("unique_sessions"),
        )
        .filter(
            LinkTargetDailyStat.link_target_id == int(link_target_id),
            LinkTargetDailyStat.stat_date >= start,
        )
        .order_by(LinkTargetDailyStat.stat_date.asc())
        .all()
    )
    trend_map = {
        row.stat_date: {
            "click_count": _to_int(row.click_count),
            "unique_sessions": _to_int(row.unique_sessions),
        }
        for row in trend_rows
    }

    trend: list[dict[str, Any]] = []
    current_day = start
    while current_day <= date.today():
        current = trend_map.get(current_day, {})
        trend.append(
            {
                "date": current_day.isoformat(),
                "click_count": _to_int(current.get("click_count")),
                "unique_sessions": _to_int(current.get("unique_sessions")),
            }
        )
        current_day += timedelta(days=1)

    ref_rows = (
        session.query(
            MessageLinkRef.message_id.label("message_id"),
            Message.title.label("message_title"),
            MessageLinkRef.display_text.label("display_text"),
            MessageLinkRef.channel.label("channel"),
            MessageLinkRef.source.label("source"),
            MessageLinkRef.message_timestamp.label("message_timestamp"),
        )
        .outerjoin(Message, Message.id == MessageLinkRef.message_id)
        .filter(MessageLinkRef.link_target_id == int(link_target_id))
        .order_by(
            MessageLinkRef.message_timestamp.is_(None).asc(),
            MessageLinkRef.message_timestamp.desc(),
            MessageLinkRef.id.desc(),
        )
        .limit(12)
        .all()
    )

    return {
        "item": items[0],
        "recent_refs": [
            {
                "message_id": _to_int(row.message_id),
                "message_title": row.message_title or "",
                "display_text": row.display_text or "",
                "channel": row.channel or "",
                "source": row.source or "",
                "message_timestamp": row.message_timestamp,
            }
            for row in ref_rows
        ],
        "trend": trend,
    }
