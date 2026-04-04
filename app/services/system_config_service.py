from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.models.config import settings
from app.utils.env_utils import upsert_env_values


@dataclass(frozen=True)
class ConfigFieldDefinition:
    attr_name: str
    env_key: str
    serializer: Callable[[Any], str]


def _serialize_bool(value: Any) -> str:
    return str(bool(value)).lower()


def _serialize_int(value: Any) -> str:
    return str(int(value))


def _serialize_float(value: Any) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric)


CONFIG_FIELDS: tuple[ConfigFieldDefinition, ...] = (
    ConfigFieldDefinition("PUBLIC_DASHBOARD_ENABLED", "PUBLIC_DASHBOARD_ENABLED", _serialize_bool),
    ConfigFieldDefinition(
        "LINK_CHECK_DEFAULT_MAX_CONCURRENT",
        "LINK_CHECK_DEFAULT_MAX_CONCURRENT",
        _serialize_int,
    ),
    ConfigFieldDefinition(
        "LINK_CHECK_MAX_ALLOWED_CONCURRENT",
        "LINK_CHECK_MAX_ALLOWED_CONCURRENT",
        _serialize_int,
    ),
    ConfigFieldDefinition(
        "LINK_CHECK_MAX_ALLOWED_LINKS",
        "LINK_CHECK_MAX_ALLOWED_LINKS",
        _serialize_int,
    ),
    ConfigFieldDefinition(
        "LINK_CHECK_POLL_INTERVAL_SECONDS",
        "LINK_CHECK_POLL_INTERVAL_SECONDS",
        _serialize_int,
    ),
    ConfigFieldDefinition(
        "MONITOR_CHANNEL_REFRESH_INTERVAL_SECONDS",
        "MONITOR_CHANNEL_REFRESH_INTERVAL_SECONDS",
        _serialize_int,
    ),
    ConfigFieldDefinition(
        "MONITOR_DB_WRITE_MAX_RETRIES",
        "MONITOR_DB_WRITE_MAX_RETRIES",
        _serialize_int,
    ),
    ConfigFieldDefinition(
        "MONITOR_DB_WRITE_RETRY_DELAY_SECONDS",
        "MONITOR_DB_WRITE_RETRY_DELAY_SECONDS",
        _serialize_float,
    ),
)


def get_system_config_values() -> dict[str, Any]:
    return {
        "public_dashboard_enabled": bool(settings.PUBLIC_DASHBOARD_ENABLED),
        "link_check_default_max_concurrent": int(settings.LINK_CHECK_DEFAULT_MAX_CONCURRENT),
        "link_check_max_allowed_concurrent": int(settings.LINK_CHECK_MAX_ALLOWED_CONCURRENT),
        "link_check_max_allowed_links": int(settings.LINK_CHECK_MAX_ALLOWED_LINKS),
        "link_check_poll_interval_seconds": int(settings.LINK_CHECK_POLL_INTERVAL_SECONDS),
        "monitor_channel_refresh_interval_seconds": int(settings.MONITOR_CHANNEL_REFRESH_INTERVAL_SECONDS),
        "monitor_db_write_max_retries": int(settings.MONITOR_DB_WRITE_MAX_RETRIES),
        "monitor_db_write_retry_delay_seconds": float(settings.MONITOR_DB_WRITE_RETRY_DELAY_SECONDS),
    }


def apply_system_config(values: dict[str, Any], env_file: str = ".env") -> dict[str, Any]:
    previous_values = {field.attr_name: getattr(settings, field.attr_name) for field in CONFIG_FIELDS}

    try:
        env_updates: dict[str, str] = {}
        for field in CONFIG_FIELDS:
            next_value = values[field.attr_name.lower()]
            setattr(settings, field.attr_name, next_value)
            env_updates[field.env_key] = field.serializer(next_value)

        upsert_env_values(env_file, env_updates)
        return get_system_config_values()
    except Exception:
        for attr_name, previous_value in previous_values.items():
            setattr(settings, attr_name, previous_value)
        raise
