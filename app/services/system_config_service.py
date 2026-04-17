from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.config import settings
from app.models.models import BackupSettings, SystemSettings, engine, ensure_runtime_storage_tables


logger = logging.getLogger(__name__)

SYSTEM_SETTINGS_SINGLETON_ID = 1
BACKUP_SETTINGS_SINGLETON_ID = 1
FOOTER_BUILDER_EXTRA_KEY = 'footer_builder'
MAX_FOOTER_SECTION_COUNT = 12
MAX_FOOTER_SECTION_ID_LENGTH = 128
MAX_FOOTER_SECTION_TITLE_LENGTH = 255
MAX_FOOTER_SECTION_HTML_LENGTH = 20000
MAX_FOOTER_BOTTOM_HTML_LENGTH = 20000

SYSTEM_SETTINGS_FIELDS: tuple[str, ...] = (
    'site_name',
    'site_title',
    'site_description',
    'site_keywords',
    'brand_icon',
    'site_favicon_url',
    'public_dashboard_enabled',
    'public_ads_enabled',
    'public_feed_top_ad_html_desktop',
    'public_feed_top_ad_html_mobile',
    'public_feed_inline_ad_html_desktop',
    'public_feed_inline_ad_html_mobile',
    'public_feed_inline_every_n',
    'umami_enabled',
    'umami_script_url',
    'umami_website_id',
    'umami_host_url',
    'umami_share_url',
    'link_check_default_max_concurrent',
    'link_check_max_allowed_concurrent',
    'link_check_max_allowed_links',
    'link_check_poll_interval_seconds',
    'monitor_channel_refresh_interval_seconds',
    'monitor_db_write_max_retries',
    'monitor_db_write_retry_delay_seconds',
)

PUBLIC_SYSTEM_SETTINGS_FIELDS: tuple[str, ...] = (
    'site_name',
    'site_title',
    'site_description',
    'site_keywords',
    'brand_icon',
    'site_favicon_url',
    'public_dashboard_enabled',
    'public_ads_enabled',
    'public_feed_top_ad_html_desktop',
    'public_feed_top_ad_html_mobile',
    'public_feed_inline_ad_html_desktop',
    'public_feed_inline_ad_html_mobile',
    'public_feed_inline_every_n',
    'umami_enabled',
    'umami_script_url',
    'umami_website_id',
    'umami_host_url',
)

FOOTER_BUILDER_FIELDS: tuple[str, ...] = (
    'footer_builder_enabled',
    'footer_builder_sections',
    'footer_builder_bottom_html',
)

BACKUP_SETTINGS_FIELDS: tuple[str, ...] = (
    'backup_enabled',
    'local_backup_enabled',
    'local_backup_dir',
    'local_keep_count',
    'local_keep_days',
    'webdav_enabled',
    'webdav_base_url',
    'webdav_username',
    'webdav_password_encrypted',
    'webdav_root_path',
    'webdav_timeout_seconds',
    'webdav_verify_ssl',
    'schedule_enabled',
    'schedule_kind',
    'schedule_value',
    'timezone',
    'archive_format',
    'compress_level',
    'include_database',
    'include_users_json',
    'include_env_file',
    'include_runtime_data',
)

BOOLEAN_SYSTEM_SETTINGS_FIELDS = {
    'public_dashboard_enabled',
    'public_ads_enabled',
    'umami_enabled',
}

INTEGER_SYSTEM_SETTINGS_FIELDS = {
    'public_feed_inline_every_n',
    'link_check_default_max_concurrent',
    'link_check_max_allowed_concurrent',
    'link_check_max_allowed_links',
    'link_check_poll_interval_seconds',
    'monitor_channel_refresh_interval_seconds',
    'monitor_db_write_max_retries',
}

FLOAT_SYSTEM_SETTINGS_FIELDS = {
    'monitor_db_write_retry_delay_seconds',
}


