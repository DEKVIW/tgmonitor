from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import SystemSettings, ensure_runtime_storage_tables
from app.services.secret_codec import decrypt_secret, encrypt_secret
from app.services.system_config_service import (
    SYSTEM_SETTINGS_SINGLETON_ID,
    build_default_system_settings_values,
    ensure_runtime_configuration_seeded,
)


RESOURCE_OPS_RUNTIME_EXTRA_KEY = "resource_ops_runtime"
RECOGNITION_LOG_LIMIT = 120
WORKER_HEARTBEAT_GRACE_SECONDS = 30
RESOURCE_OPS_AI_API_MODES = {"auto", "chat_completions", "responses"}


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


def _coerce_bool(value: Any, default: bool) -> bool:
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


def _coerce_int(
    value: Any,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _coerce_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _coerce_text(value: Any, default: str = "", *, max_length: int | None = None) -> str:
    normalized = default if value is None else str(value).strip()
    if not normalized:
        normalized = default
    if max_length is not None:
        normalized = normalized[:max_length]
    return normalized


def _coerce_ai_api_mode(value: Any, default: str = "auto") -> str:
    normalized = _coerce_text(value, default, max_length=32).lower()
    if normalized not in RESOURCE_OPS_AI_API_MODES:
        return default
    return normalized


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _to_iso(value: datetime | None) -> str | None:
    return _to_utc_iso(value)


def build_default_resource_ops_runtime_settings() -> dict[str, Any]:
    return {
        "auto_recognition_enabled": False,
        "ai_base_url": "",
        "ai_api_mode": "auto",
        "ai_model": "",
        "ai_api_key_encrypted": "",
        "worker_state": "idle",
        "worker_started_at": None,
        "worker_finished_at": None,
        "worker_last_heartbeat_at": None,
        "worker_last_processed_at": None,
        "worker_current_link_target_id": None,
        "worker_current_title": "",
        "worker_current_source": "",
        "worker_last_error": "",
        "worker_logs": [],
        "retention_click_event_days": 90,
        "retention_daily_stat_days": 365,
        "retention_candidate_log_days": 180,
        "cleanup_interval_hours": 24,
        "last_sync_at": None,
        "last_sync_summary": {},
        "last_cleanup_at": None,
        "last_cleanup_summary": {},
    }


def _normalize_runtime_storage_values(raw_value: Any) -> dict[str, Any]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    defaults = build_default_resource_ops_runtime_settings()
    last_sync_at = _coerce_datetime(payload.get("last_sync_at"))
    last_cleanup_at = _coerce_datetime(payload.get("last_cleanup_at"))
    last_sync_summary = payload.get("last_sync_summary")
    last_cleanup_summary = payload.get("last_cleanup_summary")
    auto_recognition_raw = payload.get("auto_recognition_enabled")
    if auto_recognition_raw is None:
        auto_recognition_raw = payload.get("auto_bind_enabled")
    worker_logs = payload.get("worker_logs") or payload.get("recognition_logs")

    return {
        "auto_recognition_enabled": _coerce_bool(auto_recognition_raw, defaults["auto_recognition_enabled"]),
        "ai_base_url": _coerce_text(payload.get("ai_base_url"), defaults["ai_base_url"], max_length=512),
        "ai_api_mode": _coerce_ai_api_mode(payload.get("ai_api_mode"), defaults["ai_api_mode"]),
        "ai_model": _coerce_text(payload.get("ai_model"), defaults["ai_model"], max_length=255),
        "ai_api_key_encrypted": _coerce_text(
            payload.get("ai_api_key_encrypted"),
            defaults["ai_api_key_encrypted"],
            max_length=8000,
        ),
        "worker_state": _coerce_text(payload.get("worker_state"), defaults["worker_state"], max_length=32) or "idle",
        "worker_started_at": _coerce_datetime(payload.get("worker_started_at") or payload.get("recognition_started_at")),
        "worker_finished_at": _coerce_datetime(payload.get("worker_finished_at") or payload.get("recognition_finished_at")),
        "worker_last_heartbeat_at": _coerce_datetime(payload.get("worker_last_heartbeat_at")),
        "worker_last_processed_at": _coerce_datetime(payload.get("worker_last_processed_at")),
        "worker_current_link_target_id": _coerce_int(
            payload.get("worker_current_link_target_id"),
            0,
            minimum=0,
            maximum=10_000_000,
        ),
        "worker_current_title": _coerce_text(
            payload.get("worker_current_title"),
            defaults["worker_current_title"],
            max_length=255,
        ),
        "worker_current_source": _coerce_text(
            payload.get("worker_current_source"),
            defaults["worker_current_source"],
            max_length=32,
        ),
        "worker_last_error": _coerce_text(
            payload.get("worker_last_error") or payload.get("recognition_last_error"),
            defaults["worker_last_error"],
            max_length=2000,
        ),
        "worker_logs": [
            _coerce_text(item, "", max_length=500)
            for item in (worker_logs if isinstance(worker_logs, list) else [])
            if _coerce_text(item, "", max_length=500)
        ][-RECOGNITION_LOG_LIMIT:],
        "retention_click_event_days": _coerce_int(
            payload.get("retention_click_event_days"),
            defaults["retention_click_event_days"],
            minimum=7,
            maximum=3650,
        ),
        "retention_daily_stat_days": _coerce_int(
            payload.get("retention_daily_stat_days"),
            defaults["retention_daily_stat_days"],
            minimum=30,
            maximum=3650,
        ),
        "retention_candidate_log_days": _coerce_int(
            payload.get("retention_candidate_log_days"),
            defaults["retention_candidate_log_days"],
            minimum=7,
            maximum=3650,
        ),
        "cleanup_interval_hours": _coerce_int(
            payload.get("cleanup_interval_hours"),
            defaults["cleanup_interval_hours"],
            minimum=1,
            maximum=720,
        ),
        "last_sync_at": last_sync_at,
        "last_sync_summary": dict(last_sync_summary) if isinstance(last_sync_summary, dict) else {},
        "last_cleanup_at": last_cleanup_at,
        "last_cleanup_summary": dict(last_cleanup_summary) if isinstance(last_cleanup_summary, dict) else {},
    }


def _ensure_system_settings_record(session: Session) -> SystemSettings:
    record = session.get(SystemSettings, SYSTEM_SETTINGS_SINGLETON_ID)
    if record is not None:
        return record
    record = SystemSettings(id=SYSTEM_SETTINGS_SINGLETON_ID, **build_default_system_settings_values())
    session.add(record)
    session.flush()
    return record


def _read_runtime_bucket(record: SystemSettings) -> dict[str, Any]:
    extra_json = dict(record.extra_json or {})
    return _normalize_runtime_storage_values(extra_json.get(RESOURCE_OPS_RUNTIME_EXTRA_KEY))


def _write_runtime_bucket(record: SystemSettings, payload: dict[str, Any], *, updated_by: str | None) -> None:
    normalized = _normalize_runtime_storage_values(payload)
    normalized["last_sync_at"] = _to_iso(normalized.get("last_sync_at"))
    normalized["last_cleanup_at"] = _to_iso(normalized.get("last_cleanup_at"))
    normalized["worker_started_at"] = _to_iso(normalized.get("worker_started_at"))
    normalized["worker_finished_at"] = _to_iso(normalized.get("worker_finished_at"))
    normalized["worker_last_heartbeat_at"] = _to_iso(normalized.get("worker_last_heartbeat_at"))
    normalized["worker_last_processed_at"] = _to_iso(normalized.get("worker_last_processed_at"))

    extra_json = dict(record.extra_json or {})
    extra_json[RESOURCE_OPS_RUNTIME_EXTRA_KEY] = normalized
    record.extra_json = extra_json
    record.updated_at = _utcnow()
    record.updated_by = updated_by


def get_resource_ops_runtime_config(session: Session) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    ensure_runtime_configuration_seeded()
    record = _ensure_system_settings_record(session)
    values = _read_runtime_bucket(record)
    values["ai_api_key"] = decrypt_secret(values["ai_api_key_encrypted"])
    return values


def is_resource_ops_ai_ready(config: dict[str, Any]) -> bool:
    return bool(
        _coerce_text(config.get("ai_base_url"), "", max_length=512)
        and _coerce_text(config.get("ai_api_key"), "", max_length=8000)
    )


def is_resource_ops_worker_alive(config: dict[str, Any]) -> bool:
    heartbeat_at = _coerce_datetime(config.get("worker_last_heartbeat_at"))
    if heartbeat_at is None:
        return False
    return (_utcnow() - heartbeat_at).total_seconds() <= WORKER_HEARTBEAT_GRACE_SECONDS


def resolve_resource_ops_ai_request_config(
    session: Session,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    config = get_resource_ops_runtime_config(session)

    base_url = _coerce_text(
        request_payload.get("base_url"),
        _coerce_text(config.get("ai_base_url"), "", max_length=512),
        max_length=512,
    )
    model = _coerce_text(
        request_payload.get("model"),
        _coerce_text(config.get("ai_model"), "", max_length=255),
        max_length=255,
    )
    use_saved_api_key = _coerce_bool(request_payload.get("use_saved_api_key"), True)
    request_api_key = _coerce_text(request_payload.get("api_key"), "", max_length=8000)
    saved_api_key = _coerce_text(config.get("ai_api_key"), "", max_length=8000)
    api_key = request_api_key or (saved_api_key if use_saved_api_key else "")

    return {
        "base_url": base_url,
        "ai_api_mode": "auto",
        "model": model,
        "api_key": api_key,
        "used_saved_api_key": bool(not request_api_key and use_saved_api_key and saved_api_key),
    }


def get_resource_ops_runtime_settings(session: Session) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    ai_base_url = _coerce_text(values.get("ai_base_url"), "", max_length=512)
    ai_model = _coerce_text(values.get("ai_model"), "", max_length=255)
    ai_api_key = _coerce_text(values.get("ai_api_key"), "", max_length=8000)
    worker_state = _coerce_text(values.get("worker_state"), "idle", max_length=32) or "idle"
    worker_alive = is_resource_ops_worker_alive(values)
    current_link_target_id = _coerce_int(values.get("worker_current_link_target_id"), 0, minimum=0)

    return {
        "auto_recognition_enabled": bool(values["auto_recognition_enabled"]),
        "ai_base_url": ai_base_url,
        "ai_model": ai_model,
        "ai_api_key_configured": bool(ai_api_key),
        "ai_provider_ready": is_resource_ops_ai_ready(values),
        "retention_click_event_days": int(values["retention_click_event_days"]),
        "retention_daily_stat_days": int(values["retention_daily_stat_days"]),
        "retention_candidate_log_days": int(values["retention_candidate_log_days"]),
        "cleanup_interval_hours": int(values["cleanup_interval_hours"]),
        "last_sync_at": _to_iso(values.get("last_sync_at")),
        "last_sync_summary": dict(values.get("last_sync_summary") or {}),
        "last_cleanup_at": _to_iso(values.get("last_cleanup_at")),
        "last_cleanup_summary": dict(values.get("last_cleanup_summary") or {}),
        "recognition_status": {
            "worker_state": worker_state,
            "worker_alive": worker_alive,
            "is_running": worker_state == "running" and worker_alive,
            "started_at": _to_iso(values.get("worker_started_at")),
            "finished_at": _to_iso(values.get("worker_finished_at")),
            "last_heartbeat_at": _to_iso(values.get("worker_last_heartbeat_at")),
            "last_processed_at": _to_iso(values.get("worker_last_processed_at")),
            "current_link_target_id": current_link_target_id or None,
            "current_title": _coerce_text(values.get("worker_current_title"), "", max_length=255) or None,
            "current_source": _coerce_text(values.get("worker_current_source"), "", max_length=32) or None,
            "last_error": _coerce_text(values.get("worker_last_error"), "", max_length=2000) or None,
            "logs": list(values.get("worker_logs") or []),
        },
    }


def update_resource_ops_runtime_settings(
    session: Session,
    payload: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)

    for field in (
        "auto_recognition_enabled",
        "ai_base_url",
        "ai_model",
        "retention_click_event_days",
        "retention_daily_stat_days",
        "retention_candidate_log_days",
        "cleanup_interval_hours",
    ):
        if field in payload:
            values[field] = payload[field]

    if "ai_api_key" in payload:
        values["ai_api_key_encrypted"] = encrypt_secret(_coerce_text(payload.get("ai_api_key"), "", max_length=8000))

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)


def update_resource_ops_runtime_meta(
    session: Session,
    *,
    last_sync_summary: dict[str, Any] | None = None,
    last_cleanup_summary: dict[str, Any] | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    if last_sync_summary is not None:
        values["last_sync_at"] = _utcnow()
        values["last_sync_summary"] = dict(last_sync_summary)
    if last_cleanup_summary is not None:
        values["last_cleanup_at"] = _utcnow()
        values["last_cleanup_summary"] = dict(last_cleanup_summary)

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)


def update_resource_ops_worker_state(
    session: Session,
    payload: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    for field in (
        "worker_state",
        "worker_started_at",
        "worker_finished_at",
        "worker_last_heartbeat_at",
        "worker_last_processed_at",
        "worker_current_link_target_id",
        "worker_current_title",
        "worker_current_source",
        "worker_last_error",
    ):
        if field in payload:
            values[field] = payload[field]

    if payload.get("reset_logs"):
        values["worker_logs"] = []
    if "log_line" in payload:
        log_line = _coerce_text(payload.get("log_line"), "", max_length=500)
        if log_line:
            logs = list(values.get("worker_logs") or [])
            logs.append(log_line)
            values["worker_logs"] = [item for item in logs if item][-RECOGNITION_LOG_LIMIT:]

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)
