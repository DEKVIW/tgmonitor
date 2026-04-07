import threading
from datetime import datetime

from sqlalchemy import ARRAY, JSON, Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

from app.models.config import settings

Base = declarative_base()


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    title = Column(String)
    description = Column(String)
    links = Column(JSON)
    tags = Column(ARRAY(String))
    source = Column(String)
    channel = Column(String)
    group_name = Column(String)
    bot = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    netdisk_types = Column(JSONB, default=list)


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(String, nullable=False)
    api_hash = Column(String, nullable=False)


class DedupStats(Base):
    __tablename__ = "dedup_stats"

    id = Column(Integer, primary_key=True)
    run_time = Column(DateTime, nullable=False)
    inserted = Column(Integer, nullable=False)
    deleted = Column(Integer, nullable=False)


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    parser_profile = Column(String, nullable=True)


class LinkCheckStats(Base):
    __tablename__ = "link_check_stats"

    id = Column(Integer, primary_key=True, index=True)
    check_time = Column(DateTime, nullable=False, index=True)
    total_messages = Column(Integer, nullable=False)
    total_links = Column(Integer, nullable=False)
    valid_links = Column(Integer, nullable=False)
    invalid_links = Column(Integer, nullable=False)
    deleted_messages = Column(Integer, default=0)
    updated_messages = Column(Integer, default=0)
    netdisk_stats = Column(JSON)
    check_duration = Column(Float)
    status = Column(String(50), default="completed")
    created_at = Column(DateTime, default=datetime.utcnow)


