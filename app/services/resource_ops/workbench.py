from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import Date as SQLDate
from sqlalchemy import case, cast, distinct, func, or_
from sqlalchemy.orm import Session, aliased

from app.models.models import (
    LinkCheckDetails,
    LinkTarget,
    LinkTargetDailyStat,
    Message,
    MessageLinkRef,
    ResourceCandidateLog,
    ResourceCandidateProfile,
    ensure_runtime_storage_tables,
)
from app.schemas.resource_ops_models_v2 import ResourceOpsWorkbenchUpdateRequest
from app.services.resource_ops.analytics import (
    DEFAULT_LOOKBACK_DAYS,
    _compute_heat_metrics,
    _normalize_keyword,
    _start_date,
    _to_int,
    _utcnow,
)
from app.services.resource_ops.recognition_service import WORK_MATCH_STATUS_LABELS, get_work_binding_lookup


OPERATION_STATUS_LABELS = {
    "pending_review": "待评估",
    "observing": "观察中",
    "ready_to_mirror": "待转存",
    "ignored": "已忽略",
}
VALUE_STATUS_LABELS = {
    "unreviewed": "未判断",
    "not_worth": "不建议",
    "observe": "可观察",
    "worth": "值得做",
    "priority": "高优先",
}
RESOURCE_KIND_LABELS = {
    "unknown": "待判断",
    "fixed": "固定资源",
    "rolling": "持续更新",
    "stopped": "已停更",
}
UPDATE_MODE_LABELS = {
    "unknown": "待判断",
    "same_link": "同链接变化",
    "same_series": "同系列追更",
    "none": "一次性处理",
}
LINK_HEALTH_LABELS = {
    "healthy": "正常",
    "warning": "有波动",
    "invalid": "最近失效",
    "unknown": "暂无检测",
}

VALID_OPERATION_STATUSES = set(OPERATION_STATUS_LABELS)
VALID_VALUE_STATUSES = set(VALUE_STATUS_LABELS)
VALID_RESOURCE_KINDS = {"fixed", "rolling", "stopped"}

ROLLING_PATTERNS = (
    re.compile(r"更新|更至|连载|日更|周更|追更|持续更新", re.IGNORECASE),
    re.compile(r"第\s*\d+\s*[集话期章部季]", re.IGNORECASE),
    re.compile(r"\bep\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bs\d+\s*e\d+\b", re.IGNORECASE),
)
FIXED_PATTERNS = (
    re.compile(r"完结|全集|完整版|合集|剧场版|蓝光|电影|全季", re.IGNORECASE),
    re.compile(r"全\s*\d+\s*[集话期章部季]", re.IGNORECASE),
)
EPISODE_STRIP_PATTERN = re.compile(
    r"(更新|更至|连载|日更|周更|持续更新|第\s*\d+\s*[集话期章部季]|\bep\s*\d+\b|\bs\d+\s*e\d+\b)",
    re.IGNORECASE,
)
SERIES_CLEAN_PATTERN = re.compile(r"[\[\]()【】「」『』_#|｜\-]+")


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 1)


def _score_ratio(value: int | float, threshold: int | float, weight: float) -> float:
    safe_threshold = max(float(threshold), 1.0)
    return min(float(value or 0) / safe_threshold, 1.0) * float(weight)


def _normalize_text(value: Any, *, max_length: int | None = None) -> str:
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


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


def _normalize_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_operation_status(value: Any) -> str:
    normalized = _normalize_text(value, max_length=32).lower()
    if normalized not in VALID_OPERATION_STATUSES:
        raise ValueError("Invalid operation_status")
    return normalized


def _normalize_value_status(value: Any) -> str:
    normalized = _normalize_text(value, max_length=32).lower()
    if normalized not in VALID_VALUE_STATUSES:
        raise ValueError("Invalid value_status")
    return normalized


def _normalize_manual_resource_kind(value: Any) -> str | None:
    normalized = _normalize_text(value, max_length=32).lower()
    if not normalized:
        return None
    if normalized not in VALID_RESOURCE_KINDS:
        raise ValueError("Invalid manual_resource_kind")
    return normalized


def _normalize_note(value: Any) -> str:
    return _normalize_text(value, max_length=2000)


def _days_since(value: datetime | None) -> int | None:
    if value is None:
        return None
    try:
        return max(0, (date.today() - value.date()).days)
    except Exception:
        return None


def _build_series_key(*parts: str | None) -> str | None:
    text = " ".join(_normalize_text(part) for part in parts if part).strip()
    if not text:
        return None
    text = EPISODE_STRIP_PATTERN.sub(" ", text)
    text = SERIES_CLEAN_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -_/")
    if not text:
        return None
    return text[:120]


def _max_datetime(*values: datetime | None) -> datetime | None:
    candidates = [value for value in values if isinstance(value, datetime)]
    if not candidates:
        return None
    return max(candidates)


def _topic_rank(item: dict[str, Any]) -> tuple[float, int, int, int]:
    activity = _max_datetime(item.get("last_clicked_at"), item.get("last_message_time"))
    timestamp = activity.timestamp() if activity is not None else -1.0
    return (
        timestamp,
        _to_int(item.get("clicks_30d")),
        _to_int(item.get("clicks_7d")),
        len(_normalize_text(item.get("latest_message_title"))),
    )


def _annotate_topic_metrics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        work_id = _to_int(item.get("work_id"))
        work_title = _normalize_text(item.get("work_title"), max_length=255)
        work_status = _normalize_text(item.get("work_match_status"), max_length=16).lower()
        if work_id > 0 and work_title and work_status == "matched":
            topic_key = f"work:{work_id}"
            topic_title = work_title
        else:
            link_target_id = _to_int(item.get("link_target_id"))
            topic_key = f"link:{link_target_id}"
            topic_title = (
                _normalize_text(item.get("latest_message_title"), max_length=255)
                or _normalize_text(item.get("display_text"), max_length=255)
                or f"资源 {link_target_id}"
            )
        item["topic_key"] = topic_key
        item["topic_title"] = topic_title
        item["topic_link_target_count"] = 1
        item["topic_message_count"] = _to_int(item.get("message_count"))
        item["topic_clicks_total"] = _to_int(item.get("clicks_total"))
        item["topic_clicks_7d"] = _to_int(item.get("clicks_7d"))
        item["topic_clicks_30d"] = _to_int(item.get("clicks_30d"))
        item["topic_platform_count"] = 1 if _normalize_text(item.get("platform"), max_length=64) else 0
        item["topic_latest_message_title"] = (
            _normalize_text(item.get("latest_message_title"))
            or _normalize_text(item.get("display_text"))
            or topic_title
        )
        item["topic_last_clicked_at"] = item.get("last_clicked_at")
        item["topic_last_message_time"] = item.get("last_message_time")
        item["topic_last_activity_at"] = _max_datetime(
            item.get("last_clicked_at"),
            item.get("last_message_time"),
        )

    return items


