from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
from app.services.resource_ops.ai_title_client import recognize_resource_with_ai
from app.services.resource_ops.settings import (
    finish_resource_ops_full_sync,
    get_resource_ops_runtime_config,
    is_resource_ops_ai_ready,
    is_resource_ops_full_sync_active,
    mark_resource_ops_full_sync_started,
    request_resource_ops_full_sync,
    update_resource_ops_runtime_settings,
    update_resource_ops_runtime_meta,
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


def _candidate_needs_incremental_sync(candidate: RecognitionCandidate) -> bool:
    return candidate.work_id is None or candidate.match_status != "matched"


def _candidate_needs_full_sync(candidate: RecognitionCandidate, generation: str) -> bool:
    return _normalize_text(candidate.binding_extra_json.get("full_sync_generation"), max_length=64) != generation


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


def _upsert_ai_work(session: Session, *, candidate: dict[str, Any]) -> ResourceWork:
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
        source="ai",
    )
    return work


def _ensure_binding(session: Session, *, link_target_id: int) -> ResourceWorkBinding:
    binding = session.query(ResourceWorkBinding).filter(ResourceWorkBinding.link_target_id == int(link_target_id)).first()
    if binding is not None:
        return binding
    binding = ResourceWorkBinding(link_target_id=int(link_target_id), match_status="pending", match_source="ai")
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
            )
        )
        created_count += 1

    if created_count:
        session.flush()
    return created_count


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
    config: dict[str, Any],
) -> dict[str, Any]:
    recent_titles = _get_recent_candidate_titles(session, link_target_id=candidate.link_target_id, limit=1)
    primary_title = _normalize_text(candidate.latest_message_title, max_length=255)
    if not primary_title and recent_titles:
        primary_title = _normalize_text(recent_titles[0], max_length=255)
    if not primary_title:
        primary_title = _normalize_text(candidate.display_text, max_length=255)
    if not primary_title:
        primary_title = candidate.share_key or f"link_target_{candidate.link_target_id}"

    result = recognize_resource_with_ai(
        base_url=str(config.get("ai_base_url") or ""),
        api_key=str(config.get("ai_api_key") or ""),
        model=str(config.get("ai_model") or ""),
        primary_title=primary_title,
    )
    used_model = _normalize_text(getattr(result, "used_model", None), max_length=255)
    if used_model and used_model != _normalize_text(config.get("ai_model"), max_length=255):
        update_resource_ops_runtime_settings(
            session,
            {"ai_model": used_model},
            updated_by="system",
        )
        config["ai_model"] = used_model
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
        "aliases": aliases,
        "extra_json": {
            "provider": "ai",
            "reason": _normalize_text(result.reason, max_length=255),
            "query_title": primary_title,
            "season": None,
            "year": None,
            "used_model": used_model,
            "source_link_target_id": candidate.link_target_id,
        },
    }


def _apply_binding_success(
    session: Session,
    *,
    binding: ResourceWorkBinding,
    candidate: RecognitionCandidate,
    work: ResourceWork,
    ai_payload: dict[str, Any],
    full_generation: str | None,
) -> None:
    extra_json = dict(binding.extra_json or {})
    extra_json.update(
        {
            "query_title": (ai_payload.get("extra_json") or {}).get("query_title") or candidate.latest_message_title or candidate.display_text,
            "season": (ai_payload.get("extra_json") or {}).get("season"),
            "year": (ai_payload.get("extra_json") or {}).get("year"),
            "used_model": (ai_payload.get("extra_json") or {}).get("used_model"),
            "full_sync_generation": full_generation or extra_json.get("full_sync_generation"),
        }
    )
    binding.work_id = int(work.id)
    binding.match_status = "matched"
    binding.provider = "ai"
    binding.provider_work_id = work.provider_work_id
    binding.match_source = "ai"
    binding.query_title = (ai_payload.get("extra_json") or {}).get("query_title") or candidate.latest_message_title or candidate.display_text
    binding.candidate_title = work.canonical_title
    binding.confidence = 0
    binding.reason = f"AI 归并为：{work.canonical_title}"
    binding.last_attempted_at = _utcnow()
    binding.matched_at = binding.last_attempted_at
    binding.next_retry_after = None
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
    full_generation: str | None,
) -> None:
    extra_json = dict(binding.extra_json or {})
    extra_json.update(
        {
            "query_title": candidate.latest_message_title or candidate.display_text,
            "full_sync_generation": full_generation or extra_json.get("full_sync_generation"),
        }
    )
    binding.match_status = "error"
    binding.match_source = "ai"
    binding.query_title = candidate.latest_message_title or candidate.display_text
    binding.reason = _normalize_text(reason, max_length=255) or "AI 识别失败"
    binding.last_attempted_at = _utcnow()
    binding.error_message = binding.reason
    binding.extra_json = extra_json
    session.add(binding)
    session.flush()


def _count_full_sync_processed(rows: list[RecognitionCandidate], generation: str | None) -> int:
    if not generation:
        return 0
    return sum(1 for row in rows if _normalize_text(row.binding_extra_json.get("full_sync_generation"), max_length=64) == generation)


