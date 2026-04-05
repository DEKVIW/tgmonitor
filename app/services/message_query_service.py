"""Message query helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, case, func, literal, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import text as sql_text

from app.models.models import Message


logger = logging.getLogger(__name__)

TIME_RANGE_DELTAS = {
    "最近1小时": timedelta(hours=1),
    "最近24小时": timedelta(days=1),
    "最近7天": timedelta(days=7),
    "最近30天": timedelta(days=30),
    "鏈€杩?灏忔椂": timedelta(hours=1),
    "鏈€杩?4灏忔椂": timedelta(days=1),
    "鏈€杩?澶?": timedelta(days=7),
    "鏈€杩?0澶?": timedelta(days=30),
}


def _split_search_terms(search_query: Optional[str]) -> List[str]:
    seen = set()
    terms: List[str] = []
    for raw_term in (search_query or "").split():
        term = raw_term.strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _build_search_match_condition(search_terms: List[str]):
    per_term_filters = []
    for term in search_terms:
        like_pattern = f"%{term}%"
        per_term_filters.append(
            or_(
                Message.title.ilike(like_pattern),
                Message.description.ilike(like_pattern),
                Message.tags.any(term),
            )
        )

    if not per_term_filters:
        return None
    return and_(*per_term_filters)


def _build_search_rank_expression(search_terms: List[str]):
    normalized_query = " ".join(search_terms).strip().lower()
    title_lower = func.lower(func.coalesce(Message.title, ""))
    description_lower = func.lower(func.coalesce(Message.description, ""))
    rank = literal(0)

    if normalized_query:
        rank = rank + case((title_lower == normalized_query, 10000), else_=0)
        rank = rank + case((title_lower.like(f"{normalized_query}%"), 3000), else_=0)
        rank = rank + case((title_lower.like(f"%{normalized_query}%"), 1200), else_=0)
        rank = rank + case((description_lower.like(f"%{normalized_query}%"), 120), else_=0)

    for term in search_terms:
        normalized_term = term.lower()
        rank = rank + case((title_lower == normalized_term, 2500), else_=0)
        rank = rank + case((title_lower.like(f"{normalized_term}%"), 800), else_=0)
        rank = rank + case((Message.tags.any(term), 500), else_=0)
        rank = rank + case((title_lower.like(f"%{normalized_term}%"), 300), else_=0)
        rank = rank + case((description_lower.like(f"%{normalized_term}%"), 80), else_=0)

    return rank


def _get_message_order_by(search_terms: List[str]):
    if not search_terms:
        return (Message.timestamp.desc(),)
    return (_build_search_rank_expression(search_terms).desc(), Message.timestamp.desc())


def get_filtered_messages(
    db: Session,
    search_query: Optional[str] = None,
    time_range: str = "最近24小时",
    selected_tags: Optional[List[str]] = None,
    selected_netdisks: Optional[List[str]] = None,
    min_content_length: int = 0,
    has_links_only: bool = False,
    page: int = 1,
    page_size: int = 100,
) -> Tuple[List[Message], int, int]:
    try:
        query = db.query(Message)
        search_terms = _split_search_terms(search_query)

        search_match_condition = _build_search_match_condition(search_terms)
        if search_match_condition is not None:
            query = query.filter(search_match_condition)

        if time_range in TIME_RANGE_DELTAS:
            query = query.filter(Message.timestamp >= datetime.now() - TIME_RANGE_DELTAS[time_range])

        if selected_tags:
            filters = [Message.tags.any(tag) for tag in selected_tags]
            query = query.filter(or_(*filters))

        if selected_netdisks:
            filters = []
            for netdisk in selected_netdisks:
                filter_expr = sql_text("netdisk_types @> :netdisk_type")
                filters.append(filter_expr.bindparams(netdisk_type=json.dumps([netdisk])))
            query = query.filter(or_(*filters))

        if min_content_length > 0:
            query = query.filter(
                (
                    func.length(func.coalesce(Message.title, ""))
                    + func.length(func.coalesce(Message.description, ""))
                )
                >= min_content_length
            )

        if has_links_only:
            query = query.filter(Message.links.isnot(None))

        start_idx = (page - 1) * page_size
        order_by_clauses = _get_message_order_by(search_terms)
        messages_page = query.order_by(*order_by_clauses).offset(start_idx).limit(page_size + 1).all()

        has_more = len(messages_page) > page_size
        if has_more:
            messages_page = messages_page[:page_size]
            total_count = query.count()
        else:
            total_count = start_idx + len(messages_page)

        max_page = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        if page > max_page and max_page > 0:
            messages_page = query.order_by(*order_by_clauses).offset(0).limit(page_size).all()

        return messages_page, total_count, max_page

    except Exception as exc:
        logger.error("Failed to load messages: %s", exc, exc_info=True)
        raise


def get_message_by_id(db: Session, message_id: int) -> Optional[Message]:
    try:
        return db.query(Message).filter(Message.id == message_id).first()
    except Exception as exc:
        logger.error("Failed to load message %s: %s", message_id, exc, exc_info=True)
        return None


def get_tag_stats(
    db: Session,
    limit: int = 50,
    since: Optional[datetime] = None,
) -> List[Tuple[str, int]]:
    try:
        if since is None:
            result = db.execute(
                sql_text(
                    """
                    SELECT unnest(tags) as tag, COUNT(*) as count
                    FROM messages
                    WHERE tags IS NOT NULL AND array_length(tags, 1) > 0
                    GROUP BY tag
                    ORDER BY count DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).all()
        else:
            result = db.execute(
                sql_text(
                    """
                    SELECT unnest(tags) as tag, COUNT(*) as count
                    FROM messages
                    WHERE tags IS NOT NULL
                      AND array_length(tags, 1) > 0
                      AND timestamp >= :since
                    GROUP BY tag
                    ORDER BY count DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit, "since": since},
            ).all()

        return [(tag, count) for tag, count in result]
    except Exception as exc:
        logger.error("Failed to load tag stats: %s", exc, exc_info=True)
        return []
