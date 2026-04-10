from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.models import LinkClickEvent, LinkTarget, LinkTargetDailyStat, Message, MessageLinkRef, ResourceWorkBinding, SystemSettings
from app.models.models import ResourceCandidateLog, ResourceCandidateProfile
from app.services.link_check.constants import (
    PLATFORM_115,
    PLATFORM_123,
    PLATFORM_ALIYUN,
    PLATFORM_BAIDU,
    PLATFORM_QUARK,
    PLATFORM_TIANYI,
    PLATFORM_UC,
    PLATFORM_XUNLEI,
    UNKNOWN_PLATFORM,
)
from app.services.link_check.parser import canonical_target_key, detect_platform_from_url
from app.services.link_check.platforms import canonicalize_platform_name
from app.services.resource_ops.recognition_service import ensure_work_binding_placeholders
from app.services.system_config_service import SYSTEM_SETTINGS_SINGLETON_ID, build_default_system_settings_values


logger = logging.getLogger(__name__)

RESOURCE_OPS_EXTRA_KEY = "resource_ops"
CATALOG_CURSOR_KEY = "catalog_cursor_message_id"
CATALOG_LAST_SYNC_AT_KEY = "catalog_last_sync_at"
MAX_SEARCH_QUERY_LENGTH = 120

_PASSCODE_KEYS = ("pwd", "passcode", "code", "password", "share_pwd", "sharepwd", "accessCode")


@dataclass(slots=True)
class FlattenedMessageLink:
    link_index: int
    provider_label: str
    link_label: str | None
    display_text: str
    target_url: str
    normalized_url: str
    normalized_url_hash: str
    platform: str
    share_key: str | None
    passcode: str | None


@dataclass(slots=True)
class MatchedMessageLinkRef:
    ref: MessageLinkRef
    item: FlattenedMessageLink