def get_work_binding_summary(session: Session) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    config = get_resource_ops_runtime_config(session)
    rows = _list_recognition_candidates(session)
    total_candidates = len(rows)
    matched_count = sum(1 for row in rows if row.work_id is not None and row.match_status == "matched")
    error_count = sum(1 for row in rows if row.match_status == "error")
    pending_count = max(0, total_candidates - matched_count - error_count)

    generation = _normalize_text(config.get("full_sync_generation"), max_length=64)
    full_sync_active = bool(is_resource_ops_full_sync_active(config))
    full_sync_processed = _count_full_sync_processed(rows, generation)
    full_sync_total = total_candidates if generation else 0

    return {
        "total_candidates": total_candidates,
        "matched_count": matched_count,
        "pending_count": pending_count,
        "error_count": error_count,
        "match_rate": round((matched_count / total_candidates) * 100, 1) if total_candidates else 0.0,
        "full_sync_active": full_sync_active,
        "full_sync_total": full_sync_total,
        "full_sync_processed": full_sync_processed,
        "full_sync_progress": round((full_sync_processed / full_sync_total) * 100, 1) if full_sync_total else 0.0,
        "full_sync_started_at": config.get("full_sync_started_at").isoformat() if config.get("full_sync_started_at") else None,
        "full_sync_finished_at": config.get("full_sync_finished_at").isoformat() if config.get("full_sync_finished_at") else None,
    }


def resolve_link_target_work(
    session: Session,
    *,
    link_target_id: int,
    candidate_row: RecognitionCandidate | None = None,
    config: dict[str, Any] | None = None,
    full_generation: str | None = None,
) -> dict[str, Any]:
    runtime_config = config or get_resource_ops_runtime_config(session)
    if not is_resource_ops_ai_ready(runtime_config):
        raise ValueError("请先启用并配置可用的 AI 识别")

    candidate = candidate_row
    if candidate is None:
        candidate = next((row for row in _list_recognition_candidates(session) if row.link_target_id == int(link_target_id)), None)
    if candidate is None:
        raise LookupError(f"link_target {link_target_id} not found")

    binding = _ensure_binding(session, link_target_id=candidate.link_target_id)
    try:
        ai_payload = _build_ai_work_candidate(session, candidate=candidate, config=runtime_config)
        work = _upsert_ai_work(session, candidate=ai_payload)
        _apply_binding_success(
            session,
            binding=binding,
            candidate=candidate,
            work=work,
            ai_payload=ai_payload,
            full_generation=full_generation,
        )
        info = get_work_binding_lookup(session, link_target_ids=[candidate.link_target_id]).get(candidate.link_target_id)
        return {
            "link_target_id": candidate.link_target_id,
            "status": "matched",
            "reason": f"AI 归并为：{work.canonical_title}",
            "work": info,
        }
    except Exception as exc:
        _apply_binding_error(
            session,
            binding=binding,
            candidate=candidate,
            reason=f"AI 识别异常：{exc}",
            full_generation=full_generation,
        )
        info = get_work_binding_lookup(session, link_target_ids=[candidate.link_target_id]).get(candidate.link_target_id)
        return {
            "link_target_id": candidate.link_target_id,
            "status": "error",
            "reason": str(exc),
            "work": info,
        }


