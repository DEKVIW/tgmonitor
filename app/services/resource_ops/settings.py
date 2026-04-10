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
        "auto_bind_enabled": False,
        "sync_batch_size": 12,
        "sync_interval_minutes": 30,
        "ai_enabled": False,
        "ai_base_url": "",
        "ai_model": "",
        "ai_api_key_encrypted": "",
        "full_sync_generation": "",
        "full_sync_requested_at": None,
        "full_sync_started_at": None,
        "full_sync_finished_at": None,
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
    full_sync_requested_at = _coerce_datetime(payload.get("full_sync_requested_at"))
    full_sync_started_at = _coerce_datetime(payload.get("full_sync_started_at"))
    full_sync_finished_at = _coerce_datetime(payload.get("full_sync_finished_at"))
    last_sync_summary = payload.get("last_sync_summary")
    last_cleanup_summary = payload.get("last_cleanup_summary")

    return {
        "auto_bind_enabled": _coerce_bool(payload.get("auto_bind_enabled"), defaults["auto_bind_enabled"]),
        "sync_batch_size": _coerce_int(payload.get("sync_batch_size"), defaults["sync_batch_size"], minimum=1, maximum=100),
        "sync_interval_minutes": _coerce_int(
            payload.get("sync_interval_minutes"),
            defaults["sync_interval_minutes"],
            minimum=5,
            maximum=1440,
        ),
        "ai_enabled": _coerce_bool(payload.get("ai_enabled"), defaults["ai_enabled"]),
        "ai_base_url": _coerce_text(payload.get("ai_base_url"), defaults["ai_base_url"], max_length=512),
        "ai_model": _coerce_text(payload.get("ai_model"), defaults["ai_model"], max_length=255),
        "ai_api_key_encrypted": _coerce_text(
            payload.get("ai_api_key_encrypted"),
            defaults["ai_api_key_encrypted"],
            max_length=8000,
        ),
        "full_sync_generation": _coerce_text(payload.get("full_sync_generation"), defaults["full_sync_generation"], max_length=64),
        "full_sync_requested_at": full_sync_requested_at,
        "full_sync_started_at": full_sync_started_at,
        "full_sync_finished_at": full_sync_finished_at,
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
    normalized["full_sync_requested_at"] = _to_iso(normalized.get("full_sync_requested_at"))
    normalized["full_sync_started_at"] = _to_iso(normalized.get("full_sync_started_at"))
    normalized["full_sync_finished_at"] = _to_iso(normalized.get("full_sync_finished_at"))

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
        config.get("ai_enabled")
        and _coerce_text(config.get("ai_base_url"), "", max_length=512)
        and _coerce_text(config.get("ai_api_key"), "", max_length=8000)
    )

def is_resource_ops_full_sync_active(config: dict[str, Any]) -> bool:
    return bool(
        _coerce_text(config.get("full_sync_generation"), "", max_length=64)
        and config.get("full_sync_finished_at") is None
    )


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

    return {
        "auto_bind_enabled": bool(values["auto_bind_enabled"]),
        "sync_batch_size": int(values["sync_batch_size"]),
        "sync_interval_minutes": int(values["sync_interval_minutes"]),
        "ai_enabled": bool(values["ai_enabled"]),
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
        "full_sync_active": is_resource_ops_full_sync_active(values),
        "full_sync_requested_at": _to_iso(values.get("full_sync_requested_at")),
        "full_sync_started_at": _to_iso(values.get("full_sync_started_at")),
        "full_sync_finished_at": _to_iso(values.get("full_sync_finished_at")),
    }


def update_resource_ops_runtime_settings(
    session: Session,
    payload: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)

    for field in (
        "auto_bind_enabled",
        "sync_batch_size",
        "sync_interval_minutes",
        "ai_enabled",
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


def request_resource_ops_full_sync(
    session: Session,
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    values["full_sync_generation"] = _utcnow().strftime("%Y%m%d%H%M%S%f")
    values["full_sync_requested_at"] = _utcnow()
    values["full_sync_started_at"] = None
    values["full_sync_finished_at"] = None

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)


def mark_resource_ops_full_sync_started(
    session: Session,
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    if not _coerce_text(values.get("full_sync_generation"), "", max_length=64):
        return get_resource_ops_runtime_settings(session)
    if values.get("full_sync_started_at") is None:
        values["full_sync_started_at"] = _utcnow()
    values["full_sync_finished_at"] = None

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)


def finish_resource_ops_full_sync(
    session: Session,
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    if not _coerce_text(values.get("full_sync_generation"), "", max_length=64):
        return get_resource_ops_runtime_settings(session)
    if values.get("full_sync_started_at") is None:
        values["full_sync_started_at"] = _utcnow()
    values["full_sync_finished_at"] = _utcnow()

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_resource_ops_runtime_settings(session)
