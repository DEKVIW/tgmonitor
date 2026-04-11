from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import LinkClickEvent, LinkTargetDailyStat, MessageLinkRef
from app.services.resource_ops.catalog import normalize_search_query
from app.services.resource_ops.recognition_service import sync_resource_work_bindings_for_link_targets


EVENT_TOKEN_MAX_LENGTH = 64
SESSION_KEY_MAX_LENGTH = 128
SOURCE_PAGE_MAX_LENGTH = 64


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_text(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        text = text[:max_length].strip()
    return text or None


def _hash_value(value: str | None) -> str | None:
    normalized = _normalize_text(value, max_length=4000)
    if not normalized:
        return None
    payload = f"{settings.SECRET_SALT}:{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _extract_client_ip(request: Request | None) -> str | None:
    if request is None:
        return None

    for header_name in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        raw_value = request.headers.get(header_name)
        if not raw_value:
            continue
        candidate = raw_value.split(",")[0].strip()
        if candidate:
            return candidate

    if request.client and request.client.host:
        return request.client.host
    return None


def _extract_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return _normalize_text(request.headers.get("user-agent"), max_length=4000)


def _normalize_source_page(value: Any) -> str | None:
    normalized = _normalize_text(value, max_length=SOURCE_PAGE_MAX_LENGTH)
    if not normalized:
        return None
    return normalized.replace(" ", "_").lower()


def _resolve_session_key(session_key: str | None, current_user: dict[str, Any] | None) -> str | None:
    provided = _normalize_text(session_key, max_length=SESSION_KEY_MAX_LENGTH)
    if provided:
        return provided
    if current_user:
        return _normalize_text(current_user.get("session_id"), max_length=SESSION_KEY_MAX_LENGTH)
    return None


def _resolve_user_id(current_user: dict[str, Any] | None) -> int | None:
    if not current_user:
        return None
    raw_value = current_user.get("account_id")
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _resolve_existing_event(
    session: Session,
    *,
    event_token: str | None,
    link_ref_id: int,
) -> LinkClickEvent | None:
    if not event_token:
        return None

    event = (
        session.query(LinkClickEvent)
        .filter(LinkClickEvent.event_token == event_token)
        .first()
    )
    if event is None:
        return None
    if int(event.link_ref_id) != int(link_ref_id):
        return None
    return event


def _has_prior_session_click(
    session: Session,
    *,
    link_target_id: int,
    stat_date,
    session_key: str | None,
) -> bool:
    if not session_key:
        return False

    return (
        session.query(LinkClickEvent.id)
        .filter(
            LinkClickEvent.link_target_id == link_target_id,
            LinkClickEvent.stat_date == stat_date,
            LinkClickEvent.session_key == session_key,
        )
        .first()
        is not None
    )


def _has_prior_user_click(
    session: Session,
    *,
    link_target_id: int,
    stat_date,
    user_id: int | None,
) -> bool:
    if user_id is None:
        return False

    return (
        session.query(LinkClickEvent.id)
        .filter(
            LinkClickEvent.link_target_id == link_target_id,
            LinkClickEvent.stat_date == stat_date,
            LinkClickEvent.user_id == user_id,
        )
        .first()
        is not None
    )


def _upsert_daily_stat(
    session: Session,
    *,
    stat_date,
    link_target_id: int,
    clicked_at: datetime,
    click_increment: int,
    unique_session_increment: int,
    unique_user_increment: int,
    search_click_increment: int,
    logged_in_click_increment: int,
) -> None:
    insert_stmt = pg_insert(LinkTargetDailyStat.__table__).values(
        stat_date=stat_date,
        link_target_id=link_target_id,
        click_count=click_increment,
        unique_sessions=unique_session_increment,
        unique_users=unique_user_increment,
        search_click_count=search_click_increment,
        logged_in_click_count=logged_in_click_increment,
        last_clicked_at=clicked_at,
        created_at=clicked_at,
        updated_at=clicked_at,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["stat_date", "link_target_id"],
        set_={
            "click_count": LinkTargetDailyStat.click_count + click_increment,
            "unique_sessions": LinkTargetDailyStat.unique_sessions + unique_session_increment,
            "unique_users": LinkTargetDailyStat.unique_users + unique_user_increment,
            "search_click_count": LinkTargetDailyStat.search_click_count + search_click_increment,
            "logged_in_click_count": LinkTargetDailyStat.logged_in_click_count + logged_in_click_increment,
            "last_clicked_at": clicked_at,
            "updated_at": clicked_at,
        },
    )
    session.execute(upsert_stmt)


def record_click_event(
    session: Session,
    *,
    link_ref_id: int,
    request: Request | None = None,
    current_user: dict[str, Any] | None = None,
    event_token: str | None = None,
    session_key: str | None = None,
    source_page: str | None = None,
    search_query: str | None = None,
    redirect_confirmed: bool = False,
) -> dict[str, Any]:
    link_ref = session.get(MessageLinkRef, int(link_ref_id))
    if link_ref is None:
        raise LookupError(f"link_ref {link_ref_id} not found")

    now = _utcnow()
    stat_date = now.date()
    normalized_event_token = _normalize_text(event_token, max_length=EVENT_TOKEN_MAX_LENGTH)
    normalized_session_key = _resolve_session_key(session_key, current_user)
    normalized_source_page = _normalize_source_page(source_page)
    normalized_search_query = normalize_search_query(search_query)
    user_id = _resolve_user_id(current_user)
    is_logged_in = user_id is not None
    ip_hash = _hash_value(_extract_client_ip(request))
    ua_hash = _hash_value(_extract_user_agent(request))

    existing_event = _resolve_existing_event(
        session,
        event_token=normalized_event_token,
        link_ref_id=int(link_ref_id),
    )

    created = False
    if existing_event is None:
        if normalized_event_token:
            conflicting_event = (
                session.query(LinkClickEvent.id)
                .filter(LinkClickEvent.event_token == normalized_event_token)
                .first()
            )
            if conflicting_event is not None:
                normalized_event_token = None

        prior_session_exists = _has_prior_session_click(
            session,
            link_target_id=int(link_ref.link_target_id),
            stat_date=stat_date,
            session_key=normalized_session_key,
        )
        prior_user_exists = _has_prior_user_click(
            session,
            link_target_id=int(link_ref.link_target_id),
            stat_date=stat_date,
            user_id=user_id,
        )

        tracked_event = LinkClickEvent(
            event_token=normalized_event_token,
            link_ref_id=int(link_ref.id),
            link_target_id=int(link_ref.link_target_id),
            message_id=int(link_ref.message_id),
            user_id=user_id,
            clicked_at=now,
            stat_date=stat_date,
            source_page=normalized_source_page,
            search_query=normalized_search_query,
            session_key=normalized_session_key,
            ip_hash=ip_hash,
            ua_hash=ua_hash,
            is_logged_in=is_logged_in,
            redirect_confirmed=redirect_confirmed,
        )
        session.add(tracked_event)
        session.flush()

        _upsert_daily_stat(
            session,
            stat_date=stat_date,
            link_target_id=int(link_ref.link_target_id),
            clicked_at=now,
            click_increment=1,
            unique_session_increment=0 if prior_session_exists or not normalized_session_key else 1,
            unique_user_increment=0 if prior_user_exists or user_id is None else 1,
            search_click_increment=1 if normalized_search_query else 0,
            logged_in_click_increment=1 if is_logged_in else 0,
        )
        created = True
    else:
        tracked_event = existing_event
        updated = False
        if redirect_confirmed and not tracked_event.redirect_confirmed:
            tracked_event.redirect_confirmed = True
            updated = True
        if not tracked_event.source_page and normalized_source_page:
            tracked_event.source_page = normalized_source_page
            updated = True
        if not tracked_event.search_query and normalized_search_query:
            tracked_event.search_query = normalized_search_query
            updated = True
        if not tracked_event.session_key and normalized_session_key:
            tracked_event.session_key = normalized_session_key
            updated = True
        if tracked_event.user_id is None and user_id is not None:
            tracked_event.user_id = user_id
            tracked_event.is_logged_in = True
            updated = True
        if not tracked_event.ip_hash and ip_hash:
            tracked_event.ip_hash = ip_hash
            updated = True
        if not tracked_event.ua_hash and ua_hash:
            tracked_event.ua_hash = ua_hash
            updated = True
        if updated:
            tracked_event.updated_at = now
            session.add(tracked_event)
            session.flush()

    try:
        with session.begin_nested():
            sync_resource_work_bindings_for_link_targets(
                session,
                link_target_ids=[int(link_ref.link_target_id)],
                operator="system",
            )
    except Exception:
        # Click tracking should never fail because the recognition queue could not be updated.
        pass

    return {
        "accepted": True,
        "event_id": int(tracked_event.id),
        "event_token": tracked_event.event_token,
        "link_ref_id": int(link_ref.id),
        "link_target_id": int(link_ref.link_target_id),
        "redirect_url": str(link_ref.target_url or ""),
        "redirect_confirmed": bool(tracked_event.redirect_confirmed),
        "created": created,
    }


def get_redirect_target_url(session: Session, *, link_ref_id: int) -> str:
    link_ref = session.get(MessageLinkRef, int(link_ref_id))
    if link_ref is None or not str(link_ref.target_url or "").strip():
        raise LookupError(f"link_ref {link_ref_id} not found")
    return str(link_ref.target_url).strip()
