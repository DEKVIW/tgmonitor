from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.models.models import (
    LinkTarget,
    LinkTargetDailyStat,
    Message,
    MessageLinkRef,
    ResourceCandidateProfile,
    ResourceWork,
    ResourceWorkAlias,
    ResourceWorkBinding,
    ensure_runtime_storage_tables,
)
from app.services.resource_identity import ParsedResourceIdentity, parse_resource_identity
from app.services.resource_ops.ai_title_client import recognize_resource_with_ai_center
from app.services.resource_ops.recognition_queue import (
    CLICK_RECOGNITION_PRIORITY,
    DEFAULT_RECOGNITION_PRIORITY,
    FULL_SCAN_RECOGNITION_PRIORITY,
    enqueue_recognition_tasks,
    get_recognition_queue_summary,
)
from app.services.resource_ops.settings import (
    get_resource_ops_runtime_config,
    is_resource_ops_ai_ready,
    get_resource_ops_runtime_settings,
)


WORK_MATCH_STATUS_LABELS = {
    "pending": "待归并",
    "matched": "已归并",
    "error": "异常",
}

@dataclass(slots=True)
class RecognitionCandidate:
    link_target_id: int
    share_key: str | None
    platform: str
    display_text: str
    latest_message_title: str
    latest_message_time: datetime | None
    clicks_30d: int
    last_clicked_at: datetime | None
    match_status: str
    work_id: int | None
    last_attempted_at: datetime | None
    matched_at: datetime | None
    binding_reason: str
    binding_extra_json: dict[str, Any]


def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _normalize_alias(value: Any) -> str:
    text = _normalize_text(value, max_length=255).lower()
    normalized = "".join(char for char in text if char.isalnum() or "\u4e00" <= char <= "\u9fff")
    return normalized[:255]


def _normalize_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _build_ai_provider_work_id(title: str) -> str:
    normalized_title = _normalize_alias(title)
    if not normalized_title:
        normalized_title = hashlib.sha1(title.encode("utf-8")).hexdigest()[:20]
    return normalized_title[:128]