def _infer_resource_kind(item: dict[str, Any]) -> tuple[str, str, float, str | None, list[str]]:
    latest_title = _normalize_text(item.get("latest_message_title"))
    display_text = _normalize_text(item.get("display_text"))
    title_blob = f"{latest_title} {display_text}".strip()
    recent_ref_count = _to_int(item.get("recent_ref_count_30d"))
    ref_active_days = _to_int(item.get("ref_active_days_30d"))
    clicks_30d = _to_int(item.get("clicks_30d"))
    days_since_last_message = _days_since(item.get("last_message_time"))

    has_rolling_pattern = any(pattern.search(title_blob) for pattern in ROLLING_PATTERNS)
    has_fixed_pattern = any(pattern.search(title_blob) for pattern in FIXED_PATTERNS)

    reasons: list[str] = []
    series_key = _build_series_key(latest_title, display_text)

    if has_rolling_pattern and recent_ref_count >= 2 and ref_active_days >= 2:
        reasons.append("标题带有更新痕迹，且近 30 天多次出现")
        return "rolling", "same_series", 0.86, series_key, reasons

    if has_rolling_pattern and days_since_last_message is not None and days_since_last_message >= 45:
        reasons.append("标题像追更资源，但最近较久没有新消息")
        return "stopped", "same_series", 0.74, series_key, reasons

    if has_fixed_pattern:
        reasons.append("标题更像全集、电影或合集类资源")
        return "fixed", "none", 0.8, series_key, reasons

    if recent_ref_count >= 3 and ref_active_days >= 3 and clicks_30d >= 12:
        reasons.append("近 30 天跨多天重复出现，存在持续追更特征")
        return "rolling", "same_series", 0.6, series_key, reasons

    if days_since_last_message is not None and days_since_last_message >= 60 and clicks_30d <= 2:
        reasons.append("长时间没有新消息和点击，倾向于已停更或低价值")
        return "stopped", "unknown", 0.52, series_key, reasons

    reasons.append("当前样本不足，先保留待判断")
    return "unknown", "unknown", 0.32, series_key, reasons


def _resolve_link_health(item: dict[str, Any]) -> tuple[str, str]:
    total_checks = _to_int(item.get("total_checks_30d"))
    invalid_checks = _to_int(item.get("invalid_checks_30d"))
    latest_is_valid = item.get("latest_is_valid")
    latest_checked_at = item.get("latest_checked_at")
    latest_error_reason = _normalize_text(item.get("latest_error_reason"), max_length=200)

    if latest_is_valid is False:
        return "invalid", latest_error_reason or "最近一次链接检测判定为失效"
    if invalid_checks >= 2:
        return "warning", "最近 30 天出现过多次失效记录"
    if total_checks > 0 and latest_is_valid is True:
        if latest_checked_at is not None:
            return "healthy", f"最近一次检测正常，时间 {latest_checked_at.strftime('%Y-%m-%d %H:%M')}"
        return "healthy", "最近一次检测正常"
    if total_checks > 0:
        return "warning", latest_error_reason or "已有检测记录，但结果不够稳定"
    return "unknown", "暂无链接检测记录"


def _compute_dimension_scores(item: dict[str, Any]) -> tuple[float, float, float, float]:
    auto_kind = item.get("auto_resource_kind") or "unknown"
    update_confidence = float(item.get("update_confidence") or 0)
    health = item.get("latest_link_health") or "unknown"

    demand_score = _clamp_score(
        _score_ratio(item.get("clicks_30d"), 45, 30)
        + _score_ratio(item.get("clicks_7d"), 18, 18)
        + _score_ratio(item.get("unique_sessions_30d"), 24, 22)
        + _score_ratio(item.get("unique_users_30d"), 10, 10)
        + _score_ratio(item.get("search_clicks_30d"), 8, 8)
        + _score_ratio(item.get("active_days_30d"), 10, 12)
    )

    value_bonus = 0
    if item.get("heat_type") == "sustained":
        value_bonus += 12
    elif item.get("heat_type") == "burst":
        value_bonus += 8
    elif item.get("heat_type") == "watch":
        value_bonus += 4
    if health in {"warning", "invalid"}:
        value_bonus += 8

    value_score = _clamp_score(
        _score_ratio(item.get("message_count"), 8, 18)
        + _score_ratio(item.get("message_ref_count"), 14, 10)
        + _score_ratio(item.get("clicks_30d"), 45, 18)
        + _score_ratio(item.get("clicks_7d"), 18, 18)
        + _score_ratio(item.get("unique_sessions_30d"), 24, 16)
        + _score_ratio(item.get("search_clicks_30d"), 8, 10)
        + value_bonus
    )

    cost_score = 8.0
    if auto_kind == "rolling":
        cost_score += 34
    elif auto_kind == "unknown":
        cost_score += 18
    elif auto_kind == "stopped":
        cost_score += 10
    else:
        cost_score += 6
    cost_score += _score_ratio(item.get("recent_ref_count_30d"), 6, 12)
    cost_score += _score_ratio(item.get("file_count"), 150, 8)
    total_size_bytes = float(item.get("total_size_bytes") or 0)
    if total_size_bytes > 0:
        cost_score += min(total_size_bytes / float(1024**3 * 50), 1.0) * 12
    cost_score += max(0.0, (0.7 - update_confidence)) * 22
    cost_score = _clamp_score(cost_score)

    risk_score = 8.0
    if health == "invalid":
        risk_score += 46
    elif health == "warning":
        risk_score += 24
    elif health == "unknown":
        risk_score += 10
    risk_score += _score_ratio(item.get("invalid_checks_30d"), 3, 18)
    if auto_kind == "unknown":
        risk_score += 8
    if not _normalize_text(item.get("platform")):
        risk_score += 10
    if _to_int(item.get("clicks_30d")) <= 3 and _to_int(item.get("unique_sessions_30d")) <= 2:
        risk_score += 8
    risk_score = _clamp_score(risk_score)

    return demand_score, value_score, cost_score, risk_score


def _resolve_auto_value_status(item: dict[str, Any]) -> str:
    overall_score = float(item.get("overall_score") or 0)
    demand_score = float(item.get("demand_score") or 0)
    value_score = float(item.get("value_score") or 0)
    risk_score = float(item.get("risk_score") or 0)

    if overall_score >= 78 or (demand_score >= 72 and value_score >= 68 and risk_score <= 48):
        return "priority"
    if overall_score >= 62:
        return "worth"
    if overall_score >= 42:
        return "observe"
    return "not_worth"


def _build_suggested_action(item: dict[str, Any]) -> str:
    auto_value_status = item.get("auto_value_status") or "observe"
    effective_kind = item.get("effective_resource_kind") or "unknown"
    health = item.get("latest_link_health") or "unknown"

    if auto_value_status == "priority" and effective_kind == "fixed":
        return "优先转存并准备替换原链"
    if auto_value_status == "priority" and effective_kind == "rolling":
        return "纳入重点追更，先确定更新节奏"
    if auto_value_status in {"priority", "worth"} and effective_kind == "rolling":
        return "先观察更新模式，再安排分批转存"
    if auto_value_status in {"priority", "worth"} and health == "invalid":
        return "原链风险高，建议优先补链或转存"
    if auto_value_status in {"priority", "worth"}:
        return "进入待转存池，结合容量安排处理"
    if auto_value_status == "observe":
        return "继续观察热度和更新迹象"
    return "暂不处理，保留观察记录即可"


