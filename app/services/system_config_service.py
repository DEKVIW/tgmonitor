from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import (
    BackupSettings,
    SystemSettings,
    engine,
    ensure_runtime_storage_tables,
)


logger = logging.getLogger(__name__)

SYSTEM_SETTINGS_SINGLETON_ID = 1
BACKUP_SETTINGS_SINGLETON_ID = 1

SYSTEM_CONFIG_FIELDS: tuple[str, ...] = (
    "site_name",
    "site_title",
    "site_description",
    "site_keywords",
    "brand_icon",
    "site_favicon_url",
    "public_dashboard_enabled",
    "public_ads_enabled",
    "public_feed_top_ad_html_desktop",
    "public_feed_top_ad_html_mobile",
    "public_feed_inline_ad_html_desktop",
    "public_feed_inline_ad_html_mobile",
    "public_feed_inline_every_n",
    "umami_enabled",
    "umami_script_url",
    "umami_website_id",
    "umami_host_url",
    "umami_share_url",
    "link_check_default_max_concurrent",
    "link_check_max_allowed_concurrent",
    "link_check_max_allowed_links",
    "link_check_poll_interval_seconds",
    "monitor_channel_refresh_interval_seconds",
    "monitor_db_write_max_retries",
    "monitor_db_write_retry_delay_seconds",
)

PUBLIC_SYSTEM_CONFIG_FIELDS: tuple[str, ...] = (
    "site_name",
    "site_title",
    "site_description",
    "site_keywords",
    "brand_icon",
    "site_favicon_url",
    "public_dashboard_enabled",
    "public_ads_enabled",
    "public_feed_top_ad_html_desktop",
    "public_feed_top_ad_html_mobile",
    "public_feed_inline_ad_html_desktop",
    "public_feed_inline_ad_html_mobile",
    "public_feed_inline_every_n",
    "umami_enabled",
    "umami_script_url",
    "umami_website_id",
    "umami_host_url",
)

BACKUP_SETTINGS_FIELDS: tuple[str, ...] = (
    "backup_enabled",
    "local_backup_enabled",
    "local_backup_dir",
    "local_keep_count",
    "local_keep_days",
    "webdav_enabled",
    "webdav_base_url",
    "webdav_username",
    "webdav_password_encrypted",
    "webdav_root_path",
    "webdav_timeout_seconds",
    "webdav_verify_ssl",
    "schedule_enabled",
    "schedule_kind",
    "schedule_value",
    "timezone",
    "archive_format",
    "compress_level",
    "include_database",
    "include_users_json",
    "include_env_file",
    "include_runtime_data",
)


def build_default_system_config_values() -> dict[str, Any]:
    return {
        "site_name": "TG\u9891\u9053\u76d1\u63a7",
        "site_title": "TG\u9891\u9053\u76d1\u63a7",
        "site_description": "Telegram \u9891\u9053\u7f51\u76d8\u8d44\u6e90\u76d1\u63a7\u4e0e\u68c0\u7d22",
        "site_keywords": "telegram,\u7f51\u76d8,\u9891\u9053\u76d1\u63a7,\u8d44\u6e90\u641c\u7d22",
        "brand_icon": "\U0001F4F1",
        "site_favicon_url": "/favicon.svg",
        "public_dashboard_enabled": bool(settings.PUBLIC_DASHBOARD_ENABLED),
        "public_ads_enabled": bool(settings.PUBLIC_ADS_ENABLED),
        "public_feed_top_ad_html_desktop": str(settings.PUBLIC_FEED_TOP_AD_HTML_DESKTOP or ""),
        "public_feed_top_ad_html_mobile": str(settings.PUBLIC_FEED_TOP_AD_HTML_MOBILE or ""),
        "public_feed_inline_ad_html_desktop": str(settings.PUBLIC_FEED_INLINE_AD_HTML_DESKTOP or ""),
        "public_feed_inline_ad_html_mobile": str(settings.PUBLIC_FEED_INLINE_AD_HTML_MOBILE or ""),
        "public_feed_inline_every_n": int(settings.PUBLIC_FEED_INLINE_EVERY_N),
        "umami_enabled": bool(settings.UMAMI_ENABLED),
        "umami_script_url": str(settings.UMAMI_SCRIPT_URL or ""),
        "umami_website_id": str(settings.UMAMI_WEBSITE_ID or ""),
        "umami_host_url": str(settings.UMAMI_HOST_URL or ""),
        "umami_share_url": str(settings.UMAMI_SHARE_URL or ""),
        "link_check_default_max_concurrent": int(settings.LINK_CHECK_DEFAULT_MAX_CONCURRENT),
        "link_check_max_allowed_concurrent": int(settings.LINK_CHECK_MAX_ALLOWED_CONCURRENT),
        "link_check_max_allowed_links": int(settings.LINK_CHECK_MAX_ALLOWED_LINKS),
        "link_check_poll_interval_seconds": int(settings.LINK_CHECK_POLL_INTERVAL_SECONDS),
        "monitor_channel_refresh_interval_seconds": int(settings.MONITOR_CHANNEL_REFRESH_INTERVAL_SECONDS),
        "monitor_db_write_max_retries": int(settings.MONITOR_DB_WRITE_MAX_RETRIES),
        "monitor_db_write_retry_delay_seconds": float(settings.MONITOR_DB_WRITE_RETRY_DELAY_SECONDS),
    }
