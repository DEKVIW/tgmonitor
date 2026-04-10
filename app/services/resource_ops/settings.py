from __future__ import annotations

from datetime import datetime
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


def _utcnow() -> datetime:
    return datetime.utcnow()


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


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def build_default_resource_ops_runtime_settings() -> dict[str, Any]:
    return {
        "auto_recognition_enabled": False,
        "ai_base_url": "",
        "ai_model": "",
        "ai_api_key_encrypted": "",
        "recognition_requested_mode": "",
        "recognition_requested_at": None,
        "recognition_running_mode": "",
        "recognition_started_at": None,
        "recognition_finished_at": None,
        "recognition_total": 0,
        "recognition_processed": 0,
        "recognition_matched": 0,
        "recognition_error": 0,
        "recognition_last_error": "",
        "recognition_logs": [],
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
    recognition_logs = payload.get("recognition_logs")

    return {
        "auto_recognition_enabled": _coerce_bool(auto_recognition_raw, defaults["auto_recognition_enabled"]),
        "ai_base_url": _coerce_text(payload.get("ai_base_url"), defaults["ai_base_url"], max_length=512),
        "ai_model": _coerce_text(payload.get("ai_model"), defaults["ai_model"], max_length=255),
        "ai_api_key_encrypted": _coerce_text(
            payload.get("ai_api_key_encrypted"),
            defaults["ai_api_key_encrypted"],
            max_length=8000,
        ),
        "recognition_requested_mode": _coerce_text(
            payload.get("recognition_requested_mode"),
            defaults["recognition_requested_mode"],
            max_length=16,
        ),
        "recognition_requested_at": _coerce_datetime(payload.get("recognition_requested_at")),
        "recognition_running_mode": _coerce_text(
            payload.get("recognition_running_mode"),
            defaults["recognition_running_mode"],
            max_length=16,
        ),
        "recognition_started_at": _coerce_datetime(payload.get("recognition_started_at")),
        "recognition_finished_at": _coerce_datetime(payload.get("recognition_finished_at")),
        "recognition_total": _coerce_int(payload.get("recognition_total"), defaults["recognition_total"], minimum=0, maximum=1_000_000),
        "recognition_processed": _coerce_int(
            payload.get("recognition_processed"),
            defaults["recognition_processed"],
            minimum=0,
            maximum=1_000_000,
        ),
        "recognition_matched": _coerce_int(
            payload.get("recognition_matched"),
            defaults["recognition_matched"],
            minimum=0,
            maximum=1_000_000,
        ),
        "recognition_error": _coerce_int(
            payload.get("recognition_error"),
            defaults["recognition_error"],
            minimum=0,
            maximum=1_000_000,
        ),
        "recognition_last_error": _coerce_text(
            payload.get("recognition_last_error"),
            defaults["recognition_last_error"],
            max_length=2000,
        ),
        "recognition_logs": [
            _coerce_text(item, "", max_length=500)
            for item in (recognition_logs if isinstance(recognition_logs, list) else [])
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
    normalized["recognition_requested_at"] = _to_iso(normalized.get("recognition_requested_at"))
    normalized["recognition_started_at"] = _to_iso(normalized.get("recognition_started_at"))
    normalized["recognition_finished_at"] = _to_iso(normalized.get("recognition_finished_at"))

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


def is_resource_ops_recognition_running(config: dict[str, Any]) -> bool:
    return bool(_coerce_text(config.get("recognition_running_mode"), "", max_length=16))


def get_resource_ops_recognition_request_mode(config: dict[str, Any]) -> str | None:
    mode = _coerce_text(config.get("recognition_requested_mode"), "", max_length=16).lower()
    return mode if mode in {"pending", "all"} else None


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
        "model": model,
        "api_key": api_key,
        "used_saved_api_key": bool(not request_api_key and use_saved_api_key and saved_api_key),
    }


def get_resource_ops_runtime_settings(session: Session) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    ai_base_url = _coerce_text(values.get("ai_base_url"), "", max_length=512)
    ai_model = _coerce_text(values.get("ai_model"), "", max_length=255)
    ai_api_key = _coerce_text(values.get("ai_api_key"), "", max_length=8000)
    total_count = int(values.get("recognition_total") or 0)
    processed_count = int(values.get("recognition_processed") or 0)
    matched_count = int(values.get("recognition_matched") or 0)
    error_count = int(values.get("recognition_error") or 0)

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
            "is_running": is_resource_ops_recognition_running(values),
            "requested_mode": get_resource_ops_recognition_request_mode(values),
            "current_mode": _coerce_text(values.get("recognition_running_mode"), "", max_length=16) or None,
            "started_at": _to_iso(values.get("recognition_started_at")),
            "finished_at": _to_iso(values.get("recognition_finished_at")),
            "total_count": total_count,
            "processed_count": processed_count,
            "matched_count": matched_count,
            "error_count": error_count,
            "remaining_count": max(0, total_count - processed_count),
            "last_error": _coerce_text(values.get("recognition_last_error"), "", max_length=2000) or None,
            "logs": list(values.get("recognition_logs") or []),
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


def request_resource_ops_recognition(
    session: Session,
    *,
    mode: str,
    updated_by: str | None = None,
) -> dict[str, Any]:
    normalized_mode = _coerce_text(mode, "", max_length=16).lower()
    if normalized_mode not in {"pending", "all"}:
        raise ValueError("invalid recognition mode")

    values = get_resource_ops_runtime_config(session)
    current_request = get_resource_ops_recognition_request_mode(values)
    current_running = _coerce_text(values.get("recognition_running_mode"), "", max_length=16).lower()

    if current_running == "all":
        return get_resource_ops_runtime_settings(session)
    if current_running == "pending" and normalized_mode == "pending":
        return get_resource_ops_runtime_settings(session)
    if current_request == "all":
        return get_resource_ops_runtime_settings(session)

    values["recognition_requested_mode"] = "all" if normalized_mode == "all" else (current_request or "pending")
    values["recognition_requested_at"] = _utcnow()

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)


def start_resource_ops_recognition_run(
    session: Session,
    *,
    mode: str,
    total_count: int,
    updated_by: str | None = None,
) -> dict[str, Any]:
    normalized_mode = _coerce_text(mode, "", max_length=16).lower()
    if normalized_mode not in {"pending", "all"}:
        raise ValueError("invalid recognition mode")

    values = get_resource_ops_runtime_config(session)
    values["recognition_requested_mode"] = ""
    values["recognition_requested_at"] = None
    values["recognition_running_mode"] = normalized_mode
    values["recognition_started_at"] = _utcnow()
    values["recognition_finished_at"] = None
    values["recognition_total"] = max(0, int(total_count or 0))
    values["recognition_processed"] = 0
    values["recognition_matched"] = 0
    values["recognition_error"] = 0
    values["recognition_last_error"] = ""
    values["recognition_logs"] = []

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)


def update_resource_ops_recognition_progress(
    session: Session,
    *,
    processed_delta: int = 0,
    matched_delta: int = 0,
    error_delta: int = 0,
    log_line: str | None = None,
    last_error: str | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    values["recognition_processed"] = max(0, int(values.get("recognition_processed") or 0) + int(processed_delta or 0))
    values["recognition_matched"] = max(0, int(values.get("recognition_matched") or 0) + int(matched_delta or 0))
    values["recognition_error"] = max(0, int(values.get("recognition_error") or 0) + int(error_delta or 0))
    if log_line:
        logs = list(values.get("recognition_logs") or [])
        logs.append(_coerce_text(log_line, "", max_length=500))
        values["recognition_logs"] = [item for item in logs if item][-RECOGNITION_LOG_LIMIT:]
    if last_error is not None:
        values["recognition_last_error"] = _coerce_text(last_error, "", max_length=2000)

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)


def finish_resource_ops_recognition_run(
    session: Session,
    *,
    summary: dict[str, Any],
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    values["recognition_running_mode"] = ""
    values["recognition_finished_at"] = _utcnow()
    values["last_sync_at"] = _utcnow()
    values["last_sync_summary"] = dict(summary or {})

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)