def _evaluate_candidate_row(raw_item: dict[str, Any]) -> dict[str, Any]:
    item = _compute_heat_metrics(dict(raw_item))
    auto_kind, update_mode, update_confidence, series_key, auto_reasons = _infer_resource_kind(item)
    link_health, link_health_reason = _resolve_link_health(item)

    item["auto_resource_kind"] = auto_kind
    item["auto_resource_kind_label"] = RESOURCE_KIND_LABELS[auto_kind]
    item["update_mode"] = update_mode
    item["update_mode_label"] = UPDATE_MODE_LABELS[update_mode]
    item["update_confidence"] = round(update_confidence, 2)
    item["series_key"] = series_key
    item["latest_link_health"] = link_health
    item["latest_link_health_label"] = LINK_HEALTH_LABELS[link_health]
    item["latest_link_health_reason"] = link_health_reason
    item["auto_reasons"] = auto_reasons

    demand_score, value_score, cost_score, risk_score = _compute_dimension_scores(item)
    overall_score = _clamp_score(
        demand_score * 0.42
        + value_score * 0.33
        + (100 - cost_score) * 0.15
        + (100 - risk_score) * 0.10
    )

    item["demand_score"] = demand_score
    item["value_score"] = value_score
    item["cost_score"] = cost_score
    item["risk_score"] = risk_score
    item["overall_score"] = overall_score

    auto_value_status = _resolve_auto_value_status(item)
    manual_value_status = _normalize_text(item.get("value_status"), max_length=32).lower() or "unreviewed"
    manual_resource_kind = _normalize_text(item.get("manual_resource_kind"), max_length=32).lower() or None

    effective_value_status = auto_value_status if manual_value_status == "unreviewed" else manual_value_status
    effective_resource_kind = manual_resource_kind if manual_resource_kind in VALID_RESOURCE_KINDS else auto_kind

    item["auto_value_status"] = auto_value_status
    item["auto_value_status_label"] = VALUE_STATUS_LABELS[auto_value_status]
    item["effective_value_status"] = effective_value_status
    item["effective_value_status_label"] = VALUE_STATUS_LABELS[effective_value_status]
    item["value_status_source"] = "auto" if manual_value_status == "unreviewed" else "manual"
    item["effective_resource_kind"] = effective_resource_kind
    item["effective_resource_kind_label"] = RESOURCE_KIND_LABELS.get(effective_resource_kind, RESOURCE_KIND_LABELS["unknown"])
    item["resource_kind_source"] = "manual" if manual_resource_kind in VALID_RESOURCE_KINDS else "auto"

    operation_status = _normalize_text(item.get("operation_status"), max_length=32).lower() or "pending_review"
    if operation_status not in VALID_OPERATION_STATUSES:
        operation_status = "pending_review"
    item["operation_status"] = operation_status
    item["operation_status_label"] = OPERATION_STATUS_LABELS[operation_status]

    evidence_tags = [
        f"近 30 天点击 {item['clicks_30d']}",
        f"近 30 天会话 {item['unique_sessions_30d']}",
        f"近 30 天活跃 {item['active_days_30d']} 天",
    ]
    if item["series_key"]:
        evidence_tags.append(f"系列键：{item['series_key']}")
    if item["latest_link_health"] != "unknown":
        evidence_tags.append(f"链接健康：{item['latest_link_health_label']}")
    evidence_tags.extend(auto_reasons)
    item["evidence_tags"] = evidence_tags[:6]
    item["suggested_action"] = _build_suggested_action(item)
    item["note"] = _normalize_text(item.get("note"), max_length=2000)
    return item


def _build_sort_key(item: dict[str, Any], sort_field: str) -> tuple[Any, ...]:
    value = item.get(sort_field)
    if isinstance(value, datetime):
        normalized = value.timestamp()
    elif value is None:
        normalized = -1
    else:
        normalized = value
    return (
        normalized,
        item.get("overall_score") or 0,
        item.get("topic_clicks_30d") or 0,
        item.get("clicks_30d") or 0,
        item.get("unique_sessions_30d") or 0,
    )


def _build_workbench_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_candidates": len(items),
        "pending_review_count": sum(1 for item in items if item["operation_status"] == "pending_review"),
        "observing_count": sum(1 for item in items if item["operation_status"] == "observing"),
        "ready_to_mirror_count": sum(1 for item in items if item["operation_status"] == "ready_to_mirror"),
        "ignored_count": sum(1 for item in items if item["operation_status"] == "ignored"),
        "priority_count": sum(1 for item in items if item["effective_value_status"] == "priority"),
        "worth_count": sum(1 for item in items if item["effective_value_status"] in {"worth", "priority"}),
        "rolling_count": sum(1 for item in items if item["effective_resource_kind"] == "rolling"),
        "fixed_count": sum(1 for item in items if item["effective_resource_kind"] == "fixed"),
        "risky_count": sum(
            1
            for item in items
            if item["latest_link_health"] in {"warning", "invalid"} or float(item["risk_score"]) >= 55
        ),
        "generated_at": _utcnow(),
    }


def _datetime_sort_value(value: datetime | None) -> float:
    return value.timestamp() if isinstance(value, datetime) else -1.0


def _min_datetime(*values: datetime | None) -> datetime | None:
    candidates = [value for value in values if isinstance(value, datetime)]
    if not candidates:
        return None
    return min(candidates)


def _has_topic_manual_profile(item: dict[str, Any]) -> bool:
    operation_status = _normalize_text(item.get("operation_status"), max_length=32).lower() or "pending_review"
    value_status = _normalize_text(item.get("value_status"), max_length=32).lower() or "unreviewed"
    manual_resource_kind = _normalize_text(item.get("manual_resource_kind"), max_length=32).lower()
    note = _normalize_text(item.get("note"), max_length=2000)
    return bool(
        operation_status != "pending_review"
        or value_status != "unreviewed"
        or manual_resource_kind in VALID_RESOURCE_KINDS
        or note
    )


def _select_topic_anchor_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    return max(items, key=_topic_rank)


def _select_topic_profile_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    profiled_items = [item for item in items if _to_int(item.get("profile_id")) > 0]
    manual_items = [item for item in profiled_items if _has_topic_manual_profile(item)]
    source_items = manual_items or profiled_items
    if not source_items:
        return None
    return max(
        source_items,
        key=lambda item: (
            _datetime_sort_value(item.get("profile_updated_at")),
            *_topic_rank(item),
        ),
    )


def _select_topic_work_item(items: list[dict[str, Any]], anchor_item: dict[str, Any]) -> dict[str, Any]:
    matched_items = [
        item
        for item in items
        if _to_int(item.get("work_id")) > 0 and _normalize_text(item.get("work_match_status"), max_length=16).lower() == "matched"
    ]
    if matched_items:
        return max(matched_items, key=_topic_rank)

    attempted_items = [
        item
        for item in items
        if _normalize_text(item.get("work_match_status"), max_length=16).lower() in {"pending", "error"}
    ]
    if attempted_items:
        return max(
            attempted_items,
            key=lambda item: (
                _datetime_sort_value(item.get("work_last_attempted_at")),
                *_topic_rank(item),
            ),
        )
    return anchor_item