class LinkCheckDetails(Base):
    __tablename__ = "link_check_details"

    id = Column(Integer, primary_key=True, index=True)
    check_time = Column(DateTime, nullable=False, index=True)
    message_id = Column(Integer, nullable=False, index=True)
    netdisk_type = Column(String(50), index=True)
    url = Column(Text)
    is_valid = Column(Boolean, nullable=False)
    response_time = Column(Float)
    error_reason = Column(String(200))
    action_taken = Column(String(50), default="none")
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    site_name = Column(String(255), nullable=False, default="TG\u9891\u9053\u76d1\u63a7")
    site_title = Column(String(255), nullable=False, default="TG\u9891\u9053\u76d1\u63a7")
    site_description = Column(Text, nullable=False, default="Telegram \u9891\u9053\u7f51\u76d8\u8d44\u6e90\u76d1\u63a7\u4e0e\u68c0\u7d22")
    site_keywords = Column(Text, nullable=False, default="telegram,\u7f51\u76d8,\u9891\u9053\u76d1\u63a7,\u8d44\u6e90\u641c\u7d22")
    brand_icon = Column(String(32), nullable=False, default="\U0001F4F1")
    site_favicon_url = Column(Text, nullable=False, default="/favicon.svg")
    public_dashboard_enabled = Column(Boolean, nullable=False, default=False)
    public_ads_enabled = Column(Boolean, nullable=False, default=False)
    public_feed_top_ad_html_desktop = Column(Text, nullable=False, default="")
    public_feed_top_ad_html_mobile = Column(Text, nullable=False, default="")
    public_feed_inline_ad_html_desktop = Column(Text, nullable=False, default="")
    public_feed_inline_ad_html_mobile = Column(Text, nullable=False, default="")
    public_feed_inline_every_n = Column(Integer, nullable=False, default=8)
    umami_enabled = Column(Boolean, nullable=False, default=False)
    umami_script_url = Column(Text, nullable=False, default="")
    umami_website_id = Column(String(255), nullable=False, default="")
    umami_host_url = Column(Text, nullable=False, default="")
    umami_share_url = Column(Text, nullable=False, default="")
    link_check_default_max_concurrent = Column(Integer, nullable=False, default=5)
    link_check_max_allowed_concurrent = Column(Integer, nullable=False, default=10)
    link_check_max_allowed_links = Column(Integer, nullable=False, default=1000)
    link_check_poll_interval_seconds = Column(Integer, nullable=False, default=2)
    monitor_channel_refresh_interval_seconds = Column(Integer, nullable=False, default=60)
    monitor_db_write_max_retries = Column(Integer, nullable=False, default=3)
    monitor_db_write_retry_delay_seconds = Column(Float, nullable=False, default=1.0)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class BackupSettings(Base):
    __tablename__ = "backup_settings"

    id = Column(Integer, primary_key=True)
    backup_enabled = Column(Boolean, nullable=False, default=False)
    local_backup_enabled = Column(Boolean, nullable=False, default=True)
    local_backup_dir = Column(Text, nullable=False, default="data/backups")
    local_keep_count = Column(Integer, nullable=False, default=14)
    local_keep_days = Column(Integer, nullable=False, default=30)
    webdav_enabled = Column(Boolean, nullable=False, default=False)
    webdav_base_url = Column(Text, nullable=False, default="")
    webdav_username = Column(String(255), nullable=False, default="")
    webdav_password_encrypted = Column(Text, nullable=False, default="")
    webdav_root_path = Column(Text, nullable=False, default="")
    webdav_timeout_seconds = Column(Integer, nullable=False, default=60)
    webdav_verify_ssl = Column(Boolean, nullable=False, default=True)
    schedule_enabled = Column(Boolean, nullable=False, default=False)
    schedule_kind = Column(String(32), nullable=False, default="manual")
    schedule_value = Column(String(255), nullable=False, default="")
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    archive_format = Column(String(32), nullable=False, default="tar.gz")
    compress_level = Column(Integer, nullable=False, default=6)
    include_database = Column(Boolean, nullable=False, default=True)
    include_users_json = Column(Boolean, nullable=False, default=True)
    include_env_file = Column(Boolean, nullable=False, default=False)
    include_runtime_data = Column(Boolean, nullable=False, default=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(32), nullable=False, default="manual")
    trigger_source = Column(String(32), nullable=False, default="manual")
    status = Column(String(32), nullable=False, default="pending", index=True)
    target_scope = Column(String(64), nullable=False, default="local")
    archive_name = Column(String(255), nullable=True)
    archive_format = Column(String(32), nullable=False, default="tar.gz")
    file_size_bytes = Column(Float, nullable=True)
    sha256 = Column(String(128), nullable=True)
    local_path = Column(Text, nullable=True)
    webdav_path = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    created_by = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)
    result_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class BackupTarget(Base):
    __tablename__ = "backup_targets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    target_kind = Column(String(32), nullable=False, default="local", index=True)
    provider = Column(String(64), nullable=False, default="local")
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    backup_mode = Column(String(32), nullable=False, default="full", index=True)
    schedule_enabled = Column(Boolean, nullable=False, default=False)
    schedule_kind = Column(String(32), nullable=False, default="manual")
    schedule_hour = Column(Integer, nullable=False, default=3)
    schedule_minute = Column(Integer, nullable=False, default=0)
    schedule_weekday = Column(Integer, nullable=True)
    schedule_day = Column(Integer, nullable=True)
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    retention_count = Column(Integer, nullable=False, default=10)
    retention_days = Column(Integer, nullable=False, default=30)
    run_log_retention_days = Column(Integer, nullable=False, default=0)
    local_dir = Column(Text, nullable=False, default="")
    webdav_base_url = Column(Text, nullable=False, default="")
    webdav_username = Column(String(255), nullable=False, default="")
    webdav_password_encrypted = Column(Text, nullable=False, default="")
    webdav_root_path = Column(Text, nullable=False, default="")
    webdav_timeout_seconds = Column(Integer, nullable=False, default=60)
    webdav_verify_ssl = Column(Boolean, nullable=False, default=True)
    include_database = Column(Boolean, nullable=False, default=True)
    include_users_json = Column(Boolean, nullable=False, default=True)
    include_env_file = Column(Boolean, nullable=False, default=False)
    include_runtime_data = Column(Boolean, nullable=False, default=True)
    export_range_kind = Column(String(16), nullable=False, default="all")
    export_range_days = Column(Integer, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    last_status = Column(String(32), nullable=True)
    last_error_message = Column(Text, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class BackupRun(Base):
    __tablename__ = "backup_runs"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, nullable=True, index=True)
    target_name = Column(String(255), nullable=False, default="")
    target_kind = Column(String(32), nullable=False, default="local")
    provider = Column(String(64), nullable=False, default="local")
    backup_mode = Column(String(32), nullable=False, default="full")
    trigger_source = Column(String(32), nullable=False, default="manual")
    status = Column(String(32), nullable=False, default="pending", index=True)
    file_name = Column(String(255), nullable=True)
    file_format = Column(String(32), nullable=True)
    file_size_bytes = Column(Float, nullable=True)
    sha256 = Column(String(128), nullable=True)
    local_path = Column(Text, nullable=True)
    remote_path = Column(Text, nullable=True)
    remote_url = Column(Text, nullable=True)
    item_count = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    created_by = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)
    result_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"options": "-c timezone=Asia/Shanghai"},
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo=False,
    pool_reset_on_return="commit",
)

