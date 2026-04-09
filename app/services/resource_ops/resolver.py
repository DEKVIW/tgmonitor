from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Iterable

from sqlalchemy import distinct, func, or_
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
from app.services.resource_ops.providers import BangumiClient, TmdbClient
from app.services.resource_ops.settings import get_resource_ops_runtime_config, update_resource_ops_runtime_meta
from app.services.resource_ops.topic_extractor import extract_resource_topic


WORK_MATCH_STATUS_LABELS = {
    "pending": "待识别",
    "matched": "已识别",
    "no_match": "未命中",
    "low_confidence": "低置信度",
    "error": "识别异常",
}

ALIAS_SANITIZE_PATTERN = re.compile(r"[^\w\u4e00-\u9fff]+", re.IGNORECASE)
ANIME_HINT_PATTERN = re.compile(
    r"(动漫|番剧|新番|剧场版|OVA|OAD|TV动画|动画|anime|anim[eé]|声优|完结篇)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class WorkQueryProfile:
    link_target_id: int
    primary_title: str
    query_titles: list[str]
    season_hint: str | None
    year_hint: int | None
    is_anime_like: bool


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        return text[:max_length].strip()
    return text


def _normalize_alias(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    text = ALIAS_SANITIZE_PATTERN.sub("", text)
    return text[:255]


def _clamp_confidence(value: float) -> float:
    return round(max(0.0, min(0.99, float(value))), 4)


def _build_title_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_alias(left)
    normalized_right = _normalize_alias(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0

    shorter, longer = (
        (normalized_left, normalized_right)
        if len(normalized_left) <= len(normalized_right)
        else (normalized_right, normalized_left)
    )
    if len(shorter) >= 4 and shorter in longer:
        coverage = len(shorter) / max(len(longer), 1)
        return max(0.88, min(0.97, 0.84 + coverage * 0.16))

    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _is_anime_like(*parts: str | None) -> bool:
    text = " ".join(_normalize_text(part) for part in parts if part)
    if not text:
        return False
    return bool(ANIME_HINT_PATTERN.search(text))


def _parse_year(value: Any) -> int | None:
    text = _normalize_text(value)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _format_work_title(title: str | None, year: int | None, season_hint: str | None) -> str:
    display_title = _normalize_text(title, max_length=255) or "未命名作品"
    suffix_parts: list[str] = []
    if season_hint:
        suffix_parts.append(f"S{season_hint}")
    elif year:
        suffix_parts.append(str(year))
    if suffix_parts:
        return f"{display_title} {' '.join(suffix_parts)}"
    return display_title


def _build_query_profile(row: dict[str, Any]) -> WorkQueryProfile:
    link_target_id = int(row["link_target_id"])
    latest_message_title = _normalize_text(row.get("latest_message_title"), max_length=255)
    display_text = _normalize_text(row.get("display_text"), max_length=255)
    share_key = _normalize_text(row.get("share_key"), max_length=255) or None
    extracted = extract_resource_topic(
        latest_message_title,
        display_text,
        share_key=share_key,
        fallback_id=link_target_id,
    )
    primary_title = _normalize_text(extracted.get("topic_title"), max_length=255) or f"资源 {link_target_id}"
    query_titles: list[str] = []
    for candidate in (
        extracted.get("topic_title"),
        extracted.get("topic_source_text"),
        latest_message_title,
        display_text,
    ):
        normalized = _normalize_text(candidate, max_length=255)
        if normalized and normalized not in query_titles:
            query_titles.append(normalized)

    season_hint = _normalize_text(extracted.get("season_hint"), max_length=16) or None
    year_hint = _parse_year(extracted.get("year_hint"))
    return WorkQueryProfile(
        link_target_id=link_target_id,
        primary_title=primary_title,
        query_titles=query_titles or [primary_title],
        season_hint=season_hint,
        year_hint=year_hint,
        is_anime_like=_is_anime_like(primary_title, latest_message_title, display_text),
    )


def _candidate_title_list(candidate: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for raw_value in (
        candidate.get("canonical_title"),
        candidate.get("original_title"),
        *list(candidate.get("aliases") or []),
    ):
        normalized = _normalize_text(raw_value, max_length=255)
        if normalized and normalized not in titles:
            titles.append(normalized)
    return titles


def _score_candidate(profile: WorkQueryProfile, candidate: dict[str, Any]) -> float:
    title_score = 0.0
    candidate_titles = _candidate_title_list(candidate)
    for query_title in profile.query_titles:
        for candidate_title in candidate_titles:
            title_score = max(title_score, _build_title_similarity(query_title, candidate_title))

    if title_score <= 0:
        return 0.0

    score = title_score * 0.88
    release_year = _parse_year(candidate.get("release_year"))
    if profile.year_hint is not None and release_year is not None:
        year_diff = abs(int(profile.year_hint) - int(release_year))
        if year_diff == 0:
            score += 0.08
        elif year_diff <= 1:
            score += 0.04
        elif year_diff >= 4:
            score -= min(0.12, year_diff * 0.02)

    media_type = _normalize_text(candidate.get("media_type"), max_length=32).lower()
    if profile.season_hint:
        score += 0.04 if media_type in {"tv", "anime"} else -0.03
    if profile.is_anime_like and candidate.get("provider") == "bangumi":
        score += 0.05
    if (not profile.is_anime_like) and candidate.get("provider") == "tmdb":
        score += 0.02

    popularity = float(candidate.get("popularity") or 0)
    if popularity > 0:
        score += min(popularity / 200.0, 0.03)
    return _clamp_confidence(score)


def _ensure_work_aliases(
    session: Session,
    *,
    work_id: int,
    aliases: Iterable[str],
    source: str,
) -> None:
    normalized_aliases = {
        (_normalize_text(alias, max_length=255), _normalize_alias(alias))
        for alias in aliases
        if _normalize_text(alias, max_length=255)
    }
    normalized_aliases = {
        (alias_text, normalized_alias)
        for alias_text, normalized_alias in normalized_aliases
        if normalized_alias
    }
    if not normalized_aliases:
        return

    existing = {
        alias.normalized_alias
        for alias in (
            session.query(ResourceWorkAlias)
            .filter(ResourceWorkAlias.work_id == int(work_id))
            .all()
        )
    }
    for alias_text, normalized_alias in normalized_aliases:
        if normalized_alias in existing:
            continue
        session.add(
            ResourceWorkAlias(
                work_id=int(work_id),
                alias=alias_text,
                normalized_alias=normalized_alias,
                source=_normalize_text(source, max_length=32) or "provider",
            )
        )


def _upsert_work_from_candidate(session: Session, candidate: dict[str, Any]) -> ResourceWork:
    provider = _normalize_text(candidate.get("provider"), max_length=32) or "unknown"
    provider_work_id = _normalize_text(candidate.get("provider_work_id"), max_length=128)
    work = (
        session.query(ResourceWork)
        .filter(
            ResourceWork.provider == provider,
            ResourceWork.provider_work_id == provider_work_id,
        )
        .first()
    )
    if work is None:
        work = ResourceWork(
            provider=provider,
            provider_work_id=provider_work_id,
            canonical_title=_normalize_text(candidate.get("canonical_title"), max_length=255) or provider_work_id,
        )
        session.add(work)

    work.media_type = _normalize_text(candidate.get("media_type"), max_length=32) or None
    work.canonical_title = _normalize_text(candidate.get("canonical_title"), max_length=255) or work.canonical_title
    work.original_title = _normalize_text(candidate.get("original_title"), max_length=255) or None
    work.release_year = _parse_year(candidate.get("release_year"))
    work.poster_url = _normalize_text(candidate.get("poster_url"), max_length=4000) or None
    work.detail_url = _normalize_text(candidate.get("detail_url"), max_length=4000) or None
    work.popularity = float(candidate.get("popularity") or 0)
    work.extra_json = dict(candidate.get("extra_json") or {})
    work.updated_at = _utcnow()
    session.add(work)
    session.flush()

    _ensure_work_aliases(
        session,
        work_id=int(work.id),
        aliases=[*list(candidate.get("aliases") or []), work.canonical_title, work.original_title or ""],
        source=str(candidate.get("provider") or "provider"),
    )
    return work


def ensure_work_binding_placeholder(session: Session, *, link_target_id: int) -> ResourceWorkBinding:
    binding = (
        session.query(ResourceWorkBinding)
        .filter(ResourceWorkBinding.link_target_id == int(link_target_id))
        .first()
    )
    if binding is not None:
        return binding

    binding = ResourceWorkBinding(
        link_target_id=int(link_target_id),
        match_status="pending",
        match_source="pending",
    )
    session.add(binding)
    session.flush()
    return binding


def ensure_work_binding_placeholders(session: Session, *, link_target_ids: Iterable[int]) -> None:
    for link_target_id in link_target_ids:
        try:
            normalized_id = int(link_target_id)
        except (TypeError, ValueError):
            continue
        if normalized_id <= 0:
            continue
        ensure_work_binding_placeholder(session, link_target_id=normalized_id)


def _resolve_from_alias_cache(session: Session, profile: WorkQueryProfile, *, min_confidence: float) -> tuple[dict[str, Any] | None, float]:
    normalized_queries = [_normalize_alias(title) for title in profile.query_titles if _normalize_alias(title)]
    if not normalized_queries:
        return None, 0.0

    rows = (
        session.query(ResourceWorkAlias, ResourceWork)
        .join(ResourceWork, ResourceWorkAlias.work_id == ResourceWork.id)
        .filter(ResourceWorkAlias.normalized_alias.in_(normalized_queries))
        .all()
    )
    best_candidate: dict[str, Any] | None = None
    best_score = 0.0
    for alias_row, work in rows:
        candidate = {
            "provider": work.provider,
            "provider_work_id": work.provider_work_id,
            "media_type": work.media_type,
            "canonical_title": work.canonical_title,
            "original_title": work.original_title,
            "release_year": work.release_year,
            "poster_url": work.poster_url,
            "detail_url": work.detail_url,
            "popularity": work.popularity,
            "aliases": [alias_row.alias, work.canonical_title, work.original_title or ""],
            "extra_json": dict(work.extra_json or {}),
            "_matched_work_id": int(work.id),
        }
        score = _score_candidate(profile, candidate)
        if score > best_score:
            best_candidate = candidate
            best_score = score
    if best_candidate is None or best_score < min_confidence:
        return best_candidate, best_score
    return best_candidate, best_score


def _build_provider_candidates(profile: WorkQueryProfile, config: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    tmdb_client = TmdbClient(
        read_access_token=str(config.get("tmdb_read_access_token") or ""),
        api_key=str(config.get("tmdb_api_key") or ""),
        language=str(config.get("tmdb_language") or "zh-CN"),
    )
    if config.get("tmdb_enabled") and tmdb_client.is_configured:
        for query_title in profile.query_titles[:3]:
            candidates.extend(tmdb_client.search(query=query_title, year=profile.year_hint, limit=6))
            if len(candidates) >= 12:
                break

    bangumi_client = BangumiClient(
        user_agent=str(config.get("bangumi_user_agent") or "TGMonitor/1.0"),
    )
    should_try_bangumi = bool(config.get("bangumi_enabled") and bangumi_client.is_configured)
    if should_try_bangumi and (profile.is_anime_like or not candidates):
        for query_title in profile.query_titles[:2]:
            candidates.extend(bangumi_client.search(query=query_title, limit=6))
            if len(candidates) >= 18:
                break

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        identity = (
            _normalize_text(candidate.get("provider"), max_length=32),
            _normalize_text(candidate.get("provider_work_id"), max_length=128),
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(candidate)
    return deduped


def _update_binding_no_match(
    binding: ResourceWorkBinding,
    *,
    profile: WorkQueryProfile,
    status: str,
    reason: str,
    confidence: float,
    candidate: dict[str, Any] | None,
    cooldown_hours: int,
) -> None:
    now = _utcnow()
    binding.work_id = None
    binding.match_status = status
    binding.provider = _normalize_text(candidate.get("provider") if candidate else None, max_length=32) or None
    binding.provider_work_id = _normalize_text(candidate.get("provider_work_id") if candidate else None, max_length=128) or None
    binding.match_source = _normalize_text(status, max_length=32) or "pending"
    binding.query_title = profile.primary_title
    binding.candidate_title = _normalize_text(candidate.get("canonical_title") if candidate else None, max_length=255) or None
    binding.confidence = _clamp_confidence(confidence)
    binding.reason = _normalize_text(reason, max_length=255)
    binding.last_attempted_at = now
    binding.matched_at = None
    binding.next_retry_after = now + timedelta(hours=max(1, int(cooldown_hours or 24)))
    binding.error_message = binding.reason if status == "error" else None
    binding.extra_json = {
        "season_hint": profile.season_hint,
        "year_hint": profile.year_hint,
        "query_titles": profile.query_titles[:5],
    }


def _bind_candidate_to_work(
    session: Session,
    *,
    binding: ResourceWorkBinding,
    profile: WorkQueryProfile,
    candidate: dict[str, Any],
    confidence: float,
    match_source: str,
) -> ResourceWork:
    matched_work_id = candidate.get("_matched_work_id")
    if matched_work_id:
        work = session.get(ResourceWork, int(matched_work_id))
        if work is None:
            work = _upsert_work_from_candidate(session, candidate)
    else:
        work = _upsert_work_from_candidate(session, candidate)

    _ensure_work_aliases(
        session,
        work_id=int(work.id),
        aliases=[*profile.query_titles, work.canonical_title, work.original_title or ""],
        source=match_source,
    )

    binding.work_id = int(work.id)
    binding.match_status = "matched"
    binding.provider = work.provider
    binding.provider_work_id = work.provider_work_id
    binding.match_source = _normalize_text(match_source, max_length=32) or "provider"
    binding.query_title = profile.primary_title
    binding.candidate_title = work.canonical_title
    binding.confidence = _clamp_confidence(confidence)
    binding.reason = _normalize_text(f"识别为 {work.canonical_title}", max_length=255)
    binding.last_attempted_at = _utcnow()
    binding.matched_at = binding.last_attempted_at
    binding.next_retry_after = None
    binding.error_message = None
    binding.extra_json = {
        "season_hint": profile.season_hint,
        "year_hint": profile.year_hint,
        "query_titles": profile.query_titles[:5],
    }
    session.add(binding)
    session.flush()
    return work


def _build_resolution_target_query(session: Session):
    start_date = date.today() - timedelta(days=29)
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
    binding = aliased(ResourceWorkBinding)
    profile = aliased(ResourceCandidateProfile)

    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.share_key.label("share_key"),
            LinkTarget.platform.label("platform"),
            latest_ref.display_text.label("display_text"),
            latest_message.title.label("latest_message_title"),
            click_subquery.c.clicks_30d,
            click_subquery.c.last_clicked_at,
            binding.id.label("binding_id"),
            binding.match_status.label("match_status"),
            binding.next_retry_after.label("next_retry_after"),
        )
        .join(latest_ref_id_subquery, latest_ref_id_subquery.c.link_target_id == LinkTarget.id)
        .join(latest_ref, latest_ref.id == latest_ref_id_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .outerjoin(click_subquery, click_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(profile, profile.link_target_id == LinkTarget.id)
        .outerjoin(binding, binding.link_target_id == LinkTarget.id)
        .filter(or_(click_subquery.c.link_target_id.isnot(None), profile.id.isnot(None)))
    )
    return query, binding


def _normalize_resolution_target_row(row: Any) -> dict[str, Any]:
    return {
        "link_target_id": int(row.link_target_id),
        "share_key": row.share_key,
        "platform": row.platform,
        "display_text": row.display_text or "",
        "latest_message_title": row.latest_message_title or "",
        "clicks_30d": int(row.clicks_30d or 0),
        "last_clicked_at": row.last_clicked_at,
        "match_status": row.match_status or "pending",
        "next_retry_after": row.next_retry_after,
    }


def _get_resolution_target_row(session: Session, *, link_target_id: int) -> dict[str, Any] | None:
    query, _binding = _build_resolution_target_query(session)
    row = query.filter(LinkTarget.id == int(link_target_id)).first()
    if row is None:
        return None
    return _normalize_resolution_target_row(row)


def _list_resolution_targets(session: Session, *, limit: int, force: bool) -> list[dict[str, Any]]:
    now = _utcnow()
    query, binding = _build_resolution_target_query(session)
    if not force:
        query = query.filter(
            or_(
                binding.id.is_(None),
                binding.match_status != "matched",
                binding.next_retry_after.is_(None),
                binding.next_retry_after <= now,
            )
        )

    rows = query.all()
    normalized_rows = [_normalize_resolution_target_row(row) for row in rows]

    normalized_rows.sort(
        key=lambda item: (
            int(item.get("clicks_30d") or 0),
            item.get("last_clicked_at").timestamp() if isinstance(item.get("last_clicked_at"), datetime) else -1,
            int(item["link_target_id"]),
        ),
        reverse=True,
    )
    return normalized_rows[: max(1, min(int(limit or 20), 200))]


def _candidate_pool_link_target_ids(session: Session) -> list[int]:
    query, _binding = _build_resolution_target_query(session)
    return [
        int(link_target_id)
        for (link_target_id,) in query.with_entities(LinkTarget.id).distinct().all()
        if link_target_id is not None
    ]


def get_work_binding_lookup(session: Session, *, link_target_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    normalized_ids = []
    seen: set[int] = set()
    for raw_value in link_target_ids:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized_ids.append(value)

    if not normalized_ids:
        return {}

    rows = (
        session.query(ResourceWorkBinding, ResourceWork)
        .outerjoin(ResourceWork, ResourceWorkBinding.work_id == ResourceWork.id)
        .filter(ResourceWorkBinding.link_target_id.in_(normalized_ids))
        .all()
    )
    payload: dict[int, dict[str, Any]] = {}
    for binding, work in rows:
        extra_json = dict(binding.extra_json or {})
        work_id = int(work.id) if work is not None and getattr(work, "id", None) is not None else None
        release_year = getattr(work, "release_year", None) if work is not None else None
        payload[int(binding.link_target_id)] = {
            "work_id": work_id,
            "work_title": _format_work_title(
                getattr(work, "canonical_title", None) if work is not None else None,
                release_year,
                _normalize_text(extra_json.get("season_hint"), max_length=16) or None,
            )
            if work is not None
            else None,
            "work_canonical_title": getattr(work, "canonical_title", None) if work is not None else None,
            "work_original_title": getattr(work, "original_title", None) if work is not None else None,
            "work_provider": getattr(work, "provider", None) if work is not None else binding.provider,
            "work_media_type": getattr(work, "media_type", None) if work is not None else None,
            "work_release_year": release_year,
            "work_poster_url": getattr(work, "poster_url", None) if work is not None else None,
            "work_detail_url": getattr(work, "detail_url", None) if work is not None else None,
            "work_match_status": binding.match_status or "pending",
            "work_match_status_label": WORK_MATCH_STATUS_LABELS.get(binding.match_status or "pending", "待识别"),
            "work_match_source": binding.match_source or "pending",
            "work_confidence": float(binding.confidence or 0),
            "work_match_reason": binding.reason or "",
            "work_query_title": binding.query_title or "",
            "work_candidate_title": binding.candidate_title or "",
            "work_season_hint": _normalize_text(extra_json.get("season_hint"), max_length=16) or None,
            "work_year_hint": _parse_year(extra_json.get("year_hint")),
            "work_last_attempted_at": binding.last_attempted_at,
            "work_matched_at": binding.matched_at,
        }

    for link_target_id in normalized_ids:
        if link_target_id in payload:
            continue
        payload[link_target_id] = {
            "work_id": None,
            "work_title": None,
            "work_canonical_title": None,
            "work_original_title": None,
            "work_provider": None,
            "work_media_type": None,
            "work_release_year": None,
            "work_poster_url": None,
            "work_detail_url": None,
            "work_match_status": "pending",
            "work_match_status_label": WORK_MATCH_STATUS_LABELS["pending"],
            "work_match_source": "pending",
            "work_confidence": 0.0,
            "work_match_reason": "",
            "work_query_title": "",
            "work_candidate_title": "",
            "work_season_hint": None,
            "work_year_hint": None,
            "work_last_attempted_at": None,
            "work_matched_at": None,
        }
    return payload


def resolve_link_target_work(
    session: Session,
    *,
    link_target_id: int,
    force: bool = False,
) -> dict[str, Any]:
    config = get_resource_ops_runtime_config(session)
    tmdb_ready = bool(config.get("tmdb_enabled") and (config.get("tmdb_api_key") or config.get("tmdb_read_access_token")))
    bangumi_ready = bool(config.get("bangumi_enabled") and config.get("bangumi_user_agent"))
    if not tmdb_ready and not bangumi_ready:
        raise ValueError("请先至少启用并配置一个作品识别来源")

    target_row = _get_resolution_target_row(session, link_target_id=int(link_target_id))
    if target_row is None:
        raise LookupError(f"link_target {link_target_id} not found")

    binding = ensure_work_binding_placeholder(session, link_target_id=int(link_target_id))
    if not force and binding.match_status == "matched" and binding.work_id is not None:
        info = get_work_binding_lookup(session, link_target_ids=[int(link_target_id)]).get(int(link_target_id))
        return {
            "link_target_id": int(link_target_id),
            "status": "skipped",
            "reason": "当前链接已经完成作品识别",
            "work": info,
        }

    profile = _build_query_profile(target_row)
    min_confidence = float(config.get("min_confidence") or 0.72)
    cooldown_hours = int(config.get("retry_cooldown_hours") or 24)

    alias_candidate, alias_score = _resolve_from_alias_cache(session, profile, min_confidence=min_confidence)
    if alias_candidate is not None and alias_score >= min_confidence:
        work = _bind_candidate_to_work(
            session,
            binding=binding,
            profile=profile,
            candidate=alias_candidate,
            confidence=alias_score,
            match_source="alias_cache",
        )
        info = get_work_binding_lookup(session, link_target_ids=[int(link_target_id)]).get(int(link_target_id))
        return {
            "link_target_id": int(link_target_id),
            "status": "matched",
            "reason": f"命中本地别名缓存：{work.canonical_title}",
            "work": info,
        }

    best_candidate = alias_candidate
    best_score = alias_score
    for candidate in _build_provider_candidates(profile, config):
        candidate_score = _score_candidate(profile, candidate)
        if candidate_score > best_score:
            best_candidate = candidate
            best_score = candidate_score

    if best_candidate is None:
        _update_binding_no_match(
            binding,
            profile=profile,
            status="no_match",
            reason="没有找到可用的作品匹配结果",
            confidence=0.0,
            candidate=None,
            cooldown_hours=cooldown_hours,
        )
        session.add(binding)
        session.flush()
        return {
            "link_target_id": int(link_target_id),
            "status": "no_match",
            "reason": binding.reason,
            "work": None,
        }

    if best_score < min_confidence:
        _update_binding_no_match(
            binding,
            profile=profile,
            status="low_confidence",
            reason=f"最佳候选置信度不足：{_normalize_text(best_candidate.get('canonical_title'), max_length=255)}",
            confidence=best_score,
            candidate=best_candidate,
            cooldown_hours=cooldown_hours,
        )
        session.add(binding)
        session.flush()
        return {
            "link_target_id": int(link_target_id),
            "status": "low_confidence",
            "reason": binding.reason,
            "work": None,
        }

    work = _bind_candidate_to_work(
        session,
        binding=binding,
        profile=profile,
        candidate=best_candidate,
        confidence=best_score,
        match_source=str(best_candidate.get("provider") or "provider"),
    )
    info = get_work_binding_lookup(session, link_target_ids=[int(link_target_id)]).get(int(link_target_id))
    return {
        "link_target_id": int(link_target_id),
        "status": "matched",
        "reason": f"识别为 {work.canonical_title}",
        "work": info,
    }


def get_work_binding_summary(session: Session) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    candidate_target_ids = _candidate_pool_link_target_ids(session)
    total_tracked_targets = len(candidate_target_ids)
    if not candidate_target_ids:
        return {
            "total_tracked_targets": 0,
            "matched_count": 0,
            "pending_count": 0,
            "no_match_count": 0,
            "low_confidence_count": 0,
            "error_count": 0,
            "match_rate": 0.0,
        }

    rows = (
        session.query(
            ResourceWorkBinding.match_status,
            func.count(ResourceWorkBinding.id),
        )
        .filter(ResourceWorkBinding.link_target_id.in_(candidate_target_ids))
        .group_by(ResourceWorkBinding.match_status)
        .all()
    )
    counts = {str(status or "pending"): int(count or 0) for status, count in rows}
    resolved_count = sum(counts.values())
    pending_missing = max(0, total_tracked_targets - resolved_count)

    matched_count = int(counts.get("matched", 0))
    no_match_count = int(counts.get("no_match", 0))
    low_confidence_count = int(counts.get("low_confidence", 0))
    error_count = int(counts.get("error", 0))
    pending_count = int(counts.get("pending", 0)) + pending_missing

    return {
        "total_tracked_targets": total_tracked_targets,
        "matched_count": matched_count,
        "pending_count": pending_count,
        "no_match_count": no_match_count,
        "low_confidence_count": low_confidence_count,
        "error_count": error_count,
        "match_rate": round((matched_count / total_tracked_targets) * 100, 1) if total_tracked_targets else 0.0,
    }


def sync_resource_work_bindings(
    session: Session,
    *,
    limit: int = 20,
    force: bool = False,
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    config = get_resource_ops_runtime_config(session)
    tmdb_ready = bool(config.get("tmdb_enabled") and (config.get("tmdb_api_key") or config.get("tmdb_read_access_token")))
    bangumi_ready = bool(config.get("bangumi_enabled") and config.get("bangumi_user_agent"))
    if not tmdb_ready and not bangumi_ready:
        raise ValueError("请先至少启用并配置一个作品识别来源")

    started_at = _utcnow()
    target_rows = _list_resolution_targets(session, limit=limit, force=force)
    processed_items: list[dict[str, Any]] = []
    summary = {
        "processed_count": 0,
        "matched_count": 0,
        "no_match_count": 0,
        "low_confidence_count": 0,
        "error_count": 0,
        "skipped_count": 0,
        "started_at": started_at.isoformat(),
    }

    for target_row in target_rows:
        link_target_id = int(target_row["link_target_id"])
        try:
            result = resolve_link_target_work(session, link_target_id=link_target_id, force=force)
            processed_items.append(result)
            status = str(result.get("status") or "skipped")
            summary["processed_count"] += 1
            if status == "matched":
                summary["matched_count"] += 1
            elif status == "no_match":
                summary["no_match_count"] += 1
            elif status == "low_confidence":
                summary["low_confidence_count"] += 1
            else:
                summary["skipped_count"] += 1
        except Exception as exc:
            binding = ensure_work_binding_placeholder(session, link_target_id=link_target_id)
            profile = _build_query_profile(target_row)
            _update_binding_no_match(
                binding,
                profile=profile,
                status="error",
                reason=f"识别异常：{exc}",
                confidence=0.0,
                candidate=None,
                cooldown_hours=int(config.get("retry_cooldown_hours") or 24),
            )
            session.add(binding)
            session.flush()
            summary["processed_count"] += 1
            summary["error_count"] += 1
            processed_items.append(
                {
                    "link_target_id": link_target_id,
                    "status": "error",
                    "reason": str(exc),
                    "work": None,
                }
            )

    summary["finished_at"] = _utcnow().isoformat()
    summary["items"] = processed_items
    summary["binding_summary"] = get_work_binding_summary(session)
    update_resource_ops_runtime_meta(session, last_sync_summary=summary, updated_by=operator or "system")
    return summary