def _collect_topic_auto_reasons(items: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for item in items:
        for reason in item.get("auto_reasons") or []:
            normalized = _normalize_text(reason, max_length=200)
            if normalized and normalized not in reasons:
                reasons.append(normalized)
    return reasons[:8]


def _build_topic_health_snapshot(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "healthy": 0,
        "warning": 0,
        "invalid": 0,
        "unknown": 0,
    }
    latest_reason = ""
    latest_checked_at: datetime | None = None

    for item in items:
        status = _normalize_text(item.get("latest_link_health"), max_length=16).lower() or "unknown"
        if status not in counts:
            status = "unknown"
        counts[status] += 1
        checked_at = item.get("latest_checked_at")
        if _datetime_sort_value(checked_at) >= _datetime_sort_value(latest_checked_at):
            latest_checked_at = checked_at
            latest_reason = _normalize_text(item.get("latest_link_health_reason"), max_length=255)

    checked_count = counts["healthy"] + counts["warning"] + counts["invalid"]
    if counts["invalid"] > 0:
        status = "invalid"
        reason = latest_reason or f"{counts['invalid']} 个成员链接最近失效"
        latest_is_valid = False
    elif counts["warning"] > 0:
        status = "warning"
        reason = latest_reason or f"{counts['warning']} 个成员链接近期波动"
        latest_is_valid = None
    elif counts["healthy"] > 0:
        status = "healthy"
        reason = latest_reason or f"已检测 {checked_count} 个成员链接"
        latest_is_valid = True
    else:
        status = "unknown"
        reason = "暂无成员链接检测记录"
        latest_is_valid = None

    return {
        "latest_link_health": status,
        "latest_link_health_reason": reason,
        "latest_is_valid": latest_is_valid,
        "checked_link_target_count": checked_count,
        "healthy_link_target_count": counts["healthy"],
        "warning_link_target_count": counts["warning"],
        "invalid_link_target_count": counts["invalid"],
        "unknown_link_target_count": counts["unknown"],
    }


def _merge_topic_work_fields(items: list[dict[str, Any]], work_item: dict[str, Any]) -> dict[str, Any]:
    matched_item = next(
        (
            item
            for item in sorted(items, key=_topic_rank, reverse=True)
            if _to_int(item.get("work_id")) > 0 and _normalize_text(item.get("work_match_status"), max_length=16).lower() == "matched"
        ),
        None,
    )
    source_item = matched_item or work_item
    season_hint = _normalize_text(source_item.get("work_season_hint"), max_length=32) or None
    year_hint = _normalize_optional_int(source_item.get("work_year_hint"))
    payload = {
        "work_id": source_item.get("work_id"),
        "work_title": source_item.get("work_title"),
        "work_canonical_title": source_item.get("work_canonical_title"),
        "work_original_title": source_item.get("work_original_title"),
        "work_provider": source_item.get("work_provider"),
        "work_media_type": source_item.get("work_media_type"),
        "work_release_year": source_item.get("work_release_year"),
        "work_poster_url": source_item.get("work_poster_url"),
        "work_detail_url": source_item.get("work_detail_url"),
        "work_match_status": source_item.get("work_match_status") or "pending",
        "work_match_status_label": source_item.get("work_match_status_label") or "待归并",
        "work_match_source": source_item.get("work_match_source") or "ai",
        "work_match_reason": source_item.get("work_match_reason") or "",
        "work_query_title": source_item.get("work_query_title"),
        "work_candidate_title": source_item.get("work_candidate_title"),
        "work_season_hint": season_hint,
        "work_year_hint": year_hint,
        "work_last_attempted_at": source_item.get("work_last_attempted_at"),
        "work_matched_at": source_item.get("work_matched_at"),
    }
    if matched_item is not None:
        payload["work_match_status"] = "matched"
        payload["work_match_status_label"] = WORK_MATCH_STATUS_LABELS["matched"]
    return payload


def _aggregate_topic_item(
    items: list[dict[str, Any]],
    *,
    message_ids_by_link_target: dict[int, set[int]] | None = None,
) -> dict[str, Any]:
    anchor_item = _select_topic_anchor_item(items)
    profile_item = _select_topic_profile_item(items)
    work_item = _select_topic_work_item(items, anchor_item)
    latest_message_item = max(items, key=lambda item: (_datetime_sort_value(item.get("last_message_time")), len(_normalize_text(item.get("latest_message_title")))))
    latest_click_item = max(items, key=lambda item: (_datetime_sort_value(item.get("last_clicked_at")), _to_int(item.get("clicks_30d"))))
    latest_check_item = max(items, key=lambda item: (_datetime_sort_value(item.get("latest_checked_at")), _to_int(item.get("total_checks_30d"))))
    storage_item = profile_item or anchor_item
    health_snapshot = _build_topic_health_snapshot(items)
    topic_title = _normalize_text(work_item.get("work_title"), max_length=255) or _normalize_text(anchor_item.get("topic_title"), max_length=255)
    topic_message_ids: set[int] = set()
    if message_ids_by_link_target:
        for item in items:
            topic_message_ids.update(
                message_ids_by_link_target.get(_to_int(item.get("link_target_id")), set())
            )
    topic_message_count = len(topic_message_ids) if topic_message_ids else sum(
        _to_int(item.get("message_count")) for item in items
    )

    raw_item = {
        "link_target_id": _to_int(storage_item.get("link_target_id")) or _to_int(anchor_item.get("link_target_id")),
        "platform": anchor_item.get("platform") or "",
        "display_text": anchor_item.get("display_text") or latest_message_item.get("display_text") or topic_title,
        "target_url": anchor_item.get("target_url") or "",
        "share_key": anchor_item.get("share_key"),
        "file_count": max(_to_int(item.get("file_count")) for item in items) if items else 0,
        "total_size_bytes": max(float(item.get("total_size_bytes") or 0) for item in items) if items else 0,
        "topic_title": topic_title or "未命名资源",
        "topic_key": anchor_item.get("topic_key") or f"link:{_to_int(anchor_item.get('link_target_id'))}",
        "topic_link_target_count": len(items),
        "topic_message_count": topic_message_count,
        "topic_clicks_total": sum(_to_int(item.get("clicks_total")) for item in items),
        "topic_clicks_7d": sum(_to_int(item.get("clicks_7d")) for item in items),
        "topic_clicks_30d": sum(_to_int(item.get("clicks_30d")) for item in items),
        "topic_platform_count": len({_normalize_text(item.get("platform"), max_length=64) for item in items if _normalize_text(item.get("platform"), max_length=64)}),
        "topic_latest_message_title": latest_message_item.get("latest_message_title") or latest_message_item.get("display_text") or topic_title,
        "topic_last_clicked_at": latest_click_item.get("last_clicked_at"),
        "topic_last_message_time": latest_message_item.get("last_message_time"),
        "topic_last_activity_at": _max_datetime(latest_click_item.get("last_clicked_at"), latest_message_item.get("last_message_time")),
        "message_ref_count": sum(_to_int(item.get("message_ref_count")) for item in items),
        "message_count": sum(_to_int(item.get("message_count")) for item in items),
        "recent_ref_count_30d": sum(_to_int(item.get("recent_ref_count_30d")) for item in items),
        "ref_active_days_30d": min(30, sum(_to_int(item.get("ref_active_days_30d")) for item in items)),
        "clicks_total": sum(_to_int(item.get("clicks_total")) for item in items),
        "clicks_1d": sum(_to_int(item.get("clicks_1d")) for item in items),
        "clicks_3d": sum(_to_int(item.get("clicks_3d")) for item in items),
        "clicks_7d": sum(_to_int(item.get("clicks_7d")) for item in items),
        "clicks_30d": sum(_to_int(item.get("clicks_30d")) for item in items),
        "unique_sessions_30d": sum(_to_int(item.get("unique_sessions_30d")) for item in items),
        "unique_users_30d": sum(_to_int(item.get("unique_users_30d")) for item in items),
        "search_clicks_30d": sum(_to_int(item.get("search_clicks_30d")) for item in items),
        "active_days_30d": min(30, sum(_to_int(item.get("active_days_30d")) for item in items)),
        "first_seen_at": _min_datetime(*(item.get("first_seen_at") for item in items)),
        "last_seen_at": _max_datetime(*(item.get("last_seen_at") for item in items)),
        "last_message_time": latest_message_item.get("last_message_time"),
        "last_clicked_at": latest_click_item.get("last_clicked_at"),
        "latest_message_title": latest_message_item.get("latest_message_title") or latest_message_item.get("display_text") or "",
        "latest_checked_at": latest_check_item.get("latest_checked_at"),
        "latest_error_reason": health_snapshot["latest_link_health_reason"],
        "latest_is_valid": health_snapshot["latest_is_valid"],
        "total_checks_30d": sum(_to_int(item.get("total_checks_30d")) for item in items),
        "invalid_checks_30d": sum(_to_int(item.get("invalid_checks_30d")) for item in items),
        "operation_status": (profile_item or {}).get("operation_status") or "pending_review",
        "value_status": (profile_item or {}).get("value_status") or "unreviewed",
        "manual_resource_kind": (profile_item or {}).get("manual_resource_kind"),
        "note": (profile_item or {}).get("note") or "",
        "profile_updated_at": (profile_item or {}).get("profile_updated_at"),
        "updated_by": (profile_item or {}).get("updated_by"),
        "profile_id": (profile_item or {}).get("profile_id"),
    }
    raw_item.update(_merge_topic_work_fields(items, work_item))

    aggregated = _evaluate_candidate_row(raw_item)
    aggregated["topic_title"] = raw_item["topic_title"]
    aggregated["topic_key"] = raw_item["topic_key"]
    aggregated["topic_link_target_count"] = raw_item["topic_link_target_count"]
    aggregated["topic_message_count"] = raw_item["topic_message_count"]
    aggregated["topic_clicks_total"] = raw_item["topic_clicks_total"]
    aggregated["topic_clicks_7d"] = raw_item["topic_clicks_7d"]
    aggregated["topic_clicks_30d"] = raw_item["topic_clicks_30d"]
    aggregated["topic_platform_count"] = raw_item["topic_platform_count"]
    aggregated["topic_latest_message_title"] = raw_item["topic_latest_message_title"]
    aggregated["topic_last_clicked_at"] = raw_item["topic_last_clicked_at"]
    aggregated["topic_last_message_time"] = raw_item["topic_last_message_time"]
    aggregated["topic_last_activity_at"] = raw_item["topic_last_activity_at"]
    aggregated["latest_link_health"] = health_snapshot["latest_link_health"]
    aggregated["latest_link_health_label"] = LINK_HEALTH_LABELS[health_snapshot["latest_link_health"]]
    aggregated["latest_link_health_reason"] = health_snapshot["latest_link_health_reason"]
    aggregated["checked_link_target_count"] = health_snapshot["checked_link_target_count"]
    aggregated["healthy_link_target_count"] = health_snapshot["healthy_link_target_count"]
    aggregated["warning_link_target_count"] = health_snapshot["warning_link_target_count"]
    aggregated["invalid_link_target_count"] = health_snapshot["invalid_link_target_count"]
    aggregated["unknown_link_target_count"] = health_snapshot["unknown_link_target_count"]
    aggregated["suggested_action"] = _build_suggested_action(aggregated)
    aggregated["auto_reasons"] = _collect_topic_auto_reasons(items)
    aggregated["_member_link_target_ids"] = [
        _to_int(item.get("link_target_id"))
        for item in sorted(items, key=_topic_rank, reverse=True)
        if _to_int(item.get("link_target_id")) > 0
    ]
    aggregated["_profile_link_target_id"] = _to_int((profile_item or {}).get("link_target_id")) or _to_int(raw_item["link_target_id"])
    return aggregated


def _load_workbench_topic_rows(
    session: Session,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    platform: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    candidate_rows = _load_workbench_candidate_rows(
        session,
        days=days,
        platform=platform,
        keyword=keyword,
    )
    grouped_items: dict[str, list[dict[str, Any]]] = {}
    for item in candidate_rows:
        topic_key = _normalize_text(item.get("topic_key"), max_length=160) or f"link:{_to_int(item.get('link_target_id'))}"
        grouped_items.setdefault(topic_key, []).append(item)
    member_link_target_ids = _normalize_positive_ids(
        _to_int(item.get("link_target_id"))
        for group_items in grouped_items.values()
        for item in group_items
    )
    message_ids_by_link_target: dict[int, set[int]] = {}
    if member_link_target_ids:
        message_rows = (
            session.query(
                MessageLinkRef.link_target_id.label("link_target_id"),
                MessageLinkRef.message_id.label("message_id"),
            )
            .filter(MessageLinkRef.link_target_id.in_(member_link_target_ids))
            .all()
        )
        for row in message_rows:
            link_target_id = _to_int(row.link_target_id)
            message_id = _to_int(row.message_id)
            if link_target_id <= 0 or message_id <= 0:
                continue
            message_ids_by_link_target.setdefault(link_target_id, set()).add(message_id)

    return [
        _aggregate_topic_item(group_items, message_ids_by_link_target=message_ids_by_link_target)
        for group_items in grouped_items.values()
    ]


def _find_topic_item_by_link_target_id(items: list[dict[str, Any]], *, link_target_id: int) -> dict[str, Any] | None:
    for item in items:
        if _to_int(item.get("link_target_id")) == int(link_target_id):
            return item
        member_ids = item.get("_member_link_target_ids") or []
        if int(link_target_id) in member_ids:
            return item
    return None


def _load_workbench_candidate_rows(
    session: Session,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    platform: str | None = None,
    keyword: str | None = None,
    link_target_id: int | None = None,
) -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    start = _start_date(days)
    start_dt = datetime.combine(start, datetime.min.time())
    day_7 = date.today() - timedelta(days=6)
    day_3 = date.today() - timedelta(days=2)
    day_1 = date.today()
    keyword_value = _normalize_keyword(keyword)

    click_metrics_subquery = (
        session.query(
            LinkTargetDailyStat.link_target_id.label("link_target_id"),
            func.sum(LinkTargetDailyStat.click_count).label("clicks_30d"),
            func.sum(LinkTargetDailyStat.unique_sessions).label("unique_sessions_30d"),
            func.sum(LinkTargetDailyStat.unique_users).label("unique_users_30d"),
            func.sum(case((LinkTargetDailyStat.stat_date >= day_7, LinkTargetDailyStat.click_count), else_=0)).label("clicks_7d"),
            func.sum(case((LinkTargetDailyStat.stat_date >= day_3, LinkTargetDailyStat.click_count), else_=0)).label("clicks_3d"),
            func.sum(case((LinkTargetDailyStat.stat_date >= day_1, LinkTargetDailyStat.click_count), else_=0)).label("clicks_1d"),
            func.sum(LinkTargetDailyStat.search_click_count).label("search_clicks_30d"),
            func.count(distinct(LinkTargetDailyStat.stat_date)).label("active_days_30d"),
            func.max(LinkTargetDailyStat.last_clicked_at).label("last_clicked_at"),
        )
        .filter(LinkTargetDailyStat.stat_date >= start)
        .group_by(LinkTargetDailyStat.link_target_id)
        .subquery()
    )
    click_total_subquery = (
        session.query(
            LinkTargetDailyStat.link_target_id.label("link_target_id"),
            func.sum(LinkTargetDailyStat.click_count).label("clicks_total"),
        )
        .group_by(LinkTargetDailyStat.link_target_id)
        .subquery()
    )

    ref_stats_subquery = (
        session.query(
            MessageLinkRef.link_target_id.label("link_target_id"),
            func.count(MessageLinkRef.id).label("message_ref_count"),
            func.count(distinct(MessageLinkRef.message_id)).label("message_count"),
            func.max(MessageLinkRef.message_timestamp).label("last_message_time"),
            func.sum(case((MessageLinkRef.message_timestamp >= start_dt, 1), else_=0)).label("recent_ref_count_30d"),
            func.count(
                distinct(
                    case(
                        (MessageLinkRef.message_timestamp >= start_dt, cast(MessageLinkRef.message_timestamp, SQLDate)),
                        else_=None,
                    )
                )
            ).label("ref_active_days_30d"),
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

    health_metrics_subquery = (
        session.query(
            LinkCheckDetails.normalized_url.label("normalized_url"),
            func.count(LinkCheckDetails.id).label("total_checks_30d"),
            func.sum(case((LinkCheckDetails.is_valid.is_(False), 1), else_=0)).label("invalid_checks_30d"),
        )
        .filter(LinkCheckDetails.normalized_url.isnot(None), LinkCheckDetails.check_time >= start_dt)
        .group_by(LinkCheckDetails.normalized_url)
        .subquery()
    )

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
    profile = aliased(ResourceCandidateProfile)

    query = (
        session.query(
            LinkTarget.id.label("link_target_id"),
            LinkTarget.platform.label("platform"),
            LinkTarget.original_url.label("original_url"),
            LinkTarget.normalized_url.label("normalized_url"),
            LinkTarget.share_key.label("share_key"),
            LinkTarget.file_count.label("file_count"),
            LinkTarget.total_size_bytes.label("total_size_bytes"),
            LinkTarget.first_seen_at.label("first_seen_at"),
            LinkTarget.last_seen_at.label("last_seen_at"),
            click_total_subquery.c.clicks_total,
            click_metrics_subquery.c.clicks_30d,
            click_metrics_subquery.c.unique_sessions_30d,
            click_metrics_subquery.c.unique_users_30d,
            click_metrics_subquery.c.clicks_7d,
            click_metrics_subquery.c.clicks_3d,
            click_metrics_subquery.c.clicks_1d,
            click_metrics_subquery.c.search_clicks_30d,
            click_metrics_subquery.c.active_days_30d,
            click_metrics_subquery.c.last_clicked_at,
            ref_stats_subquery.c.message_ref_count,
            ref_stats_subquery.c.message_count,
            ref_stats_subquery.c.last_message_time,
            ref_stats_subquery.c.recent_ref_count_30d,
            ref_stats_subquery.c.ref_active_days_30d,
            latest_ref.display_text.label("display_text"),
            latest_ref.provider_label.label("provider_label"),
            latest_ref.target_url.label("target_url"),
            latest_message.title.label("latest_message_title"),
            health_metrics_subquery.c.total_checks_30d,
            health_metrics_subquery.c.invalid_checks_30d,
            latest_health.is_valid.label("latest_is_valid"),
            latest_health.error_reason.label("latest_error_reason"),
            latest_health.check_time.label("latest_checked_at"),
            profile.operation_status.label("operation_status"),
            profile.value_status.label("value_status"),
            profile.manual_resource_kind.label("manual_resource_kind"),
            profile.note.label("note"),
            profile.updated_at.label("profile_updated_at"),
            profile.updated_by.label("updated_by"),
            profile.id.label("profile_id"),
        )
        .join(ref_stats_subquery, ref_stats_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(click_total_subquery, click_total_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(click_metrics_subquery, click_metrics_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref_id_subquery, latest_ref_id_subquery.c.link_target_id == LinkTarget.id)
        .outerjoin(latest_ref, latest_ref.id == latest_ref_id_subquery.c.latest_ref_id)
        .outerjoin(latest_message, latest_message.id == latest_ref.message_id)
        .outerjoin(health_metrics_subquery, health_metrics_subquery.c.normalized_url == LinkTarget.normalized_url)
        .outerjoin(latest_health_id_subquery, latest_health_id_subquery.c.normalized_url == LinkTarget.normalized_url)
        .outerjoin(latest_health, latest_health.id == latest_health_id_subquery.c.latest_detail_id)
        .outerjoin(profile, profile.link_target_id == LinkTarget.id)
        .filter(or_(click_metrics_subquery.c.link_target_id.isnot(None), profile.id.isnot(None)))
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
                func.lower(func.coalesce(latest_message.title, "")).like(like_pattern),
                func.lower(func.coalesce(LinkTarget.share_key, "")).like(like_pattern),
                func.lower(func.coalesce(LinkTarget.original_url, "")).like(like_pattern),
                func.lower(func.coalesce(profile.note, "")).like(like_pattern),
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
            "file_count": _to_int(row.file_count),
            "total_size_bytes": float(row.total_size_bytes or 0),
            "message_ref_count": _to_int(row.message_ref_count),
            "message_count": _to_int(row.message_count),
            "recent_ref_count_30d": _to_int(row.recent_ref_count_30d),
            "ref_active_days_30d": _to_int(row.ref_active_days_30d),
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
            "last_message_time": row.last_message_time,
            "last_clicked_at": row.last_clicked_at,
            "clicks_total": _to_int(row.clicks_total),
            "clicks_30d": _to_int(row.clicks_30d),
            "unique_sessions_30d": _to_int(row.unique_sessions_30d),
            "unique_users_30d": _to_int(row.unique_users_30d),
            "clicks_7d": _to_int(row.clicks_7d),
            "clicks_3d": _to_int(row.clicks_3d),
            "clicks_1d": _to_int(row.clicks_1d),
            "search_clicks_30d": _to_int(row.search_clicks_30d),
            "active_days_30d": _to_int(row.active_days_30d),
            "latest_message_title": row.latest_message_title or "",
            "total_checks_30d": _to_int(row.total_checks_30d),
            "invalid_checks_30d": _to_int(row.invalid_checks_30d),
            "latest_is_valid": row.latest_is_valid,
            "latest_error_reason": row.latest_error_reason,
            "latest_checked_at": row.latest_checked_at,
            "operation_status": row.operation_status or "pending_review",
            "value_status": row.value_status or "unreviewed",
            "manual_resource_kind": row.manual_resource_kind,
            "note": row.note or "",
            "profile_updated_at": row.profile_updated_at,
            "updated_by": row.updated_by,
        }
        items.append(_evaluate_candidate_row(item))
    binding_lookup = get_work_binding_lookup(
        session,
        link_target_ids=[_to_int(item.get("link_target_id")) for item in items],
    )
    for item in items:
        item.update(binding_lookup.get(_to_int(item.get("link_target_id")), {}))
    return _annotate_topic_metrics(items)


def list_resource_op_workbench_items(
    session: Session,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    page: int = 1,
    page_size: int = 20,
    platform: str | None = None,
    heat_type: str | None = None,
    operation_status: str | None = None,
    value_status: str | None = None,
    resource_kind: str | None = None,
    health_status: str | None = None,
    keyword: str | None = None,
    sort_by: str = "overall_score",
    sort_order: str = "desc",
) -> dict[str, Any]:
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    normalized_heat_type = _normalize_text(heat_type, max_length=32).lower() or None
    normalized_operation_status = _normalize_text(operation_status, max_length=32).lower() or None
    normalized_value_status = _normalize_text(value_status, max_length=32).lower() or None
    normalized_resource_kind = _normalize_text(resource_kind, max_length=32).lower() or None
    normalized_health_status = _normalize_text(health_status, max_length=32).lower() or None

    items = _load_workbench_topic_rows(
        session,
        days=days,
        platform=platform,
        keyword=keyword,
    )

    if normalized_heat_type:
        items = [item for item in items if item["heat_type"] == normalized_heat_type]
    if normalized_operation_status in VALID_OPERATION_STATUSES:
        items = [item for item in items if item["operation_status"] == normalized_operation_status]
    if normalized_value_status in VALID_VALUE_STATUSES:
        items = [item for item in items if item["effective_value_status"] == normalized_value_status]
    if normalized_resource_kind in RESOURCE_KIND_LABELS:
        items = [item for item in items if item["effective_resource_kind"] == normalized_resource_kind]
    if normalized_health_status in LINK_HEALTH_LABELS:
        items = [item for item in items if item["latest_link_health"] == normalized_health_status]

    summary = _build_workbench_summary(items)

    allowed_sort_fields = {
        "overall_score",
        "demand_score",
        "value_score",
        "cost_score",
        "risk_score",
        "topic_clicks_total",
        "topic_clicks_30d",
        "topic_clicks_7d",
        "topic_message_count",
        "topic_link_target_count",
        "topic_last_activity_at",
        "clicks_total",
        "clicks_30d",
        "clicks_7d",
        "unique_sessions_30d",
        "last_clicked_at",
        "last_message_time",
        "profile_updated_at",
    }
    sort_field = sort_by if sort_by in allowed_sort_fields else "overall_score"
    reverse = _normalize_text(sort_order, max_length=8).lower() != "asc"
    items.sort(key=lambda current: _build_sort_key(current, sort_field), reverse=reverse)

    total = len(items)
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size
    return {
        "items": items[start_index:end_index],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "summary": summary,
    }


def _get_topic_recent_refs(session: Session, *, link_target_ids: Iterable[int]) -> list[dict[str, Any]]:
    normalized_ids = _normalize_positive_ids(link_target_ids)
    if not normalized_ids:
        return []

    ref_rows = (
        session.query(
            MessageLinkRef.message_id.label("message_id"),
            Message.title.label("message_title"),
            Message.channel.label("message_channel"),
            Message.source.label("message_source"),
            Message.timestamp.label("message_time_fallback"),
            MessageLinkRef.link_target_id.label("link_target_id"),
            MessageLinkRef.display_text.label("display_text"),
            MessageLinkRef.target_url.label("target_url"),
            MessageLinkRef.provider_label.label("provider_label"),
            MessageLinkRef.channel.label("channel"),
            MessageLinkRef.source.label("source"),
            MessageLinkRef.message_timestamp.label("message_timestamp"),
            LinkTarget.platform.label("platform"),
            LinkTarget.share_key.label("share_key"),
        )
        .outerjoin(Message, Message.id == MessageLinkRef.message_id)
        .outerjoin(LinkTarget, LinkTarget.id == MessageLinkRef.link_target_id)
        .filter(MessageLinkRef.link_target_id.in_(normalized_ids))
        .order_by(
            MessageLinkRef.message_timestamp.is_(None).asc(),
            MessageLinkRef.message_timestamp.desc(),
            MessageLinkRef.id.desc(),
        )
        .all()
    )

    grouped: dict[int, dict[str, Any]] = {}
    for row in ref_rows:
        message_id = _to_int(row.message_id)
        if message_id <= 0:
            continue
        bucket = grouped.setdefault(
            message_id,
            {
                "message_id": message_id,
                "message_title": row.message_title or row.display_text or "",
                "display_text": row.display_text or "",
                "channel": row.channel or row.message_channel or "",
                "source": row.source or row.message_source or "",
                "message_timestamp": row.message_timestamp or row.message_time_fallback,
                "links": [],
            },
        )
        if not bucket["message_title"]:
            bucket["message_title"] = row.message_title or row.display_text or ""
        if not bucket["channel"]:
            bucket["channel"] = row.channel or row.message_channel or ""
        if not bucket["source"]:
            bucket["source"] = row.source or row.message_source or ""
        if bucket["message_timestamp"] is None:
            bucket["message_timestamp"] = row.message_timestamp or row.message_time_fallback
        existing_link_ids = {entry["link_target_id"] for entry in bucket["links"]}
        link_target_id = _to_int(row.link_target_id)
        if link_target_id > 0 and link_target_id not in existing_link_ids:
            bucket["links"].append(
                {
                    "link_target_id": link_target_id,
                    "platform": row.platform or "",
                    "display_text": row.display_text or row.provider_label or row.share_key or f"链接 {link_target_id}",
                    "target_url": row.target_url or "",
                    "share_key": row.share_key,
                }
            )

    items = list(grouped.values())
    items.sort(
        key=lambda item: (
            _datetime_sort_value(item.get("message_timestamp")),
            item.get("message_id") or 0,
        ),
        reverse=True,
    )
    return items


def _get_topic_trend_points(session: Session, *, link_target_ids: Iterable[int], days: int = 14) -> list[dict[str, Any]]:
    normalized_ids = _normalize_positive_ids(link_target_ids)
    if not normalized_ids:
        return []

    safe_days = max(7, min(int(days or 14), 30))
    start = _start_date(safe_days)
    trend_rows = (
        session.query(
            LinkTargetDailyStat.stat_date.label("stat_date"),
            func.sum(LinkTargetDailyStat.click_count).label("click_count"),
            func.sum(LinkTargetDailyStat.unique_sessions).label("unique_sessions"),
        )
        .filter(
            LinkTargetDailyStat.link_target_id.in_(normalized_ids),
            LinkTargetDailyStat.stat_date >= start,
        )
        .group_by(LinkTargetDailyStat.stat_date)
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
    points: list[dict[str, Any]] = []
    current_day = start
    while current_day <= date.today():
        current = trend_map.get(current_day, {})
        points.append(
            {
                "date": current_day.isoformat(),
                "click_count": _to_int(current.get("click_count")),
                "unique_sessions": _to_int(current.get("unique_sessions")),
                "clicked_targets": 1 if _to_int(current.get("click_count")) > 0 else 0,
            }
        )
        current_day += timedelta(days=1)
    return points


def _get_topic_candidate_logs(session: Session, *, link_target_ids: Iterable[int], limit: int = 20) -> list[dict[str, Any]]:
    normalized_ids = _normalize_positive_ids(link_target_ids)
    if not normalized_ids:
        return []

    rows = (
        session.query(ResourceCandidateLog)
        .filter(ResourceCandidateLog.link_target_id.in_(normalized_ids))
        .order_by(ResourceCandidateLog.created_at.desc(), ResourceCandidateLog.id.desc())
        .limit(max(1, min(int(limit or 20), 100)))
        .all()
    )
    return [
        {
            "id": int(row.id),
            "action_type": row.action_type or "profile_updated",
            "action_summary": row.action_summary or "",
            "note": row.note or "",
            "operator": row.operator,
            "created_at": row.created_at or _utcnow(),
            "payload": dict(row.payload or {}),
        }
        for row in rows
    ]


def get_resource_op_workbench_detail(
    session: Session,
    *,
    link_target_id: int,
    days: int = 14,
) -> dict[str, Any]:
    items = _load_workbench_topic_rows(
        session,
        days=DEFAULT_LOOKBACK_DAYS,
    )
    item = _find_topic_item_by_link_target_id(items, link_target_id=int(link_target_id))
    if item is None:
        raise LookupError(f"link_target {link_target_id} not found")

    member_link_target_ids = item.get("_member_link_target_ids") or [_to_int(item.get("link_target_id"))]
    recent_refs = _get_topic_recent_refs(session, link_target_ids=member_link_target_ids)
    topic_item = dict(item)
    topic_item["topic_message_count"] = len(recent_refs)
    return {
        "item": topic_item,
        "recent_refs": recent_refs,
        "trend": _get_topic_trend_points(session, link_target_ids=member_link_target_ids, days=days),
        "logs": _get_topic_candidate_logs(session, link_target_ids=member_link_target_ids),
        "auto_reasons": list(topic_item.get("auto_reasons") or []),
    }


def _ensure_candidate_profile(session: Session, *, link_target_id: int) -> ResourceCandidateProfile:
    profile = (
        session.query(ResourceCandidateProfile)
        .filter(ResourceCandidateProfile.link_target_id == int(link_target_id))
        .first()
    )
    if profile is not None:
        return profile

    profile = ResourceCandidateProfile(
        link_target_id=int(link_target_id),
        operation_status="pending_review",
        value_status="unreviewed",
        manual_resource_kind=None,
        note="",
    )
    session.add(profile)
    session.flush()
    return profile


def update_resource_op_workbench_item(
    session: Session,
    *,
    link_target_id: int,
    payload: ResourceOpsWorkbenchUpdateRequest,
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    items = _load_workbench_topic_rows(
        session,
        days=DEFAULT_LOOKBACK_DAYS,
    )
    topic_item = _find_topic_item_by_link_target_id(items, link_target_id=int(link_target_id))
    if topic_item is None:
        raise LookupError(f"link_target {link_target_id} not found")
    storage_link_target_id = _to_int(topic_item.get("_profile_link_target_id")) or _to_int(topic_item.get("link_target_id"))
    target = session.get(LinkTarget, int(storage_link_target_id))
    if target is None:
        raise LookupError(f"link_target {storage_link_target_id} not found")

    fields_set = set(getattr(payload, "__fields_set__", set()))
    profile_exists = (
        session.query(ResourceCandidateProfile.id)
        .filter(ResourceCandidateProfile.link_target_id == int(storage_link_target_id))
        .first()
        is not None
    )
    profile = _ensure_candidate_profile(session, link_target_id=storage_link_target_id)

    changes: dict[str, dict[str, Any]] = {}

    if "operation_status" in fields_set:
        next_operation_status = _normalize_operation_status(payload.operation_status)
        if profile.operation_status != next_operation_status:
            changes["operation_status"] = {"from": profile.operation_status, "to": next_operation_status}
            profile.operation_status = next_operation_status

    if "value_status" in fields_set:
        next_value_status = _normalize_value_status(payload.value_status)
        if profile.value_status != next_value_status:
            changes["value_status"] = {"from": profile.value_status, "to": next_value_status}
            profile.value_status = next_value_status

    if "manual_resource_kind" in fields_set:
        next_manual_kind = _normalize_manual_resource_kind(payload.manual_resource_kind)
        current_manual_kind = profile.manual_resource_kind or None
        if current_manual_kind != next_manual_kind:
            changes["manual_resource_kind"] = {"from": current_manual_kind, "to": next_manual_kind}
            profile.manual_resource_kind = next_manual_kind

    if "note" in fields_set:
        next_note = _normalize_note(payload.note)
        current_note = profile.note or ""
        if current_note != next_note:
            changes["note"] = {"from": current_note, "to": next_note}
            profile.note = next_note

    if changes:
        now = _utcnow()
        profile.updated_at = now
        profile.updated_by = operator
        session.add(profile)
        session.flush()

        summary_parts: list[str] = []
        if "operation_status" in changes:
            before = OPERATION_STATUS_LABELS.get(changes["operation_status"]["from"] or "", "未设置")
            after = OPERATION_STATUS_LABELS.get(changes["operation_status"]["to"] or "", "未设置")
            summary_parts.append(f"状态 {before} -> {after}")
        if "value_status" in changes:
            before = VALUE_STATUS_LABELS.get(changes["value_status"]["from"] or "", "未设置")
            after = VALUE_STATUS_LABELS.get(changes["value_status"]["to"] or "", "未设置")
            summary_parts.append(f"价值判断 {before} -> {after}")
        if "manual_resource_kind" in changes:
            before = RESOURCE_KIND_LABELS.get(changes["manual_resource_kind"]["from"] or "unknown", "跟随系统")
            after = RESOURCE_KIND_LABELS.get(changes["manual_resource_kind"]["to"] or "unknown", "跟随系统")
            summary_parts.append(f"资源类型 {before} -> {after}")
        if "note" in changes and len(summary_parts) < 3:
            summary_parts.append("更新备注")

        session.add(
            ResourceCandidateLog(
                profile_id=int(profile.id),
                link_target_id=int(storage_link_target_id),
                action_type="profile_created" if not profile_exists else "profile_updated",
                action_summary="；".join(summary_parts) if summary_parts else "更新候选资源策略",
                note=profile.note or "",
                payload=changes,
                operator=operator,
                created_at=now,
            )
        )
        session.flush()

    return get_resource_op_workbench_detail(session, link_target_id=storage_link_target_id)
