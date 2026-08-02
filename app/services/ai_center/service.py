from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    AiCallEvent,
    AiProviderConfig,
    AiProviderModel,
    AiRouteProfile,
    AiRouteStep,
    ensure_runtime_storage_tables,
)
from app.services.ai_center.client import (
    AI_API_MODE_AUTO,
    AiCenterError,
    complete_openai_compatible_text,
    list_openai_compatible_models,
    normalize_api_mode,
    normalize_base_url,
)
from app.services.secret_codec import decrypt_secret, encrypt_secret


logger = logging.getLogger(__name__)


AI_PROVIDER_TYPE_OPENAI_COMPATIBLE = "openai_compatible"
AI_ROUTE_OUTPUT_MODE_TEXT = "text"
AI_ROUTE_OUTPUT_MODE_JSON = "json"
AI_ROUTE_DEFAULT_MAX_ATTEMPTS = 3
AI_ROUTE_SELECTION_MODE_AUTOMATIC = "automatic"
AI_ROUTE_SELECTION_MODE_MANUAL = "manual_steps"
AI_ROUTE_SELECTION_MODE_DEFAULT = AI_ROUTE_SELECTION_MODE_AUTOMATIC
AI_ROUTE_OPTIMIZATION_GOAL_BALANCED = "balanced"
AI_ROUTE_OPTIMIZATION_GOAL_QUALITY = "quality"
AI_ROUTE_OPTIMIZATION_GOAL_STABILITY = "stability"
AI_ROUTE_OPTIMIZATION_GOAL_SPEED = "speed"
AI_ROUTE_OPTIMIZATION_GOAL_COST = "cost"
AI_ROUTE_DEFAULT_OPTIMIZATION_GOAL = AI_ROUTE_OPTIMIZATION_GOAL_BALANCED
AI_EVENT_STATUS_SUCCESS = "success"
AI_EVENT_STATUS_ERROR = "error"
AI_EVENT_STATUS_SKIPPED = "skipped"
AI_MODEL_SCORE_DEFAULT = 50
AI_EMPTY_RESPONSE_MARKERS = (
    "empty message",
    "no content",
    "recognizable text",
    "returned no content",
)
AI_ROUTE_CAPABILITY_DEFAULTS: dict[str, list[str]] = {
    "resource_ops_title_extract": ["title_extraction", "chinese", "low_latency"],
    "pan_transfer_follow_identity_extract": ["structured_output", "entity_extraction", "chinese"],
    "pan_transfer_follow_candidate_judge": ["structured_output", "reasoning", "chinese"],
}
AI_ROUTE_GOAL_DEFAULTS: dict[str, str] = {
    "resource_ops_title_extract": AI_ROUTE_OPTIMIZATION_GOAL_SPEED,
    "pan_transfer_follow_identity_extract": AI_ROUTE_OPTIMIZATION_GOAL_STABILITY,
    "pan_transfer_follow_candidate_judge": AI_ROUTE_OPTIMIZATION_GOAL_QUALITY,
}

AI_ROUTE_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "route_key": "resource_ops_title_extract",
        "display_name": "作品归并标题提取",
        "description": "供作品归并队列调用，从原始资源标题中提取作品核心标题。",
        "output_mode": AI_ROUTE_OUTPUT_MODE_TEXT,
    },
    {
        "route_key": "pan_transfer_follow_identity_extract",
        "display_name": "追更身份提取",
        "description": "供追更同步创建与巡检调用，抽取核心剧名、别名、年份、季集线索。",
        "output_mode": AI_ROUTE_OUTPUT_MODE_JSON,
    },
    {
        "route_key": "pan_transfer_follow_candidate_judge",
        "display_name": "追更候选判断",
        "description": "供追更同步巡检调用，判断候选消息是否同作品且是否较当前资源更新。",
        "output_mode": AI_ROUTE_OUTPUT_MODE_JSON,
    },
)


@dataclass(slots=True)
class AiCenterRouteResult:
    text: str
    route_key: str
    provider_id: int | None
    provider_label: str | None
    model_id: str | None
    used_api_mode: str | None
    route_profile_id: int | None
    route_step_id: int | None
    duration_ms: int | None
    event_id: int | None
    selection_summary: str | None = None
    attempt_trace: list[dict[str, Any]] | None = None


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


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _normalize_int(
    value: Any,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    if minimum is not None:
        normalized = max(minimum, normalized)
    if maximum is not None:
        normalized = min(maximum, normalized)
    return normalized


def _normalize_string_list(
    value: Any,
    *,
    max_items: int = 24,
    item_max_length: int = 64,
) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n,，;；]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = _normalize_text(raw, max_length=item_max_length)
        if not text:
            continue
        normalized_key = text.lower()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        items.append(text)
        if len(items) >= max_items:
            break
    return items


def _normalize_score(value: Any, *, default: int = AI_MODEL_SCORE_DEFAULT) -> int:
    return _normalize_int(value, default, minimum=0, maximum=100)


def _default_route_preferred_capabilities(route_key: str) -> list[str]:
    return list(AI_ROUTE_CAPABILITY_DEFAULTS.get(route_key, []))


def _default_route_optimization_goal(route_key: str) -> str:
    return AI_ROUTE_GOAL_DEFAULTS.get(route_key, AI_ROUTE_DEFAULT_OPTIMIZATION_GOAL)


