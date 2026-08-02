from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    AiCallEvent,
    PanTransferExecutionLog,
    PanTransferReplacementLog,
    PanTransferSyncTaskLog,
    SystemSettings,
    ensure_runtime_storage_tables,
)
from app.services.system_config_service import (
    SYSTEM_SETTINGS_SINGLETON_ID,
    build_default_system_settings_values,
)


logger = logging.getLogger(__name__)

PAN_TRANSFER_MAINTENANCE_EXTRA_KEY = "pan_transfer_maintenance"
DEFAULT_CLEANUP_INTERVAL_HOURS = 24
DEFAULT_EXECUTION_LOG_RETENTION_DAYS = 90
DEFAULT_FOLLOW_LOG_RETENTION_DAYS = 90
DEFAULT_AI_CALL_EVENT_RETENTION_DAYS = 90
DEFAULT_REPLACEMENT_LOG_RETENTION_DAYS = 365


def _utcnow() -> datetime:
    return datetime.utcnow()


def _coerce_int(
    value: Any,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


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


def _to_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _ensure_system_settings_record(session: Session) -> SystemSettings:
    record = session.get(SystemSettings, SYSTEM_SETTINGS_SINGLETON_ID)
    if record is not None:
        return record
    record = SystemSettings(id=SYSTEM_SETTINGS_SINGLETON_ID, **build_default_system_settings_values())
    session.add(record)
    session.flush()
    return record


def _normalize_maintenance_config(raw_value: Any) -> dict[str, Any]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    last_cleanup_summary = payload.get("last_cleanup_summary")
    return {
        "cleanup_interval_hours": _coerce_int(
            payload.get("cleanup_interval_hours"),
            DEFAULT_CLEANUP_INTERVAL_HOURS,
            minimum=1,
            maximum=720,
        ),
        "execution_log_retention_days": _coerce_int(
            payload.get("execution_log_retention_days"),
            DEFAULT_EXECUTION_LOG_RETENTION_DAYS,
            minimum=7,
            maximum=3650,
        ),
        "follow_log_retention_days": _coerce_int(
            payload.get("follow_log_retention_days"),
            DEFAULT_FOLLOW_LOG_RETENTION_DAYS,
            minimum=7,
            maximum=3650,
        ),
        "ai_call_event_retention_days": _coerce_int(
            payload.get("ai_call_event_retention_days"),
            DEFAULT_AI_CALL_EVENT_RETENTION_DAYS,
            minimum=7,
            maximum=3650,
        ),
        "replacement_log_retention_days": _coerce_int(
            payload.get("replacement_log_retention_days"),
            DEFAULT_REPLACEMENT_LOG_RETENTION_DAYS,
            minimum=30,
            maximum=3650,
        ),
        "last_cleanup_at": _coerce_datetime(payload.get("last_cleanup_at")),
        "last_cleanup_summary": dict(last_cleanup_summary) if isinstance(last_cleanup_summary, dict) else {},
    }


def _read_maintenance_config(record: SystemSettings) -> dict[str, Any]:
    extra_json = dict(record.extra_json or {})
    return _normalize_maintenance_config(extra_json.get(PAN_TRANSFER_MAINTENANCE_EXTRA_KEY))


def _write_maintenance_config(
    record: SystemSettings,
    config: dict[str, Any],
    *,
    updated_by: str | None,
) -> None:
    extra_json = dict(record.extra_json or {})
    normalized = _normalize_maintenance_config(config)
    extra_json[PAN_TRANSFER_MAINTENANCE_EXTRA_KEY] = {
        **normalized,
        "last_cleanup_at": _to_utc_iso(normalized.get("last_cleanup_at")),
    }
    record.extra_json = extra_json
    record.updated_by = updated_by or record.updated_by


def _delete_logs_older_than(session: Session, model: type[Any], cutoff: datetime) -> int:
    return int(
        session.query(model)
        .filter(model.created_at < cutoff)
        .delete(synchronize_session=False)
        or 0
    )


def should_run_pan_transfer_log_retention(config: dict[str, Any], *, now: datetime | None = None) -> bool:
    interval_hours = _coerce_int(
        config.get("cleanup_interval_hours"),
        DEFAULT_CLEANUP_INTERVAL_HOURS,
        minimum=1,
        maximum=720,
    )
    last_cleanup_at = _coerce_datetime(config.get("last_cleanup_at"))
    if last_cleanup_at is None:
        return True
    return last_cleanup_at + timedelta(hours=interval_hours) <= (now or _utcnow())


def run_pan_transfer_log_retention(
    session: Session,
    *,
    operator: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    record = _ensure_system_settings_record(session)
    config = _read_maintenance_config(record)
    now = _utcnow()

    execution_log_cutoff = now - timedelta(days=int(config["execution_log_retention_days"]))
    follow_log_cutoff = now - timedelta(days=int(config["follow_log_retention_days"]))
    ai_event_cutoff = now - timedelta(days=int(config["ai_call_event_retention_days"]))
    replacement_log_cutoff = now - timedelta(days=int(config["replacement_log_retention_days"]))

    summary = {
        "deleted_execution_logs": _delete_logs_older_than(session, PanTransferExecutionLog, execution_log_cutoff),
        "deleted_follow_task_logs": _delete_logs_older_than(session, PanTransferSyncTaskLog, follow_log_cutoff),
        "deleted_ai_call_events": _delete_logs_older_than(session, AiCallEvent, ai_event_cutoff),
        "deleted_replacement_logs": _delete_logs_older_than(session, PanTransferReplacementLog, replacement_log_cutoff),
        "execution_log_retention_days": int(config["execution_log_retention_days"]),
        "follow_log_retention_days": int(config["follow_log_retention_days"]),
        "ai_call_event_retention_days": int(config["ai_call_event_retention_days"]),
        "replacement_log_retention_days": int(config["replacement_log_retention_days"]),
        "cleaned_at": _to_utc_iso(now),
    }
    config["last_cleanup_at"] = now
    config["last_cleanup_summary"] = summary
    _write_maintenance_config(record, config, updated_by=operator or "system")
    session.add(record)
    session.flush()
    logger.info("pan transfer log retention finished: %s", summary)
    return summary


def run_pan_transfer_log_retention_if_due(session: Session, *, worker_name: str) -> bool:
    ensure_runtime_storage_tables()
    record = _ensure_system_settings_record(session)
    config = _read_maintenance_config(record)
    if not should_run_pan_transfer_log_retention(config):
        return False
    run_pan_transfer_log_retention(session, operator=worker_name)
    return True
