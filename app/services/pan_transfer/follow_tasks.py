from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.models.models import (
    LinkTarget,
    Message,
    MessageLinkRef,
    PanTransferAccount,
    PanTransferBatchItem,
    PanTransferPublishRecord,
    PanTransferSyncTask,
    PanTransferSyncTaskLog,
    ResourceWorkBinding,
    ensure_runtime_storage_tables,
)
from app.services.ai_center import execute_text_route, extract_json_object_from_text
from app.services.resource_ops import get_work_binding_lookup

from .common import normalize_relative_path, utcnow
from .validation import validate_share_url


logger = logging.getLogger(__name__)


PAN_TRANSFER_SYNC_STATUS_ACTIVE = "active"
PAN_TRANSFER_SYNC_STATUS_PAUSED = "paused"

PAN_TRANSFER_SYNC_STATE_IDLE = "idle"
PAN_TRANSFER_SYNC_STATE_QUEUED = "queued"
PAN_TRANSFER_SYNC_STATE_CHECKING = "checking"
PAN_TRANSFER_SYNC_STATE_CANDIDATE_FOUND = "candidate_found"
PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED = "sync_queued"
PAN_TRANSFER_SYNC_STATE_SOURCE_INVALID = "source_invalid"
PAN_TRANSFER_SYNC_STATE_SHARE_INVALID = "share_invalid"
PAN_TRANSFER_SYNC_STATE_ERROR = "error"

PAN_TRANSFER_SYNC_ALLOWED_STATUS = {
    PAN_TRANSFER_SYNC_STATUS_ACTIVE,
    PAN_TRANSFER_SYNC_STATUS_PAUSED,
}

PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES = 3 * 60
PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES = 15
PAN_TRANSFER_SYNC_MAX_INTERVAL_MINUTES = 7 * 24 * 60
PAN_TRANSFER_SYNC_CANDIDATE_LOOKBACK_DAYS = 3
PAN_TRANSFER_SYNC_MIN_CANDIDATE_LOOKBACK_DAYS = 1
PAN_TRANSFER_SYNC_MAX_CANDIDATE_LOOKBACK_DAYS = 90
PAN_TRANSFER_FOLLOW_IDENTITY_ROUTE_KEY = "pan_transfer_follow_identity_extract"
PAN_TRANSFER_FOLLOW_CANDIDATE_JUDGE_ROUTE_KEY = "pan_transfer_follow_candidate_judge"
PAN_TRANSFER_FOLLOW_MAX_RECALL_CANDIDATES = 12
PAN_TRANSFER_FOLLOW_MAX_JUDGE_CANDIDATES = 6
PAN_TRANSFER_FOLLOW_MIN_RECALL_CANDIDATES = 1
PAN_TRANSFER_FOLLOW_RECALL_CANDIDATES_LIMIT = 30
PAN_TRANSFER_FOLLOW_MIN_JUDGE_CANDIDATES = 1
PAN_TRANSFER_FOLLOW_JUDGE_CANDIDATES_LIMIT = 12

FOLLOW_EPISODE_PATTERNS = (
    re.compile(r"更\s*(\d{1,4})\s*集"),
    re.compile(r"第\s*(\d{1,4})\s*集"),
    re.compile(r"\bS\d{1,2}E(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\bE(\d{1,4})\b", re.IGNORECASE),
)
FOLLOW_SEASON_PATTERNS = (
    re.compile(r"第\s*(\d{1,3})\s*季"),
    re.compile(r"\bS(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\bSeason\s*(\d{1,2})\b", re.IGNORECASE),
)
FOLLOW_TITLE_NOISE_PATTERNS = (
    re.compile(r"[（(【\[]?(19|20)\d{2}[）)】\]]?"),
    re.compile(r"\b(?:S\d{1,2}E\d{1,4}(?:\s*[-~]\s*E?\d{1,4})?)\b", re.IGNORECASE),
    re.compile(r"\b(?:E\d{1,4})\b", re.IGNORECASE),
    re.compile(r"(?:更|第)\s*\d{1,4}\s*集"),
    re.compile(r"\b(?:60FPS|120FPS|4K|8K|1080P|2160P|HDR|DV|HQ)\b", re.IGNORECASE),
    re.compile(r"[|｜/／,，].*$"),
)


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def _normalize_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _normalize_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = _normalize_text(value, max_length=16).lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _normalize_interval_minutes(value: Any) -> int:
    if value in (None, ""):
        return PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("check_interval_minutes must be an integer") from exc
    if normalized < PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES or normalized > PAN_TRANSFER_SYNC_MAX_INTERVAL_MINUTES:
        raise ValueError(
            f"check_interval_minutes must be between {PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES} and {PAN_TRANSFER_SYNC_MAX_INTERVAL_MINUTES}"
        )
    return normalized


def _normalize_candidate_lookback_days(value: Any) -> int:
    if value in (None, ""):
        return PAN_TRANSFER_SYNC_CANDIDATE_LOOKBACK_DAYS
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate_lookback_days must be an integer") from exc
    if normalized < PAN_TRANSFER_SYNC_MIN_CANDIDATE_LOOKBACK_DAYS or normalized > PAN_TRANSFER_SYNC_MAX_CANDIDATE_LOOKBACK_DAYS:
        raise ValueError(
            f"candidate_lookback_days must be between {PAN_TRANSFER_SYNC_MIN_CANDIDATE_LOOKBACK_DAYS} and {PAN_TRANSFER_SYNC_MAX_CANDIDATE_LOOKBACK_DAYS}"
        )
    return normalized


def _normalize_max_recall_candidates(value: Any) -> int:
    if value in (None, ""):
        return PAN_TRANSFER_FOLLOW_MAX_RECALL_CANDIDATES
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate_max_recall_candidates must be an integer") from exc
    if normalized < PAN_TRANSFER_FOLLOW_MIN_RECALL_CANDIDATES or normalized > PAN_TRANSFER_FOLLOW_RECALL_CANDIDATES_LIMIT:
        raise ValueError(
            f"candidate_max_recall_candidates must be between {PAN_TRANSFER_FOLLOW_MIN_RECALL_CANDIDATES} and {PAN_TRANSFER_FOLLOW_RECALL_CANDIDATES_LIMIT}"
        )
    return normalized


def _normalize_max_judge_candidates(value: Any, *, max_recall_candidates: int) -> int:
    if value in (None, ""):
        normalized = PAN_TRANSFER_FOLLOW_MAX_JUDGE_CANDIDATES
    else:
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("candidate_max_judge_candidates must be an integer") from exc
    if normalized < PAN_TRANSFER_FOLLOW_MIN_JUDGE_CANDIDATES or normalized > PAN_TRANSFER_FOLLOW_JUDGE_CANDIDATES_LIMIT:
        raise ValueError(
            f"candidate_max_judge_candidates must be between {PAN_TRANSFER_FOLLOW_MIN_JUDGE_CANDIDATES} and {PAN_TRANSFER_FOLLOW_JUDGE_CANDIDATES_LIMIT}"
        )
    if normalized > max_recall_candidates:
        raise ValueError("candidate_max_judge_candidates cannot be greater than candidate_max_recall_candidates")
    return normalized


def _next_check_time(*, interval_minutes: int) -> Any:
    return utcnow() + timedelta(minutes=max(PAN_TRANSFER_SYNC_MIN_INTERVAL_MINUTES, int(interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES)))


