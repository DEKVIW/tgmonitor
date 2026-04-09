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
        "min_confidence": 0.72,
        "retry_cooldown_hours": 24,
        "tmdb_enabled": False,
        "tmdb_language": "zh-CN",
        "tmdb_api_key_encrypted": "",
        "tmdb_read_access_token_encrypted": "",
        "bangumi_enabled": False,
        "bangumi_user_agent": "TGMonitor/1.0",
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

    return {
        "auto_bind_enabled": _coerce_bool(payload.get("auto_bind_enabled"), defaults["auto_bind_enabled"]),
        "sync_batch_size": _coerce_int(payload.get("sync_batch_size"), defaults["sync_batch_size"], minimum=1, maximum=100),
        "sync_interval_minutes": _coerce_int(
            payload.get("sync_interval_minutes"),
            defaults["sync_interval_minutes"],
            minimum=5,
            maximum=1440,
        ),
        "min_confidence": _coerce_float(
            payload.get("min_confidence"),
            defaults["min_confidence"],
            minimum=0.4,
            maximum=0.99,
        ),
        "retry_cooldown_hours": _coerce_int(
            payload.get("retry_cooldown_hours"),
            defaults["retry_cooldown_hours"],
            minimum=1,
            maximum=720,
        ),
        "tmdb_enabled": _coerce_bool(payload.get("tmdb_enabled"), defaults["tmdb_enabled"]),
        "tmdb_language": _coerce_text(payload.get("tmdb_language"), defaults["tmdb_language"], max_length=32),
        "tmdb_api_key_encrypted": _coerce_text(
            payload.get("tmdb_api_key_encrypted"),
            defaults["tmdb_api_key_encrypted"],
            max_length=8000,
        ),
        "tmdb_read_access_token_encrypted": _coerce_text(
            payload.get("tmdb_read_access_token_encrypted"),
            defaults["tmdb_read_access_token_encrypted"],
            max_length=8000,
        ),
        "bangumi_enabled": _coerce_bool(payload.get("bangumi_enabled"), defaults["bangumi_enabled"]),
        "bangumi_user_agent": _coerce_text(
            payload.get("bangumi_user_agent"),
            defaults["bangumi_user_agent"],
            max_length=255,
        ),
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
    values["tmdb_api_key"] = decrypt_secret(values["tmdb_api_key_encrypted"])
    values["tmdb_read_access_token"] = decrypt_secret(values["tmdb_read_access_token_encrypted"])
    return values


def get_resource_ops_runtime_settings(session: Session) -> dict[str, Any]:
    values = get_resource_ops_runtime_config(session)
    tmdb_api_key = _coerce_text(values.get("tmdb_api_key"), "", max_length=512)
    tmdb_token = _coerce_text(values.get("tmdb_read_access_token"), "", max_length=4096)
    bangumi_user_agent = _coerce_text(values.get("bangumi_user_agent"), "TGMonitor/1.0", max_length=255)

    return {
        "auto_bind_enabled": bool(values["auto_bind_enabled"]),
        "sync_batch_size": int(values["sync_batch_size"]),
        "sync_interval_minutes": int(values["sync_interval_minutes"]),
        "min_confidence": float(values["min_confidence"]),
        "retry_cooldown_hours": int(values["retry_cooldown_hours"]),
        "tmdb_enabled": bool(values["tmdb_enabled"]),
        "tmdb_language": values["tmdb_language"],
        "tmdb_api_key_configured": bool(tmdb_api_key),
        "tmdb_read_access_token_configured": bool(tmdb_token),
        "tmdb_provider_ready": bool(values["tmdb_enabled"] and (tmdb_api_key or tmdb_token)),
        "bangumi_enabled": bool(values["bangumi_enabled"]),
        "bangumi_user_agent": bangumi_user_agent,
        "bangumi_provider_ready": bool(values["bangumi_enabled"] and bangumi_user_agent),
        "retention_click_event_days": int(values["retention_click_event_days"]),
        "retention_daily_stat_days": int(values["retention_daily_stat_days"]),
        "retention_candidate_log_days": int(values["retention_candidate_log_days"]),
        "cleanup_interval_hours": int(values["cleanup_interval_hours"]),
        "last_sync_at": _to_iso(values.get("last_sync_at")),
        "last_sync_summary": dict(values.get("last_sync_summary") or {}),
        "last_cleanup_at": _to_iso(values.get("last_cleanup_at")),
        "last_cleanup_summary": dict(values.get("last_cleanup_summary") or {}),
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
        "min_confidence",
        "retry_cooldown_hours",
        "tmdb_enabled",
        "tmdb_language",
        "bangumi_enabled",
        "bangumi_user_agent",
        "retention_click_event_days",
        "retention_daily_stat_days",
        "retention_candidate_log_days",
        "cleanup_interval_hours",
    ):
        if field in payload:
            values[field] = payload[field]

    if "tmdb_api_key" in payload:
        values["tmdb_api_key_encrypted"] = encrypt_secret(_coerce_text(payload.get("tmdb_api_key"), "", max_length=512))
    if "tmdb_read_access_token" in payload:
        values["tmdb_read_access_token_encrypted"] = encrypt_secret(
            _coerce_text(payload.get("tmdb_read_access_token"), "", max_length=4096)
        )

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
