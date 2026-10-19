"""Runtime state shared by the Telegram monitor and the API process."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


RUNTIME_STATE_PATH = Path("data/monitor_runtime.json")
RUNTIME_STATE_MAX_AGE_SECONDS = 90


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return _to_iso(value)
    return str(value)


def write_monitor_runtime_state(
    *,
    status: str,
    configured_channels: list[str],
    channel_info: Dict[str, Dict[str, Any]],
    started_at: datetime,
    last_message_at: datetime | None = None,
    last_message_channel: str | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "version": 1,
        "status": status,
        "pid": os.getpid(),
        "started_at": _to_iso(started_at),
        "heartbeat_at": _to_iso(_utc_now()),
        "configured_channels": list(configured_channels),
        "active_channels": list(channel_info),
        "channel_info": channel_info,
        "last_message_at": _to_iso(last_message_at),
        "last_message_channel": last_message_channel,
        "error": error,
    }
    RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = RUNTIME_STATE_PATH.with_name(f".{RUNTIME_STATE_PATH.name}.{os.getpid()}.tmp")
    temp_path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temp_path, RUNTIME_STATE_PATH)


def read_monitor_runtime_state() -> Dict[str, Any] | None:
    try:
        payload = json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def get_fresh_monitor_runtime_state(
    max_age_seconds: int = RUNTIME_STATE_MAX_AGE_SECONDS,
) -> Dict[str, Any] | None:
    payload = read_monitor_runtime_state()
    if not payload:
        return None
    if payload.get("status") != "running":
        return None

    heartbeat_at = payload.get("heartbeat_at")
    if not heartbeat_at:
        return None
    try:
        heartbeat_time = datetime.fromisoformat(str(heartbeat_at))
    except ValueError:
        return None
    if heartbeat_time.tzinfo is None:
        heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)
    age_seconds = (_utc_now() - heartbeat_time.astimezone(timezone.utc)).total_seconds()
    if age_seconds < 0 or age_seconds > max(1, int(max_age_seconds)):
        return None
    payload["age_seconds"] = age_seconds
    return payload