def build_default_system_settings_values() -> dict[str, Any]:
    return {
        'site_name': '',
        'site_title': '',
        'site_description': '',
        'site_keywords': '',
        'brand_icon': '',
        'site_favicon_url': '/favicon.svg',
        'public_dashboard_enabled': bool(settings.PUBLIC_DASHBOARD_ENABLED),
        'public_ads_enabled': bool(settings.PUBLIC_ADS_ENABLED),
        'public_feed_top_ad_html_desktop': str(settings.PUBLIC_FEED_TOP_AD_HTML_DESKTOP or ''),
        'public_feed_top_ad_html_mobile': str(settings.PUBLIC_FEED_TOP_AD_HTML_MOBILE or ''),
        'public_feed_inline_ad_html_desktop': str(settings.PUBLIC_FEED_INLINE_AD_HTML_DESKTOP or ''),
        'public_feed_inline_ad_html_mobile': str(settings.PUBLIC_FEED_INLINE_AD_HTML_MOBILE or ''),
        'public_feed_inline_every_n': int(settings.PUBLIC_FEED_INLINE_EVERY_N),
        'umami_enabled': bool(settings.UMAMI_ENABLED),
        'umami_script_url': str(settings.UMAMI_SCRIPT_URL or ''),
        'umami_website_id': str(settings.UMAMI_WEBSITE_ID or ''),
        'umami_host_url': str(settings.UMAMI_HOST_URL or ''),
        'umami_share_url': str(settings.UMAMI_SHARE_URL or ''),
        'link_check_default_max_concurrent': int(settings.LINK_CHECK_DEFAULT_MAX_CONCURRENT),
        'link_check_max_allowed_concurrent': int(settings.LINK_CHECK_MAX_ALLOWED_CONCURRENT),
        'link_check_max_allowed_links': int(settings.LINK_CHECK_MAX_ALLOWED_LINKS),
        'link_check_poll_interval_seconds': int(settings.LINK_CHECK_POLL_INTERVAL_SECONDS),
        'monitor_channel_refresh_interval_seconds': int(settings.MONITOR_CHANNEL_REFRESH_INTERVAL_SECONDS),
        'monitor_db_write_max_retries': int(settings.MONITOR_DB_WRITE_MAX_RETRIES),
        'monitor_db_write_retry_delay_seconds': float(settings.MONITOR_DB_WRITE_RETRY_DELAY_SECONDS),
    }


def build_default_footer_builder_values() -> dict[str, Any]:
    return {
        'footer_builder_enabled': False,
        'footer_builder_sections': [],
        'footer_builder_bottom_html': '',
    }


def build_default_system_config_values() -> dict[str, Any]:
    values = build_default_system_settings_values()
    values.update(build_default_footer_builder_values())
    return values


def build_default_backup_settings_values() -> dict[str, Any]:
    return {
        'backup_enabled': False,
        'local_backup_enabled': True,
        'local_backup_dir': 'data/backups',
        'local_keep_count': 14,
        'local_keep_days': 30,
        'webdav_enabled': False,
        'webdav_base_url': '',
        'webdav_username': '',
        'webdav_password_encrypted': '',
        'webdav_root_path': '',
        'webdav_timeout_seconds': 60,
        'webdav_verify_ssl': True,
        'schedule_enabled': False,
        'schedule_kind': 'manual',
        'schedule_value': '',
        'timezone': 'Asia/Shanghai',
        'archive_format': 'tar.gz',
        'compress_level': 6,
        'include_database': True,
        'include_users_json': True,
        'include_env_file': False,
        'include_runtime_data': True,
    }