def _normalize_model_settings(extra_json: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(extra_json or {})
    return {
        "capabilities": _normalize_string_list(raw.get("capabilities")),
        "route_allowlist": _normalize_string_list(raw.get("route_allowlist"), max_items=24, item_max_length=128),
        "priority_bias": _normalize_int(raw.get("priority_bias"), 0, minimum=-200, maximum=200),
        "quality_score": _normalize_score(raw.get("quality_score")),
        "speed_score": _normalize_score(raw.get("speed_score")),
        "cost_score": _normalize_score(raw.get("cost_score")),
        "stability_score": _normalize_score(raw.get("stability_score")),
        "notes": _normalize_text(raw.get("notes"), max_length=500) or None,
    }


def _merge_model_settings(*, existing: dict[str, Any] | None, payload: dict[str, Any] | None) -> dict[str, Any]:
    merged = {
        **dict(existing or {}),
        **dict(payload or {}),
    }
    normalized = _normalize_model_settings(merged)
    return {
        **dict(existing or {}),
        **dict(payload or {}),
        **normalized,
    }


def _extract_model_settings_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    normalized = {
        "capabilities": raw.get("capabilities"),
        "route_allowlist": raw.get("route_allowlist"),
        "priority_bias": raw.get("priority_bias"),
        "quality_score": raw.get("quality_score"),
        "speed_score": raw.get("speed_score"),
        "cost_score": raw.get("cost_score"),
        "stability_score": raw.get("stability_score"),
        "notes": raw.get("notes"),
    }
    return {
        **dict(raw.get("extra_json") or {}),
        **{key: value for key, value in normalized.items() if value is not None},
    }


def _normalize_route_settings(*, route_key: str, extra_json: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(extra_json or {})
    selection_mode = _normalize_text(raw.get("selection_mode"), max_length=32).lower() or AI_ROUTE_SELECTION_MODE_DEFAULT
    if selection_mode not in {AI_ROUTE_SELECTION_MODE_AUTOMATIC, AI_ROUTE_SELECTION_MODE_MANUAL}:
        selection_mode = AI_ROUTE_SELECTION_MODE_DEFAULT
    optimization_goal = _normalize_text(raw.get("optimization_goal"), max_length=32).lower() or _default_route_optimization_goal(route_key)
    if optimization_goal not in {
        AI_ROUTE_OPTIMIZATION_GOAL_BALANCED,
        AI_ROUTE_OPTIMIZATION_GOAL_QUALITY,
        AI_ROUTE_OPTIMIZATION_GOAL_STABILITY,
        AI_ROUTE_OPTIMIZATION_GOAL_SPEED,
        AI_ROUTE_OPTIMIZATION_GOAL_COST,
    }:
        optimization_goal = _default_route_optimization_goal(route_key)
    preferred_capabilities = _normalize_string_list(raw.get("preferred_capabilities")) or _default_route_preferred_capabilities(route_key)
    return {
        "selection_mode": selection_mode,
        "optimization_goal": optimization_goal,
        "preferred_capabilities": preferred_capabilities,
        "allow_same_provider_model_failover": _normalize_bool(raw.get("allow_same_provider_model_failover"), True),
        "allow_cross_provider_failover": _normalize_bool(raw.get("allow_cross_provider_failover"), True),
    }


def _merge_route_settings(
    *,
    route_key: str,
    existing: dict[str, Any] | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = {
        **dict(existing or {}),
        **dict(payload or {}),
    }
    normalized = _normalize_route_settings(route_key=route_key, extra_json=merged)
    return {
        **merged,
        **normalized,
    }


def _is_empty_response_error(message: str | None) -> bool:
    normalized = _normalize_text(message, max_length=2000).lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in AI_EMPTY_RESPONSE_MARKERS)


def _load_ai_call_stats(
    session: Session,
    *,
    provider_ids: list[int],
    route_key: str,
    since_days: int = 14,
) -> dict[str, dict[tuple[int, str], dict[str, Any]]]:
    if not provider_ids:
        return {"global": {}, "route": {}}
    since = _utcnow() - timedelta(days=max(1, int(since_days)))
    rows = (
        session.query(AiCallEvent)
        .filter(
            AiCallEvent.provider_id.in_(provider_ids),
            AiCallEvent.created_at >= since,
        )
        .order_by(AiCallEvent.created_at.desc(), AiCallEvent.id.desc())
        .all()
    )
    stats = {"global": {}, "route": {}}
    for row in rows:
        provider_id = int(row.provider_id) if row.provider_id is not None else None
        if provider_id is None:
            continue
        model_id = _normalize_text(row.model_id, max_length=255)
        if not model_id:
            continue
        bucket_names = ["global"]
        if _normalize_text(row.route_key, max_length=128) == route_key:
            bucket_names.append("route")
        for bucket_name in bucket_names:
            key = (provider_id, model_id)
            bucket = stats[bucket_name].setdefault(
                key,
                {
                    "success_count": 0,
                    "error_count": 0,
                    "empty_response_count": 0,
                    "last_success_at": None,
                    "last_error_at": None,
                    "last_event_at": None,
                },
            )
            bucket["last_event_at"] = bucket["last_event_at"] or row.created_at
            status = _normalize_text(row.status, max_length=32).lower()
            if status == AI_EVENT_STATUS_SUCCESS:
                bucket["success_count"] += 1
                bucket["last_success_at"] = bucket["last_success_at"] or row.created_at
            elif status == AI_EVENT_STATUS_ERROR:
                bucket["error_count"] += 1
                if _is_empty_response_error(row.error_message):
                    bucket["empty_response_count"] += 1
                bucket["last_error_at"] = bucket["last_error_at"] or row.created_at
    return stats


def _score_model_goal(model_settings: dict[str, Any], optimization_goal: str) -> float:
    metrics = {
        "quality": int(model_settings.get("quality_score") or AI_MODEL_SCORE_DEFAULT),
        "stability": int(model_settings.get("stability_score") or AI_MODEL_SCORE_DEFAULT),
        "speed": int(model_settings.get("speed_score") or AI_MODEL_SCORE_DEFAULT),
        "cost": int(model_settings.get("cost_score") or AI_MODEL_SCORE_DEFAULT),
    }
    weights: dict[str, float]
    if optimization_goal == AI_ROUTE_OPTIMIZATION_GOAL_QUALITY:
        weights = {"quality": 0.55, "stability": 0.2, "speed": 0.1, "cost": 0.15}
    elif optimization_goal == AI_ROUTE_OPTIMIZATION_GOAL_STABILITY:
        weights = {"quality": 0.2, "stability": 0.55, "speed": 0.1, "cost": 0.15}
    elif optimization_goal == AI_ROUTE_OPTIMIZATION_GOAL_SPEED:
        weights = {"quality": 0.15, "stability": 0.15, "speed": 0.55, "cost": 0.15}
    elif optimization_goal == AI_ROUTE_OPTIMIZATION_GOAL_COST:
        weights = {"quality": 0.15, "stability": 0.15, "speed": 0.1, "cost": 0.6}
    else:
        weights = {"quality": 0.3, "stability": 0.3, "speed": 0.2, "cost": 0.2}
    weighted = sum((metrics[name] - AI_MODEL_SCORE_DEFAULT) * weight for name, weight in weights.items())
    return round(weighted / 2.0, 2)


def _score_stats_bucket(stats: dict[str, Any] | None, *, weight: float) -> float:
    if not stats:
        return 0.0
    score = 0.0
    score += min(int(stats.get("success_count") or 0) * 2, 12)
    score -= min(int(stats.get("error_count") or 0) * 3, 18)
    score -= min(int(stats.get("empty_response_count") or 0) * 5, 20)
    return round(score * weight, 2)


def _build_candidate_summary(candidate: dict[str, Any]) -> str:
    provider_label = _normalize_text(candidate.get("provider_label"), max_length=128) or "-"
    model_id = _normalize_text(candidate.get("model_id"), max_length=255) or "auto"
    mode = _normalize_text(candidate.get("selection_mode"), max_length=32) or AI_ROUTE_SELECTION_MODE_DEFAULT
    goal = _normalize_text(candidate.get("optimization_goal"), max_length=32) or AI_ROUTE_DEFAULT_OPTIMIZATION_GOAL
    score = candidate.get("score")
    score_label = f"{float(score):.1f}" if isinstance(score, (float, int)) else "-"
    return f"{provider_label} / {model_id} ({mode}, {goal}, score {score_label})"

def _normalize_provider_key(value: Any) -> str:
    raw = _normalize_text(value, max_length=64).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return normalized[:64]


def _serialize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _to_utc_iso(value)
    if isinstance(value, dict):
        return {str(key): _serialize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_json_value(item) for item in value]
    return _normalize_text(value, max_length=4000) or repr(value)


def _normalize_event_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _serialize_json_value(payload or {})
    return normalized if isinstance(normalized, dict) else {"value": normalized}


def _truncate_text(value: Any, *, max_length: int = 240) -> str:
    text = _normalize_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _serialize_provider_model(
    row: AiProviderModel,
    *,
    stats_by_model: dict[tuple[int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    model_settings = _normalize_model_settings(dict(row.extra_json or {}))
    stats = (stats_by_model or {}).get((int(row.provider_id), _normalize_text(row.model_id, max_length=255)), {})
    return {
        "id": int(row.id),
        "provider_id": int(row.provider_id),
        "model_id": str(row.model_id or ""),
        "label": _normalize_text(row.label, max_length=255) or _normalize_text(row.model_id, max_length=255),
        "owned_by": _normalize_text(row.owned_by, max_length=255) or None,
        "is_enabled": bool(row.is_enabled),
        "is_preferred": bool(row.is_preferred),
        "capabilities": list(model_settings["capabilities"]),
        "route_allowlist": list(model_settings["route_allowlist"]),
        "priority_bias": int(model_settings["priority_bias"]),
        "quality_score": int(model_settings["quality_score"]),
        "speed_score": int(model_settings["speed_score"]),
        "cost_score": int(model_settings["cost_score"]),
        "stability_score": int(model_settings["stability_score"]),
        "notes": model_settings["notes"],
        "recent_success_count": int(stats.get("success_count") or 0),
        "recent_error_count": int(stats.get("error_count") or 0),
        "recent_empty_response_count": int(stats.get("empty_response_count") or 0),
        "last_event_at": stats.get("last_event_at"),
        "extra_json": dict(row.extra_json or {}),
        "last_refreshed_at": row.last_refreshed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _load_provider_models(session: Session, *, provider_id: int) -> list[AiProviderModel]:
    return (
        session.query(AiProviderModel)
        .filter(AiProviderModel.provider_id == int(provider_id))
        .order_by(
            AiProviderModel.is_preferred.desc(),
            AiProviderModel.is_enabled.desc(),
            AiProviderModel.model_id.asc(),
            AiProviderModel.id.asc(),
        )
        .all()
    )


def _serialize_provider(
    row: AiProviderConfig,
    *,
    models: list[AiProviderModel],
    stats_by_model: dict[tuple[int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    enabled_models = [item for item in models if bool(item.is_enabled)]
    preferred_model = next((item for item in enabled_models if bool(item.is_preferred)), None)
    decrypted_api_key = decrypt_secret(_normalize_text(row.api_key_encrypted, max_length=8000))
    return {
        "id": int(row.id),
        "provider_key": str(row.provider_key or ""),
        "display_name": _normalize_text(row.display_name, max_length=128) or _normalize_text(row.provider_key, max_length=64),
        "provider_type": _normalize_text(row.provider_type, max_length=32) or AI_PROVIDER_TYPE_OPENAI_COMPATIBLE,
        "base_url": _normalize_text(row.base_url, max_length=512),
        "api_mode": normalize_api_mode(row.api_mode or AI_API_MODE_AUTO),
        "is_enabled": bool(row.is_enabled),
        "is_default": bool(row.is_default),
        "priority": int(row.priority or 100),
        "timeout_seconds": int(row.timeout_seconds or 25),
        "max_retries": int(row.max_retries or 1),
        "cooldown_seconds": int(row.cooldown_seconds or 300),
        "cooldown_until": row.cooldown_until,
        "health_status": _normalize_text(row.health_status, max_length=32) or "unknown",
        "consecutive_failures": int(row.consecutive_failures or 0),
        "last_checked_at": row.last_checked_at,
        "last_success_at": row.last_success_at,
        "last_failure_at": row.last_failure_at,
        "last_error_message": _normalize_text(row.last_error_message, max_length=2000) or None,
        "has_api_key": bool(decrypted_api_key),
        "model_count": len(models),
        "enabled_model_count": len(enabled_models),
        "preferred_model_id": _normalize_text(getattr(preferred_model, "model_id", None), max_length=255) or None,
        "updated_by": _normalize_text(row.updated_by, max_length=128) or None,
        "extra_json": dict(row.extra_json or {}),
        "models": [_serialize_provider_model(model, stats_by_model=stats_by_model) for model in models],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_route_step(
    row: AiRouteStep,
    *,
    provider: AiProviderConfig | None,
    provider_models: list[AiProviderModel],
) -> dict[str, Any]:
    provider_model_lookup = {str(model.model_id or ""): model for model in provider_models}
    model = provider_model_lookup.get(_normalize_text(row.model_id, max_length=255))
    return {
        "id": int(row.id),
        "step_index": int(row.step_index or 1),
        "provider_id": int(row.provider_id),
        "provider_key": _normalize_text(getattr(provider, "provider_key", None), max_length=64) or None,
        "provider_label": _normalize_text(getattr(provider, "display_name", None), max_length=128)
        or _normalize_text(getattr(provider, "provider_key", None), max_length=64)
        or None,
        "provider_enabled": bool(getattr(provider, "is_enabled", False)),
        "provider_health_status": _normalize_text(getattr(provider, "health_status", None), max_length=32) or "unknown",
        "model_id": _normalize_text(row.model_id, max_length=255) or None,
        "model_label": _normalize_text(getattr(model, "label", None), max_length=255)
        or _normalize_text(getattr(model, "model_id", None), max_length=255)
        or _normalize_text(row.model_id, max_length=255)
        or None,
        "is_enabled": bool(row.is_enabled),
        "extra_json": dict(row.extra_json or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _resolve_provider_model_id(
    *,
    step: AiRouteStep,
    provider_id: int,
    provider_models_lookup: dict[int, list[AiProviderModel]],
) -> str | None:
    configured_model_id = _normalize_text(step.model_id, max_length=255)
    if configured_model_id:
        return configured_model_id
    provider_models = provider_models_lookup.get(int(provider_id), [])
    preferred = next((row for row in provider_models if bool(row.is_enabled) and bool(row.is_preferred)), None)
    if preferred is not None:
        return _normalize_text(preferred.model_id, max_length=255) or None
    enabled = next((row for row in provider_models if bool(row.is_enabled)), None)
    if enabled is not None:
        return _normalize_text(enabled.model_id, max_length=255) or None
    fallback = provider_models[0] if provider_models else None
    if fallback is None:
        return None
    return _normalize_text(fallback.model_id, max_length=255) or None


def _build_route_candidates(
    session: Session,
    *,
    route: AiRouteProfile,
    steps: list[AiRouteStep],
    provider_lookup: dict[int, AiProviderConfig],
    provider_models_lookup: dict[int, list[AiProviderModel]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    route_key = _normalize_text(route.route_key, max_length=128)
    route_settings = _normalize_route_settings(route_key=route_key, extra_json=dict(route.extra_json or {}))
    provider_ids = [int(step.provider_id) for step in steps if int(step.provider_id or 0) > 0]
    stats = _load_ai_call_stats(session, provider_ids=provider_ids, route_key=route_key)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    now = _utcnow()

    for step in sorted(steps, key=lambda item: (int(item.step_index or 1), int(item.id))):
        if not bool(step.is_enabled):
            continue
        provider = provider_lookup.get(int(step.provider_id))
        if provider is None or not bool(provider.is_enabled):
            continue
        if provider.cooldown_until is not None and provider.cooldown_until > now:
            continue
        api_key = decrypt_secret(_normalize_text(provider.api_key_encrypted, max_length=8000))
        if not normalize_base_url(provider.base_url or "") or not _normalize_text(api_key, max_length=8000):
            continue

        provider_models = provider_models_lookup.get(int(provider.id), [])
        explicit_model_id = _normalize_text(step.model_id, max_length=255)
        model_candidates: list[AiProviderModel | None] = []
        if explicit_model_id:
            matched_model = next(
                (
                    row
                    for row in provider_models
                    if _normalize_text(row.model_id, max_length=255) == explicit_model_id and bool(row.is_enabled)
                ),
                None,
            )
            if matched_model is not None:
                model_candidates = [matched_model]
            else:
                model_candidates = [None]
        elif route_settings["selection_mode"] == AI_ROUTE_SELECTION_MODE_AUTOMATIC and route_settings["allow_same_provider_model_failover"]:
            model_candidates = [row for row in provider_models if bool(row.is_enabled)]
            if not model_candidates:
                model_candidates = [None]
        else:
            resolved_model_id = _resolve_provider_model_id(
                step=step,
                provider_id=int(provider.id),
                provider_models_lookup=provider_models_lookup,
            )
            if resolved_model_id:
                matched_model = next(
                    (
                        row
                        for row in provider_models
                        if _normalize_text(row.model_id, max_length=255) == resolved_model_id and bool(row.is_enabled)
                    ),
                    None,
                )
                model_candidates = [matched_model] if matched_model is not None else [None]
            else:
                model_candidates = [None]

        for model in model_candidates:
            model_id = _normalize_text(getattr(model, "model_id", None), max_length=255) or explicit_model_id
            candidate_key = (int(provider.id), model_id or "__provider_auto__")
            if candidate_key in seen:
                continue

            model_settings = _normalize_model_settings(dict(getattr(model, "extra_json", {}) or {}))
            allowlist = set(model_settings["route_allowlist"])
            if allowlist and route_key not in allowlist:
                continue

            reasons: list[str] = []
            score = 0.0
            if route_settings["selection_mode"] == AI_ROUTE_SELECTION_MODE_MANUAL:
                score += 1000 - int(step.step_index or 1) * 10
                reasons.append(f"manual step {int(step.step_index or 1)}")
            else:
                step_bonus = max(0, 18 - (int(step.step_index or 1) - 1) * 3)
                if step_bonus:
                    score += step_bonus
                    reasons.append(f"step+{step_bonus}")

            provider_bonus = max(-12, 12 - int(provider.priority or 100) // 10)
            if provider_bonus:
                score += provider_bonus
                reasons.append(f"provider{provider_bonus:+d}")
            if bool(provider.is_default):
                score += 4
                reasons.append("default+4")
            if _normalize_text(provider.health_status, max_length=32) == "healthy":
                score += 6
                reasons.append("healthy+6")
            elif _normalize_text(provider.health_status, max_length=32) == "degraded":
                score -= 6
                reasons.append("degraded-6")

            if model is not None and bool(model.is_preferred):
                score += 8
                reasons.append("preferred+8")

            priority_bias = int(model_settings["priority_bias"])
            if priority_bias:
                score += priority_bias
                reasons.append(f"bias{priority_bias:+d}")

            preferred_capabilities = set(route_settings["preferred_capabilities"])
            matched_capabilities = [
                capability
                for capability in model_settings["capabilities"]
                if capability in preferred_capabilities
            ]
            if matched_capabilities:
                capability_bonus = len(matched_capabilities) * 6
                score += capability_bonus
                reasons.append(f"caps+{capability_bonus}")

            goal_bonus = _score_model_goal(model_settings, route_settings["optimization_goal"])
            if goal_bonus:
                score += goal_bonus
                reasons.append(f"goal{goal_bonus:+.1f}")

            stats_key = (int(provider.id), model_id)
            route_stats = stats["route"].get(stats_key, {}) if model_id else {}
            global_stats = stats["global"].get(stats_key, {}) if model_id else {}
            route_stats_bonus = _score_stats_bucket(route_stats, weight=1.0)
            global_stats_bonus = _score_stats_bucket(global_stats, weight=0.5)
            if route_stats_bonus:
                score += route_stats_bonus
                reasons.append(f"route{route_stats_bonus:+.1f}")
            if global_stats_bonus:
                score += global_stats_bonus
                reasons.append(f"global{global_stats_bonus:+.1f}")

            candidate = {
                "route_step_id": int(step.id),
                "step_index": int(step.step_index or 1),
                "provider_id": int(provider.id),
                "provider_label": _normalize_text(provider.display_name, max_length=128) or provider.provider_key,
                "provider_key": _normalize_text(provider.provider_key, max_length=64) or None,
                "provider_priority": int(provider.priority or 100),
                "model_id": model_id or None,
                "model_label": (
                    _normalize_text(getattr(model, "label", None), max_length=255)
                    or model_id
                    or "auto"
                ),
                "model_row": model,
                "selection_mode": route_settings["selection_mode"],
                "optimization_goal": route_settings["optimization_goal"],
                "score": round(score, 2),
                "reasons": reasons,
            }
            candidate["selection_summary"] = _build_candidate_summary(candidate)
            candidates.append(candidate)
            seen.add(candidate_key)

    if route_settings["selection_mode"] == AI_ROUTE_SELECTION_MODE_MANUAL or not route_settings["allow_cross_provider_failover"]:
        candidates.sort(
            key=lambda item: (
                int(item["step_index"]),
                -float(item["score"]),
                int(item["provider_priority"]),
                0 if item["model_id"] else 1,
                _normalize_text(item["model_id"], max_length=255),
            )
        )
    else:
        candidates.sort(
            key=lambda item: (
                -float(item["score"]),
                int(item["step_index"]),
                int(item["provider_priority"]),
                0 if item["model_id"] else 1,
                _normalize_text(item["model_id"], max_length=255),
            )
        )

    return candidates, route_settings


def _build_route_readiness(
    session: Session,
    route: AiRouteProfile,
    *,
    steps: list[AiRouteStep],
    provider_lookup: dict[int, AiProviderConfig],
    provider_models_lookup: dict[int, list[AiProviderModel]],
) -> dict[str, Any]:
    enabled_steps = [step for step in steps if bool(step.is_enabled)]
    route_settings = _normalize_route_settings(
        route_key=_normalize_text(route.route_key, max_length=128),
        extra_json=dict(route.extra_json or {}),
    )
    if not bool(route.is_enabled):
        return {
            "is_ready": False,
            "reason": "route_disabled",
            "provider_label": None,
            "model_id": None,
            "selection_mode": route_settings["selection_mode"],
            "optimization_goal": route_settings["optimization_goal"],
            "candidate_count": 0,
            "selection_summary": None,
            "step_count": len(steps),
            "enabled_step_count": len(enabled_steps),
        }
    candidates, route_settings = _build_route_candidates(
        session,
        route=route,
        steps=enabled_steps,
        provider_lookup=provider_lookup,
        provider_models_lookup=provider_models_lookup,
    )
    top_candidate = candidates[0] if candidates else None
    if top_candidate is not None:
        return {
            "is_ready": True,
            "reason": None,
            "provider_label": top_candidate["provider_label"],
            "model_id": top_candidate["model_id"],
            "selection_mode": route_settings["selection_mode"],
            "optimization_goal": route_settings["optimization_goal"],
            "candidate_count": len(candidates),
            "selection_summary": top_candidate["selection_summary"],
            "step_count": len(steps),
            "enabled_step_count": len(enabled_steps),
        }
    return {
        "is_ready": False,
        "reason": "no_enabled_provider_step",
        "provider_label": None,
        "model_id": None,
        "selection_mode": route_settings["selection_mode"],
        "optimization_goal": route_settings["optimization_goal"],
        "candidate_count": 0,
        "selection_summary": None,
        "step_count": len(steps),
        "enabled_step_count": len(enabled_steps),
    }


def _serialize_route(
    session: Session,
    row: AiRouteProfile,
    *,
    steps: list[AiRouteStep],
    provider_lookup: dict[int, AiProviderConfig],
    provider_models_lookup: dict[int, list[AiProviderModel]],
) -> dict[str, Any]:
    route_settings = _normalize_route_settings(
        route_key=_normalize_text(row.route_key, max_length=128),
        extra_json=dict(row.extra_json or {}),
    )
    serialized_steps = [
        _serialize_route_step(
            step,
            provider=provider_lookup.get(int(step.provider_id)),
            provider_models=provider_models_lookup.get(int(step.provider_id), []),
        )
        for step in sorted(steps, key=lambda item: (int(item.step_index or 1), int(item.id)))
    ]
    readiness = _build_route_readiness(
        session,
        row,
        steps=steps,
        provider_lookup=provider_lookup,
        provider_models_lookup=provider_models_lookup,
    )
    return {
        "id": int(row.id),
        "route_key": str(row.route_key or ""),
        "display_name": _normalize_text(row.display_name, max_length=128) or _normalize_text(row.route_key, max_length=128),
        "description": _normalize_text(row.description, max_length=2000),
        "output_mode": _normalize_text(row.output_mode, max_length=32) or AI_ROUTE_OUTPUT_MODE_TEXT,
        "is_enabled": bool(row.is_enabled),
        "max_attempts": int(row.max_attempts or AI_ROUTE_DEFAULT_MAX_ATTEMPTS),
        "selection_mode": route_settings["selection_mode"],
        "optimization_goal": route_settings["optimization_goal"],
        "preferred_capabilities": list(route_settings["preferred_capabilities"]),
        "allow_same_provider_model_failover": bool(route_settings["allow_same_provider_model_failover"]),
        "allow_cross_provider_failover": bool(route_settings["allow_cross_provider_failover"]),
        "updated_by": _normalize_text(row.updated_by, max_length=128) or None,
        "extra_json": dict(row.extra_json or {}),
        "steps": serialized_steps,
        "configured_step_count": len(steps),
        "enabled_step_count": sum(1 for step in steps if bool(step.is_enabled)),
        "candidate_count": int(readiness["candidate_count"] or 0),
        "is_ready": bool(readiness["is_ready"]),
        "ready_reason": readiness["reason"],
        "ready_provider_label": readiness["provider_label"],
        "ready_model_id": readiness["model_id"],
        "selection_summary": readiness["selection_summary"],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_call_event(row: AiCallEvent) -> dict[str, Any]:
    extra_json = dict(row.extra_json or {})
    candidate_score = None
    if extra_json.get("candidate_score") is not None:
        try:
            candidate_score = float(extra_json.get("candidate_score"))
        except (TypeError, ValueError):
            candidate_score = None
    return {
        "id": int(row.id),
        "route_key": str(row.route_key or ""),
        "route_profile_id": int(row.route_profile_id) if row.route_profile_id is not None else None,
        "route_step_id": int(row.route_step_id) if row.route_step_id is not None else None,
        "provider_id": int(row.provider_id) if row.provider_id is not None else None,
        "provider_label": _normalize_text(row.provider_label, max_length=128) or None,
        "model_id": _normalize_text(row.model_id, max_length=255) or None,
        "status": _normalize_text(row.status, max_length=32) or AI_EVENT_STATUS_SUCCESS,
        "error_type": _normalize_text(row.error_type, max_length=64) or None,
        "error_message": _normalize_text(row.error_message, max_length=2000) or None,
        "duration_ms": int(row.duration_ms) if row.duration_ms is not None else None,
        "used_api_mode": _normalize_text(extra_json.get("used_api_mode"), max_length=32) or None,
        "selection_mode": _normalize_text(extra_json.get("selection_mode"), max_length=32) or None,
        "selection_summary": _normalize_text(extra_json.get("selection_summary"), max_length=255) or None,
        "attempt_index": int(extra_json.get("attempt_index")) if extra_json.get("attempt_index") is not None else None,
        "candidate_score": candidate_score,
        "extra_json": extra_json,
        "created_at": row.created_at,
    }


def _set_provider_default(session: Session, *, provider_id: int) -> None:
    (
        session.query(AiProviderConfig)
        .filter(AiProviderConfig.id != int(provider_id), AiProviderConfig.is_default.is_(True))
        .update({"is_default": False}, synchronize_session=False)
    )


def _ensure_preferred_provider_model(session: Session, *, provider_id: int) -> None:
    models = _load_provider_models(session, provider_id=provider_id)
    if not models:
        return
    enabled_models = [row for row in models if bool(row.is_enabled)]
    preferred = next((row for row in enabled_models if bool(row.is_preferred)), None)
    if preferred is not None:
        return
    candidate = enabled_models[0] if enabled_models else models[0]
    for row in models:
        row.is_preferred = int(row.id) == int(candidate.id)
        session.add(row)


def _record_call_event(
    session: Session,
    *,
    route_key: str,
    route_profile_id: int | None,
    route_step_id: int | None,
    provider_id: int | None,
    provider_label: str | None,
    model_id: str | None,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    extra_json: dict[str, Any] | None = None,
) -> AiCallEvent:
    row = AiCallEvent(
        route_key=_normalize_text(route_key, max_length=128),
        route_profile_id=route_profile_id,
        route_step_id=route_step_id,
        provider_id=provider_id,
        provider_label=_normalize_text(provider_label, max_length=128) or None,
        model_id=_normalize_text(model_id, max_length=255) or None,
        status=_normalize_text(status, max_length=32) or AI_EVENT_STATUS_SUCCESS,
        error_type=_normalize_text(error_type, max_length=64) or None,
        error_message=_normalize_text(error_message, max_length=2000) or None,
        duration_ms=duration_ms,
        extra_json=_normalize_event_payload(extra_json),
    )
    session.add(row)
    session.flush()
    return row


def _mark_provider_success(session: Session, *, provider: AiProviderConfig) -> None:
    now = _utcnow()
    provider.health_status = "healthy"
    provider.consecutive_failures = 0
    provider.cooldown_until = None
    provider.last_checked_at = now
    provider.last_success_at = now
    provider.last_error_message = None
    session.add(provider)


def _mark_provider_failure(session: Session, *, provider: AiProviderConfig, error_message: str) -> None:
    now = _utcnow()
    provider.consecutive_failures = int(provider.consecutive_failures or 0) + 1
    provider.health_status = "degraded"
    provider.last_checked_at = now
    provider.last_failure_at = now
    provider.last_error_message = _normalize_text(error_message, max_length=2000) or "unknown error"
    cooldown_seconds = max(0, int(provider.cooldown_seconds or 0))
    provider.cooldown_until = now + timedelta(seconds=cooldown_seconds) if cooldown_seconds > 0 else None
    session.add(provider)


def _upsert_provider_model(
    session: Session,
    *,
    provider_id: int,
    payload: dict[str, Any],
    preferred_model_id: str | None = None,
) -> AiProviderModel:
    model_id = _normalize_text(payload.get("id") or payload.get("model_id"), max_length=255)
    if not model_id:
        raise ValueError("model_id cannot be empty")
    row = (
        session.query(AiProviderModel)
        .filter(
            AiProviderModel.provider_id == int(provider_id),
            AiProviderModel.model_id == model_id,
        )
        .first()
    )
    if row is None:
        row = AiProviderModel(
            provider_id=int(provider_id),
            model_id=model_id,
        )
    incoming_label = _normalize_text(payload.get("label"), max_length=255)
    if row.id is None or not _normalize_text(row.label, max_length=255):
        row.label = incoming_label or model_id
    elif incoming_label and _normalize_text(row.label, max_length=255) == _normalize_text(row.model_id, max_length=255):
        row.label = incoming_label
    row.owned_by = _normalize_text(payload.get("owned_by"), max_length=255) or row.owned_by
    if "is_enabled" in payload:
        row.is_enabled = _normalize_bool(payload.get("is_enabled"), bool(row.is_enabled) if row.id is not None else True)
    elif row.id is None:
        row.is_enabled = True
    if preferred_model_id is not None:
        row.is_preferred = model_id == _normalize_text(preferred_model_id, max_length=255)
    row.last_refreshed_at = _utcnow()
    row.extra_json = _merge_model_settings(
        existing=dict(row.extra_json or {}),
        payload=_extract_model_settings_payload(payload),
    )
    session.add(row)
    session.flush()
    return row


def _save_provider_models(
    session: Session,
    *,
    provider_id: int,
    payload_models: list[dict[str, Any]],
) -> None:
    existing_rows = _load_provider_models(session, provider_id=provider_id)
    by_id = {int(row.id): row for row in existing_rows}
    by_model_id = {
        _normalize_text(row.model_id, max_length=255): row
        for row in existing_rows
        if _normalize_text(row.model_id, max_length=255)
    }
    preferred_model_id = _normalize_text(
        next(
            (
                raw.get("model_id")
                for raw in payload_models
                if _normalize_bool(raw.get("is_preferred"), False) and _normalize_text(raw.get("model_id"), max_length=255)
            ),
            None,
        ),
        max_length=255,
    ) or None

    claimed_model_ids: set[str] = set()
    for raw in payload_models:
        payload = dict(raw or {})
        model_id = _normalize_text(payload.get("model_id") or payload.get("id"), max_length=255)
        if not model_id:
            continue
        row = None
        explicit_id = _normalize_int(payload.get("id"), 0, minimum=0)
        if explicit_id > 0:
            row = by_id.get(explicit_id)
        if row is None:
            row = by_model_id.get(model_id)
        if row is None:
            row = AiProviderModel(provider_id=int(provider_id), model_id=model_id, label=model_id)
        row.model_id = model_id
        label = _normalize_text(payload.get("label"), max_length=255)
        if label:
            row.label = label
        elif not _normalize_text(row.label, max_length=255):
            row.label = model_id
        row.owned_by = _normalize_text(payload.get("owned_by"), max_length=255) or row.owned_by
        row.is_enabled = _normalize_bool(payload.get("is_enabled"), bool(row.is_enabled) if row.id is not None else True)
        row.extra_json = _merge_model_settings(
            existing=dict(row.extra_json or {}),
            payload=_extract_model_settings_payload(payload),
        )
        row.is_preferred = preferred_model_id is not None and model_id == preferred_model_id
        session.add(row)
        session.flush()
        claimed_model_ids.add(model_id)

    for row in existing_rows:
        row_model_id = _normalize_text(row.model_id, max_length=255)
        if row_model_id and row_model_id not in claimed_model_ids:
            row.is_enabled = False
            row.is_preferred = False
            session.add(row)

    if preferred_model_id is not None:
        rows = _load_provider_models(session, provider_id=provider_id)
        for row in rows:
            row_model_id = _normalize_text(row.model_id, max_length=255)
            row.is_preferred = row_model_id == preferred_model_id
            session.add(row)

    _ensure_preferred_provider_model(session, provider_id=provider_id)


def _ensure_route_seed_rows(session: Session) -> None:
    existing = {
        str(row.route_key or ""): row
        for row in session.query(AiRouteProfile).all()
    }
    for seed in AI_ROUTE_SEEDS:
        route_key = str(seed["route_key"])
        row = existing.get(route_key)
        if row is None:
            row = AiRouteProfile(
                route_key=route_key,
                display_name=str(seed["display_name"]),
                description=str(seed["description"]),
                output_mode=str(seed.get("output_mode") or AI_ROUTE_OUTPUT_MODE_TEXT),
                is_enabled=True,
                max_attempts=AI_ROUTE_DEFAULT_MAX_ATTEMPTS,
                extra_json=_merge_route_settings(
                    route_key=route_key,
                    existing={"seeded": True},
                    payload={},
                ),
                updated_by="system",
            )
            session.add(row)
        else:
            changed = False
            if not _normalize_text(row.display_name, max_length=128):
                row.display_name = str(seed["display_name"])
                changed = True
            if not _normalize_text(row.description, max_length=2000):
                row.description = str(seed["description"])
                changed = True
            if not _normalize_text(row.output_mode, max_length=32):
                row.output_mode = str(seed.get("output_mode") or AI_ROUTE_OUTPUT_MODE_TEXT)
                changed = True
            normalized_extra_json = _merge_route_settings(
                route_key=route_key,
                existing=dict(row.extra_json or {}),
                payload={},
            )
            if normalized_extra_json != dict(row.extra_json or {}):
                row.extra_json = normalized_extra_json
                changed = True
            if changed:
                row.updated_by = "system"
                session.add(row)
    session.flush()


def _migrate_legacy_resource_ops_provider_if_needed(session: Session) -> None:
    provider_count = int(session.query(func.count(AiProviderConfig.id)).scalar() or 0)
    if provider_count > 0:
        return

    from app.services.resource_ops.settings import get_resource_ops_runtime_config

    legacy_config = get_resource_ops_runtime_config(session)
    legacy_base_url = normalize_base_url(str(legacy_config.get("ai_base_url") or ""))
    legacy_api_key = _normalize_text(legacy_config.get("ai_api_key"), max_length=8000)
    legacy_model = _normalize_text(legacy_config.get("ai_model"), max_length=255)
    legacy_api_mode = normalize_api_mode(legacy_config.get("ai_api_mode") or AI_API_MODE_AUTO)

    if not legacy_base_url or not legacy_api_key:
        return

    provider = AiProviderConfig(
        provider_key="legacy_resource_ops_default",
        display_name="默认 AI 提供方",
        provider_type=AI_PROVIDER_TYPE_OPENAI_COMPATIBLE,
        base_url=legacy_base_url,
        api_key_encrypted=encrypt_secret(legacy_api_key),
        api_mode=legacy_api_mode,
        is_enabled=True,
        is_default=True,
        priority=100,
        timeout_seconds=25,
        max_retries=1,
        cooldown_seconds=300,
        health_status="unknown",
        extra_json={
            "migrated_from": "resource_ops_runtime",
            "migrated_at": _to_utc_iso(_utcnow()),
            "legacy_model": legacy_model or None,
        },
        updated_by="system",
    )
    session.add(provider)
    session.flush()

    if legacy_model:
        _upsert_provider_model(
            session,
            provider_id=int(provider.id),
            payload={
                "id": legacy_model,
                "label": legacy_model,
                "owned_by": "",
                "is_enabled": True,
            },
            preferred_model_id=legacy_model,
        )

    route_lookup = {
        str(row.route_key or ""): row
        for row in session.query(AiRouteProfile).all()
    }
    for seed in AI_ROUTE_SEEDS:
        route = route_lookup.get(str(seed["route_key"]))
        if route is None:
            continue
        existing_step = (
            session.query(AiRouteStep)
            .filter(AiRouteStep.route_profile_id == int(route.id), AiRouteStep.step_index == 1)
            .first()
        )
        if existing_step is not None:
            continue
        session.add(
            AiRouteStep(
                route_profile_id=int(route.id),
                step_index=1,
                provider_id=int(provider.id),
                model_id=legacy_model or None,
                is_enabled=True,
                extra_json={"migrated_from": "resource_ops_runtime"},
                updated_by="system",
            )
        )
    session.flush()


def ensure_ai_center_seeded(session: Session) -> None:
    ensure_runtime_storage_tables()
    _ensure_route_seed_rows(session)
    _migrate_legacy_resource_ops_provider_if_needed(session)


def get_ai_center_overview(session: Session) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    provider_rows = session.query(AiProviderConfig).all()
    route_rows = session.query(AiRouteProfile).all()
    step_rows = session.query(AiRouteStep).all()
    provider_lookup = {int(row.id): row for row in provider_rows}
    provider_models_lookup = {
        int(row.id): _load_provider_models(session, provider_id=int(row.id))
        for row in provider_rows
    }
    steps_by_route: dict[int, list[AiRouteStep]] = {}
    for step in step_rows:
        steps_by_route.setdefault(int(step.route_profile_id), []).append(step)

    ready_route_count = 0
    for route in route_rows:
        readiness = _build_route_readiness(
            session,
            route,
            steps=steps_by_route.get(int(route.id), []),
            provider_lookup=provider_lookup,
            provider_models_lookup=provider_models_lookup,
        )
        if readiness["is_ready"]:
            ready_route_count += 1

    since = _utcnow() - timedelta(hours=24)
    success_count_24h = (
        session.query(func.count(AiCallEvent.id))
        .filter(AiCallEvent.created_at >= since, AiCallEvent.status == AI_EVENT_STATUS_SUCCESS)
        .scalar()
        or 0
    )
    failure_count_24h = (
        session.query(func.count(AiCallEvent.id))
        .filter(AiCallEvent.created_at >= since, AiCallEvent.status == AI_EVENT_STATUS_ERROR)
        .scalar()
        or 0
    )
    default_provider = next((row for row in provider_rows if bool(row.is_default)), None)
    migrated_provider = next(
        (
            row
            for row in provider_rows
            if _normalize_text(dict(row.extra_json or {}).get("migrated_from"), max_length=64) == "resource_ops_runtime"
        ),
        None,
    )
    return {
        "total_providers": len(provider_rows),
        "enabled_providers": sum(1 for row in provider_rows if bool(row.is_enabled)),
        "default_provider_id": int(default_provider.id) if default_provider is not None else None,
        "default_provider_label": _normalize_text(getattr(default_provider, "display_name", None), max_length=128)
        or _normalize_text(getattr(default_provider, "provider_key", None), max_length=64)
        or None,
        "total_routes": len(route_rows),
        "ready_routes": ready_route_count,
        "recent_success_count_24h": int(success_count_24h),
        "recent_failure_count_24h": int(failure_count_24h),
        "legacy_migration_applied": migrated_provider is not None,
        "generated_at": _utcnow(),
    }


def list_ai_providers(session: Session) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    rows = (
        session.query(AiProviderConfig)
        .order_by(
            AiProviderConfig.is_default.desc(),
            AiProviderConfig.priority.asc(),
            AiProviderConfig.display_name.asc(),
            AiProviderConfig.id.asc(),
        )
        .all()
    )
    stats_by_model = _load_ai_call_stats(
        session,
        provider_ids=[int(row.id) for row in rows],
        route_key="",
    )["global"]
    items = []
    for row in rows:
        items.append(
            _serialize_provider(
                row,
                models=_load_provider_models(session, provider_id=int(row.id)),
                stats_by_model=stats_by_model,
            )
        )
    return {
        "items": items,
        "total": len(items),
    }


def get_ai_provider_detail(session: Session, *, provider_id: int) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    row = session.get(AiProviderConfig, int(provider_id))
    if row is None:
        raise LookupError("AI provider not found")
    stats_by_model = _load_ai_call_stats(session, provider_ids=[int(row.id)], route_key="")["global"]
    return _serialize_provider(
        row,
        models=_load_provider_models(session, provider_id=int(row.id)),
        stats_by_model=stats_by_model,
    )


def save_ai_provider(
    session: Session,
    *,
    payload: dict[str, Any],
    updated_by: str | None,
    provider_id: int | None = None,
) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    row = session.get(AiProviderConfig, int(provider_id)) if provider_id is not None else None
    creating = row is None
    if row is None:
        row = AiProviderConfig(
            provider_key="",
            display_name="",
            provider_type=AI_PROVIDER_TYPE_OPENAI_COMPATIBLE,
            base_url="",
            api_key_encrypted="",
            api_mode=AI_API_MODE_AUTO,
            is_enabled=True,
            is_default=False,
            priority=100,
            timeout_seconds=25,
            max_retries=1,
            cooldown_seconds=300,
            health_status="unknown",
            extra_json={},
        )

    provider_key = _normalize_provider_key(payload.get("provider_key") or row.provider_key or row.display_name)
    if not provider_key:
        raise ValueError("provider_key cannot be empty")

    duplicate = session.query(AiProviderConfig).filter(AiProviderConfig.provider_key == provider_key).first()
    if duplicate is not None and (creating or int(duplicate.id) != int(row.id)):
        raise ValueError("provider_key already exists")

    row.provider_key = provider_key
    row.display_name = _normalize_text(payload.get("display_name"), max_length=128) or provider_key
    row.provider_type = AI_PROVIDER_TYPE_OPENAI_COMPATIBLE
    row.base_url = normalize_base_url(str(payload.get("base_url") or row.base_url or ""))
    row.api_mode = normalize_api_mode(payload.get("api_mode") or row.api_mode or AI_API_MODE_AUTO)
    row.is_enabled = _normalize_bool(payload.get("is_enabled"), bool(row.is_enabled) if not creating else True)
    row.is_default = _normalize_bool(payload.get("is_default"), bool(row.is_default))
    row.priority = _normalize_int(payload.get("priority"), int(row.priority or 100), minimum=0, maximum=100_000)
    row.timeout_seconds = _normalize_int(payload.get("timeout_seconds"), int(row.timeout_seconds or 25), minimum=5, maximum=120)
    row.max_retries = _normalize_int(payload.get("max_retries"), int(row.max_retries or 1), minimum=0, maximum=5)
    row.cooldown_seconds = _normalize_int(payload.get("cooldown_seconds"), int(row.cooldown_seconds or 300), minimum=0, maximum=86_400)
    row.updated_by = _normalize_text(updated_by, max_length=128) or None
    row.extra_json = {
        **dict(row.extra_json or {}),
        **dict(payload.get("extra_json") or {}),
    }

    if "api_key" in payload:
        api_key = _normalize_text(payload.get("api_key"), max_length=8000)
        if api_key:
            row.api_key_encrypted = encrypt_secret(api_key)
    if _normalize_bool(payload.get("clear_api_key"), False):
        row.api_key_encrypted = encrypt_secret("")

    if row.is_default:
        session.add(row)
        session.flush()
        _set_provider_default(session, provider_id=int(row.id))

    session.add(row)
    session.flush()
    if "models" in payload:
        _save_provider_models(
            session,
            provider_id=int(row.id),
            payload_models=[dict(item or {}) for item in list(payload.get("models") or [])],
        )
        session.flush()
    return get_ai_provider_detail(session, provider_id=int(row.id))


def delete_ai_provider(session: Session, *, provider_id: int) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    row = session.get(AiProviderConfig, int(provider_id))
    if row is None:
        raise LookupError("AI provider not found")

    route_step_ids = [
        int(step_id)
        for (step_id,) in (
            session.query(AiRouteStep.id)
            .filter(AiRouteStep.provider_id == int(row.id))
            .all()
        )
        if step_id is not None
    ]
    deleted_route_steps = 0
    if route_step_ids:
        (
            session.query(AiCallEvent)
            .filter(AiCallEvent.route_step_id.in_(route_step_ids))
            .update({"route_step_id": None}, synchronize_session=False)
        )
        deleted_route_steps = int(
            session.query(AiRouteStep)
            .filter(AiRouteStep.id.in_(route_step_ids))
            .delete(synchronize_session=False)
            or 0
        )

    (
        session.query(AiCallEvent)
        .filter(AiCallEvent.provider_id == int(row.id))
        .update({"provider_id": None}, synchronize_session=False)
    )
    deleted_models = int(
        session.query(AiProviderModel)
        .filter(AiProviderModel.provider_id == int(row.id))
        .delete(synchronize_session=False)
        or 0
    )
    was_default = bool(row.is_default)
    session.delete(row)
    if was_default:
        fallback_provider = (
            session.query(AiProviderConfig)
            .filter(AiProviderConfig.id != int(provider_id), AiProviderConfig.is_enabled.is_(True))
            .order_by(AiProviderConfig.priority.asc(), AiProviderConfig.id.asc())
            .first()
        )
        if fallback_provider is not None:
            fallback_provider.is_default = True
            session.add(fallback_provider)
            _set_provider_default(session, provider_id=int(fallback_provider.id))
    session.flush()
    return {
        "id": int(provider_id),
        "deleted": True,
        "deleted_models": deleted_models,
        "deleted_route_steps": deleted_route_steps,
    }


def refresh_ai_provider_models(session: Session, *, provider_id: int) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    provider = session.get(AiProviderConfig, int(provider_id))
    if provider is None:
        raise LookupError("AI provider not found")
    if _normalize_text(provider.provider_type, max_length=32) != AI_PROVIDER_TYPE_OPENAI_COMPATIBLE:
        raise ValueError("Only openai_compatible providers are currently supported")

    api_key = decrypt_secret(_normalize_text(provider.api_key_encrypted, max_length=8000))
    models = list_openai_compatible_models(
        base_url=str(provider.base_url or ""),
        api_key=api_key,
        timeout_seconds=int(provider.timeout_seconds or 25),
    )
    if not models:
        raise ValueError("No models were returned by the provider")

    existing = _load_provider_models(session, provider_id=int(provider.id))
    preferred_model_id = _normalize_text(
        next((row.model_id for row in existing if bool(row.is_preferred)), None),
        max_length=255,
    ) or _normalize_text(models[0].get("id"), max_length=255)

    for payload in models:
        if not _normalize_text(payload.get("id"), max_length=255):
            continue
        _upsert_provider_model(
            session,
            provider_id=int(provider.id),
            payload=payload,
            preferred_model_id=preferred_model_id,
        )
    _ensure_preferred_provider_model(session, provider_id=int(provider.id))
    _mark_provider_success(session, provider=provider)
    session.flush()
    return get_ai_provider_detail(session, provider_id=int(provider.id))


def test_ai_provider(
    session: Session,
    *,
    provider_id: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    provider = session.get(AiProviderConfig, int(provider_id))
    if provider is None:
        raise LookupError("AI provider not found")

    provider_models_lookup = {
        int(provider.id): _load_provider_models(session, provider_id=int(provider.id))
    }
    pseudo_step = AiRouteStep(
        route_profile_id=0,
        step_index=1,
        provider_id=int(provider.id),
        model_id=_normalize_text((payload or {}).get("model_id"), max_length=255) or None,
        is_enabled=True,
    )
    model_id = _resolve_provider_model_id(
        step=pseudo_step,
        provider_id=int(provider.id),
        provider_models_lookup=provider_models_lookup,
    )
    result = complete_openai_compatible_text(
        base_url=str(provider.base_url or ""),
        api_key=decrypt_secret(_normalize_text(provider.api_key_encrypted, max_length=8000)),
        model=model_id or "",
        system_prompt="You are an AI connectivity checker. Reply with a short confirmation only.",
        user_prompt=_normalize_text((payload or {}).get("sample_text"), max_length=500) or "Reply with OK only.",
        api_mode=_normalize_text(provider.api_mode, max_length=32) or AI_API_MODE_AUTO,
        timeout_seconds=int(provider.timeout_seconds or 25),
    )
    _mark_provider_success(session, provider=provider)
    session.flush()
    return {
        "provider_id": int(provider.id),
        "provider_label": _normalize_text(provider.display_name, max_length=128)
        or _normalize_text(provider.provider_key, max_length=64)
        or None,
        "model_id": result.used_model or model_id,
        "used_api_mode": result.used_api_mode,
        "text": result.text,
        "ok": True,
    }


def list_ai_routes(session: Session) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    routes = session.query(AiRouteProfile).order_by(AiRouteProfile.route_key.asc(), AiRouteProfile.id.asc()).all()
    steps = session.query(AiRouteStep).order_by(AiRouteStep.route_profile_id.asc(), AiRouteStep.step_index.asc(), AiRouteStep.id.asc()).all()
    providers = session.query(AiProviderConfig).all()
    provider_lookup = {int(row.id): row for row in providers}
    provider_models_lookup = {
        int(row.id): _load_provider_models(session, provider_id=int(row.id))
        for row in providers
    }
    steps_by_route: dict[int, list[AiRouteStep]] = {}
    for step in steps:
        steps_by_route.setdefault(int(step.route_profile_id), []).append(step)

    items = [
        _serialize_route(
            session,
            row,
            steps=steps_by_route.get(int(row.id), []),
            provider_lookup=provider_lookup,
            provider_models_lookup=provider_models_lookup,
        )
        for row in routes
    ]
    return {
        "items": items,
        "total": len(items),
    }


def get_ai_route_detail(session: Session, *, route_key: str) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    normalized_route_key = _normalize_text(route_key, max_length=128)
    route = session.query(AiRouteProfile).filter(AiRouteProfile.route_key == normalized_route_key).first()
    if route is None:
        raise LookupError("AI route not found")
    providers = session.query(AiProviderConfig).all()
    provider_lookup = {int(row.id): row for row in providers}
    provider_models_lookup = {
        int(row.id): _load_provider_models(session, provider_id=int(row.id))
        for row in providers
    }
    steps = (
        session.query(AiRouteStep)
        .filter(AiRouteStep.route_profile_id == int(route.id))
        .order_by(AiRouteStep.step_index.asc(), AiRouteStep.id.asc())
        .all()
    )
    return _serialize_route(
        session,
        route,
        steps=steps,
        provider_lookup=provider_lookup,
        provider_models_lookup=provider_models_lookup,
    )


def save_ai_route(
    session: Session,
    *,
    route_key: str,
    payload: dict[str, Any],
    updated_by: str | None,
) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    normalized_route_key = _normalize_text(route_key, max_length=128)
    route = session.query(AiRouteProfile).filter(AiRouteProfile.route_key == normalized_route_key).first()
    if route is None:
        route = AiRouteProfile(
            route_key=normalized_route_key,
            display_name=_normalize_text(payload.get("display_name"), max_length=128) or normalized_route_key,
            description=_normalize_text(payload.get("description"), max_length=2000),
            output_mode=_normalize_text(payload.get("output_mode"), max_length=32) or AI_ROUTE_OUTPUT_MODE_TEXT,
            is_enabled=True,
            max_attempts=AI_ROUTE_DEFAULT_MAX_ATTEMPTS,
            extra_json={},
            updated_by=_normalize_text(updated_by, max_length=128) or None,
        )
        session.add(route)
        session.flush()

    route.display_name = _normalize_text(payload.get("display_name"), max_length=128) or route.display_name or normalized_route_key
    route.description = _normalize_text(payload.get("description"), max_length=2000)
    route.output_mode = _normalize_text(payload.get("output_mode"), max_length=32) or route.output_mode or AI_ROUTE_OUTPUT_MODE_TEXT
    route.is_enabled = _normalize_bool(payload.get("is_enabled"), bool(route.is_enabled))
    route.max_attempts = _normalize_int(payload.get("max_attempts"), int(route.max_attempts or AI_ROUTE_DEFAULT_MAX_ATTEMPTS), minimum=1, maximum=10)
    route.updated_by = _normalize_text(updated_by, max_length=128) or None
    route.extra_json = _merge_route_settings(
        route_key=normalized_route_key,
        existing=dict(route.extra_json or {}),
        payload={
            **dict(payload.get("extra_json") or {}),
            "selection_mode": payload.get("selection_mode"),
            "optimization_goal": payload.get("optimization_goal"),
            "preferred_capabilities": payload.get("preferred_capabilities"),
            "allow_same_provider_model_failover": payload.get("allow_same_provider_model_failover"),
            "allow_cross_provider_failover": payload.get("allow_cross_provider_failover"),
        },
    )
    session.add(route)
    session.flush()

    requested_steps = list(payload.get("steps") or [])
    existing_steps = (
        session.query(AiRouteStep)
        .filter(AiRouteStep.route_profile_id == int(route.id))
        .order_by(AiRouteStep.step_index.asc(), AiRouteStep.id.asc())
        .all()
    )
    existing_by_id = {int(row.id): row for row in existing_steps}

    temp_base = max([int(row.step_index or 0) for row in existing_steps] + [0]) + 100
    for index, row in enumerate(existing_steps):
        row.step_index = temp_base + index
        session.add(row)
    session.flush()

    claimed_ids: set[int] = set()
    for index, raw_step in enumerate(requested_steps, start=1):
        step_payload = dict(raw_step or {})
        provider_id = _normalize_int(step_payload.get("provider_id"), 0, minimum=0)
        if provider_id <= 0 or session.get(AiProviderConfig, provider_id) is None:
            raise ValueError(f"Invalid provider_id for route step {index}")
        step_id = _normalize_int(step_payload.get("id"), 0, minimum=0)
        step = existing_by_id.get(step_id) if step_id > 0 else None
        if step is None:
            step = AiRouteStep(route_profile_id=int(route.id))
        else:
            claimed_ids.add(int(step.id))
        step.step_index = index
        step.provider_id = provider_id
        step.model_id = _normalize_text(step_payload.get("model_id"), max_length=255) or None
        step.is_enabled = _normalize_bool(step_payload.get("is_enabled"), True)
        step.extra_json = {
            **dict(step.extra_json or {}),
            **dict(step_payload.get("extra_json") or {}),
        }
        step.updated_by = _normalize_text(updated_by, max_length=128) or None
        session.add(step)

    for row in existing_steps:
        if int(row.id) in claimed_ids:
            continue
        row.is_enabled = False
        session.add(row)

    session.flush()
    return get_ai_route_detail(session, route_key=normalized_route_key)


def get_ai_route_readiness(session: Session, *, route_key: str) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    normalized_route_key = _normalize_text(route_key, max_length=128)
    route = session.query(AiRouteProfile).filter(AiRouteProfile.route_key == normalized_route_key).first()
    if route is None:
        return {
            "route_key": normalized_route_key,
            "is_ready": False,
            "reason": "route_missing",
            "provider_label": None,
            "model_id": None,
            "selection_mode": AI_ROUTE_SELECTION_MODE_DEFAULT,
            "optimization_goal": _default_route_optimization_goal(normalized_route_key),
            "candidate_count": 0,
            "selection_summary": None,
        }
    providers = session.query(AiProviderConfig).all()
    provider_lookup = {int(row.id): row for row in providers}
    provider_models_lookup = {
        int(row.id): _load_provider_models(session, provider_id=int(row.id))
        for row in providers
    }
    steps = (
        session.query(AiRouteStep)
        .filter(AiRouteStep.route_profile_id == int(route.id))
        .order_by(AiRouteStep.step_index.asc(), AiRouteStep.id.asc())
        .all()
    )
    readiness = _build_route_readiness(
        session,
        route,
        steps=steps,
        provider_lookup=provider_lookup,
        provider_models_lookup=provider_models_lookup,
    )
    return {
        "route_key": normalized_route_key,
        **readiness,
    }


def execute_text_route(
    session: Session,
    *,
    route_key: str,
    system_prompt: str,
    user_prompt: str,
    metadata: dict[str, Any] | None = None,
) -> AiCenterRouteResult:
    ensure_ai_center_seeded(session)
    normalized_route_key = _normalize_text(route_key, max_length=128)
    route = session.query(AiRouteProfile).filter(AiRouteProfile.route_key == normalized_route_key).first()
    if route is None:
        raise AiCenterError(f"AI route not found: {normalized_route_key}")
    if not bool(route.is_enabled):
        raise AiCenterError(f"AI route is disabled: {normalized_route_key}")

    steps = (
        session.query(AiRouteStep)
        .filter(AiRouteStep.route_profile_id == int(route.id), AiRouteStep.is_enabled.is_(True))
        .order_by(AiRouteStep.step_index.asc(), AiRouteStep.id.asc())
        .all()
    )
    if not steps:
        raise AiCenterError(f"AI route has no enabled step: {normalized_route_key}")

    provider_lookup = {
        int(row.id): row
        for row in session.query(AiProviderConfig).filter(AiProviderConfig.id.in_([int(step.provider_id) for step in steps])).all()
    }
    provider_models_lookup = {
        provider_id: _load_provider_models(session, provider_id=provider_id)
        for provider_id in provider_lookup.keys()
    }

    candidates, route_settings = _build_route_candidates(
        session,
        route=route,
        steps=steps,
        provider_lookup=provider_lookup,
        provider_models_lookup=provider_models_lookup,
    )
    if not candidates:
        raise AiCenterError(f"AI route has no available candidate: {normalized_route_key}")

    errors: list[str] = []
    attempts = 0
    route_max_attempts = max(1, int(route.max_attempts or AI_ROUTE_DEFAULT_MAX_ATTEMPTS))
    provider_attempts: dict[int, dict[str, Any]] = {}
    attempt_trace: list[dict[str, Any]] = []
    for candidate in candidates:
        if attempts >= route_max_attempts:
            break
        provider = provider_lookup.get(int(candidate["provider_id"]))
        if provider is None:
            continue
        api_key = decrypt_secret(_normalize_text(provider.api_key_encrypted, max_length=8000))
        base_url = normalize_base_url(str(provider.base_url or ""))
        if not base_url or not _normalize_text(api_key, max_length=8000):
            continue
        attempts += 1
        provider_state = provider_attempts.setdefault(
            int(provider.id),
            {
                "provider": provider,
                "errors": [],
                "success": False,
            },
        )
        model_id = _normalize_text(candidate.get("model_id"), max_length=255) or ""
        start_time = _utcnow()
        try:
            result = complete_openai_compatible_text(
                base_url=base_url,
                api_key=api_key,
                model=model_id,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_mode=_normalize_text(provider.api_mode, max_length=32) or AI_API_MODE_AUTO,
                timeout_seconds=int(provider.timeout_seconds or 25),
            )
            duration_ms = int((_utcnow() - start_time).total_seconds() * 1000)
            provider_state["success"] = True
            trace_row = {
                "attempt_index": attempts,
                "provider_id": int(provider.id),
                "provider_label": candidate["provider_label"],
                "model_id": result.used_model or model_id or None,
                "status": AI_EVENT_STATUS_SUCCESS,
                "used_api_mode": result.used_api_mode,
                "duration_ms": duration_ms,
                "selection_summary": candidate["selection_summary"],
                "candidate_score": float(candidate["score"]),
                "candidate_reasons": list(candidate["reasons"]),
            }
            attempt_trace.append(trace_row)
            event = _record_call_event(
                session,
                route_key=normalized_route_key,
                route_profile_id=int(route.id),
                route_step_id=int(candidate["route_step_id"]),
                provider_id=int(provider.id),
                provider_label=candidate["provider_label"],
                model_id=result.used_model or model_id or None,
                status=AI_EVENT_STATUS_SUCCESS,
                duration_ms=duration_ms,
                extra_json={
                    "used_api_mode": result.used_api_mode,
                    "metadata": metadata or {},
                    "system_prompt_preview": _truncate_text(system_prompt),
                    "user_prompt_preview": _truncate_text(user_prompt),
                    "selection_mode": route_settings["selection_mode"],
                    "selection_summary": candidate["selection_summary"],
                    "attempt_index": attempts,
                    "candidate_score": float(candidate["score"]),
                    "candidate_reasons": list(candidate["reasons"]),
                    "attempt_trace": list(attempt_trace),
                },
            )
            for state in provider_attempts.values():
                if state["success"]:
                    _mark_provider_success(session, provider=state["provider"])
                elif state["errors"]:
                    _mark_provider_failure(
                        session,
                        provider=state["provider"],
                        error_message=_normalize_text(state["errors"][-1], max_length=2000) or "unknown error",
                    )
            session.flush()
            return AiCenterRouteResult(
                text=result.text,
                route_key=normalized_route_key,
                provider_id=int(provider.id),
                provider_label=candidate["provider_label"],
                model_id=result.used_model or model_id or None,
                used_api_mode=result.used_api_mode,
                route_profile_id=int(route.id),
                route_step_id=int(candidate["route_step_id"]),
                duration_ms=duration_ms,
                event_id=int(event.id),
                selection_summary=candidate["selection_summary"],
                attempt_trace=list(attempt_trace),
            )
        except Exception as exc:
            error_message = _normalize_text(exc, max_length=2000) or type(exc).__name__
            duration_ms = int((_utcnow() - start_time).total_seconds() * 1000)
            provider_state["errors"].append(error_message)
            trace_row = {
                "attempt_index": attempts,
                "provider_id": int(provider.id),
                "provider_label": candidate["provider_label"],
                "model_id": model_id or None,
                "status": AI_EVENT_STATUS_ERROR,
                "error_message": error_message,
                "duration_ms": duration_ms,
                "selection_summary": candidate["selection_summary"],
                "candidate_score": float(candidate["score"]),
                "candidate_reasons": list(candidate["reasons"]),
            }
            attempt_trace.append(trace_row)
            _record_call_event(
                session,
                route_key=normalized_route_key,
                route_profile_id=int(route.id),
                route_step_id=int(candidate["route_step_id"]),
                provider_id=int(provider.id),
                provider_label=candidate["provider_label"],
                model_id=model_id or None,
                status=AI_EVENT_STATUS_ERROR,
                error_type=type(exc).__name__,
                error_message=error_message,
                duration_ms=duration_ms,
                extra_json={
                    "metadata": metadata or {},
                    "system_prompt_preview": _truncate_text(system_prompt),
                    "user_prompt_preview": _truncate_text(user_prompt),
                    "selection_mode": route_settings["selection_mode"],
                    "selection_summary": candidate["selection_summary"],
                    "attempt_index": attempts,
                    "candidate_score": float(candidate["score"]),
                    "candidate_reasons": list(candidate["reasons"]),
                },
            )
            errors.append(f"candidate#{attempts}: {error_message}")
            logger.warning(
                "AI route failed route=%s candidate=%s provider=%s error=%s",
                normalized_route_key,
                attempts,
                int(provider.id),
                error_message,
            )

    for state in provider_attempts.values():
        if state["success"]:
            _mark_provider_success(session, provider=state["provider"])
        elif state["errors"]:
            _mark_provider_failure(
                session,
                provider=state["provider"],
                error_message=_normalize_text(state["errors"][-1], max_length=2000) or "unknown error",
            )
    session.flush()

    if not errors:
        raise AiCenterError(f"AI route execution failed: {normalized_route_key}")
    if len(errors) == 1:
        raise AiCenterError(errors[0])
    raise AiCenterError(" ; ".join(errors))


def test_ai_route(
    session: Session,
    *,
    route_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    result = execute_text_route(
        session,
        route_key=route_key,
        system_prompt=_normalize_text(payload.get("system_prompt"), max_length=12_000),
        user_prompt=_normalize_text(payload.get("user_prompt"), max_length=12_000),
        metadata={"source": "admin_test"},
    )
    return {
        "route_key": result.route_key,
        "provider_id": result.provider_id,
        "provider_label": result.provider_label,
        "model_id": result.model_id,
        "used_api_mode": result.used_api_mode,
        "duration_ms": result.duration_ms,
        "text": result.text,
        "event_id": result.event_id,
        "selection_summary": result.selection_summary,
        "attempt_trace": list(result.attempt_trace or []),
        "ok": True,
    }


def list_ai_call_events(
    session: Session,
    *,
    route_key: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    safe_limit = max(1, min(int(limit or 50), 200))
    query = session.query(AiCallEvent)
    normalized_route_key = _normalize_text(route_key, max_length=128)
    if normalized_route_key:
        query = query.filter(AiCallEvent.route_key == normalized_route_key)
    rows = (
        query.order_by(AiCallEvent.created_at.desc(), AiCallEvent.id.desc())
        .limit(safe_limit)
        .all()
    )
    return {
        "items": [_serialize_call_event(row) for row in rows],
        "total": len(rows),
        "limit": safe_limit,
    }


def clear_ai_call_events(
    session: Session,
    *,
    route_key: str | None = None,
) -> dict[str, Any]:
    ensure_ai_center_seeded(session)
    query = session.query(AiCallEvent)
    normalized_route_key = _normalize_text(route_key, max_length=128)
    if normalized_route_key:
        query = query.filter(AiCallEvent.route_key == normalized_route_key)
    deleted_count = int(query.delete(synchronize_session=False) or 0)
    session.flush()
    return {"deleted_count": deleted_count}


def extract_json_object_from_text(raw_text: str) -> dict[str, Any] | None:
    text = _normalize_text(raw_text)
    if not text:
        return None

    code_fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    candidates = [code_fence_match.group(1)] if code_fence_match else []
    candidates.append(text)

    decoder = json.JSONDecoder()
    for candidate in candidates:
        stripped = candidate.strip()
        if not stripped:
            continue
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        brace_index = stripped.find("{")
        while brace_index >= 0:
            try:
                parsed, _ = decoder.raw_decode(stripped[brace_index:])
            except json.JSONDecodeError:
                brace_index = stripped.find("{", brace_index + 1)
                continue
            if isinstance(parsed, dict):
                return parsed
            brace_index = stripped.find("{", brace_index + 1)
    return None