def _serialize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        text = value.isoformat()
        return f"{text}Z" if value.tzinfo is None else text
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _serialize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_json_value(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return _normalize_text(value, max_length=4000) or repr(value)


def _normalize_log_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _serialize_json_value(payload or {})
    return normalized if isinstance(normalized, dict) else {"value": normalized}


def _normalize_match_key(value: Any) -> str:
    text = _normalize_text(value, max_length=255).lower()
    return "".join(char for char in text if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def _dedupe_texts(values: list[str], *, max_items: int = 6, max_length: int = 120) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        text = _normalize_text(raw_value, max_length=max_length)
        if not text:
            continue
        key = _normalize_match_key(text) or text.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= max_items:
            break
    return normalized


def _clean_follow_title(value: Any) -> str:
    title = _normalize_text(value, max_length=255)
    if not title:
        return ""
    cleaned = title
    for pattern in FOLLOW_TITLE_NOISE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_|/,.，。[]【】()（）")
    return _normalize_text(cleaned, max_length=255) or title


def _extract_follow_episode_hint(*texts: Any) -> int | None:
    matches: list[int] = []
    for raw_value in texts:
        text = _normalize_text(raw_value, max_length=500)
        if not text:
            continue
        for pattern in FOLLOW_EPISODE_PATTERNS:
            for matched in pattern.findall(text):
                try:
                    matches.append(int(matched))
                except (TypeError, ValueError):
                    continue
    return max(matches) if matches else None


def _extract_follow_season_hint(*texts: Any) -> int | None:
    for raw_value in texts:
        text = _normalize_text(raw_value, max_length=500)
        if not text:
            continue
        for pattern in FOLLOW_SEASON_PATTERNS:
            matched = pattern.search(text)
            if matched is None:
                continue
            try:
                return int(matched.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _get_task_extra_section(task: PanTransferSyncTask, key: str) -> dict[str, Any]:
    extra_json = dict(task.extra_json or {})
    section = extra_json.get(key)
    return dict(section or {}) if isinstance(section, dict) else {}


def _set_task_extra_section(task: PanTransferSyncTask, key: str, value: dict[str, Any] | None) -> None:
    extra_json = dict(task.extra_json or {})
    if value:
        extra_json[key] = _normalize_log_payload(value)
    else:
        extra_json.pop(key, None)
    task.extra_json = extra_json


def _normalize_source_message_snapshot(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    normalized_tags = [
        tag
        for tag in [_normalize_text(item, max_length=64) for item in list(raw.get("tags") or [])]
        if tag
    ]
    message_time_value = raw.get("message_time")
    normalized_message_time = None
    if message_time_value not in (None, ""):
        normalized_message_time = _serialize_json_value(_parse_datetime(message_time_value) or message_time_value)
    snapshot = {
        "title": _normalize_text(raw.get("title"), max_length=255) or None,
        "description": _normalize_text(raw.get("description"), max_length=2000) or None,
        "tags": normalized_tags,
        "message_time": normalized_message_time,
    }
    return {key: value for key, value in snapshot.items() if value not in (None, [], "")}


def _resolve_follow_task_resource_title(task: PanTransferSyncTask) -> str:
    source_message_snapshot = _normalize_source_message_snapshot(_get_task_extra_section(task, "source_message_snapshot"))
    return (
        _normalize_text(source_message_snapshot.get("title"), max_length=255)
        or _normalize_text(task.work_title, max_length=255)
        or _normalize_text(task.topic_title, max_length=255)
        or _normalize_text(task.task_name, max_length=255)
        or f"resource_{int(task.id)}"
    )


def _collect_follow_reference_texts(task: PanTransferSyncTask) -> list[str]:
    texts = [
        _resolve_follow_task_resource_title(task),
        _normalize_text(task.work_title, max_length=255),
        _normalize_text(task.topic_title, max_length=255),
        _normalize_text(task.task_name, max_length=255),
        _normalize_text(task.last_candidate_title, max_length=255),
    ]
    return _dedupe_texts([item for item in texts if item], max_items=8, max_length=255)


def _build_follow_candidate_policy(raw_value: Any) -> dict[str, int]:
    raw = dict(raw_value or {}) if isinstance(raw_value, dict) else {}
    max_recall_candidates = _normalize_max_recall_candidates(raw.get("max_recall_candidates"))
    return {
        "lookback_days": _normalize_candidate_lookback_days(raw.get("lookback_days")),
        "max_recall_candidates": max_recall_candidates,
        "max_judge_candidates": _normalize_max_judge_candidates(
            raw.get("max_judge_candidates"),
            max_recall_candidates=max_recall_candidates,
        ),
    }


def _get_follow_candidate_policy(task: PanTransferSyncTask) -> dict[str, int]:
    return _build_follow_candidate_policy(_get_task_extra_section(task, "candidate_policy"))


def _build_follow_identity_fallback(task: PanTransferSyncTask) -> dict[str, Any]:
    resource_title = _resolve_follow_task_resource_title(task)
    reference_titles = _collect_follow_reference_texts(task)
    cleaned_titles = _dedupe_texts([_clean_follow_title(item) for item in reference_titles], max_items=6)
    core_title = cleaned_titles[0] if cleaned_titles else (_clean_follow_title(resource_title) or resource_title)
    aliases = _dedupe_texts(reference_titles + cleaned_titles, max_items=6)
    latest_episode = _extract_follow_episode_hint(*reference_titles)
    season = _extract_follow_season_hint(*reference_titles)
    source_message_snapshot = _normalize_source_message_snapshot(_get_task_extra_section(task, "source_message_snapshot"))
    reference_message_time = _serialize_json_value(
        _parse_datetime(source_message_snapshot.get("message_time")) or task.last_candidate_message_time
    )
    release_year = None
    for raw_value in reference_titles:
        matched = re.search(r"(19|20)\d{2}", raw_value)
        if matched is None:
            continue
        try:
            release_year = int(matched.group(0))
        except (TypeError, ValueError):
            release_year = None
        if release_year is not None:
            break
    search_queries = _dedupe_texts([core_title, *(aliases[:4])], max_items=4, max_length=80)
    return {
        "resource_title": resource_title,
        "core_title": core_title or (_normalize_text(task.topic_title, max_length=255) or f"resource_{int(task.id)}"),
        "aliases": aliases,
        "release_year": release_year,
        "season": season,
        "latest_episode": latest_episode,
        "content_type": None,
        "search_queries": search_queries,
        "reference_titles": reference_titles,
        "reference_message_time": reference_message_time,
        "reason": "fallback_title_extract",
        "source": "fallback",
        "updated_at": _serialize_json_value(utcnow()),
        "used_model": None,
        "used_api_mode": None,
    }


def _build_follow_identity_user_prompt(task: PanTransferSyncTask) -> str:
    source_message_snapshot = _normalize_source_message_snapshot(_get_task_extra_section(task, "source_message_snapshot"))
    reference_titles = _collect_follow_reference_texts(task)
    payload = {
        "platform": _normalize_text(task.platform, max_length=64) or None,
        "reference_titles": reference_titles,
        "source_message_title": _normalize_text(source_message_snapshot.get("title"), max_length=255) or None,
        "source_message_description": _normalize_text(source_message_snapshot.get("description"), max_length=1000) or None,
        "current_topic_title": _normalize_text(task.topic_title, max_length=255) or None,
        "current_work_title": _normalize_text(task.work_title, max_length=255) or None,
    }
    return (
        "从这些资源标题里提取追更识别身份。\n"
        "只返回 JSON，对象字段固定为："
        "core_title, aliases, release_year, season, latest_episode, content_type, search_queries, reason。\n"
        "要求：\n"
        "1. core_title 只保留作品本身名字，去掉年份、分辨率、帧率、集数范围、演员、更新文案。\n"
        "2. aliases 只保留同一作品的紧凑别名，不要放无关噪音。\n"
        "3. search_queries 用于站内召回，按从严格到宽松排序，最多 4 个。\n"
        "4. latest_episode 只填当前资源明确能看出的最新集数，没有就填 null。\n"
        "5. 如果不确定，也要尽量给出最稳妥的 core_title。\n\n"
        f"{_normalize_log_payload(payload)}"
    )


def _build_follow_identity_user_prompt_v2(task: PanTransferSyncTask) -> str:
    resource_title = _resolve_follow_task_resource_title(task)
    reference_titles = _collect_follow_reference_texts(task)
    payload = {
        "platform": _normalize_text(task.platform, max_length=64) or None,
        "resource_title": resource_title,
        "alternate_titles": [item for item in reference_titles if item != resource_title][:4],
    }
    return (
        "Extract a follow-tracking identity from the current resource title.\n"
        "Return JSON only with keys: core_title, aliases, release_year, season, latest_episode, content_type, search_queries, reason.\n"
        "Rules:\n"
        "1. Use resource_title as the primary input and treat alternate_titles only as fallback context.\n"
        "2. core_title should keep only the work name itself and strip year, resolution, frame rate, episode range, actor list, and update copy.\n"
        "3. aliases should contain only compact alternate names for the same work, without noisy metadata.\n"
        "4. search_queries should be ordered from strict to loose for in-site recall, with at most 4 items.\n"
        "5. latest_episode should only be filled when the current resource title clearly shows the latest episode; otherwise use null.\n"
        f"{_normalize_log_payload(payload)}"
    )


def _extract_follow_identity_with_ai(session: Session, *, task: PanTransferSyncTask) -> dict[str, Any]:
    route_result = execute_text_route(
        session,
        route_key=PAN_TRANSFER_FOLLOW_IDENTITY_ROUTE_KEY,
        system_prompt=(
            "你是追更同步的资源身份提取助手。"
            "你要从资源标题中提取作品核心标题和召回关键词。"
            "必须只返回 JSON 对象，不要输出解释。"
        ),
        user_prompt=_build_follow_identity_user_prompt_v2(task),
        metadata={
            "source": "pan_transfer_follow_identity",
            "task_id": int(task.id),
            "platform": _normalize_text(task.platform, max_length=64) or None,
        },
    )
    parsed = extract_json_object_from_text(route_result.text)
    if not isinstance(parsed, dict):
        raise ValueError("identity route did not return a JSON object")
    core_title = _clean_follow_title(parsed.get("core_title"))
    if not core_title:
        raise ValueError("identity route returned an empty core title")
    aliases = _dedupe_texts(
        [core_title, *list(parsed.get("aliases") or []), *_collect_follow_reference_texts(task)],
        max_items=6,
    )
    search_queries = _dedupe_texts(
        list(parsed.get("search_queries") or []) + [core_title, *aliases],
        max_items=4,
        max_length=80,
    )
    resource_title = _resolve_follow_task_resource_title(task)
    return {
        "resource_title": resource_title,
        "core_title": core_title,
        "aliases": aliases,
        "release_year": _normalize_optional_int(parsed.get("release_year")),
        "season": _normalize_optional_int(parsed.get("season")),
        "latest_episode": _normalize_optional_int(parsed.get("latest_episode")),
        "content_type": _normalize_text(parsed.get("content_type"), max_length=32) or None,
        "search_queries": search_queries,
        "reference_titles": _collect_follow_reference_texts(task),
        "reference_message_time": _serialize_json_value(_get_follow_reference_message_time(task, {})),
        "reason": _normalize_text(parsed.get("reason"), max_length=255) or "ai_identity_extract",
        "source": "ai",
        "updated_at": _serialize_json_value(utcnow()),
        "used_model": _normalize_text(route_result.model_id, max_length=255) or None,
        "used_api_mode": _normalize_text(route_result.used_api_mode, max_length=64) or None,
    }


def _ensure_follow_task_identity_snapshot(
    session: Session,
    *,
    task: PanTransferSyncTask,
) -> tuple[dict[str, Any], bool]:
    existing = _get_task_extra_section(task, "identity_snapshot")
    current_resource_title = _resolve_follow_task_resource_title(task)
    existing_resource_title = _normalize_text(existing.get("resource_title"), max_length=255)
    if existing.get("core_title") and existing_resource_title == current_resource_title:
        return existing, False
    try:
        snapshot = _extract_follow_identity_with_ai(session, task=task)
    except Exception as exc:
        logger.warning(
            "follow identity extraction fell back task_id=%s error=%s",
            int(task.id),
            _normalize_text(exc, max_length=1000) or type(exc).__name__,
        )
        snapshot = _build_follow_identity_fallback(task)
        snapshot["identity_error"] = _normalize_text(exc, max_length=500) or type(exc).__name__
    snapshot["resource_title"] = current_resource_title
    _set_task_extra_section(task, "identity_snapshot", snapshot)
    if not _normalize_text(task.work_title, max_length=255):
        task.topic_title = _normalize_text(snapshot.get("core_title"), max_length=255) or task.topic_title
    session.add(task)
    session.flush()
    return snapshot, True


def _append_follow_task_log(
    session: Session,
    *,
    task: PanTransferSyncTask,
    stage: str,
    message: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    normalized_payload = _normalize_log_payload(payload)
    normalized_stage = _normalize_text(stage, max_length=32) or "general"
    normalized_message = _normalize_text(message, max_length=4000)
    try:
        with session.begin_nested():
            session.add(
                PanTransferSyncTaskLog(
                    task_id=int(task.id),
                    level=_normalize_text(level, max_length=16) or "info",
                    stage=normalized_stage,
                    message=normalized_message,
                    payload=normalized_payload,
                )
            )
            session.flush()
    except Exception as exc:
        logger.warning(
            "failed to append follow task log task_id=%s stage=%s message=%s payload=%s error=%s",
            int(task.id),
            normalized_stage,
            normalized_message,
            normalized_payload,
            _normalize_text(exc, max_length=1000) or type(exc).__name__,
        )


def _serialize_follow_task_log(row: PanTransferSyncTaskLog) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "task_id": int(row.task_id),
        "level": str(row.level or "info"),
        "stage": str(row.stage or "general"),
        "message": str(row.message or ""),
        "payload": dict(row.payload or {}),
        "created_at": row.created_at,
    }


def _build_task_automation_config(raw_value: Any) -> dict[str, Any]:
    raw = dict(raw_value or {}) if isinstance(raw_value, dict) else {}
    switch_source_mode = _normalize_text(raw.get("switch_source_mode"), max_length=64).lower() or "source_invalid_only"
    if switch_source_mode not in {"disabled", "source_invalid_only", "candidate_preferred"}:
        switch_source_mode = "source_invalid_only"
    return {
        "enabled": bool(raw.get("enabled")),
        "switch_source_mode": switch_source_mode,
        "reuse_existing_share_if_valid": bool(raw.get("reuse_existing_share_if_valid", True)),
        "update_publish_record": bool(raw.get("update_publish_record", True)),
    }


def _build_follow_task_rule_assessment(row: PanTransferSyncTask) -> dict[str, Any]:
    task_state = _normalize_text(row.task_state, max_length=32).lower() or PAN_TRANSFER_SYNC_STATE_IDLE
    source_status = _normalize_text(row.source_link_status, max_length=32).lower() or "unknown"
    share_status = _normalize_text(row.current_share_status, max_length=32).lower() or "unknown"
    has_candidate = bool(_normalize_text(row.last_candidate_url))
    has_error = bool(_normalize_text(row.last_error_message, max_length=2000))

    if task_state in {
        PAN_TRANSFER_SYNC_STATE_QUEUED,
        PAN_TRANSFER_SYNC_STATE_CHECKING,
        PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED,
    }:
        return {
            "rule_key": "busy",
            "rule_label": "等待当前任务完成",
            "summary": "当前已经有检查或同步在进行，先等待本轮完成，再决定是否执行新的同步规则。",
            "recommended_source_kind": None,
            "recommended_sync_mode": None,
            "execution_mode": "busy",
            "risk_level": "info",
            "requires_manual_confirmation": False,
            "can_execute": False,
        }

    if has_candidate:
        return {
            "rule_key": "candidate_manual_review",
            "rule_label": "规则三：候选人工确认",
            "summary": (
                "已发现新的候选原链。为避免不同目录结构直接写入现有资源目录，"
                "默认先进入人工确认，核对目录或文件后再同步。"
            ),
            "recommended_source_kind": "candidate",
            "recommended_sync_mode": "incremental",
            "execution_mode": "manual_modal",
            "risk_level": "warning",
            "requires_manual_confirmation": True,
            "can_execute": True,
        }

    if source_status in {"invalid", "error"}:
        return {
            "rule_key": "await_candidate",
            "rule_label": "等待新候选原链",
            "summary": "当前原链已不可用，先重新检查或等待新的候选原链出现，再决定后续同步处理。",
            "recommended_source_kind": None,
            "recommended_sync_mode": None,
            "execution_mode": "wait_candidate",
            "risk_level": "warning",
            "requires_manual_confirmation": False,
            "can_execute": False,
        }

    if has_error:
        return {
            "rule_key": "recheck_required",
            "rule_label": "先重新检查",
            "summary": "最近一次跟踪出现异常，建议先重新检查，确认原链、分享和候选状态后再继续同步。",
            "recommended_source_kind": None,
            "recommended_sync_mode": None,
            "execution_mode": "recheck_only",
            "risk_level": "warning",
            "requires_manual_confirmation": False,
            "can_execute": True,
        }

    if share_status in {"invalid", "error"}:
        return {
            "rule_key": "safe_sync_current",
            "rule_label": "规则一：安全同步当前原链",
            "summary": "当前主要问题是对外分享异常。优先复用现有资源目录，从当前原链重新同步并刷新对外分享。",
            "recommended_source_kind": "current",
            "recommended_sync_mode": "standard",
            "execution_mode": "direct_sync",
            "risk_level": "info",
            "requires_manual_confirmation": False,
            "can_execute": True,
        }

    return {
        "rule_key": "safe_sync_current",
        "rule_label": "规则一：安全同步当前原链",
        "summary": "当前原链仍可用，默认复用现有资源目录执行安全同步，不主动删除旧内容。",
        "recommended_source_kind": "current",
        "recommended_sync_mode": "standard",
        "execution_mode": "direct_sync",
        "risk_level": "info",
        "requires_manual_confirmation": False,
        "can_execute": True,
    }


def _build_follow_publish_binding_snapshot(row: PanTransferPublishRecord | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "record_id": int(row.id),
        "published_title": _normalize_text(row.published_title, max_length=255) or None,
        "published_message_id": int(row.published_message_id) if row.published_message_id is not None else None,
        "published_at": row.published_at.isoformat() if row.published_at is not None else None,
        "source_url": _normalize_text(row.source_url) or None,
    }


def _sync_follow_task_publish_binding(
    task: PanTransferSyncTask,
    *,
    publish_record: PanTransferPublishRecord | None,
) -> None:
    extra_json = dict(task.extra_json or {})
    extra_json["publish_binding"] = _build_follow_publish_binding_snapshot(publish_record)
    task.publish_record_id = int(publish_record.id) if publish_record is not None else None
    task.extra_json = extra_json


def _can_bind_follow_publish_record(row: PanTransferPublishRecord | None) -> bool:
    if row is None or row.published_message_id is None:
        return False
    extra_json = dict(row.extra_json or {})
    lifecycle = dict(extra_json.get("lifecycle") or {})
    lifecycle_state = _normalize_text(lifecycle.get("state"), max_length=32).lower()
    return lifecycle_state not in {"frontend_offline", "resource_reclaimed"}


def _find_follow_task_publish_record(
    session: Session,
    *,
    task: PanTransferSyncTask,
) -> PanTransferPublishRecord | None:
    if task.publish_record_id is not None:
        row = session.get(PanTransferPublishRecord, int(task.publish_record_id))
        if _can_bind_follow_publish_record(row):
            return row
    if task.source_batch_item_id is None:
        return None
    rows = (
        session.query(PanTransferPublishRecord)
        .filter(PanTransferPublishRecord.source_batch_item_id == int(task.source_batch_item_id))
        .order_by(PanTransferPublishRecord.updated_at.desc(), PanTransferPublishRecord.id.desc())
        .all()
    )
    for row in rows:
        if _can_bind_follow_publish_record(row):
            return row
    return None


def bind_follow_task_publish_record(
    session: Session,
    *,
    task: PanTransferSyncTask,
) -> PanTransferPublishRecord | None:
    publish_record = _find_follow_task_publish_record(session, task=task)
    _sync_follow_task_publish_binding(task, publish_record=publish_record)
    session.add(task)
    session.flush()
    return publish_record


def _serialize_follow_task(row: PanTransferSyncTask) -> dict[str, Any]:
    extra_json = dict(row.extra_json or {})
    publish_binding = dict(extra_json.get("publish_binding") or {})
    last_sync = dict(extra_json.get("last_sync") or {})
    identity_snapshot = dict(extra_json.get("identity_snapshot") or {})
    candidate_assessment = dict(extra_json.get("candidate_assessment") or {})
    candidate_recall = dict(extra_json.get("candidate_recall") or {})
    candidate_policy = _build_follow_candidate_policy(extra_json.get("candidate_policy"))
    source_message_snapshot = _normalize_source_message_snapshot(dict(extra_json.get("source_message_snapshot") or {}))
    return {
        "id": int(row.id),
        "task_name": str(row.task_name or ""),
        "status": str(row.status or PAN_TRANSFER_SYNC_STATUS_ACTIVE),
        "task_state": str(row.task_state or PAN_TRANSFER_SYNC_STATE_IDLE),
        "platform": str(row.platform or ""),
        "source_batch_id": int(row.source_batch_id) if row.source_batch_id is not None else None,
        "source_batch_item_id": int(row.source_batch_item_id) if row.source_batch_item_id is not None else None,
        "source_link_target_id": int(row.source_link_target_id) if row.source_link_target_id is not None else None,
        "source_url": str(row.source_url or ""),
        "source_share_key": str(row.source_share_key or "") or None,
        "source_message_title": _normalize_text(source_message_snapshot.get("title"), max_length=255) or None,
        "topic_key": str(row.topic_key or ""),
        "topic_title": str(row.topic_title or ""),
        "work_id": int(row.work_id) if row.work_id is not None else None,
        "work_title": str(row.work_title or "") or None,
        "publish_record_id": int(row.publish_record_id) if row.publish_record_id is not None else _normalize_optional_int(publish_binding.get("record_id")),
        "publish_record_title": _normalize_text(publish_binding.get("published_title"), max_length=255) or None,
        "publish_record_message_id": _normalize_optional_int(publish_binding.get("published_message_id")),
        "publish_record_published_at": _parse_datetime(publish_binding.get("published_at")),
        "publish_record_source_url": _normalize_text(publish_binding.get("source_url")) or None,
        "target_account_id": int(row.target_account_id) if row.target_account_id is not None else None,
        "target_account_name": str(row.target_account_name or "") or None,
        "fixed_save_path": str(row.fixed_save_path or ""),
        "transfer_layout": str(row.transfer_layout or "independent"),
        "batch_folder_name": str(row.batch_folder_name or "") or None,
        "item_folder_mode": str(row.item_folder_mode or "auto"),
        "item_folder_template": str(row.item_folder_template or "") or None,
        "share_target_mode": str(row.share_target_mode or "resource_dir"),
        "current_share_url": str(row.current_share_url or "") or None,
        "current_share_link_target_id": int(row.current_share_link_target_id) if row.current_share_link_target_id is not None else None,
        "source_link_status": str(row.source_link_status or "unknown"),
        "current_share_status": str(row.current_share_status or "unknown"),
        "last_change_type": str(row.last_change_type or "") or None,
        "last_candidate_link_target_id": int(row.last_candidate_link_target_id) if row.last_candidate_link_target_id is not None else None,
        "last_candidate_url": str(row.last_candidate_url or "") or None,
        "last_candidate_title": str(row.last_candidate_title or "") or None,
        "last_candidate_message_time": row.last_candidate_message_time,
        "check_interval_minutes": int(row.check_interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES),
        "last_checked_at": row.last_checked_at,
        "next_check_at": row.next_check_at,
        "locked_by": str(row.locked_by or "") or None,
        "locked_at": row.locked_at,
        "last_error_message": str(row.last_error_message or "") or None,
        "last_sync_batch_id": _normalize_optional_int(last_sync.get("batch_id")),
        "last_sync_batch_item_id": _normalize_optional_int(last_sync.get("batch_item_id")),
        "last_sync_source_kind": _normalize_text(last_sync.get("source_kind"), max_length=32) or None,
        "last_sync_started_at": _parse_datetime(last_sync.get("started_at")),
        "rule_assessment": _build_follow_task_rule_assessment(row),
        "identity_snapshot": identity_snapshot,
        "candidate_assessment": candidate_assessment,
        "candidate_recall": candidate_recall,
        "candidate_policy": candidate_policy,
        "extra_json": extra_json,
        "created_by": str(row.created_by or "") or None,
        "updated_by": str(row.updated_by or "") or None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _get_follow_task(session: Session, *, task_id: int) -> PanTransferSyncTask:
    task = session.get(PanTransferSyncTask, int(task_id))
    if task is None:
        raise LookupError("follow task not found")
    return task


def _get_follow_task_logs(session: Session, *, task_id: int) -> list[dict[str, Any]]:
    rows = (
        session.query(PanTransferSyncTaskLog)
        .filter(PanTransferSyncTaskLog.task_id == int(task_id))
        .order_by(PanTransferSyncTaskLog.created_at.asc(), PanTransferSyncTaskLog.id.asc())
        .all()
    )
    return [_serialize_follow_task_log(row) for row in rows]


def get_pan_transfer_follow_task_detail(session: Session, *, task_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    return {
        "task": _serialize_follow_task(task),
        "logs": _get_follow_task_logs(session, task_id=int(task.id)),
    }


def clear_pan_transfer_follow_task_logs(session: Session, *, task_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    (
        session.query(PanTransferSyncTaskLog)
        .filter(PanTransferSyncTaskLog.task_id == int(task.id))
        .delete(synchronize_session=False)
    )
    session.flush()
    return {
        "task": _serialize_follow_task(task),
        "logs": [],
    }


def list_pan_transfer_follow_tasks(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    query = session.query(PanTransferSyncTask)
    normalized_status = _normalize_text(status, max_length=32).lower()
    if normalized_status in PAN_TRANSFER_SYNC_ALLOWED_STATUS:
        query = query.filter(PanTransferSyncTask.status == normalized_status)
    total = int(query.count() or 0)
    rows = (
        query.order_by(
            PanTransferSyncTask.updated_at.desc(),
            PanTransferSyncTask.next_check_at.asc().nullslast(),
            PanTransferSyncTask.id.desc(),
        )
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    return {
        "items": [_serialize_follow_task(row) for row in rows],
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
    }


def _build_follow_topic_payload(
    session: Session,
    *,
    item: PanTransferBatchItem,
) -> dict[str, Any]:
    lookup = get_work_binding_lookup(session, link_target_ids=[int(item.link_target_id)]).get(int(item.link_target_id), {})
    work_id = lookup.get("work_id")
    work_title = _normalize_text(lookup.get("work_title"), max_length=255) or None
    if work_id and work_title:
        return {
            "work_id": int(work_id),
            "work_title": work_title,
            "topic_key": f"work:{int(work_id)}",
            "topic_title": work_title,
        }
    topic_title = _normalize_text(item.short_title, max_length=255) or _normalize_text(item.latest_message_title, max_length=255) or f"资源 {int(item.link_target_id)}"
    return {
        "work_id": None,
        "work_title": None,
        "topic_key": f"link:{int(item.link_target_id)}",
        "topic_title": topic_title,
    }


def create_pan_transfer_follow_task_from_batch_item(
    session: Session,
    *,
    batch_id: int,
    item_id: int,
    payload: dict[str, Any] | None,
    created_by: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    item = (
        session.query(PanTransferBatchItem)
        .filter(
            PanTransferBatchItem.batch_id == int(batch_id),
            PanTransferBatchItem.id == int(item_id),
        )
        .first()
    )
    if item is None:
        raise LookupError("pan transfer batch item not found")

    existing = (
        session.query(PanTransferSyncTask)
        .filter(
            PanTransferSyncTask.status.in_([PAN_TRANSFER_SYNC_STATUS_ACTIVE, PAN_TRANSFER_SYNC_STATUS_PAUSED]),
            or_(
                PanTransferSyncTask.source_batch_item_id == int(item.id),
                PanTransferSyncTask.source_link_target_id == int(item.link_target_id),
            ),
        )
        .first()
    )
    if existing is not None:
        raise ValueError(f"follow task #{int(existing.id)} already exists for this resource")

    source_target = session.get(LinkTarget, int(item.link_target_id))
    current_share_target = session.get(LinkTarget, int(item.new_link_target_id)) if item.new_link_target_id is not None else None
    account = session.get(PanTransferAccount, int(item.target_account_id)) if item.target_account_id is not None else None
    extra_json = dict(item.extra_json or {})
    resolved_paths = dict(extra_json.get("resolved_paths") or {})
    path_strategy = dict(extra_json.get("path_strategy") or {})
    share_validation = dict(extra_json.get("share_validation") or {})
    source_message_snapshot = _normalize_source_message_snapshot(dict(extra_json.get("source_message_snapshot") or {}))
    if not source_message_snapshot.get("message_time") and item.latest_message_time is not None:
        source_message_snapshot["message_time"] = _serialize_json_value(item.latest_message_time)
    topic_payload = _build_follow_topic_payload(session, item=item)
    interval_minutes = _normalize_interval_minutes((payload or {}).get("check_interval_minutes"))
    candidate_policy = _build_follow_candidate_policy((payload or {}).get("candidate_policy"))
    task_name = (
        _normalize_text((payload or {}).get("task_name"), max_length=255)
        or topic_payload["topic_title"]
        or _normalize_text(item.short_title, max_length=255)
        or f"追更任务 {int(item.id)}"
    )
    source_url = (
        _normalize_text(getattr(source_target, "original_url", None))
        or _normalize_text(item.original_url)
    )
    if not source_url:
        raise ValueError("source url is missing")

    current_share_url = (
        _normalize_text(getattr(current_share_target, "original_url", None))
        or _normalize_text(item.new_share_url)
        or source_url
    )
    current_share_link_target_id = (
        int(item.new_link_target_id)
        if item.new_link_target_id is not None
        else (int(item.link_target_id) if source_url == current_share_url else None)
    )
    fixed_save_path = normalize_relative_path(_normalize_text(resolved_paths.get("resolved_path"), max_length=512))
    source_share_key = _normalize_text(getattr(source_target, "share_key", None), max_length=255) or None
    current_share_status = _normalize_text(share_validation.get("status"), max_length=32).lower() or (
        _normalize_text(item.latest_link_health, max_length=32).lower() if current_share_url == source_url else "unknown"
    )
    publish_record = (
        session.query(PanTransferPublishRecord)
        .filter(PanTransferPublishRecord.source_batch_item_id == int(item.id))
        .order_by(PanTransferPublishRecord.updated_at.desc(), PanTransferPublishRecord.id.desc())
        .first()
    )
    task = PanTransferSyncTask(
        task_name=task_name,
        status=PAN_TRANSFER_SYNC_STATUS_ACTIVE,
        task_state=PAN_TRANSFER_SYNC_STATE_QUEUED,
        platform=str(item.platform or ""),
        source_batch_id=int(item.batch_id),
        source_batch_item_id=int(item.id),
        source_link_target_id=int(item.link_target_id),
        source_url=source_url,
        source_share_key=source_share_key,
        topic_key=str(topic_payload["topic_key"]),
        topic_title=str(topic_payload["topic_title"]),
        work_id=int(topic_payload["work_id"]) if topic_payload["work_id"] is not None else None,
        work_title=str(topic_payload["work_title"] or "") or None,
        publish_record_id=int(publish_record.id) if publish_record is not None else None,
        target_account_id=int(item.target_account_id) if item.target_account_id is not None else None,
        target_account_name=_normalize_text(getattr(account, "account_name", None), max_length=128) or _normalize_text(extra_json.get("recommended_account_name"), max_length=128) or None,
        fixed_save_path=fixed_save_path,
        transfer_layout=_normalize_text(resolved_paths.get("transfer_layout"), max_length=32) or _normalize_text(path_strategy.get("transfer_layout"), max_length=32) or "independent",
        batch_folder_name=_normalize_text(resolved_paths.get("batch_folder_name"), max_length=120) or None,
        item_folder_mode=_normalize_text(path_strategy.get("item_folder_mode"), max_length=32) or "auto",
        item_folder_template=_normalize_text(path_strategy.get("item_folder_template"), max_length=120) or None,
        share_target_mode=_normalize_text(resolved_paths.get("share_target_mode"), max_length=32) or _normalize_text(path_strategy.get("share_target_mode"), max_length=32) or "resource_dir",
        current_share_url=current_share_url or None,
        current_share_link_target_id=current_share_link_target_id,
        source_link_status=_normalize_text(item.latest_link_health, max_length=32).lower() or "unknown",
        current_share_status=current_share_status or "unknown",
        check_interval_minutes=interval_minutes,
        next_check_at=utcnow(),
        extra_json={
            "source_message_snapshot": _normalize_source_message_snapshot(source_message_snapshot),
            "path_strategy": path_strategy,
            "resolved_paths": resolved_paths,
            "publish_binding": _build_follow_publish_binding_snapshot(publish_record),
            "automation": _build_task_automation_config((payload or {}).get("automation")),
            "candidate_policy": candidate_policy,
            "created_from_batch_item": {
                "batch_id": int(item.batch_id),
                "item_id": int(item.id),
            },
        },
        created_by=_normalize_text(created_by, max_length=128) or None,
        updated_by=_normalize_text(created_by, max_length=128) or None,
    )
    session.add(task)
    session.flush()
    identity_snapshot, identity_created = _ensure_follow_task_identity_snapshot(session, task=task)
    _append_follow_task_log(
        session,
        task=task,
        stage="setup",
        message="Follow task created from transfer batch item",
        payload={
            "source_batch_id": int(item.batch_id),
            "source_batch_item_id": int(item.id),
            "source_url": source_url,
            "current_share_url": current_share_url,
            "fixed_save_path": fixed_save_path,
        },
    )
    if identity_created:
        _append_follow_task_log(
            session,
            task=task,
            stage="identity",
            message="Built follow task identity snapshot",
            payload=identity_snapshot,
        )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def queue_pan_transfer_follow_task_check(
    session: Session,
    *,
    task_id: int,
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    if str(task.status or "") != PAN_TRANSFER_SYNC_STATUS_ACTIVE:
        raise ValueError("only active follow tasks can be queued")
    task.task_state = PAN_TRANSFER_SYNC_STATE_QUEUED
    task.next_check_at = utcnow()
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="queue",
        message="Follow task queued for immediate check",
        payload={"operator": _normalize_text(operator, max_length=128) or None},
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def pause_pan_transfer_follow_task(
    session: Session,
    *,
    task_id: int,
    operator: str | None,
) -> dict[str, Any]:
    task = _get_follow_task(session, task_id=task_id)
    task.status = PAN_TRANSFER_SYNC_STATUS_PAUSED
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    task.next_check_at = None
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="control",
        message="Follow task paused",
        payload={"operator": _normalize_text(operator, max_length=128) or None},
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def resume_pan_transfer_follow_task(
    session: Session,
    *,
    task_id: int,
    operator: str | None,
) -> dict[str, Any]:
    task = _get_follow_task(session, task_id=task_id)
    task.status = PAN_TRANSFER_SYNC_STATUS_ACTIVE
    task.task_state = PAN_TRANSFER_SYNC_STATE_QUEUED
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    task.next_check_at = utcnow()
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="control",
        message="Follow task resumed and queued",
        payload={"operator": _normalize_text(operator, max_length=128) or None},
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def update_pan_transfer_follow_task_settings(
    session: Session,
    *,
    task_id: int,
    payload: dict[str, Any] | None,
    operator: str | None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    update_payload = dict(payload or {})

    next_interval_minutes = int(task.check_interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES)
    if "check_interval_minutes" in update_payload:
        next_interval_minutes = _normalize_interval_minutes(update_payload.get("check_interval_minutes"))
        task.check_interval_minutes = next_interval_minutes

    next_candidate_policy = _get_follow_candidate_policy(task)
    if "candidate_policy" in update_payload:
        raw_candidate_policy = update_payload.get("candidate_policy")
        merged_candidate_policy = {
            **next_candidate_policy,
            **(dict(raw_candidate_policy) if isinstance(raw_candidate_policy, dict) else {}),
        }
        next_candidate_policy = _build_follow_candidate_policy(merged_candidate_policy)
        _set_task_extra_section(task, "candidate_policy", next_candidate_policy)

    if str(task.status or "") == PAN_TRANSFER_SYNC_STATUS_ACTIVE and str(task.task_state or "") not in {
        PAN_TRANSFER_SYNC_STATE_QUEUED,
        PAN_TRANSFER_SYNC_STATE_CHECKING,
        PAN_TRANSFER_SYNC_STATE_SYNC_QUEUED,
    }:
        task.next_check_at = _next_check_time(interval_minutes=next_interval_minutes)
    if str(task.status or "") == PAN_TRANSFER_SYNC_STATUS_PAUSED:
        task.next_check_at = None

    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="settings",
        message="Updated follow task settings",
        payload={
            "operator": _normalize_text(operator, max_length=128) or None,
            "check_interval_minutes": next_interval_minutes,
            "candidate_policy": next_candidate_policy,
        },
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def clear_pan_transfer_follow_task_candidate(
    session: Session,
    *,
    task_id: int,
    operator: str | None,
    reason: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    if not task.last_candidate_url and task.last_candidate_link_target_id is None:
        return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))

    previous_candidate_payload = {
        "link_target_id": int(task.last_candidate_link_target_id) if task.last_candidate_link_target_id is not None else None,
        "url": str(task.last_candidate_url or ""),
        "title": str(task.last_candidate_title or "") or None,
        "latest_message_time": task.last_candidate_message_time,
        "reason": _normalize_text(reason, max_length=64) or "manual_clear",
    }
    _clear_follow_task_candidate_fields(task)
    _apply_follow_task_state_without_candidate(task)
    task.updated_by = _normalize_text(operator, max_length=128) or task.updated_by
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="candidate",
        message="Cleared the stored candidate source",
        payload={
            **previous_candidate_payload,
            "operator": _normalize_text(operator, max_length=128) or None,
        },
    )
    session.flush()
    return get_pan_transfer_follow_task_detail(session, task_id=int(task.id))


def delete_pan_transfer_follow_task(session: Session, *, task_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    task = _get_follow_task(session, task_id=task_id)
    (
        session.query(PanTransferSyncTaskLog)
        .filter(PanTransferSyncTaskLog.task_id == int(task.id))
        .delete(synchronize_session=False)
    )
    session.delete(task)
    session.flush()
    return {"id": int(task_id), "deleted": True}


def _build_task_excluded_target_ids(task: PanTransferSyncTask) -> list[int]:
    excluded: list[int] = []
    for raw_value in [task.source_link_target_id, task.current_share_link_target_id, task.last_candidate_link_target_id]:
        if raw_value is None:
            continue
        value = int(raw_value)
        if value <= 0 or value in excluded:
            continue
        excluded.append(value)
    return excluded


def _is_useful_follow_query(value: Any) -> bool:
    normalized = _normalize_match_key(value)
    if not normalized:
        return False
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in normalized)
    return len(normalized) >= (2 if has_cjk else 4)


def _build_follow_candidate_payload(row: Any, *, fallback_title: str) -> dict[str, Any]:
    latest_message_title = _normalize_text(getattr(row, "latest_message_title", None), max_length=255)
    display_text = _normalize_text(getattr(row, "display_text", None), max_length=255)
    return {
        "link_target_id": int(row.link_target_id),
        "url": _normalize_text(getattr(row, "original_url", None)),
        "title": latest_message_title or display_text or fallback_title,
        "display_text": display_text or None,
        "description": _normalize_text(getattr(row, "latest_message_description", None), max_length=1000) or None,
        "latest_message_time": getattr(row, "latest_message_time", None),
    }


def _merge_follow_candidate_lists(*candidate_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for candidate_list in candidate_lists:
        for candidate in candidate_list:
            link_target_id = _normalize_optional_int(candidate.get("link_target_id"))
            if link_target_id is None:
                continue
            previous = merged.get(link_target_id)
            if previous is None:
                merged[link_target_id] = candidate
                continue
            previous_time = previous.get("latest_message_time")
            next_time = candidate.get("latest_message_time")
            if isinstance(next_time, datetime) and (
                not isinstance(previous_time, datetime) or next_time > previous_time
            ):
                merged[link_target_id] = candidate
    return sorted(
        merged.values(),
        key=lambda item: (
            item.get("latest_message_time") or datetime.min,
            _normalize_optional_int(item.get("link_target_id")) or 0,
        ),
        reverse=True,
    )


def _list_follow_candidates_by_work(session: Session, *, task: PanTransferSyncTask) -> list[dict[str, Any]]:
    if task.work_id is None:
        return []
    candidate_policy = _get_follow_candidate_policy(task)
    excluded_ids = _build_task_excluded_target_ids(task)
    earliest_message_time = utcnow() - timedelta(days=int(candidate_policy["lookback_days"]))
    latest_ref_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.max(MessageLinkRef.id).label("latest_ref_id"),
        )
        .filter(
            or_(
                MessageLinkRef.message_timestamp.is_(None),
                MessageLinkRef.message_timestamp >= earliest_message_time,
            )
        )
        .group_by(MessageLinkRef.link_target_id)
        .subquery()
    )
    latest_ref = aliased(MessageLinkRef)
    latest_message = aliased(Message)
    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.original_url.label("original_url"),
            latest_ref.display_text.label("display_text"),
            latest_message.title.label("latest_message_title"),
            latest_message.description.label("latest_message_description"),
            latest_ref.message_timestamp.label("latest_message_time"),
        )
        .join(ResourceWorkBinding, ResourceWorkBinding.link_target_id == LinkTarget.id)
        .join(latest_ref_subquery, latest_ref_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .filter(
            ResourceWorkBinding.work_id == int(task.work_id),
            ResourceWorkBinding.match_status == "matched",
            LinkTarget.platform == str(task.platform or ""),
        )
    )
    if excluded_ids:
        query = query.filter(~LinkTarget.id.in_(excluded_ids))
    query = query.order_by(
        latest_ref.message_timestamp.desc().nullslast(),
        LinkTarget.last_seen_at.desc(),
        LinkTarget.id.desc(),
    ).limit(int(candidate_policy["max_recall_candidates"]))
    return [
        _build_follow_candidate_payload(row, fallback_title=_normalize_text(task.topic_title, max_length=255) or f"task_{int(task.id)}")
        for row in query.all()
    ]


def _build_follow_candidate_search_queries(task: PanTransferSyncTask, snapshot: dict[str, Any]) -> list[str]:
    queries = list(snapshot.get("search_queries") or [])
    queries.extend(snapshot.get("aliases") or [])
    queries.extend([snapshot.get("core_title"), task.work_title, task.topic_title])
    return _dedupe_texts([item for item in queries if _is_useful_follow_query(item)], max_items=4, max_length=80)


def _list_follow_candidates_by_identity(
    session: Session,
    *,
    task: PanTransferSyncTask,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    queries = _build_follow_candidate_search_queries(task, snapshot)
    if not queries:
        return []
    candidate_policy = _get_follow_candidate_policy(task)
    excluded_ids = _build_task_excluded_target_ids(task)
    earliest_message_time = utcnow() - timedelta(days=int(candidate_policy["lookback_days"]))
    latest_ref_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.max(MessageLinkRef.id).label("latest_ref_id"),
        )
        .filter(
            or_(
                MessageLinkRef.message_timestamp.is_(None),
                MessageLinkRef.message_timestamp >= earliest_message_time,
            )
        )
        .group_by(MessageLinkRef.link_target_id)
        .subquery()
    )
    latest_ref = aliased(MessageLinkRef)
    latest_message = aliased(Message)
    like_filters: list[Any] = []
    for query in queries:
        like_pattern = f"%{query}%"
        like_filters.extend(
            [
                latest_message.title.ilike(like_pattern),
                latest_message.description.ilike(like_pattern),
                latest_ref.display_text.ilike(like_pattern),
            ]
        )
    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.original_url.label("original_url"),
            latest_ref.display_text.label("display_text"),
            latest_message.title.label("latest_message_title"),
            latest_message.description.label("latest_message_description"),
            latest_ref.message_timestamp.label("latest_message_time"),
        )
        .join(latest_ref_subquery, latest_ref_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .filter(LinkTarget.platform == str(task.platform or ""), or_(*like_filters))
    )
    if excluded_ids:
        query = query.filter(~LinkTarget.id.in_(excluded_ids))
    query = query.order_by(
        latest_ref.message_timestamp.desc().nullslast(),
        LinkTarget.last_seen_at.desc(),
        LinkTarget.id.desc(),
    ).limit(int(candidate_policy["max_recall_candidates"]))
    return [
        _build_follow_candidate_payload(row, fallback_title=_normalize_text(snapshot.get("core_title"), max_length=255) or f"task_{int(task.id)}")
        for row in query.all()
    ]


def _get_follow_reference_message_time(task: PanTransferSyncTask, snapshot: dict[str, Any]) -> datetime | None:
    parsed = _parse_datetime(snapshot.get("reference_message_time"))
    if parsed is not None:
        return parsed
    source_message_snapshot = _normalize_source_message_snapshot(_get_task_extra_section(task, "source_message_snapshot"))
    parsed = _parse_datetime(source_message_snapshot.get("message_time"))
    if parsed is not None:
        return parsed
    return None


def _judge_follow_candidate_fallback(
    task: PanTransferSyncTask,
    *,
    snapshot: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    candidate_title = _normalize_text(candidate.get("title"), max_length=255)
    current_resource_title = _normalize_text(snapshot.get("resource_title"), max_length=255) or _resolve_follow_task_resource_title(task)
    query_keys = [
        _normalize_match_key(snapshot.get("core_title")),
        *[_normalize_match_key(item) for item in list(snapshot.get("aliases") or [])],
        *[_normalize_match_key(item) for item in list(snapshot.get("search_queries") or [])],
    ]
    candidate_key = _normalize_match_key(candidate_title)
    same_work = any(key and key in candidate_key for key in query_keys)
    current_episode = _normalize_optional_int(snapshot.get("latest_episode")) or _extract_follow_episode_hint(
        current_resource_title,
    )
    candidate_episode = _extract_follow_episode_hint(candidate_title)
    is_newer = bool(same_work and current_episode is not None and candidate_episode is not None and candidate_episode > current_episode)
    return {
        "is_same_work": same_work,
        "is_newer": is_newer,
        "should_promote": bool(same_work and is_newer),
        "confidence": 0.66 if same_work and is_newer else (0.5 if same_work else 0.2),
        "current_episode": current_episode,
        "candidate_episode": candidate_episode,
        "reason": (
            "fallback_episode_compare"
            if same_work and current_episode is not None and candidate_episode is not None
            else "fallback_keyword_compare"
        ),
        "judge_source": "fallback",
    }


def _build_follow_candidate_judge_user_prompt(
    task: PanTransferSyncTask,
    *,
    snapshot: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    payload = {
        "tracked_resource": {
            "platform": _normalize_text(task.platform, max_length=64) or None,
            "core_title": snapshot.get("core_title"),
            "aliases": list(snapshot.get("aliases") or []),
            "release_year": snapshot.get("release_year"),
            "season": snapshot.get("season"),
            "latest_episode": snapshot.get("latest_episode"),
            "reference_titles": list(snapshot.get("reference_titles") or []),
            "reference_message_time": snapshot.get("reference_message_time")
            or _serialize_json_value(_get_follow_reference_message_time(task, snapshot)),
        },
        "candidate": {
            "title": candidate.get("title"),
            "display_text": candidate.get("display_text"),
            "description": candidate.get("description"),
            "latest_message_time": _serialize_json_value(candidate.get("latest_message_time")),
        },
    }
    return (
        "判断这个候选资源是否应该成为追更候选。\n"
        "只返回 JSON，对象字段固定为："
        "is_same_work, is_newer, should_promote, confidence, current_episode, candidate_episode, reason。\n"
        "要求：\n"
        "1. 必须先判断是不是同一作品。\n"
        "2. 只有同一作品且候选明显比当前资源更新时，should_promote 才能为 true。\n"
        "3. 如果标题只是噪音不同，但核心作品一致，也算同一作品。\n"
        "4. 如果候选集数更高、更新时间更晚，优先判断为更新。\n\n"
        f"{_normalize_log_payload(payload)}"
    )


def _build_follow_candidate_judge_user_prompt_v2(
    task: PanTransferSyncTask,
    *,
    snapshot: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    payload = {
        "tracked_resource": {
            "platform": _normalize_text(task.platform, max_length=64) or None,
            "resource_title": _normalize_text(snapshot.get("resource_title"), max_length=255) or _resolve_follow_task_resource_title(task),
            "core_title": snapshot.get("core_title"),
            "aliases": list(snapshot.get("aliases") or []),
            "release_year": snapshot.get("release_year"),
            "season": snapshot.get("season"),
            "latest_episode": snapshot.get("latest_episode"),
            "search_queries": list(snapshot.get("search_queries") or []),
        },
        "candidate": {
            "title": _normalize_text(candidate.get("title"), max_length=255) or None,
        },
    }
    return (
        "Decide whether this candidate source should be promoted for follow sync.\n"
        "Return JSON only with keys: is_same_work, is_newer, should_promote, confidence, current_episode, candidate_episode, reason.\n"
        "Rules:\n"
        "1. First determine whether the candidate is the same work.\n"
        "2. should_promote can be true only when it is the same work and clearly newer than the tracked resource.\n"
        "3. Treat title formatting differences as the same work when the core work identity still matches.\n"
        "4. Prefer episode progress as the main newer signal.\n"
        f"{_normalize_log_payload(payload)}"
    )


def _judge_follow_candidate_with_ai(
    session: Session,
    *,
    task: PanTransferSyncTask,
    snapshot: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    route_result = execute_text_route(
        session,
        route_key=PAN_TRANSFER_FOLLOW_CANDIDATE_JUDGE_ROUTE_KEY,
        system_prompt=(
            "你是追更候选裁决助手。"
            "你只负责判断候选是不是同一作品，以及是不是比当前资源更新。"
            "必须只返回 JSON。"
        ),
        user_prompt=_build_follow_candidate_judge_user_prompt_v2(task, snapshot=snapshot, candidate=candidate),
        metadata={
            "source": "pan_transfer_follow_candidate_judge",
            "task_id": int(task.id),
            "candidate_link_target_id": int(candidate.get("link_target_id") or 0),
        },
    )
    parsed = extract_json_object_from_text(route_result.text)
    if not isinstance(parsed, dict):
        raise ValueError("candidate judge route did not return a JSON object")
    same_work = _normalize_optional_bool(parsed.get("is_same_work"))
    is_newer = _normalize_optional_bool(parsed.get("is_newer"))
    should_promote = _normalize_optional_bool(parsed.get("should_promote"))
    if same_work is None or is_newer is None or should_promote is None:
        raise ValueError("candidate judge route returned invalid booleans")
    return {
        "is_same_work": same_work,
        "is_newer": is_newer,
        "should_promote": should_promote,
        "confidence": float(parsed.get("confidence") or 0),
        "current_episode": _normalize_optional_int(parsed.get("current_episode")),
        "candidate_episode": _normalize_optional_int(parsed.get("candidate_episode")),
        "reason": _normalize_text(parsed.get("reason"), max_length=255) or "ai_candidate_judge",
        "judge_source": "ai",
        "used_model": _normalize_text(route_result.model_id, max_length=255) or None,
        "used_api_mode": _normalize_text(route_result.used_api_mode, max_length=64) or None,
    }


def _build_follow_candidate_recall_snapshot(
    *,
    task: PanTransferSyncTask,
    snapshot: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_policy = _get_follow_candidate_policy(task)
    return {
        "queries": _build_follow_candidate_search_queries(task, snapshot),
        "recall_count": len(candidates),
        "judge_limit": int(candidate_policy["max_judge_candidates"]),
        "items": [
            {
                "link_target_id": _normalize_optional_int(item.get("link_target_id")),
                "title": _normalize_text(item.get("title"), max_length=255) or None,
                "url": _normalize_text(item.get("url"), max_length=1000) or None,
                "latest_message_time": _serialize_json_value(item.get("latest_message_time")),
            }
            for item in candidates
        ],
    }


def _pick_follow_candidate(
    session: Session,
    *,
    task: PanTransferSyncTask,
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    candidate_policy = _get_follow_candidate_policy(task)
    recalled_candidates = _merge_follow_candidate_lists(
        _list_follow_candidates_by_work(session, task=task),
        _list_follow_candidates_by_identity(session, task=task, snapshot=snapshot),
    )[: int(candidate_policy["max_recall_candidates"])]
    recall_snapshot = _build_follow_candidate_recall_snapshot(task=task, snapshot=snapshot, candidates=recalled_candidates)
    if not recalled_candidates:
        return (
            None,
            {
                "judge_source": "none",
                "reason": "no_recalled_candidate",
                "recall_count": 0,
                "queries": list(recall_snapshot.get("queries") or []),
            },
            recall_snapshot,
        )

    last_assessment: dict[str, Any] | None = None
    for candidate in recalled_candidates[: int(candidate_policy["max_judge_candidates"])]:
        try:
            assessment = _judge_follow_candidate_with_ai(session, task=task, snapshot=snapshot, candidate=candidate)
        except Exception as exc:
            logger.warning(
                "follow candidate judge fell back task_id=%s candidate=%s error=%s",
                int(task.id),
                int(candidate.get("link_target_id") or 0),
                _normalize_text(exc, max_length=1000) or type(exc).__name__,
            )
            assessment = _judge_follow_candidate_fallback(task, snapshot=snapshot, candidate=candidate)
            assessment["judge_error"] = _normalize_text(exc, max_length=500) or type(exc).__name__
        assessment["checked_at"] = _serialize_json_value(utcnow())
        assessment["candidate_link_target_id"] = int(candidate.get("link_target_id") or 0)
        assessment["candidate_title"] = _normalize_text(candidate.get("title"), max_length=255) or None
        assessment["recall_count"] = len(recalled_candidates)
        assessment["queries"] = list(recall_snapshot.get("queries") or [])
        last_assessment = assessment
        if assessment.get("should_promote"):
            recall_snapshot["selected_link_target_id"] = _normalize_optional_int(candidate.get("link_target_id"))
            return candidate, assessment, recall_snapshot
    return None, last_assessment, recall_snapshot


async def _safe_validate_url(url: str | None) -> dict[str, Any]:
    normalized_url = _normalize_text(url)
    if not normalized_url:
        return {"status": "unknown", "detail_message": None, "result": None}
    try:
        return await validate_share_url(normalized_url)
    except Exception as exc:
        return {
            "status": "error",
            "detail_message": _normalize_text(exc, max_length=1000) or type(exc).__name__,
            "result": None,
        }


def _is_healthy_link_status(value: Any) -> bool:
    normalized = _normalize_text(value, max_length=32).lower()
    return normalized in {"valid", "healthy"}


def _clear_follow_task_candidate_fields(task: PanTransferSyncTask) -> None:
    task.last_candidate_link_target_id = None
    task.last_candidate_url = None
    task.last_candidate_title = None
    task.last_candidate_message_time = None
    _set_task_extra_section(task, "candidate_assessment", None)
    _set_task_extra_section(task, "candidate_recall", None)


def _apply_follow_task_state_without_candidate(task: PanTransferSyncTask) -> None:
    if _normalize_text(task.source_link_status, max_length=32).lower() == "invalid":
        task.task_state = PAN_TRANSFER_SYNC_STATE_SOURCE_INVALID
        task.last_change_type = "source_invalid"
        return
    if task.current_share_url and _normalize_text(task.current_share_status, max_length=32).lower() == "invalid":
        task.task_state = PAN_TRANSFER_SYNC_STATE_SHARE_INVALID
        task.last_change_type = "share_invalid"
        return
    task.task_state = PAN_TRANSFER_SYNC_STATE_IDLE
    task.last_change_type = "no_change"


async def _process_pan_transfer_follow_task_async(
    session: Session,
    *,
    task: PanTransferSyncTask,
    worker_name: str,
) -> None:
    _append_follow_task_log(
        session,
        task=task,
        stage="check",
        message="Starting follow task check",
        payload={
            "worker_name": worker_name,
            "source_url": str(task.source_url or ""),
            "current_share_url": str(task.current_share_url or "") or None,
        },
    )

    source_status = await _safe_validate_url(task.source_url)
    task.source_link_status = _normalize_text(source_status.get("status"), max_length=32).lower() or "unknown"
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="source",
        message=f"Source link validation finished with status: {task.source_link_status}",
        level="warning" if task.source_link_status in {"invalid", "error"} else "info",
        payload=dict(source_status),
    )

    share_status = await _safe_validate_url(task.current_share_url)
    task.current_share_status = _normalize_text(share_status.get("status"), max_length=32).lower() or "unknown"
    session.add(task)
    session.flush()
    _append_follow_task_log(
        session,
        task=task,
        stage="share",
        message=f"Current share validation finished with status: {task.current_share_status}",
        level="warning" if task.current_share_status in {"invalid", "error"} else "info",
        payload=dict(share_status),
    )

    identity_snapshot, identity_created = _ensure_follow_task_identity_snapshot(session, task=task)
    if identity_created:
        _append_follow_task_log(
            session,
            task=task,
            stage="identity",
            message="Built follow task identity snapshot",
            payload=identity_snapshot,
        )

    healthy_existing_candidate: dict[str, Any] | None = None
    existing_candidate_assessment: dict[str, Any] | None = None
    if task.last_candidate_url:
        existing_candidate_payload = {
            "link_target_id": int(task.last_candidate_link_target_id) if task.last_candidate_link_target_id is not None else None,
            "url": str(task.last_candidate_url or ""),
            "title": str(task.last_candidate_title or "") or None,
            "latest_message_time": task.last_candidate_message_time,
        }
        existing_candidate_status = await _safe_validate_url(task.last_candidate_url)
        normalized_existing_candidate_status = _normalize_text(
            existing_candidate_status.get("status"), max_length=32
        ).lower() or "unknown"
        if _is_healthy_link_status(normalized_existing_candidate_status):
            healthy_existing_candidate = existing_candidate_payload
            existing_candidate_assessment = {
                "is_same_work": True,
                "is_newer": True,
                "should_promote": True,
                "confidence": 1.0,
                "current_episode": _normalize_optional_int(identity_snapshot.get("latest_episode")),
                "candidate_episode": None,
                "reason": "stored_candidate_still_valid",
                "judge_source": "stored_candidate",
                "candidate_link_target_id": existing_candidate_payload.get("link_target_id"),
                "candidate_title": existing_candidate_payload.get("title"),
                "checked_at": _serialize_json_value(utcnow()),
                "validation_status": normalized_existing_candidate_status,
                "validation_detail_message": existing_candidate_status.get("detail_message"),
            }
        else:
            _clear_follow_task_candidate_fields(task)
            session.add(task)
            session.flush()
            _append_follow_task_log(
                session,
                task=task,
                stage="candidate",
                level="warning",
                message=(
                    "Removed the stored candidate source because link validation "
                    f"finished with status: {normalized_existing_candidate_status}"
                ),
                payload={
                    **existing_candidate_payload,
                    "candidate_status": normalized_existing_candidate_status,
                    "candidate_detail_message": existing_candidate_status.get("detail_message"),
                },
            )

    candidate_discarded = False
    candidate, candidate_assessment, candidate_recall = _pick_follow_candidate(
        session,
        task=task,
        snapshot=identity_snapshot,
    )
    selected_candidate: dict[str, Any] | None = None
    selected_assessment = dict(candidate_assessment or {}) if candidate_assessment else None
    if candidate is not None:
        candidate_status = await _safe_validate_url(str(candidate.get("url") or ""))
        normalized_candidate_status = _normalize_text(candidate_status.get("status"), max_length=32).lower() or "unknown"
        if selected_assessment is None:
            selected_assessment = {}
        selected_assessment["validation_status"] = normalized_candidate_status
        selected_assessment["validation_detail_message"] = candidate_status.get("detail_message")
        if _is_healthy_link_status(normalized_candidate_status):
            selected_candidate = candidate
        else:
            candidate_discarded = True
            _append_follow_task_log(
                session,
                task=task,
                stage="candidate",
                level="warning",
                message=(
                    "Discarded a detected candidate source because link validation "
                    f"finished with status: {normalized_candidate_status}"
                ),
                payload={
                    **dict(candidate),
                    "candidate_status": normalized_candidate_status,
                    "candidate_detail_message": candidate_status.get("detail_message"),
                    "candidate_assessment": selected_assessment,
                },
            )

    if selected_candidate is not None:
        candidate_recall["selected_link_target_id"] = _normalize_optional_int(selected_candidate.get("link_target_id"))
        _set_task_extra_section(task, "candidate_recall", candidate_recall)
        _set_task_extra_section(task, "candidate_assessment", selected_assessment)
        task.task_state = PAN_TRANSFER_SYNC_STATE_CANDIDATE_FOUND
        task.last_change_type = "candidate_found"
        task.last_candidate_link_target_id = int(selected_candidate["link_target_id"])
        task.last_candidate_url = str(selected_candidate["url"])
        task.last_candidate_title = str(selected_candidate["title"])
        task.last_candidate_message_time = selected_candidate.get("latest_message_time")
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            message="Detected a recent candidate source link for this tracked resource",
            payload={
                **dict(selected_candidate),
                "candidate_assessment": selected_assessment,
                "candidate_recall": candidate_recall,
            },
        )
        return

    if healthy_existing_candidate is not None:
        _set_task_extra_section(task, "candidate_recall", candidate_recall)
        _set_task_extra_section(task, "candidate_assessment", existing_candidate_assessment)
        task.task_state = PAN_TRANSFER_SYNC_STATE_CANDIDATE_FOUND
        task.last_change_type = "candidate_found"
        session.add(task)
        session.flush()
        if not candidate_discarded:
            _append_follow_task_log(
                session,
                task=task,
                stage="candidate",
                message="Keeping the stored candidate source because it is still valid",
                payload={
                    **healthy_existing_candidate,
                    "candidate_assessment": existing_candidate_assessment,
                    "candidate_recall": candidate_recall,
                },
            )
        return

    _clear_follow_task_candidate_fields(task)
    _set_task_extra_section(task, "candidate_recall", candidate_recall)
    if selected_assessment is not None:
        _set_task_extra_section(task, "candidate_assessment", selected_assessment)
    _apply_follow_task_state_without_candidate(task)
    session.add(task)
    session.flush()
    if task.task_state == PAN_TRANSFER_SYNC_STATE_SOURCE_INVALID:
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            level="warning",
            message="No new candidate found and the current source link is invalid",
            payload={
                "candidate_assessment": selected_assessment,
                "candidate_recall": candidate_recall,
            },
        )
    elif task.task_state == PAN_TRANSFER_SYNC_STATE_SHARE_INVALID:
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            level="warning",
            message="No new candidate found and the current outward share is invalid",
            payload={
                "candidate_assessment": selected_assessment,
                "candidate_recall": candidate_recall,
            },
        )
    elif not candidate_discarded:
        _append_follow_task_log(
            session,
            task=task,
            stage="candidate",
            message="No recent candidate source link was found for this check",
            payload={
                "candidate_assessment": selected_assessment,
                "candidate_recall": candidate_recall,
            },
        )


def process_next_pan_transfer_follow_task(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    now = utcnow()
    task = (
        session.query(PanTransferSyncTask)
        .filter(
            PanTransferSyncTask.status == PAN_TRANSFER_SYNC_STATUS_ACTIVE,
            PanTransferSyncTask.next_check_at.isnot(None),
            PanTransferSyncTask.next_check_at <= now,
        )
        .order_by(PanTransferSyncTask.next_check_at.asc(), PanTransferSyncTask.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if task is None:
        return False
    task_id = int(task.id)

    task.task_state = PAN_TRANSFER_SYNC_STATE_CHECKING
    task.locked_by = worker_name[:128]
    task.locked_at = now
    task.updated_by = worker_name[:128]
    task.last_error_message = None
    session.add(task)
    session.flush()

    try:
        asyncio.run(_process_pan_transfer_follow_task_async(session, task=task, worker_name=worker_name))
        task.locked_by = None
        task.locked_at = None
        task.last_checked_at = utcnow()
        task.next_check_at = _next_check_time(interval_minutes=int(task.check_interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES))
        task.last_error_message = None
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="finish",
            message="Follow task check completed",
            payload={
                "task_state": str(task.task_state or ""),
                "next_check_at": task.next_check_at.isoformat() + "Z" if task.next_check_at is not None else None,
            },
        )
        return True
    except Exception as exc:
        session.rollback()
        task = _get_follow_task(session, task_id=task_id)
        error_message = _normalize_text(exc, max_length=2000) or type(exc).__name__
        task.task_state = PAN_TRANSFER_SYNC_STATE_ERROR
        task.locked_by = None
        task.locked_at = None
        task.last_checked_at = utcnow()
        task.next_check_at = _next_check_time(interval_minutes=int(task.check_interval_minutes or PAN_TRANSFER_SYNC_DEFAULT_INTERVAL_MINUTES))
        task.last_error_message = error_message
        session.add(task)
        session.flush()
        _append_follow_task_log(
            session,
            task=task,
            stage="finish",
            level="error",
            message=f"Follow task check failed: {error_message}",
            payload={
                "error_type": type(exc).__name__,
                "next_check_at": task.next_check_at.isoformat() + "Z" if task.next_check_at is not None else None,
            },
        )
        return True