def _trim_text(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        return text[:max_length].strip() or None
    return text


def normalize_search_query(value: str | None) -> str | None:
    text = " ".join((value or "").split()).strip()
    if not text:
        return None
    return text[:MAX_SEARCH_QUERY_LENGTH]


def _build_display_text(provider_label: str, link_label: str | None) -> str:
    provider = _trim_text(provider_label, max_length=64) or "网盘链接"
    label = _trim_text(link_label, max_length=255)
    if not label:
        return provider
    if label.casefold() == provider.casefold():
        return provider
    return f"{provider} {label}"


def _hash_normalized_url(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extract_passcode(parsed, query: dict[str, list[str]]) -> str | None:
    for key in _PASSCODE_KEYS:
        value = (query.get(key) or [""])[0]
        if value:
            return value.strip() or None
    if parsed.fragment:
        fragment_query = parse_qs(parsed.fragment)
        for key in _PASSCODE_KEYS:
            value = (fragment_query.get(key) or [""])[0]
            if value:
                return value.strip() or None
    return None


def _extract_share_key(platform: str, normalized_url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(normalized_url)
    query = parse_qs(parsed.query)
    path_parts = [part for part in (parsed.path or "").split("/") if part]
    passcode = _extract_passcode(parsed, query)

    if platform == PLATFORM_BAIDU:
        if parsed.path.startswith("/s/") and len(path_parts) >= 2:
            return path_parts[1], passcode
        if parsed.path.startswith("/share/init"):
            return (query.get("surl") or [""])[0] or None, passcode
    elif platform == PLATFORM_QUARK:
        if len(path_parts) >= 2 and path_parts[0] == "s":
            return path_parts[1], passcode
        return (query.get("pwd_id") or [""])[0] or None, passcode
    elif platform == PLATFORM_ALIYUN:
        if len(path_parts) >= 2 and path_parts[0] == "s":
            return path_parts[-1], passcode
    elif platform == PLATFORM_115:
        return (path_parts[-1] if path_parts else None), passcode
    elif platform == PLATFORM_TIANYI:
        if len(path_parts) >= 2 and path_parts[0] in {"t", "share"}:
            return path_parts[-1], passcode
        return (query.get("code") or [""])[0] or None, passcode
    elif platform == PLATFORM_123:
        if len(path_parts) >= 2 and path_parts[0] == "s":
            return path_parts[-1], passcode
    elif platform == PLATFORM_UC:
        if len(path_parts) >= 2 and path_parts[0] in {"s", "share"}:
            return path_parts[-1], passcode
    elif platform == PLATFORM_XUNLEI:
        if len(path_parts) >= 2 and path_parts[0] in {"s", "share"}:
            return path_parts[-1], passcode
        return (query.get("share_id") or [""])[0] or None, passcode

    return None, passcode


def _flatten_message_links(
    links: Any,
    *,
    provider_label: str | None = None,
    items: list[FlattenedMessageLink],
    counter: list[int],
) -> None:
    if isinstance(links, dict):
        if "url" in links and isinstance(links.get("url"), str):
            raw_url = str(links["url"]).strip()
            normalized_url = canonical_target_key(raw_url)
            if not normalized_url:
                return
            platform = canonicalize_platform_name(detect_platform_from_url(normalized_url))
            share_key, passcode = _extract_share_key(platform, normalized_url)
            label = _trim_text(links.get("label"), max_length=255)
            counter[0] += 1
            items.append(
                FlattenedMessageLink(
                    link_index=counter[0],
                    provider_label=_trim_text(provider_label, max_length=64) or platform or "网盘链接",
                    link_label=label,
                    display_text=_build_display_text(
                        _trim_text(provider_label, max_length=64) or platform or "网盘链接",
                        label,
                    ),
                    target_url=raw_url,
                    normalized_url=normalized_url,
                    normalized_url_hash=_hash_normalized_url(normalized_url),
                    platform=platform or UNKNOWN_PLATFORM,
                    share_key=share_key,
                    passcode=passcode,
                )
            )
            return

        for key, value in links.items():
            next_provider = provider_label or _trim_text(key, max_length=64) or "网盘链接"
            _flatten_message_links(
                value,
                provider_label=next_provider,
                items=items,
                counter=counter,
            )
        return

    if isinstance(links, list):
        for item in links:
            _flatten_message_links(
                item,
                provider_label=provider_label,
                items=items,
                counter=counter,
            )
        return

    if isinstance(links, str):
        raw_url = links.strip()
        normalized_url = canonical_target_key(raw_url)
        if not normalized_url:
            return
        platform = canonicalize_platform_name(detect_platform_from_url(normalized_url))
        share_key, passcode = _extract_share_key(platform, normalized_url)
        counter[0] += 1
        items.append(
            FlattenedMessageLink(
                link_index=counter[0],
                provider_label=_trim_text(provider_label, max_length=64) or platform or "网盘链接",
                link_label=None,
                display_text=_build_display_text(
                    _trim_text(provider_label, max_length=64) or platform or "网盘链接",
                    None,
                ),
                target_url=raw_url,
                normalized_url=normalized_url,
                normalized_url_hash=_hash_normalized_url(normalized_url),
                platform=platform or UNKNOWN_PLATFORM,
                share_key=share_key,
                passcode=passcode,
            )
        )


def flatten_message_links(links: Any) -> list[FlattenedMessageLink]:
    items: list[FlattenedMessageLink] = []
    _flatten_message_links(links, items=items, counter=[-1])
    return items


def _ensure_system_settings_record(session: Session) -> SystemSettings:
    record = session.get(SystemSettings, SYSTEM_SETTINGS_SINGLETON_ID)
    if record is not None:
        return record

    record = SystemSettings(id=SYSTEM_SETTINGS_SINGLETON_ID, **build_default_system_settings_values())
    session.add(record)
    session.flush()
    return record


def _read_resource_ops_extra(record: SystemSettings) -> dict[str, Any]:
    extra_json = dict(record.extra_json or {})
    bucket = extra_json.get(RESOURCE_OPS_EXTRA_KEY)
    if isinstance(bucket, dict):
        return dict(bucket)
    return {}


def _write_resource_ops_extra(record: SystemSettings, payload: dict[str, Any]) -> None:
    extra_json = dict(record.extra_json or {})
    extra_json[RESOURCE_OPS_EXTRA_KEY] = payload
    record.extra_json = extra_json
    record.updated_at = datetime.utcnow()


def _ensure_link_target(
    session: Session,
    *,
    flattened: FlattenedMessageLink,
    observed_at: datetime | None = None,
    cache: dict[tuple[str, str], LinkTarget],
) -> LinkTarget:
    cache_key = (flattened.platform, flattened.normalized_url_hash)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    observed_time = observed_at or datetime.utcnow()

    target = (
        session.query(LinkTarget)
        .filter(
            LinkTarget.platform == flattened.platform,
            LinkTarget.normalized_url_hash == flattened.normalized_url_hash,
        )
        .first()
    )
    if target is None:
        target = LinkTarget(
            platform=flattened.platform,
            original_url=flattened.target_url,
            normalized_url=flattened.normalized_url,
            normalized_url_hash=flattened.normalized_url_hash,
            share_key=flattened.share_key,
            passcode=flattened.passcode,
            first_seen_at=observed_time,
            last_seen_at=observed_time,
        )
        session.add(target)
        session.flush()
    else:
        target.original_url = target.original_url or flattened.target_url
        target.normalized_url = flattened.normalized_url
        target.share_key = target.share_key or flattened.share_key
        target.passcode = target.passcode or flattened.passcode
        if target.first_seen_at is None or observed_time < target.first_seen_at:
            target.first_seen_at = observed_time
        if target.last_seen_at is None or observed_time > target.last_seen_at:
            target.last_seen_at = observed_time

    cache[cache_key] = target
    if getattr(target, "id", None) is not None:
        ensure_work_binding_placeholders(session, link_target_ids=[int(target.id)])
    return target


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


def _build_flattened_identity_key(item: FlattenedMessageLink) -> tuple[str, str]:
    return item.platform or UNKNOWN_PLATFORM, item.normalized_url_hash


def _build_ref_identity_key(ref: MessageLinkRef) -> tuple[str, str] | None:
    normalized_url = canonical_target_key(str(ref.target_url or ""))
    if not normalized_url:
        return None
    platform = canonicalize_platform_name(detect_platform_from_url(normalized_url)) or UNKNOWN_PLATFORM
    return platform, _hash_normalized_url(normalized_url)


def _build_ref_match_score(ref: MessageLinkRef, item: FlattenedMessageLink) -> tuple[int, int, int, int, int]:
    return (
        1 if int(ref.link_index) == int(item.link_index) else 0,
        1 if (ref.provider_label or "") == item.provider_label else 0,
        1 if (ref.link_label or "") == (item.link_label or "") else 0,
        1 if (ref.display_text or "") == item.display_text else 0,
        -abs(int(ref.link_index) - int(item.link_index)),
    )


def _delete_link_click_events_for_ref_ids(session: Session, ref_ids: list[int]) -> set[int]:
    if not ref_ids:
        return set()

    target_ids = {
        int(target_id)
        for (target_id,) in (
            session.query(LinkClickEvent.link_target_id)
            .filter(LinkClickEvent.link_ref_id.in_(ref_ids))
            .distinct()
            .all()
        )
        if target_id is not None
    }
    (
        session.query(LinkClickEvent)
        .filter(LinkClickEvent.link_ref_id.in_(ref_ids))
        .delete(synchronize_session=False)
    )
    return target_ids


def _delete_link_click_events_for_message_ids(session: Session, message_ids: list[int]) -> set[int]:
    if not message_ids:
        return set()

    target_ids = {
        int(target_id)
        for (target_id,) in (
            session.query(LinkClickEvent.link_target_id)
            .filter(LinkClickEvent.message_id.in_(message_ids))
            .distinct()
            .all()
        )
        if target_id is not None
    }
    (
        session.query(LinkClickEvent)
        .filter(LinkClickEvent.message_id.in_(message_ids))
        .delete(synchronize_session=False)
    )
    return target_ids


def _refresh_link_target_daily_stats(session: Session, target_ids: Iterable[int]) -> None:
    normalized_target_ids = _normalize_positive_ids(target_ids)
    if not normalized_target_ids:
        return

    (
        session.query(LinkTargetDailyStat)
        .filter(LinkTargetDailyStat.link_target_id.in_(normalized_target_ids))
        .delete(synchronize_session=False)
    )

    rows = (
        session.query(
            LinkClickEvent.link_target_id.label("link_target_id"),
            LinkClickEvent.stat_date.label("stat_date"),
            func.count(LinkClickEvent.id).label("click_count"),
            func.count(func.distinct(LinkClickEvent.session_key)).label("unique_sessions"),
            func.count(func.distinct(LinkClickEvent.user_id)).label("unique_users"),
            func.sum(case((LinkClickEvent.search_query.isnot(None), 1), else_=0)).label("search_click_count"),
            func.sum(case((LinkClickEvent.is_logged_in.is_(True), 1), else_=0)).label("logged_in_click_count"),
            func.max(LinkClickEvent.clicked_at).label("last_clicked_at"),
        )
        .filter(LinkClickEvent.link_target_id.in_(normalized_target_ids))
        .group_by(LinkClickEvent.link_target_id, LinkClickEvent.stat_date)
        .all()
    )

    for row in rows:
        session.add(
            LinkTargetDailyStat(
                stat_date=row.stat_date,
                link_target_id=int(row.link_target_id),
                click_count=int(row.click_count or 0),
                unique_sessions=int(row.unique_sessions or 0),
                unique_users=int(row.unique_users or 0),
                search_click_count=int(row.search_click_count or 0),
                logged_in_click_count=int(row.logged_in_click_count or 0),
                last_clicked_at=row.last_clicked_at,
            )
        )


def _purge_orphan_link_targets(session: Session, target_ids: Iterable[int]) -> None:
    normalized_target_ids = _normalize_positive_ids(target_ids)
    if not normalized_target_ids:
        return

    remaining_ref_target_ids = {
        int(target_id)
        for (target_id,) in (
            session.query(MessageLinkRef.link_target_id)
            .filter(MessageLinkRef.link_target_id.in_(normalized_target_ids))
            .distinct()
            .all()
        )
        if target_id is not None
    }
    remaining_event_target_ids = {
        int(target_id)
        for (target_id,) in (
            session.query(LinkClickEvent.link_target_id)
            .filter(LinkClickEvent.link_target_id.in_(normalized_target_ids))
            .distinct()
            .all()
        )
        if target_id is not None
    }

    orphan_target_ids = [
        target_id
        for target_id in normalized_target_ids
        if target_id not in remaining_ref_target_ids and target_id not in remaining_event_target_ids
    ]
    if not orphan_target_ids:
        return

    (
        session.query(LinkTargetDailyStat)
        .filter(LinkTargetDailyStat.link_target_id.in_(orphan_target_ids))
        .delete(synchronize_session=False)
    )
    (
        session.query(ResourceCandidateLog)
        .filter(ResourceCandidateLog.link_target_id.in_(orphan_target_ids))
        .delete(synchronize_session=False)
    )
    (
        session.query(ResourceCandidateProfile)
        .filter(ResourceCandidateProfile.link_target_id.in_(orphan_target_ids))
        .delete(synchronize_session=False)
    )
    (
        session.query(ResourceWorkBinding)
        .filter(ResourceWorkBinding.link_target_id.in_(orphan_target_ids))
        .delete(synchronize_session=False)
    )
    (
        session.query(LinkTarget)
        .filter(LinkTarget.id.in_(orphan_target_ids))
        .delete(synchronize_session=False)
    )


def _delete_message_link_refs(session: Session, refs: Iterable[MessageLinkRef]) -> bool:
    ref_list = [ref for ref in refs if getattr(ref, "id", None) is not None]
    if not ref_list:
        return False

    ref_ids = [int(ref.id) for ref in ref_list]
    target_ids = {
        int(ref.link_target_id)
        for ref in ref_list
        if getattr(ref, "link_target_id", None) is not None
    }
    target_ids.update(_delete_link_click_events_for_ref_ids(session, ref_ids))
    (
        session.query(MessageLinkRef)
        .filter(MessageLinkRef.id.in_(ref_ids))
        .delete(synchronize_session=False)
    )
    _refresh_link_target_daily_stats(session, target_ids)
    _purge_orphan_link_targets(session, target_ids)
    return True


def delete_message_resource_data(session: Session, message_ids: Iterable[int]) -> bool:
    normalized_message_ids = _normalize_positive_ids(message_ids)
    if not normalized_message_ids:
        return False

    refs = (
        session.query(MessageLinkRef)
        .filter(MessageLinkRef.message_id.in_(normalized_message_ids))
        .all()
    )
    target_ids = {
        int(ref.link_target_id)
        for ref in refs
        if getattr(ref, "link_target_id", None) is not None
    }
    target_ids.update(_delete_link_click_events_for_message_ids(session, normalized_message_ids))

    if refs:
        (
            session.query(MessageLinkRef)
            .filter(MessageLinkRef.message_id.in_(normalized_message_ids))
            .delete(synchronize_session=False)
        )

    if target_ids:
        _refresh_link_target_daily_stats(session, target_ids)
        _purge_orphan_link_targets(session, target_ids)

    return bool(refs or target_ids)


def ensure_message_link_refs_for_message_ids(
    session: Session,
    message_ids: Iterable[int],
) -> tuple[dict[int, list[MessageLinkRef]], bool]:
    normalized_message_ids = _normalize_positive_ids(message_ids)
    if not normalized_message_ids:
        return {}, False

    messages = (
        session.query(Message)
        .filter(Message.id.in_(normalized_message_ids))
        .order_by(Message.id.asc())
        .all()
    )
    return ensure_message_link_refs_for_messages(session, messages)


def ensure_message_link_refs_for_messages(
    session: Session,
    messages: Iterable[Message],
) -> tuple[dict[int, list[MessageLinkRef]], bool]:
    message_list = [message for message in messages if getattr(message, "id", None) is not None]
    if not message_list:
        return {}, False

    message_ids = [int(message.id) for message in message_list]
    existing_refs = (
        session.query(MessageLinkRef)
        .filter(MessageLinkRef.message_id.in_(message_ids))
        .all()
    )
    existing_by_message: dict[int, list[MessageLinkRef]] = {}
    for ref in existing_refs:
        existing_by_message.setdefault(int(ref.message_id), []).append(ref)

    refs_by_message: dict[int, list[MessageLinkRef]] = {}
    target_cache: dict[tuple[str, str], LinkTarget] = {}
    changed = False

    for message in message_list:
        flattened_items = flatten_message_links(getattr(message, "links", None))
        current_refs = sorted(existing_by_message.get(int(message.id), []), key=lambda ref: int(ref.link_index))
        current_by_index = {int(ref.link_index): ref for ref in current_refs}
        refs_by_message[int(message.id)] = []
        unused_ref_ids = {
            int(ref.id)
            for ref in current_refs
            if getattr(ref, "id", None) is not None
        }
        matched_refs: list[MatchedMessageLinkRef] = []
        new_items: list[FlattenedMessageLink] = []

        for item in flattened_items:
            item_identity = _build_flattened_identity_key(item)
            matched_ref: MessageLinkRef | None = None

            exact_ref = current_by_index.get(int(item.link_index))
            if (
                exact_ref is not None
                and getattr(exact_ref, "id", None) is not None
                and int(exact_ref.id) in unused_ref_ids
                and _build_ref_identity_key(exact_ref) == item_identity
            ):
                matched_ref = exact_ref
            else:
                candidates = [
                    ref
                    for ref in current_refs
                    if getattr(ref, "id", None) is not None
                    and int(ref.id) in unused_ref_ids
                    and _build_ref_identity_key(ref) == item_identity
                ]
                if candidates:
                    matched_ref = max(candidates, key=lambda ref: _build_ref_match_score(ref, item))

            if matched_ref is None:
                new_items.append(item)
                continue

            unused_ref_ids.discard(int(matched_ref.id))
            matched_refs.append(MatchedMessageLinkRef(ref=matched_ref, item=item))
            refs_by_message[int(message.id)].append(matched_ref)

        stale_refs = [
            ref
            for ref in current_refs
            if getattr(ref, "id", None) is not None and int(ref.id) in unused_ref_ids
        ]
        if stale_refs:
            if _delete_message_link_refs(session, stale_refs):
                changed = True

        refs_requiring_reindex = [
            matched
            for matched in matched_refs
            if int(matched.ref.link_index) != int(matched.item.link_index)
        ]
        if refs_requiring_reindex:
            temp_index_seed = -1_000_000
            for offset, matched in enumerate(refs_requiring_reindex):
                next_temp_index = temp_index_seed - offset
                if int(matched.ref.link_index) != next_temp_index:
                    matched.ref.link_index = next_temp_index
                    changed = True
            session.flush()

        for matched in matched_refs:
            target = _ensure_link_target(
                session,
                flattened=matched.item,
                observed_at=getattr(message, "timestamp", None),
                cache=target_cache,
            )
            next_values = {
                "link_target_id": int(target.id),
                "link_index": matched.item.link_index,
                "provider_label": matched.item.provider_label,
                "link_label": matched.item.link_label,
                "display_text": matched.item.display_text,
                "target_url": matched.item.target_url,
                "channel": _trim_text(getattr(message, "channel", None), max_length=255),
                "source": _trim_text(getattr(message, "source", None), max_length=255),
                "message_timestamp": getattr(message, "timestamp", None),
            }
            for field_name, next_value in next_values.items():
                if getattr(matched.ref, field_name) != next_value:
                    setattr(matched.ref, field_name, next_value)
                    changed = True

        for item in new_items:
            target = _ensure_link_target(
                session,
                flattened=item,
                observed_at=getattr(message, "timestamp", None),
                cache=target_cache,
            )
            ref = MessageLinkRef(
                message_id=int(message.id),
                link_target_id=int(target.id),
                link_index=item.link_index,
                provider_label=item.provider_label,
                link_label=item.link_label,
                display_text=item.display_text,
                target_url=item.target_url,
                channel=_trim_text(getattr(message, "channel", None), max_length=255),
                source=_trim_text(getattr(message, "source", None), max_length=255),
                message_timestamp=getattr(message, "timestamp", None),
            )
            session.add(ref)
            refs_by_message[int(message.id)].append(ref)
            changed = True

        refs_by_message[int(message.id)].sort(key=lambda ref: int(ref.link_index))

    if changed:
        session.flush()

    return refs_by_message, changed


def ensure_message_link_refs(session: Session, message: Message) -> tuple[list[MessageLinkRef], bool]:
    refs_by_message, changed = ensure_message_link_refs_for_messages(session, [message])
    return refs_by_message.get(int(message.id), []), changed


def build_tracked_link_payloads(refs: Iterable[MessageLinkRef]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for ref in sorted(refs, key=lambda item: int(item.link_index)):
        payloads.append(
            {
                "link_ref_id": int(ref.id),
                "link_target_id": int(ref.link_target_id),
                "provider_label": ref.provider_label,
                "link_label": ref.link_label,
                "display_text": ref.display_text,
                "target_url": ref.target_url,
                "redirect_url": f"/api/resource-ops/go/{int(ref.id)}",
            }
        )
    return payloads


def get_catalog_sync_status(session: Session) -> dict[str, Any]:
    settings_record = _ensure_system_settings_record(session)
    extra = _read_resource_ops_extra(settings_record)
    unindexed_query = (
        session.query(Message.id)
        .filter(Message.links.isnot(None))
        .filter(
            ~session.query(MessageLinkRef.id)
            .filter(MessageLinkRef.message_id == Message.id)
            .exists()
        )
    )
    total_messages_with_links = int(
        session.query(func.count(Message.id))
        .filter(Message.links.isnot(None))
        .scalar()
        or 0
    )
    indexed_messages = int(session.query(func.count(func.distinct(MessageLinkRef.message_id))).scalar() or 0)
    cursor_message_id = int(extra.get(CATALOG_CURSOR_KEY) or 0)
    has_more = bool(unindexed_query.limit(1).first() is not None)
    return {
        "total_messages_with_links": total_messages_with_links,
        "indexed_messages": indexed_messages,
        "link_target_count": int(session.query(func.count(func.distinct(MessageLinkRef.link_target_id))).scalar() or 0),
        "link_ref_count": int(session.query(func.count(MessageLinkRef.id)).scalar() or 0),
        "cursor_message_id": cursor_message_id,
        "last_sync_at": extra.get(CATALOG_LAST_SYNC_AT_KEY),
        "is_fully_synced": bool(total_messages_with_links == 0 or not has_more),
        "has_more": has_more,
    }


def sync_message_link_catalog_batch(session: Session, *, batch_size: int = 500) -> dict[str, Any]:
    batch_size = max(50, min(int(batch_size or 500), 2000))
    settings_record = _ensure_system_settings_record(session)
    extra = _read_resource_ops_extra(settings_record)
    cursor_message_id = int(extra.get(CATALOG_CURSOR_KEY) or 0)

    messages = (
        session.query(Message)
        .filter(Message.links.isnot(None))
        .filter(
            ~session.query(MessageLinkRef.id)
            .filter(MessageLinkRef.message_id == Message.id)
            .exists()
        )
        .order_by(Message.id.asc())
        .limit(batch_size)
        .all()
    )

    refs_by_message, changed = ensure_message_link_refs_for_messages(session, messages)
    processed_count = len(messages)
    indexed_ref_count = sum(len(items) for items in refs_by_message.values())
    next_cursor = int(messages[-1].id) if messages else cursor_message_id

    extra[CATALOG_CURSOR_KEY] = next_cursor
    extra[CATALOG_LAST_SYNC_AT_KEY] = datetime.utcnow().isoformat()
    _write_resource_ops_extra(settings_record, extra)

    session.commit()

    status = get_catalog_sync_status(session)
    status.update(
        {
            "processed_messages": processed_count,
            "indexed_links": indexed_ref_count,
            "changed": changed,
            "batch_size": batch_size,
        }
    )
    return status