def _build_recognition_candidate_query(session: Session):
    start_date = date.today() - timedelta(days=29)
    click_subquery = (
        session.query(
            LinkTargetDailyStat.link_target_id.label("link_target_id"),
            func.sum(LinkTargetDailyStat.click_count).label("clicks_30d"),
            func.max(LinkTargetDailyStat.last_clicked_at).label("last_clicked_at"),
        )
        .filter(LinkTargetDailyStat.stat_date >= start_date)
        .group_by(LinkTargetDailyStat.link_target_id)
        .subquery()
    )
    ref_stats_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.max(MessageLinkRef.message_timestamp).label("latest_message_time"),
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
    latest_message = aliased(Message)
    binding = aliased(ResourceWorkBinding)
    profile = aliased(ResourceCandidateProfile)

    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.share_key.label("share_key"),
            LinkTarget.platform.label("platform"),
            latest_ref.display_text.label("display_text"),
            latest_message.title.label("latest_message_title"),
            ref_stats_subquery.c.latest_message_time.label("latest_message_time"),
            click_subquery.c.clicks_30d.label("clicks_30d"),
            click_subquery.c.last_clicked_at.label("last_clicked_at"),
            binding.match_status.label("match_status"),
            binding.work_id.label("work_id"),
            binding.last_attempted_at.label("last_attempted_at"),
            binding.matched_at.label("matched_at"),
            binding.reason.label("binding_reason"),
            binding.extra_json.label("binding_extra_json"),
        )
        .join(ref_stats_subquery, ref_stats_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref_id_subquery, latest_ref_id_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_id_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .outerjoin(click_subquery, click_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(profile, profile.link_target_id == LinkTarget.id)
        .outerjoin(binding, binding.link_target_id == LinkTarget.id)
        .filter(or_(click_subquery.c.link_target_id.isnot(None), profile.id.isnot(None)))
    )
    return query


def _row_to_candidate(row: Any) -> RecognitionCandidate:
    raw_status = _normalize_text(row.match_status, max_length=32).lower()
    match_status = raw_status if raw_status in {"matched", "error"} else "pending"
    return RecognitionCandidate(
        link_target_id=int(row.link_target_id),
        share_key=_normalize_text(row.share_key, max_length=255) or None,
        platform=_normalize_text(row.platform, max_length=64) or "unknown",
        display_text=_normalize_text(row.display_text, max_length=255),
        latest_message_title=_normalize_text(row.latest_message_title, max_length=255),
        latest_message_time=row.latest_message_time,
        clicks_30d=int(row.clicks_30d or 0),
        last_clicked_at=row.last_clicked_at,
        match_status=match_status,
        work_id=int(row.work_id) if row.work_id is not None else None,
        last_attempted_at=row.last_attempted_at,
        matched_at=row.matched_at,
        binding_reason=_normalize_text(row.binding_reason, max_length=255),
        binding_extra_json=dict(row.binding_extra_json or {}),
    )


def _candidate_sort_key(candidate: RecognitionCandidate) -> tuple[int, float, float, int]:
    last_clicked = candidate.last_clicked_at.timestamp() if isinstance(candidate.last_clicked_at, datetime) else -1.0
    last_message = candidate.latest_message_time.timestamp() if isinstance(candidate.latest_message_time, datetime) else -1.0
    return (
        int(candidate.clicks_30d or 0),
        last_clicked,
        last_message,
        candidate.link_target_id,
    )


def _list_recognition_candidates(session: Session) -> list[RecognitionCandidate]:
    query = _build_recognition_candidate_query(session)
    rows = [_row_to_candidate(row) for row in query.all()]
    rows.sort(key=_candidate_sort_key, reverse=True)
    return rows


def _get_candidate_by_link_target_id(session: Session, *, link_target_id: int) -> RecognitionCandidate | None:
    return next(
        (row for row in _list_recognition_candidates(session) if row.link_target_id == int(link_target_id)),
        None,
    )


def _candidate_needs_pending_processing(
    candidate: RecognitionCandidate,
) -> bool:
    if bool(dict(candidate.binding_extra_json or {}).get("terminal_skip")):
        return False
    if candidate.work_id is not None and candidate.match_status == "matched":
        return False
    return True


def _candidate_needs_full_processing(candidate: RecognitionCandidate) -> bool:
    del candidate
    return True


def _collect_processing_target_ids(session: Session, *, mode: str) -> list[int]:
    normalized_mode = _normalize_text(mode, max_length=16).lower() or "pending"
    rows = _list_recognition_candidates(session)
    if normalized_mode == "all":
        return [row.link_target_id for row in rows if _candidate_needs_full_processing(row)]
    return [row.link_target_id for row in rows if _candidate_needs_pending_processing(row)]


def _get_recent_candidate_titles(session: Session, *, link_target_id: int, limit: int = 5) -> list[str]:
    rows = (
        session.query(Message.title, MessageLinkRef.display_text)
        .outerjoin(Message, Message.id == MessageLinkRef.message_id)
        .filter(MessageLinkRef.link_target_id == int(link_target_id))
        .order_by(
            MessageLinkRef.message_timestamp.is_(None).asc(),
            MessageLinkRef.message_timestamp.desc(),
            MessageLinkRef.id.desc(),
        )
        .limit(max(1, min(int(limit or 5), 10)))
        .all()
    )
    titles: list[str] = []
    for row in rows:
        for value in (row.title, row.display_text):
            normalized = _normalize_text(value, max_length=255)
            if normalized and normalized not in titles:
                titles.append(normalized)
    return titles


def _get_primary_title(candidate: RecognitionCandidate, session: Session | None = None) -> str:
    primary_title = _normalize_text(candidate.latest_message_title, max_length=255)
    if primary_title:
        return primary_title
    if session is not None:
        recent_titles = _get_recent_candidate_titles(session, link_target_id=candidate.link_target_id, limit=1)
        if recent_titles:
            return _normalize_text(recent_titles[0], max_length=255)
    primary_title = _normalize_text(candidate.display_text, max_length=255)
    if primary_title:
        return primary_title
    return candidate.share_key or f"link_target_{candidate.link_target_id}"


def _build_recognition_context(
    session: Session,
    *,
    candidate: RecognitionCandidate,
) -> dict[str, Any]:
    primary_title = _get_primary_title(candidate, session)
    recent_titles = _get_recent_candidate_titles(session, link_target_id=candidate.link_target_id, limit=5)
    if primary_title and primary_title not in recent_titles:
        recent_titles.insert(0, primary_title)
    alternate_titles = [title for title in recent_titles if title != primary_title]
    return {
        "primary_title": primary_title,
        "recent_titles": recent_titles[:5],
        "alternate_titles": alternate_titles[:4],
    }


def _serialize_identity_payload(identity: ParsedResourceIdentity | None) -> dict[str, Any] | None:
    if identity is None:
        return None
    return identity.to_dict()


def _ensure_work_aliases(session: Session, *, work_id: int, aliases: Iterable[str], source: str) -> None:
    normalized_pairs = {
        (_normalize_text(alias, max_length=255), _normalize_alias(alias))
        for alias in aliases
        if _normalize_text(alias, max_length=255) and _normalize_alias(alias)
    }
    if not normalized_pairs:
        return
    existing = {
        row.normalized_alias
        for row in session.query(ResourceWorkAlias).filter(ResourceWorkAlias.work_id == int(work_id)).all()
    }
    for alias_text, normalized_alias in normalized_pairs:
        if normalized_alias in existing:
            continue
        session.add(
            ResourceWorkAlias(
                work_id=int(work_id),
                alias=alias_text,
                normalized_alias=normalized_alias,
                source=_normalize_text(source, max_length=32) or "ai",
            )
        )


def _upsert_recognized_work(session: Session, *, candidate: dict[str, Any]) -> ResourceWork:
    provider = "ai"
    provider_work_id = _normalize_text(candidate.get("provider_work_id"), max_length=128)
    work = (
        session.query(ResourceWork)
        .filter(ResourceWork.provider == provider, ResourceWork.provider_work_id == provider_work_id)
        .first()
    )
    canonical_title = _normalize_text(candidate.get("canonical_title"), max_length=255)
    if work is None and canonical_title:
        work = (
            session.query(ResourceWork)
            .filter(ResourceWork.provider == provider, ResourceWork.canonical_title == canonical_title)
            .order_by(ResourceWork.id.asc())
            .first()
        )
    if work is None:
        work = ResourceWork(provider=provider, provider_work_id=provider_work_id, canonical_title=candidate["canonical_title"])
        session.add(work)
    elif provider_work_id and not _normalize_text(work.provider_work_id, max_length=128):
        work.provider_work_id = provider_work_id

    work.media_type = _normalize_text(candidate.get("media_type"), max_length=32) or None
    work.canonical_title = canonical_title or work.canonical_title
    work.original_title = _normalize_text(candidate.get("original_title"), max_length=255) or None
    work.release_year = candidate.get("release_year")
    work.poster_url = None
    work.detail_url = None
    work.popularity = None
    work.extra_json = dict(candidate.get("extra_json") or {})
    work.updated_at = _utcnow()
    session.add(work)
    session.flush()

    _ensure_work_aliases(
        session,
        work_id=int(work.id),
        aliases=candidate.get("aliases") or [],
        source=_normalize_text((candidate.get("extra_json") or {}).get("provider"), max_length=32) or "ai",
    )
    return work


def _upsert_ai_work(session: Session, *, candidate: dict[str, Any]) -> ResourceWork:
    return _upsert_recognized_work(session, candidate=candidate)


def _ensure_binding(session: Session, *, link_target_id: int) -> ResourceWorkBinding:
    binding = session.query(ResourceWorkBinding).filter(ResourceWorkBinding.link_target_id == int(link_target_id)).first()
    if binding is not None:
        return binding
    binding = ResourceWorkBinding(
        link_target_id=int(link_target_id),
        match_status="pending",
        match_source="ai",
        confidence=0.0,
    )
    session.add(binding)
    session.flush()
    return binding


def ensure_work_binding_placeholders(session: Session, *, link_target_ids: Iterable[int]) -> int:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_value in link_target_ids:
        try:
            normalized = int(raw_value)
        except (TypeError, ValueError):
            continue
        if normalized <= 0 or normalized in seen:
            continue
        seen.add(normalized)
        normalized_ids.append(normalized)
    if not normalized_ids:
        return 0

    existing_ids = {
        int(link_target_id)
        for (link_target_id,) in (
            session.query(ResourceWorkBinding.link_target_id)
            .filter(ResourceWorkBinding.link_target_id.in_(normalized_ids))
            .all()
        )
        if link_target_id is not None
    }

    created_count = 0
    for link_target_id in normalized_ids:
        if link_target_id in existing_ids:
            continue
        session.add(
            ResourceWorkBinding(
                link_target_id=link_target_id,
                match_status="pending",
                match_source="ai",
                confidence=0.0,
            )
        )
        created_count += 1

    if created_count:
        session.flush()
    return created_count


def mark_work_bindings_pending(
    session: Session,
    *,
    link_target_ids: Iterable[int],
) -> int:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_value in link_target_ids:
        try:
            normalized = int(raw_value)
        except (TypeError, ValueError):
            continue
        if normalized <= 0 or normalized in seen:
            continue
        seen.add(normalized)
        normalized_ids.append(normalized)
    if not normalized_ids:
        return 0

    ensure_work_binding_placeholders(session, link_target_ids=normalized_ids)
    rows = (
        session.query(ResourceWorkBinding)
        .filter(ResourceWorkBinding.link_target_id.in_(normalized_ids))
        .all()
    )
    updated_count = 0
    for row in rows:
        if row.work_id is not None and row.match_status == "matched":
            continue
        row.match_status = "pending"
        session.add(row)
        updated_count += 1
    if updated_count:
        session.flush()
    return updated_count


def _build_lookup_payload(binding: ResourceWorkBinding | None, work: ResourceWork | None) -> dict[str, Any]:
    extra_json = dict(binding.extra_json or {}) if binding is not None else {}
    raw_status = _normalize_text(getattr(binding, "match_status", None), max_length=32).lower()
    match_status = raw_status if raw_status in {"matched", "error"} else "pending"
    release_year = getattr(work, "release_year", None) if work is not None else None
    season_hint = _normalize_text(extra_json.get("season"), max_length=32) or None
    year_hint = _normalize_optional_int(extra_json.get("year"))
    work_title = getattr(work, "canonical_title", None) if work is not None else None
    return {
        "work_id": int(work.id) if work is not None else None,
        "work_title": work_title,
        "work_canonical_title": getattr(work, "canonical_title", None) if work is not None else None,
        "work_original_title": getattr(work, "original_title", None) if work is not None else None,
        "work_provider": getattr(work, "provider", None) if work is not None else getattr(binding, "provider", None),
        "work_media_type": getattr(work, "media_type", None) if work is not None else None,
        "work_release_year": release_year,
        "work_poster_url": getattr(work, "poster_url", None) if work is not None else None,
        "work_detail_url": getattr(work, "detail_url", None) if work is not None else None,
        "work_match_status": match_status,
        "work_match_status_label": WORK_MATCH_STATUS_LABELS.get(match_status, WORK_MATCH_STATUS_LABELS["pending"]),
        "work_match_source": getattr(binding, "match_source", None) or "ai",
        "work_match_reason": getattr(binding, "reason", None) or "",
        "work_query_title": extra_json.get("query_title"),
        "work_candidate_title": getattr(binding, "candidate_title", None) or getattr(work, "canonical_title", None),
        "work_season_hint": season_hint,
        "work_year_hint": year_hint,
        "work_last_attempted_at": getattr(binding, "last_attempted_at", None),
        "work_matched_at": getattr(binding, "matched_at", None),
    }


def get_work_binding_lookup(session: Session, *, link_target_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_value in link_target_ids:
        try:
            normalized = int(raw_value)
        except (TypeError, ValueError):
            continue
        if normalized <= 0 or normalized in seen:
            continue
        seen.add(normalized)
        normalized_ids.append(normalized)
    if not normalized_ids:
        return {}

    rows = (
        session.query(ResourceWorkBinding, ResourceWork)
        .outerjoin(ResourceWork, ResourceWorkBinding.work_id == ResourceWork.id)
        .filter(ResourceWorkBinding.link_target_id.in_(normalized_ids))
        .all()
    )
    payload = {int(binding.link_target_id): _build_lookup_payload(binding, work) for binding, work in rows}
    for link_target_id in normalized_ids:
        payload.setdefault(link_target_id, _build_lookup_payload(None, None))
    return payload


def _build_ai_work_candidate(
    session: Session,
    *,
    candidate: RecognitionCandidate,
    context: dict[str, Any] | None = None,
    rule_identity: ParsedResourceIdentity | None = None,
) -> dict[str, Any]:
    recognition_context = context or _build_recognition_context(session, candidate=candidate)
    primary_title = _normalize_text(recognition_context.get("primary_title"), max_length=255)

    result = recognize_resource_with_ai_center(
        session,
        primary_title=primary_title,
    )
    used_model = _normalize_text(getattr(result, "used_model", None), max_length=255)
    used_api_mode = _normalize_text(getattr(result, "used_api_mode", None), max_length=64)
    canonical_title = _normalize_text(result.title, max_length=255)
    if not canonical_title:
        raise ValueError("AI 没有返回作品标题")

    aliases: list[str] = []
    for value in [canonical_title, primary_title]:
        normalized = _normalize_text(value, max_length=255)
        if normalized and normalized not in aliases:
            aliases.append(normalized)

    return {
        "provider_work_id": _build_ai_provider_work_id(canonical_title),
        "canonical_title": canonical_title,
        "original_title": canonical_title,
        "release_year": None,
        "media_type": None,
        "confidence": float(getattr(result, "confidence", 0) or 0),
        "aliases": aliases,
        "extra_json": {
            "provider": "ai",
            "reason": _normalize_text(result.reason, max_length=255),
            "query_title": primary_title,
            "season": None,
            "year": None,
            "used_model": used_model,
            "used_api_mode": used_api_mode,
            "source_link_target_id": candidate.link_target_id,
            "recent_titles": list(recognition_context.get("recent_titles") or []),
            "rule_identity": _serialize_identity_payload(rule_identity),
        },
        "match_source": "ai",
        "match_reason": f"AI 归并为：{canonical_title}",
    }


def _build_rule_work_candidate(
    *,
    candidate: RecognitionCandidate,
    context: dict[str, Any],
    identity: ParsedResourceIdentity,
) -> dict[str, Any]:
    canonical_title = _normalize_text(identity.core_title, max_length=255)
    if not canonical_title:
        raise ValueError("rule identity did not produce a canonical title")

    aliases: list[str] = []
    for value in [canonical_title, *(identity.aliases or []), _normalize_text(context.get("primary_title"), max_length=255)]:
        normalized = _normalize_text(value, max_length=255)
        if normalized and normalized not in aliases:
            aliases.append(normalized)

    return {
        "provider_work_id": _build_ai_provider_work_id(canonical_title),
        "canonical_title": canonical_title,
        "original_title": _normalize_text(context.get("primary_title"), max_length=255) or canonical_title,
        "release_year": identity.release_year,
        "media_type": _normalize_text(identity.content_type, max_length=32) or None,
        "confidence": float(identity.confidence or 0),
        "aliases": aliases,
        "extra_json": {
            "provider": "rule",
            "reason": _normalize_text(identity.reason, max_length=255) or "rule_title_parse",
            "query_title": _normalize_text(context.get("primary_title"), max_length=255) or canonical_title,
            "season": identity.season,
            "year": identity.release_year,
            "used_model": None,
            "used_api_mode": None,
            "source_link_target_id": candidate.link_target_id,
            "parsed_identity": identity.to_dict(),
            "recent_titles": list(context.get("recent_titles") or []),
        },
        "match_source": "rule",
        "match_reason": f"规则归并为：{canonical_title}",
    }


def _apply_binding_success(
    session: Session,
    *,
    binding: ResourceWorkBinding,
    candidate: RecognitionCandidate,
    work: ResourceWork,
    recognized_payload: dict[str, Any],
) -> None:
    extra_json = dict(binding.extra_json or {})
    payload_extra = dict(recognized_payload.get("extra_json") or {})
    extra_json.update(
        {
            "query_title": payload_extra.get("query_title") or candidate.latest_message_title or candidate.display_text,
            "season": payload_extra.get("season"),
            "year": payload_extra.get("year"),
            "used_model": payload_extra.get("used_model"),
            "used_api_mode": payload_extra.get("used_api_mode"),
            "recognition_source": _normalize_text(recognized_payload.get("match_source"), max_length=32) or "ai",
            "terminal_skip": False,
        }
    )
    if payload_extra.get("parsed_identity") is not None:
        extra_json["parsed_identity"] = dict(payload_extra.get("parsed_identity") or {})
    if payload_extra.get("rule_identity") is not None:
        extra_json["rule_identity"] = dict(payload_extra.get("rule_identity") or {})
    if payload_extra.get("recent_titles") is not None:
        extra_json["recent_titles"] = list(payload_extra.get("recent_titles") or [])
    binding.work_id = int(work.id)
    binding.match_status = "matched"
    binding.provider = work.provider
    binding.provider_work_id = work.provider_work_id
    binding.confidence = float(recognized_payload.get("confidence") or 0)
    binding.match_source = _normalize_text(recognized_payload.get("match_source"), max_length=32) or "ai"
    binding.query_title = payload_extra.get("query_title") or candidate.latest_message_title or candidate.display_text
    binding.candidate_title = work.canonical_title
    binding.reason = _normalize_text(recognized_payload.get("match_reason"), max_length=255) or f"归并为：{work.canonical_title}"
    binding.last_attempted_at = _utcnow()
    binding.matched_at = binding.last_attempted_at
    binding.error_message = None
    binding.extra_json = extra_json
    session.add(binding)
    session.flush()


def _apply_binding_error(
    session: Session,
    *,
    binding: ResourceWorkBinding,
    candidate: RecognitionCandidate,
    reason: str,
    match_source: str = "ai",
    extra_payload: dict[str, Any] | None = None,
) -> None:
    extra_json = dict(binding.extra_json or {})
    extra_json.update(
        {
            "query_title": candidate.latest_message_title or candidate.display_text,
            "recognition_source": _normalize_text(match_source, max_length=32) or "ai",
        }
    )
    if extra_payload:
        extra_json.update(dict(extra_payload))
    binding.match_status = "error"
    binding.confidence = 0.0
    binding.match_source = _normalize_text(match_source, max_length=32) or "ai"
    binding.query_title = candidate.latest_message_title or candidate.display_text
    binding.reason = _normalize_text(reason, max_length=255) or "AI 识别失败"
    binding.last_attempted_at = _utcnow()
    binding.error_message = binding.reason
    binding.extra_json = extra_json
    session.add(binding)
    session.flush()


def _apply_preserved_binding_error(
    session: Session,
    *,
    binding: ResourceWorkBinding,
    candidate: RecognitionCandidate,
    reason: str,
    match_source: str = "ai",
    extra_payload: dict[str, Any] | None = None,
) -> None:
    extra_json = dict(binding.extra_json or {})
    extra_json["query_title"] = _get_primary_title(candidate)
    extra_json["last_error"] = _normalize_text(reason, max_length=500)
    extra_json["recognition_source"] = _normalize_text(match_source, max_length=32) or "ai"
    if extra_payload:
        extra_json.update(dict(extra_payload))
    binding.last_attempted_at = _utcnow()
    binding.error_message = _normalize_text(reason, max_length=500)
    binding.extra_json = extra_json
    session.add(binding)
    session.flush()


def get_work_binding_summary(session: Session) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    rows = _list_recognition_candidates(session)
    total_candidates = len(rows)
    matched_count = sum(1 for row in rows if row.work_id is not None and row.match_status == "matched")
    binding_error_count = sum(1 for row in rows if row.match_status == "error")
    queue_summary = get_recognition_queue_summary(session)

    return {
        "total_candidates": total_candidates,
        "matched_count": matched_count,
        "pending_count": int(queue_summary["pending_count"]),
        "queued_count": int(queue_summary["queued_count"]),
        "processing_count": int(queue_summary["processing_count"]),
        "retry_wait_count": int(queue_summary["retry_wait_count"]),
        "done_count": int(queue_summary["done_count"]),
        "failed_count": int(queue_summary["failed_count"]),
        "error_count": int(queue_summary["failed_count"]),
        "binding_error_count": binding_error_count,
        "match_rate": round((matched_count / total_candidates) * 100, 1) if total_candidates else 0.0,
    }


def _legacy_resolve_link_target_work(
    session: Session,
    *,
    link_target_id: int,
    candidate_row: RecognitionCandidate | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_config = config or get_resource_ops_runtime_config(session)

    candidate = candidate_row or _get_candidate_by_link_target_id(session, link_target_id=int(link_target_id))
    if candidate is None:
        raise LookupError(f"link_target {link_target_id} not found")

    binding = _ensure_binding(session, link_target_id=candidate.link_target_id)
    had_matched_binding = binding.work_id is not None and binding.match_status == "matched"
    try:
        ai_payload = _build_ai_work_candidate(session, candidate=candidate)
        work = _upsert_ai_work(session, candidate=ai_payload)
        _apply_binding_success(
            session,
            binding=binding,
            candidate=candidate,
            work=work,
            ai_payload=ai_payload,
        )
        info = get_work_binding_lookup(session, link_target_ids=[candidate.link_target_id]).get(candidate.link_target_id)
        return {
            "link_target_id": candidate.link_target_id,
            "status": "matched",
            "reason": f"AI 归并为：{work.canonical_title}",
            "work": info,
        }
    except Exception as exc:
        error_reason = f"AI 识别异常：{exc}"
        if had_matched_binding:
            _apply_preserved_binding_error(
                session,
                binding=binding,
                candidate=candidate,
                reason=error_reason,
            )
        else:
            _apply_binding_error(
                session,
                binding=binding,
                candidate=candidate,
                reason=error_reason,
            )
        info = get_work_binding_lookup(session, link_target_ids=[candidate.link_target_id]).get(candidate.link_target_id)
        return {
            "link_target_id": candidate.link_target_id,
            "status": "error",
            "reason": str(exc),
            "work": info,
        }


def resolve_link_target_work(
    session: Session,
    *,
    link_target_id: int,
    candidate_row: RecognitionCandidate | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_config = config or get_resource_ops_runtime_config(session)
    candidate = candidate_row or _get_candidate_by_link_target_id(session, link_target_id=int(link_target_id))
    if candidate is None:
        raise LookupError(f"link_target {link_target_id} not found")

    binding = _ensure_binding(session, link_target_id=candidate.link_target_id)
    had_matched_binding = binding.work_id is not None and binding.match_status == "matched"
    recognition_context = _build_recognition_context(session, candidate=candidate)
    rule_identity = parse_resource_identity(
        recognition_context.get("primary_title"),
        alternate_titles=recognition_context.get("alternate_titles") or [],
    )

    try:
        if rule_identity.should_skip_ai:
            skip_reason = f"规则判定为非目标资源：{_normalize_text(rule_identity.reason, max_length=120) or 'rule_skip'}"
            terminal_payload = {
                "parsed_identity": rule_identity.to_dict(),
                "terminal_skip": True,
            }
            if had_matched_binding:
                _apply_preserved_binding_error(
                    session,
                    binding=binding,
                    candidate=candidate,
                    reason=skip_reason,
                    match_source="rule",
                    extra_payload=terminal_payload,
                )
            else:
                _apply_binding_error(
                    session,
                    binding=binding,
                    candidate=candidate,
                    reason=skip_reason,
                    match_source="rule",
                    extra_payload=terminal_payload,
                )
            info = get_work_binding_lookup(session, link_target_ids=[candidate.link_target_id]).get(candidate.link_target_id)
            return {
                "link_target_id": candidate.link_target_id,
                "status": "ignored",
                "reason": skip_reason,
                "work": info,
            }

        if rule_identity.core_title and not rule_identity.needs_ai_review:
            recognized_payload = _build_rule_work_candidate(
                candidate=candidate,
                context=recognition_context,
                identity=rule_identity,
            )
        else:
            if not is_resource_ops_ai_ready(session=session, config=runtime_config):
                raise ValueError("规则识别结果不够确定，且当前没有可用的 AI 回退配置")
            recognized_payload = _build_ai_work_candidate(
                session,
                candidate=candidate,
                context=recognition_context,
                rule_identity=rule_identity,
            )

        work = _upsert_recognized_work(session, candidate=recognized_payload)
        _apply_binding_success(
            session,
            binding=binding,
            candidate=candidate,
            work=work,
            recognized_payload=recognized_payload,
        )
        info = get_work_binding_lookup(session, link_target_ids=[candidate.link_target_id]).get(candidate.link_target_id)
        return {
            "link_target_id": candidate.link_target_id,
            "status": "matched",
            "reason": _normalize_text(recognized_payload.get("match_reason"), max_length=255) or f"归并为：{work.canonical_title}",
            "work": info,
        }
    except Exception as exc:
        error_reason = _normalize_text(exc, max_length=255) or type(exc).__name__
        error_payload = {
            "parsed_identity": rule_identity.to_dict(),
            "terminal_skip": False,
        }
        if had_matched_binding:
            _apply_preserved_binding_error(
                session,
                binding=binding,
                candidate=candidate,
                reason=error_reason,
                match_source="rule" if rule_identity.core_title else "ai",
                extra_payload=error_payload,
            )
        else:
            _apply_binding_error(
                session,
                binding=binding,
                candidate=candidate,
                reason=error_reason,
                match_source="rule" if rule_identity.core_title else "ai",
                extra_payload=error_payload,
            )
        info = get_work_binding_lookup(session, link_target_ids=[candidate.link_target_id]).get(candidate.link_target_id)
        return {
            "link_target_id": candidate.link_target_id,
            "status": "error",
            "reason": error_reason,
            "work": info,
        }


def build_recognition_log_line(result: dict[str, Any]) -> str:
    work_payload = dict(result.get("work") or {})
    query_title = _normalize_text(work_payload.get("work_query_title"), max_length=160) or "-"
    resolved_title = _normalize_text(
        work_payload.get("work_title") or work_payload.get("work_canonical_title"),
        max_length=160,
    ) or "-"
    match_source = _normalize_text(work_payload.get("work_match_source"), max_length=32) or "unknown"
    status = _normalize_text(result.get("status"), max_length=16).lower()
    if status == "matched":
        return f"[OK][{match_source}] {query_title} -> {resolved_title}"
    if status == "ignored":
        return f"[SKIP][{match_source}] {query_title} -> {_normalize_text(result.get('reason'), max_length=220) or 'ignored'}"
    return f"[ERR][{match_source}] {query_title} -> {_normalize_text(result.get('reason'), max_length=220) or 'recognition error'}"


_build_recognition_log_line = build_recognition_log_line


def run_resource_ops_recognition_job(
    session: Session,
    *,
    mode: str = "pending",
    respect_retry_after: bool = False,
    operator: str | None = None,
) -> dict[str, Any]:
    del respect_retry_after
    payload = sync_resource_work_bindings(
        session,
        mode=mode,
        operator=operator,
    )
    return {
        "mode": payload["mode"],
        "processed_count": 0,
        "matched_count": 0,
        "error_count": 0,
        "remaining_count": int(payload["binding_summary"]["pending_count"]),
        "started_at": _to_utc_iso(_utcnow()),
        "finished_at": _to_utc_iso(_utcnow()),
        "items": [],
        "binding_summary": payload["binding_summary"],
    }


def sync_resource_work_bindings(
    session: Session,
    *,
    mode: str = "pending",
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    config = get_resource_ops_runtime_config(session)
    normalized_mode = _normalize_text(mode, max_length=16).lower() or "pending"
    if normalized_mode == "full":
        normalized_mode = "all"
    if normalized_mode not in {"pending", "all"}:
        raise ValueError("invalid recognition mode")
    link_target_ids = _collect_processing_target_ids(session, mode=normalized_mode)
    enqueue_result = enqueue_recognition_tasks(
        session,
        link_target_ids=link_target_ids,
        source="full_scan" if normalized_mode == "all" else "manual",
        priority=FULL_SCAN_RECOGNITION_PRIORITY if normalized_mode == "all" else DEFAULT_RECOGNITION_PRIORITY,
        skip_matched=False,
    )
    settings_payload = get_resource_ops_runtime_settings(session)
    if operator:
        settings_payload["recognition_status"]["last_operator"] = str(operator)
    return {
        "accepted": enqueue_result["accepted_count"] > 0,
        "mode": normalized_mode,
        "message": "queued" if enqueue_result["accepted_count"] > 0 else "empty",
        "binding_summary": get_work_binding_summary(session),
        "recognition_status": settings_payload["recognition_status"],
    }


def sync_resource_work_bindings_for_link_targets(
    session: Session,
    *,
    link_target_ids: Iterable[int],
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    del operator
    normalized_ids = _normalize_positive_ids(link_target_ids)

    if not normalized_ids:
        return {
            "accepted": False,
            "mode": "pending",
            "message": "empty",
            "binding_summary": get_work_binding_summary(session),
            "recognition_status": get_resource_ops_runtime_settings(session)["recognition_status"],
        }

    ensure_work_binding_placeholders(session, link_target_ids=normalized_ids)
    config = get_resource_ops_runtime_config(session)
    enqueue_result = {
        "accepted_count": 0,
        "skipped_matched_count": 0,
    }
    message = "disabled"
    if bool(config.get("auto_recognition_enabled")):
        enqueue_result = enqueue_recognition_tasks(
            session,
            link_target_ids=normalized_ids,
            source="click",
            priority=CLICK_RECOGNITION_PRIORITY,
            skip_matched=True,
        )
        message = "queued" if enqueue_result["accepted_count"] > 0 else "skipped"
    settings_payload = get_resource_ops_runtime_settings(session)
    return {
        "accepted": enqueue_result["accepted_count"] > 0,
        "mode": "pending",
        "message": message,
        "binding_summary": get_work_binding_summary(session),
        "recognition_status": settings_payload["recognition_status"],
    }


def sync_resource_work_bindings_for_message_ids(
    session: Session,
    *,
    message_ids: Iterable[int],
    operator: str | None = None,
) -> dict[str, Any]:
    normalized_message_ids = _normalize_positive_ids(message_ids)
    if not normalized_message_ids:
        return {
            "accepted": False,
            "mode": "pending",
            "message": "empty",
            "binding_summary": get_work_binding_summary(session),
            "recognition_status": get_resource_ops_runtime_settings(session)["recognition_status"],
        }

    link_target_ids = [
        int(link_target_id)
        for (link_target_id,) in (
            session.query(MessageLinkRef.link_target_id)
            .filter(MessageLinkRef.message_id.in_(normalized_message_ids))
            .distinct()
            .all()
        )
        if link_target_id is not None
    ]
    return sync_resource_work_bindings_for_link_targets(
        session,
        link_target_ids=link_target_ids,
        operator=operator,
    )