_channel_schema_lock = threading.RLock()
_channel_schema_checked = False
_runtime_storage_lock = threading.RLock()
_runtime_storage_checked = False


def create_tables():
    Base.metadata.create_all(bind=engine)
    ensure_channel_parser_profile_column()
    ensure_runtime_storage_tables()


def ensure_channel_parser_profile_column() -> None:
    global _channel_schema_checked
    if _channel_schema_checked:
        return

    with _channel_schema_lock:
        if _channel_schema_checked:
            return

        inspector = inspect(engine)
        try:
            columns = {column["name"] for column in inspector.get_columns("channels")}
        except Exception:
            columns = set()

        if "parser_profile" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE channels ADD COLUMN parser_profile VARCHAR"))

        _channel_schema_checked = True


def ensure_runtime_storage_tables() -> None:
    global _runtime_storage_checked
    if _runtime_storage_checked:
        return

    with _runtime_storage_lock:
        if _runtime_storage_checked:
            return

        Base.metadata.create_all(
            bind=engine,
            tables=[
                SystemSettings.__table__,
                BackupSettings.__table__,
                BackupRecord.__table__,
                BackupTarget.__table__,
                BackupRun.__table__,
            ],
        )
        _ensure_system_settings_columns()
        _ensure_backup_target_columns()
        _ensure_backup_management_indexes()
        _runtime_storage_checked = True


def _ensure_system_settings_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("system_settings")}
    except Exception:
        columns = set()

    if not columns:
        return

    pending_alters = {
        "site_name": "ALTER TABLE system_settings ADD COLUMN site_name VARCHAR(255) NOT NULL DEFAULT 'TG棰戦亾鐩戞帶'",
        "site_title": "ALTER TABLE system_settings ADD COLUMN site_title VARCHAR(255) NOT NULL DEFAULT 'TG棰戦亾鐩戞帶'",
        "site_description": "ALTER TABLE system_settings ADD COLUMN site_description TEXT NOT NULL DEFAULT 'Telegram 棰戦亾缃戠洏璧勬簮鐩戞帶涓庢绱?",
        "site_keywords": "ALTER TABLE system_settings ADD COLUMN site_keywords TEXT NOT NULL DEFAULT 'telegram,缃戠洏,棰戦亾鐩戞帶,璧勬簮鎼滅储'",
        "brand_icon": "ALTER TABLE system_settings ADD COLUMN brand_icon VARCHAR(32) NOT NULL DEFAULT '馃摫'",
        "site_favicon_url": "ALTER TABLE system_settings ADD COLUMN site_favicon_url TEXT NOT NULL DEFAULT '/favicon.svg'",
    }
    with engine.begin() as connection:
        for column_name, sql in pending_alters.items():
            if column_name in columns:
                continue
            connection.execute(text(sql))


def _ensure_backup_target_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("backup_targets")}
    except Exception:
        columns = set()

    if not columns:
        return

    pending_alters = {
        "run_log_retention_days": "ALTER TABLE backup_targets ADD COLUMN run_log_retention_days INTEGER NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        for column_name, sql in pending_alters.items():
            if column_name in columns:
                continue
            connection.execute(text(sql))


def _ensure_backup_management_indexes() -> None:
    statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_backup_targets_enabled_next_run
        ON backup_targets (is_enabled, next_run_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_backup_runs_target_started_at
        ON backup_runs (target_id, started_at DESC)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_backup_runs_active_target
        ON backup_runs (target_id)
        WHERE target_id IS NOT NULL AND status IN ('pending', 'running')
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