def _model_to_dict(model: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(model, field) for field in fields}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'off', ''}:
            return False
    return bool(value)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_text(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _trim_text(value: Any, *, max_length: int, strip: bool = False) -> str:
    text = '' if value is None else str(value)
    if strip:
        text = text.strip()
    return text[:max_length]


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


def _normalize_footer_builder_values(raw_value: Any) -> dict[str, Any]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    sections: list[dict[str, Any]] = []
    seen_section_ids: dict[str, int] = {}

    raw_sections = payload.get('sections', [])
    if not isinstance(raw_sections, list):
        raw_sections = []

    for index, item in enumerate(raw_sections[:MAX_FOOTER_SECTION_COUNT]):
        if not isinstance(item, dict):
            continue
        fallback_section_id = f'footer-section-{index + 1}'
        section_id = _trim_text(
            item.get('id') or fallback_section_id,
            max_length=MAX_FOOTER_SECTION_ID_LENGTH,
            strip=True,
        ) or fallback_section_id
        duplicate_count = seen_section_ids.get(section_id, 0)
        if duplicate_count:
            suffix = f'-{duplicate_count + 1}'
            max_base_length = MAX_FOOTER_SECTION_ID_LENGTH - len(suffix)
            section_id = f'{section_id[:max_base_length]}{suffix}'
        seen_section_ids[section_id] = duplicate_count + 1
        title = _trim_text(item.get('title'), max_length=MAX_FOOTER_SECTION_TITLE_LENGTH, strip=True)
        html = _trim_text(item.get('html'), max_length=MAX_FOOTER_SECTION_HTML_LENGTH)
        try:
            span = int(item.get('span') or 3)
        except (TypeError, ValueError):
            span = 3

        sections.append(
            {
                'id': section_id or f'footer-section-{index + 1}',
                'title': title,
                'html': html,
                'span': max(1, min(12, span)),
            }
        )

    return {
        'footer_builder_enabled': _coerce_bool(payload.get('enabled'), False),
        'footer_builder_sections': sections,
        'footer_builder_bottom_html': _trim_text(
            payload.get('bottom_html'),
            max_length=MAX_FOOTER_BOTTOM_HTML_LENGTH,
        ),
    }


def _extract_footer_builder_config(extra_json: Any) -> dict[str, Any]:
    payload = extra_json if isinstance(extra_json, dict) else {}
    return _normalize_footer_builder_values(payload.get(FOOTER_BUILDER_EXTRA_KEY))


def _normalize_footer_builder_input_values(values: Any) -> dict[str, Any]:
    payload = values if isinstance(values, dict) else {}
    return _normalize_footer_builder_values(
        {
            'enabled': payload.get('footer_builder_enabled', False),
            'sections': payload.get('footer_builder_sections', []),
            'bottom_html': payload.get('footer_builder_bottom_html', ''),
        }
    )


def _normalize_system_config_values(
    values: dict[str, Any] | None,
    *,
    footer_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_values = build_default_system_config_values()
    payload = values if isinstance(values, dict) else {}

    for field in SYSTEM_SETTINGS_FIELDS:
        default_value = normalized_values[field]
        raw_value = payload.get(field, default_value)

        if field in BOOLEAN_SYSTEM_SETTINGS_FIELDS:
            normalized_values[field] = _coerce_bool(raw_value, default_value)
            continue
        if field in INTEGER_SYSTEM_SETTINGS_FIELDS:
            normalized_values[field] = _coerce_int(raw_value, default_value)
            continue
        if field in FLOAT_SYSTEM_SETTINGS_FIELDS:
            normalized_values[field] = _coerce_float(raw_value, default_value)
            continue

        normalized_values[field] = _coerce_text(raw_value, default_value)

    normalized_footer_values = _normalize_footer_builder_input_values(
        footer_values if footer_values is not None else payload
    )
    normalized_values.update(normalized_footer_values)
    return normalized_values


def _serialize_footer_builder_config(values: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_footer_builder_input_values(values)
    return {
        'enabled': normalized['footer_builder_enabled'],
        'sections': normalized['footer_builder_sections'],
        'bottom_html': normalized['footer_builder_bottom_html'],
    }


def ensure_runtime_configuration_seeded() -> None:
    ensure_runtime_storage_tables()
    with Session(engine) as session:
        _ensure_singleton_row(
            session,
            SystemSettings,
            SYSTEM_SETTINGS_SINGLETON_ID,
            build_default_system_settings_values(),
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
                build_default_system_settings_values(),
            )
            values = _model_to_dict(record, SYSTEM_SETTINGS_FIELDS)
            footer_values = _extract_footer_builder_config(record.extra_json)
            return _normalize_system_config_values(values, footer_values=footer_values)
    except Exception as exc:
        logger.warning('Failed to load system settings from database, falling back to env defaults: %s', exc)
        return _normalize_system_config_values(build_default_system_config_values())


def get_public_system_config_values() -> dict[str, Any]:
    values = get_system_config_values()
    public_values = {field: values[field] for field in PUBLIC_SYSTEM_SETTINGS_FIELDS}
    for field in FOOTER_BUILDER_FIELDS:
        public_values[field] = values[field]
    return public_values


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
        logger.warning('Failed to load backup settings from database, falling back to defaults: %s', exc)
        return build_default_backup_settings_values()


def apply_system_config(values: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
    normalized_values = _normalize_system_config_values(values)
    ensure_runtime_configuration_seeded()
    with Session(engine) as session:
        record = _ensure_singleton_row(
            session,
            SystemSettings,
            SYSTEM_SETTINGS_SINGLETON_ID,
            build_default_system_settings_values(),
        )
        for field in SYSTEM_SETTINGS_FIELDS:
            setattr(record, field, normalized_values[field])

        extra_json = dict(record.extra_json) if isinstance(record.extra_json, dict) else {}
        extra_json[FOOTER_BUILDER_EXTRA_KEY] = _serialize_footer_builder_config(normalized_values)
        record.extra_json = extra_json
        record.updated_by = updated_by
        session.add(record)
        session.commit()
        session.refresh(record)

        updated_values = _model_to_dict(record, SYSTEM_SETTINGS_FIELDS)
        footer_values = _extract_footer_builder_config(record.extra_json)
        return _normalize_system_config_values(updated_values, footer_values=footer_values)


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
    return bool(get_system_config_values()['public_dashboard_enabled'])


def get_monitor_runtime_config() -> dict[str, Any]:
    values = get_system_config_values()
    return {
        'monitor_channel_refresh_interval_seconds': int(values['monitor_channel_refresh_interval_seconds']),
        'monitor_db_write_max_retries': int(values['monitor_db_write_max_retries']),
        'monitor_db_write_retry_delay_seconds': float(values['monitor_db_write_retry_delay_seconds']),
    }


def get_link_check_runtime_config() -> dict[str, Any]:
    values = get_system_config_values()
    return {
        'link_check_default_max_concurrent': int(values['link_check_default_max_concurrent']),
        'link_check_max_allowed_concurrent': int(values['link_check_max_allowed_concurrent']),
        'link_check_max_allowed_links': int(values['link_check_max_allowed_links']),
        'link_check_poll_interval_seconds': int(values['link_check_poll_interval_seconds']),
    }
