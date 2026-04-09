from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.models import SystemSettings, ensure_runtime_storage_tables
from app.services.system_config_service import (
    SYSTEM_SETTINGS_SINGLETON_ID,
    build_default_system_settings_values,
    ensure_runtime_configuration_seeded,
)


DEDUP_RUNTIME_EXTRA_KEY = "dedup_runtime"
ALLOWED_DEDUP_SCOPE_MODES = {"all_history", "recent_hours"}
DEFAULT_DEDUP_TIMEZONE = "Asia/Shanghai"
DEFAULT_WAIT_WHEN_BLOCKED_MINUTES = 30


def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _get_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo(DEFAULT_DEDUP_TIMEZONE)


def build_default_dedup_runtime_settings() -> dict[str, Any]:
    return {
        "enabled": False,
        "scope_mode": "all_history",
        "lookback_hours": 72,
        "schedule_hour": 4,
        "schedule_minute": 20,
        "timezone": DEFAULT_DEDUP_TIMEZONE,
        "stats_retention_hours": 240,
        "next_run_at": None,
        "last_run_at": None,
        "last_status": None,
        "last_error_message": "",
        "last_run_summary": {},
    }


def _normalize_runtime_storage_values(raw_value: Any) -> dict[str, Any]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    defaults = build_default_dedup_runtime_settings()
    scope_mode = _coerce_text(payload.get("scope_mode"), defaults["scope_mode"], max_length=32).lower()
    if scope_mode not in ALLOWED_DEDUP_SCOPE_MODES:
        scope_mode = defaults["scope_mode"]

    summary = payload.get("last_run_summary")

    return {
        "enabled": _coerce_bool(payload.get("enabled"), defaults["enabled"]),
        "scope_mode": scope_mode,
        "lookback_hours": _coerce_int(
            payload.get("lookback_hours"),
            defaults["lookback_hours"],
            minimum=1,
            maximum=24 * 365,
        ),
        "schedule_hour": _coerce_int(payload.get("schedule_hour"), defaults["schedule_hour"], minimum=0, maximum=23),
        "schedule_minute": _coerce_int(
            payload.get("schedule_minute"),
            defaults["schedule_minute"],
            minimum=0,
            maximum=59,
        ),
        "timezone": _coerce_text(payload.get("timezone"), defaults["timezone"], max_length=64) or DEFAULT_DEDUP_TIMEZONE,
        "stats_retention_hours": _coerce_int(
            payload.get("stats_retention_hours"),
            defaults["stats_retention_hours"],
            minimum=10,
            maximum=24 * 365,
        ),
        "next_run_at": _coerce_datetime(payload.get("next_run_at")),
        "last_run_at": _coerce_datetime(payload.get("last_run_at")),
        "last_status": _coerce_text(payload.get("last_status"), "", max_length=32) or None,
        "last_error_message": _coerce_text(payload.get("last_error_message"), "", max_length=2000),
        "last_run_summary": dict(summary) if isinstance(summary, dict) else {},
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
    return _normalize_runtime_storage_values(extra_json.get(DEDUP_RUNTIME_EXTRA_KEY))


def _write_runtime_bucket(record: SystemSettings, payload: dict[str, Any], *, updated_by: str | None) -> None:
    normalized = _normalize_runtime_storage_values(payload)
    serialized = dict(normalized)
    serialized["next_run_at"] = _to_iso(normalized.get("next_run_at"))
    serialized["last_run_at"] = _to_iso(normalized.get("last_run_at"))

    extra_json = dict(record.extra_json or {})
    extra_json[DEDUP_RUNTIME_EXTRA_KEY] = serialized
    record.extra_json = extra_json
    record.updated_at = _utcnow()
    record.updated_by = updated_by


def compute_dedup_next_run_at(values: dict[str, Any], *, now_utc: datetime | None = None) -> datetime | None:
    if not bool(values.get("enabled")):
        return None

    current_utc = (now_utc or _utcnow()).replace(tzinfo=timezone.utc)
    timezone_info = _get_timezone(str(values.get("timezone") or DEFAULT_DEDUP_TIMEZONE))
    local_now = current_utc.astimezone(timezone_info)
    candidate = local_now.replace(
        hour=int(values.get("schedule_hour") or 0),
        minute=int(values.get("schedule_minute") or 0),
        second=0,
        microsecond=0,
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def _build_scope_label(values: dict[str, Any]) -> str:
    scope_mode = str(values.get("scope_mode") or "all_history")
    if scope_mode == "recent_hours":
        return f"最近 {int(values.get('lookback_hours') or 72)} 小时"
    return "全量历史"


def _build_status_summary(values: dict[str, Any]) -> str:
    if not bool(values.get("enabled")):
        return "自动去重已关闭"

    schedule_label = f"每日 {int(values.get('schedule_hour') or 0):02d}:{int(values.get('schedule_minute') or 0):02d}"
    scope_label = _build_scope_label(values)
    last_status = str(values.get("last_status") or "").strip()
    last_summary = values.get("last_run_summary") if isinstance(values.get("last_run_summary"), dict) else {}
    deleted_count = int(last_summary.get("deleted_count") or 0)

    if last_status == "completed" and last_summary:
        return f"{schedule_label} 自动去重，范围 {scope_label}，上次删除 {deleted_count} 条消息"
    if last_status == "failed":
        return f"{schedule_label} 自动去重，范围 {scope_label}，上次执行失败"
    if last_status == "waiting":
        return f"{schedule_label} 自动去重，范围 {scope_label}，当前等待上一轮任务结束"
    return f"{schedule_label} 自动去重，范围 {scope_label}"


def get_dedup_runtime_config(session: Session) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    ensure_runtime_configuration_seeded()
    record = _ensure_system_settings_record(session)
    return _read_runtime_bucket(record)


def get_dedup_runtime_settings(session: Session) -> dict[str, Any]:
    values = get_dedup_runtime_config(session)
    response = dict(values)
    response["scope_label"] = _build_scope_label(values)
    response["next_run_at"] = _to_iso(values.get("next_run_at"))
    response["last_run_at"] = _to_iso(values.get("last_run_at"))
    response["status_summary"] = _build_status_summary(values)
    return response


def update_dedup_runtime_settings(
    session: Session,
    payload: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_dedup_runtime_config(session)

    for field in (
        "enabled",
        "scope_mode",
        "lookback_hours",
        "schedule_hour",
        "schedule_minute",
        "timezone",
        "stats_retention_hours",
    ):
        if field in payload:
            values[field] = payload[field]

    values = _normalize_runtime_storage_values(values)
    values["next_run_at"] = compute_dedup_next_run_at(values) if values["enabled"] else None

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_dedup_runtime_settings(session)


def update_dedup_runtime_meta(
    session: Session,
    *,
    last_status: str | None = None,
    last_error_message: str | None = None,
    last_run_summary: dict[str, Any] | None = None,
    advance_next_run: bool = False,
    wait_minutes: int | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    values = get_dedup_runtime_config(session)

    if last_status is not None:
        values["last_status"] = str(last_status).strip()[:32] or None
    if last_error_message is not None:
        values["last_error_message"] = str(last_error_message).strip()[:2000]
    if last_run_summary is not None:
        values["last_run_summary"] = dict(last_run_summary)
        values["last_run_at"] = _utcnow()

    if values.get("enabled"):
        if wait_minutes is not None:
            values["next_run_at"] = _utcnow() + timedelta(minutes=max(1, int(wait_minutes)))
        elif advance_next_run:
            values["next_run_at"] = compute_dedup_next_run_at(values)
        elif values.get("next_run_at") and values["next_run_at"] <= _utcnow():
            values["next_run_at"] = compute_dedup_next_run_at(values)
    else:
        values["next_run_at"] = None

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_dedup_runtime_settings(session)


def ensure_dedup_next_run(session: Session, *, updated_by: str | None = None) -> dict[str, Any]:
    values = get_dedup_runtime_config(session)
    if values.get("enabled") and values.get("next_run_at") is None:
        values["next_run_at"] = compute_dedup_next_run_at(values)

    record = _ensure_system_settings_record(session)
    _write_runtime_bucket(record, values, updated_by=updated_by)
    session.add(record)
    session.flush()
    return get_dedup_runtime_settings(session)