def sync_resource_work_bindings(
    session: Session,
    *,
    limit: int = 20,
    mode: str = "pending",
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    config = get_resource_ops_runtime_config(session)
    if not is_resource_ops_ai_ready(config):
        raise ValueError("请先启用并配置可用的 AI 识别")

    normalized_mode = _normalize_text(mode, max_length=16).lower() or "pending"
    if normalized_mode not in {"pending", "full"}:
        raise ValueError("invalid recognition mode")

    full_generation = _normalize_text(config.get("full_sync_generation"), max_length=64) or None
    if normalized_mode == "full":
        if not full_generation or not is_resource_ops_full_sync_active(config):
            request_resource_ops_full_sync(session, updated_by=operator or "system")
            session.flush()
            config = get_resource_ops_runtime_config(session)
            full_generation = _normalize_text(config.get("full_sync_generation"), max_length=64) or None
        mark_resource_ops_full_sync_started(session, updated_by=operator or "system")
        session.flush()
        config = get_resource_ops_runtime_config(session)
        full_generation = _normalize_text(config.get("full_sync_generation"), max_length=64) or None

    all_rows = _list_recognition_candidates(session)
    if normalized_mode == "full":
        target_rows = [row for row in all_rows if _candidate_needs_full_sync(row, full_generation or "")]
    else:
        target_rows = [row for row in all_rows if _candidate_needs_incremental_sync(row)]
    target_rows = target_rows[: max(1, min(int(limit or 20), 200))]

    started_at = _utcnow()
    processed_items: list[dict[str, Any]] = []
    matched_count = 0
    error_count = 0
    skipped_count = 0

    for row in target_rows:
        result = resolve_link_target_work(
            session,
            link_target_id=row.link_target_id,
            candidate_row=row,
            config=config,
            full_generation=full_generation,
        )
        processed_items.append(result)
        status = _normalize_text(result.get("status"), max_length=16).lower()
        if status == "matched":
            matched_count += 1
        elif status == "error":
            error_count += 1
        else:
            skipped_count += 1

    summary = get_work_binding_summary(session)
    if normalized_mode == "full" and summary["full_sync_active"] and summary["full_sync_total"] == summary["full_sync_processed"]:
        finish_resource_ops_full_sync(session, updated_by=operator or "system")
        session.flush()
        summary = get_work_binding_summary(session)

    latest_rows = _list_recognition_candidates(session)
    if normalized_mode == "full":
        remaining_count = sum(1 for row in latest_rows if _candidate_needs_full_sync(row, full_generation or ""))
    else:
        remaining_count = sum(1 for row in latest_rows if _candidate_needs_incremental_sync(row))

    response = {
        "mode": normalized_mode,
        "processed_count": len(processed_items),
        "matched_count": matched_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "remaining_count": remaining_count,
        "started_at": started_at.isoformat(),
        "finished_at": _utcnow().isoformat(),
        "items": processed_items,
        "binding_summary": summary,
    }
    compact_summary = {key: value for key, value in response.items() if key != "items"}
    update_resource_ops_runtime_meta(session, last_sync_summary=compact_summary, updated_by=operator or "system")
    return response


def sync_resource_work_bindings_for_link_targets(
    session: Session,
    *,
    link_target_ids: Iterable[int],
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
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
        return {
            "mode": "incremental_targets",
            "processed_count": 0,
            "matched_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "remaining_count": 0,
            "started_at": _utcnow().isoformat(),
            "finished_at": _utcnow().isoformat(),
            "items": [],
            "binding_summary": get_work_binding_summary(session),
        }

    ensure_work_binding_placeholders(session, link_target_ids=normalized_ids)
    config = get_resource_ops_runtime_config(session)
    if not bool(config.get("auto_bind_enabled")) or not is_resource_ops_ai_ready(config):
        return {
            "mode": "incremental_targets",
            "processed_count": 0,
            "matched_count": 0,
            "error_count": 0,
            "skipped_count": len(normalized_ids),
            "remaining_count": len(normalized_ids),
            "started_at": _utcnow().isoformat(),
            "finished_at": _utcnow().isoformat(),
            "items": [],
            "binding_summary": get_work_binding_summary(session),
        }

    candidate_map = {row.link_target_id: row for row in _list_recognition_candidates(session)}
    target_rows = [
        candidate_map[link_target_id]
        for link_target_id in normalized_ids
        if link_target_id in candidate_map and _candidate_needs_incremental_sync(candidate_map[link_target_id])
    ]

    started_at = _utcnow()
    processed_items: list[dict[str, Any]] = []
    matched_count = 0
    error_count = 0
    skipped_count = 0

    for row in target_rows:
        result = resolve_link_target_work(
            session,
            link_target_id=row.link_target_id,
            candidate_row=row,
            config=config,
        )
        processed_items.append(result)
        status = _normalize_text(result.get("status"), max_length=16).lower()
        if status == "matched":
            matched_count += 1
        elif status == "error":
            error_count += 1
        else:
            skipped_count += 1

    skipped_count += max(0, len(normalized_ids) - len(target_rows))
    latest_map = {row.link_target_id: row for row in _list_recognition_candidates(session)}
    summary = get_work_binding_summary(session)
    remaining_count = sum(
        1
        for link_target_id in normalized_ids
        if link_target_id in latest_map and _candidate_needs_incremental_sync(latest_map[link_target_id])
    )

    response = {
        "mode": "incremental_targets",
        "processed_count": len(processed_items),
        "matched_count": matched_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "remaining_count": remaining_count,
        "started_at": started_at.isoformat(),
        "finished_at": _utcnow().isoformat(),
        "items": processed_items,
        "binding_summary": summary,
    }
    compact_summary = {key: value for key, value in response.items() if key != "items"}
    update_resource_ops_runtime_meta(session, last_sync_summary=compact_summary, updated_by=operator or "system")
    return response


def sync_resource_work_bindings_for_message_ids(
    session: Session,
    *,
    message_ids: Iterable[int],
    operator: str | None = None,
) -> dict[str, Any]:
    normalized_message_ids: list[int] = []
    seen: set[int] = set()
    for raw_value in message_ids:
        try:
            normalized = int(raw_value)
        except (TypeError, ValueError):
            continue
        if normalized <= 0 or normalized in seen:
            continue
        seen.add(normalized)
        normalized_message_ids.append(normalized)
    if not normalized_message_ids:
        return {
            "mode": "incremental_messages",
            "processed_count": 0,
            "matched_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "remaining_count": 0,
            "started_at": _utcnow().isoformat(),
            "finished_at": _utcnow().isoformat(),
            "items": [],
            "binding_summary": get_work_binding_summary(session),
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
    result = sync_resource_work_bindings_for_link_targets(
        session,
        link_target_ids=link_target_ids,
        operator=operator,
    )
    result["mode"] = "incremental_messages"
    return result