def build_default_backup_settings_values() -> dict[str, Any]:
    return {
        "backup_enabled": False,
        "local_backup_enabled": True,
        "local_backup_dir": "data/backups",
        "local_keep_count": 14,
        "local_keep_days": 30,
        "webdav_enabled": False,
        "webdav_base_url": "",
        "webdav_username": "",
        "webdav_password_encrypted": "",
        "webdav_root_path": "",
        "webdav_timeout_seconds": 60,
        "webdav_verify_ssl": True,
        "schedule_enabled": False,
        "schedule_kind": "manual",
        "schedule_value": "",
        "timezone": "Asia/Shanghai",
        "archive_format": "tar.gz",
        "compress_level": 6,
        "include_database": True,
        "include_users_json": True,
        "include_env_file": False,
        "include_runtime_data": True,
    }


def _model_to_dict(model: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(model, field) for field in fields}


def _ensure_singleton_row(
    session: Session,
    model: type[Any],
    singleton_id: int,
    defaults: dict[str, Any],
) -> Any:
    instance = session.get(model, singleton_id)
    if instance is not None:
        return instance

    instance = model(id=singleton_id, **defaults)
    session.add(instance)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        instance = session.get(model, singleton_id)
        if instance is None:
            raise
        return instance

    session.refresh(instance)
    return instance


def ensure_runtime_configuration_seeded() -> None:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        _ensure_singleton_row(
            session,
            SystemSettings,
            SYSTEM_SETTINGS_SINGLETON_ID,
            build_default_system_config_values(),
        )
        _ensure_singleton_row(
            session,
            BackupSettings,
            BACKUP_SETTINGS_SINGLETON_ID,
            build_default_backup_settings_values(),
        )


def get_system_config_values() -> dict[str, Any]:
    try:
        ensure_runtime_configuration_seeded()
        with Session(engine) as session:
            record = _ensure_singleton_row(
                session,
                SystemSettings,
                SYSTEM_SETTINGS_SINGLETON_ID,
                build_default_system_config_values(),
            )
            return _model_to_dict(record, SYSTEM_CONFIG_FIELDS)
    except Exception as exc:
        logger.warning("Failed to load system settings from database, falling back to env defaults: %s", exc)
        return build_default_system_config_values()


def get_public_system_config_values() -> dict[str, Any]:
    values = get_system_config_values()
    return {field: values[field] for field in PUBLIC_SYSTEM_CONFIG_FIELDS}


def get_backup_settings_values() -> dict[str, Any]:
    try:
        ensure_runtime_configuration_seeded()
        with Session(engine) as session:
            record = _ensure_singleton_row(
                session,
                BackupSettings,
                BACKUP_SETTINGS_SINGLETON_ID,
                build_default_backup_settings_values(),
            )
            return _model_to_dict(record, BACKUP_SETTINGS_FIELDS)
    except Exception as exc:
        logger.warning("Failed to load backup settings from database, falling back to defaults: %s", exc)
        return build_default_backup_settings_values()


def apply_system_config(values: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_configuration_seeded()
    with Session(engine) as session:
        record = _ensure_singleton_row(
            session,
            SystemSettings,
            SYSTEM_SETTINGS_SINGLETON_ID,
            build_default_system_config_values(),
        )
        for field in SYSTEM_CONFIG_FIELDS:
            setattr(record, field, values[field])
        record.updated_by = updated_by
        session.add(record)
        session.commit()
        session.refresh(record)
        return _model_to_dict(record, SYSTEM_CONFIG_FIELDS)


def apply_backup_settings(values: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
    ensure_runtime_configuration_seeded()
    with Session(engine) as session:
        record = _ensure_singleton_row(
            session,
            BackupSettings,
            BACKUP_SETTINGS_SINGLETON_ID,
            build_default_backup_settings_values(),
        )
        for field in BACKUP_SETTINGS_FIELDS:
            setattr(record, field, values[field])
        record.updated_by = updated_by
        session.add(record)
        session.commit()
        session.refresh(record)
        return _model_to_dict(record, BACKUP_SETTINGS_FIELDS)


def is_public_dashboard_enabled() -> bool:
    return bool(get_system_config_values()["public_dashboard_enabled"])


def get_monitor_runtime_config() -> dict[str, Any]:
    values = get_system_config_values()
    return {
        "monitor_channel_refresh_interval_seconds": int(values["monitor_channel_refresh_interval_seconds"]),
        "monitor_db_write_max_retries": int(values["monitor_db_write_max_retries"]),
        "monitor_db_write_retry_delay_seconds": float(values["monitor_db_write_retry_delay_seconds"]),
    }


def get_link_check_runtime_config() -> dict[str, Any]:
    values = get_system_config_values()
    return {
        "link_check_default_max_concurrent": int(values["link_check_default_max_concurrent"]),
        "link_check_max_allowed_concurrent": int(values["link_check_max_allowed_concurrent"]),
        "link_check_max_allowed_links": int(values["link_check_max_allowed_links"]),
        "link_check_poll_interval_seconds": int(values["link_check_poll_interval_seconds"]),
    }

