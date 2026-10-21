import threading
from datetime import datetime
import logging

from sqlalchemy import ARRAY, JSON, BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

from app.models.config import settings

Base = declarative_base()
logger = logging.getLogger(__name__)


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
    monitor_channel_config_id = Column(Integer, ForeignKey("channels.id"), nullable=True, index=True)
    monitor_chat_id = Column(BigInteger, nullable=True, index=True)
    monitor_channel_key = Column(String(255), nullable=True, index=True)
    monitor_channel_title = Column(String(255), nullable=True)
    monitor_message_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    netdisk_types = Column(JSONB, default=list)


class LinkTarget(Base):
    __tablename__ = "link_targets"
    __table_args__ = (
        UniqueConstraint("platform", "normalized_url_hash", name="ux_link_targets_platform_normalized_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(64), nullable=False, index=True)
    original_url = Column(Text, nullable=False)
    normalized_url = Column(Text, nullable=False)
    normalized_url_hash = Column(String(64), nullable=False, index=True)
    share_key = Column(String(255), nullable=True, index=True)
    passcode = Column(String(64), nullable=True)
    share_title = Column(String(255), nullable=True)
    file_count = Column(Integer, nullable=True)
    total_size_bytes = Column(Float, nullable=True)
    author_name_masked = Column(String(255), nullable=True)
    author_platform_id = Column(String(255), nullable=True, index=True)
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MessageLinkRef(Base):
    __tablename__ = "message_link_refs"
    __table_args__ = (
        UniqueConstraint("message_id", "link_index", name="ux_message_link_refs_message_index"),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    link_index = Column(Integer, nullable=False)
    provider_label = Column(String(64), nullable=False)
    link_label = Column(String(255), nullable=True)
    display_text = Column(String(255), nullable=False)
    target_url = Column(Text, nullable=False)
    channel = Column(String(255), nullable=True)
    source = Column(String(255), nullable=True)
    message_timestamp = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LinkClickEvent(Base):
    __tablename__ = "link_click_events"
    __table_args__ = (
        UniqueConstraint("event_token", name="ux_link_click_events_event_token"),
    )

    id = Column(Integer, primary_key=True, index=True)
    event_token = Column(String(64), nullable=True, index=True)
    link_ref_id = Column(Integer, ForeignKey("message_link_refs.id"), nullable=False, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=True, index=True)
    clicked_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    stat_date = Column(Date, nullable=False, index=True)
    source_page = Column(String(64), nullable=True)
    search_query = Column(String(255), nullable=True)
    session_key = Column(String(128), nullable=True, index=True)
    ip_hash = Column(String(128), nullable=True)
    ua_hash = Column(String(128), nullable=True)
    is_logged_in = Column(Boolean, nullable=False, default=False)
    redirect_confirmed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LinkTargetDailyStat(Base):
    __tablename__ = "link_target_daily_stats"
    __table_args__ = (
        UniqueConstraint("stat_date", "link_target_id", name="ux_link_target_daily_stats_date_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    stat_date = Column(Date, nullable=False, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    click_count = Column(Integer, nullable=False, default=0)
    unique_sessions = Column(Integer, nullable=False, default=0)
    unique_users = Column(Integer, nullable=False, default=0)
    search_click_count = Column(Integer, nullable=False, default=0)
    logged_in_click_count = Column(Integer, nullable=False, default=0)
    last_clicked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChannelDailyStat(Base):
    __tablename__ = "channel_daily_stats"
    __table_args__ = (
        UniqueConstraint("stat_date", "monitor_channel_key", name="ux_channel_daily_stats_date_channel_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    stat_date = Column(Date, nullable=False, index=True)
    monitor_channel_config_id = Column(Integer, ForeignKey("channels.id"), nullable=True, index=True)
    monitor_channel_key = Column(String(255), nullable=False, index=True)
    monitor_channel_title = Column(String(255), nullable=False, default="")
    message_count = Column(Integer, nullable=False, default=0)
    link_count = Column(Integer, nullable=False, default=0)
    last_message_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceCandidateProfile(Base):
    __tablename__ = "resource_candidate_profiles"
    __table_args__ = (
        UniqueConstraint("link_target_id", name="ux_resource_candidate_profiles_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    operation_status = Column(String(32), nullable=False, default="pending_review", index=True)
    value_status = Column(String(32), nullable=False, default="unreviewed", index=True)
    manual_resource_kind = Column(String(32), nullable=True, index=True)
    note = Column(Text, nullable=False, default="")
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class ResourceCandidateLog(Base):
    __tablename__ = "resource_candidate_logs"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("resource_candidate_profiles.id"), nullable=False, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    action_type = Column(String(32), nullable=False, default="profile_updated", index=True)
    action_summary = Column(String(255), nullable=False, default="")
    note = Column(Text, nullable=False, default="")
    payload = Column(JSONB, nullable=False, default=dict)
    operator = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class ResourceWork(Base):
    __tablename__ = "resource_works"
    __table_args__ = (
        UniqueConstraint("provider", "provider_work_id", name="ux_resource_works_provider_work_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(32), nullable=False, index=True)
    provider_work_id = Column(String(128), nullable=False, index=True)
    media_type = Column(String(32), nullable=True, index=True)
    canonical_title = Column(String(255), nullable=False, index=True)
    original_title = Column(String(255), nullable=True)
    release_year = Column(Integer, nullable=True, index=True)
    poster_url = Column(Text, nullable=True)
    detail_url = Column(Text, nullable=True)
    popularity = Column(Float, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceWorkAlias(Base):
    __tablename__ = "resource_work_aliases"
    __table_args__ = (
        UniqueConstraint("work_id", "normalized_alias", name="ux_resource_work_aliases_work_normalized_alias"),
    )

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, ForeignKey("resource_works.id"), nullable=False, index=True)
    alias = Column(String(255), nullable=False)
    normalized_alias = Column(String(255), nullable=False, index=True)
    source = Column(String(32), nullable=False, default="provider", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ResourceWorkBinding(Base):
    __tablename__ = "resource_work_bindings"
    __table_args__ = (
        UniqueConstraint("link_target_id", name="ux_resource_work_bindings_link_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    work_id = Column(Integer, ForeignKey("resource_works.id"), nullable=True, index=True)
    match_status = Column(String(32), nullable=False, default="pending", index=True)
    provider = Column(String(32), nullable=True, index=True)
    provider_work_id = Column(String(128), nullable=True, index=True)
    confidence = Column(Float, nullable=False, default=0.0, server_default=text("0"))
    match_source = Column(String(32), nullable=False, default="pending", index=True)
    query_title = Column(String(255), nullable=True)
    candidate_title = Column(String(255), nullable=True)
    reason = Column(String(255), nullable=False, default="")
    last_attempted_at = Column(DateTime, nullable=True, index=True)
    matched_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceRecognitionTask(Base):
    __tablename__ = "resource_recognition_tasks"
    __table_args__ = (
        UniqueConstraint("link_target_id", name="ux_resource_recognition_tasks_link_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    source = Column(String(32), nullable=False, default="manual", index=True)
    priority = Column(Integer, nullable=False, default=100, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    locked_by = Column(String(128), nullable=True, index=True)
    locked_at = Column(DateTime, nullable=True, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    last_title = Column(String(255), nullable=True)
    last_result_title = Column(String(255), nullable=True)
    last_enqueued_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_processed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PanTransferAccount(Base):
    __tablename__ = "pan_transfer_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "account_name", name="ux_pan_transfer_accounts_platform_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(64), nullable=False, index=True)
    account_name = Column(String(128), nullable=False)
    auth_type = Column(String(32), nullable=False, default="cookie")
    credential_encrypted = Column(Text, nullable=False, default="")
    default_save_root = Column(String(255), nullable=False, default="")
    default_share_mode = Column(String(32), nullable=False, default="public")
    default_share_passcode = Column(String(32), nullable=True)
    default_share_expire_days = Column(Integer, nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    is_default = Column(Boolean, nullable=False, default=False, index=True)
    last_validated_at = Column(DateTime, nullable=True, index=True)
    last_error_message = Column(Text, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningChannelConfig(Base):
    __tablename__ = "learning_channel_configs"
    __table_args__ = (
        UniqueConstraint("channel_key", name="ux_learning_channel_configs_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    channel_key = Column(String(255), nullable=False, index=True)
    channel_title = Column(String(255), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=False, index=True)
    target_account_id = Column(Integer, ForeignKey("pan_transfer_accounts.id"), nullable=True, index=True)
    save_root = Column(String(255), nullable=False, default="")
    default_category_id = Column(Integer, nullable=True, index=True)
    parser_profile = Column(String(64), nullable=True)
    backfill_policy = Column(String(32), nullable=False, default="new_messages_only")
    transfer_policy = Column(String(32), nullable=False, default="quark_only")
    auto_create_category_dirs = Column(Boolean, nullable=False, default=True)
    last_processed_message_id = Column(Integer, nullable=True, index=True)
    last_success_at = Column(DateTime, nullable=True, index=True)
    last_error_message = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceAutomationTask(Base):
    __tablename__ = "learning_resource_automation_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=False, index=True)
    transfer_policy = Column(String(32), nullable=False, default="automatic")
    backfill_policy = Column(String(32), nullable=False, default="new_messages_only")
    status = Column(String(32), nullable=False, default="paused", index=True)
    legacy_config_id = Column(Integer, nullable=True, unique=True, index=True)
    last_enqueued_at = Column(DateTime, nullable=True, index=True)
    last_success_at = Column(DateTime, nullable=True, index=True)
    pending_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    last_error_message = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceAutomationTaskChannel(Base):
    __tablename__ = "learning_resource_automation_task_channels"
    __table_args__ = (
        UniqueConstraint("task_id", "channel_id", name="ux_learning_resource_task_channels_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("learning_resource_automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    default_category_id = Column(Integer, ForeignKey("learning_resource_categories.id"), nullable=True, index=True)
    parser_profile = Column(String(64), nullable=True)
    last_processed_message_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceAutomationTaskTarget(Base):
    __tablename__ = "learning_resource_automation_task_targets"
    __table_args__ = (
        UniqueConstraint("task_id", "target_account_id", "save_root_id", name="ux_learning_resource_task_targets_scope"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("learning_resource_automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    target_account_id = Column(Integer, ForeignKey("pan_transfer_accounts.id"), nullable=False, index=True)
    save_root_id = Column(String(255), nullable=False, default="0")
    save_root_name = Column(String(255), nullable=False, default="")
    auto_create_category_dirs = Column(Boolean, nullable=False, default=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    status = Column(String(32), nullable=False, default="ready", index=True)
    last_success_at = Column(DateTime, nullable=True, index=True)
    last_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceProcessLog(Base):
    __tablename__ = "learning_resource_process_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("learning_resource_automation_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True, index=True)
    target_id = Column(Integer, ForeignKey("learning_resource_automation_task_targets.id", ondelete="SET NULL"), nullable=True, index=True)
    resource_id = Column(Integer, ForeignKey("learning_resource_items.id", ondelete="SET NULL"), nullable=True, index=True)
    transfer_job_id = Column(Integer, ForeignKey("learning_resource_transfer_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    import_job_id = Column(Integer, ForeignKey("learning_resource_import_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    stage = Column(String(32), nullable=False, index=True)
    level = Column(String(16), nullable=False, default="info", index=True)
    message = Column(String(2000), nullable=False, default="")
    details_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class LearningResourceCategory(Base):
    __tablename__ = "learning_resource_categories"
    __table_args__ = (
        UniqueConstraint("slug", name="ux_learning_resource_categories_slug"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(160), nullable=False, index=True)
    directory_name = Column(String(255), nullable=False)
    directory_id = Column(String(255), nullable=True)
    directory_status = Column(String(32), nullable=False, default="pending", index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    show_in_tabs = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    created_by = Column(String(128), nullable=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceItem(Base):
    __tablename__ = "learning_resource_items"
    __table_args__ = (
        UniqueConstraint(
            "source_channel_key",
            "normalized_title",
            name="ux_learning_resource_items_channel_title",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    display_title = Column(String(255), nullable=False, index=True)
    normalized_title = Column(String(255), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    primary_category_id = Column(Integer, ForeignKey("learning_resource_categories.id"), nullable=True, index=True)
    source_channel_key = Column(String(255), nullable=False, index=True)
    first_source_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    latest_source_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    latest_source_at = Column(DateTime, nullable=True, index=True)
    last_published_at = Column(DateTime, nullable=True, index=True)
    tags = Column(ARRAY(String), nullable=False, default=list)
    classification_source = Column(String(32), nullable=False, default="rule", index=True)
    classification_confidence = Column(String(32), nullable=False, default="medium")
    created_by = Column(String(128), nullable=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceItemCategory(Base):
    __tablename__ = "learning_resource_item_categories"
    __table_args__ = (
        UniqueConstraint("resource_id", "category_id", name="ux_learning_resource_item_categories_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("learning_resource_items.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("learning_resource_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class LearningResourceLink(Base):
    __tablename__ = "learning_resource_links"
    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "url_fingerprint",
            "target_account_id",
            name="ux_learning_resource_links_resource_fingerprint_target",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("learning_resource_items.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(64), nullable=False, index=True)
    source_url = Column(Text, nullable=False)
    share_url = Column(Text, nullable=True)
    url_fingerprint = Column(String(64), nullable=False, index=True)
    target_account_id = Column(Integer, ForeignKey("pan_transfer_accounts.id"), nullable=True, index=True)
    source_link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=True, index=True)
    is_primary = Column(Boolean, nullable=False, default=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    last_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceTransferJob(Base):
    __tablename__ = "learning_resource_transfer_jobs"
    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "source_link_target_id",
            "target_account_id",
            name="ux_learning_resource_transfer_jobs_resource_source_target",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("learning_resource_automation_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    resource_id = Column(Integer, ForeignKey("learning_resource_items.id", ondelete="CASCADE"), nullable=False, index=True)
    source_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    source_link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    target_account_id = Column(Integer, ForeignKey("pan_transfer_accounts.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("pan_transfer_batches.id"), nullable=True, index=True)
    batch_item_id = Column(Integer, ForeignKey("pan_transfer_batch_items.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("learning_resource_categories.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    last_error_message = Column(Text, nullable=True)
    supersedes_job_id = Column(Integer, ForeignKey("learning_resource_transfer_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningResourceImportJob(Base):
    __tablename__ = "learning_resource_import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="preview", index=True)
    preview_json = Column(JSONB, nullable=False, default=dict)
    summary_json = Column(JSONB, nullable=False, default=dict)
    row_count = Column(Integer, nullable=False, default=0)
    valid_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    created_by = Column(String(128), nullable=True)
    confirmed_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PanTransferBatch(Base):
    __tablename__ = "pan_transfer_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_type = Column(String(32), nullable=False, default="manual", index=True)
    source_scope = Column(String(32), nullable=False, default="message_selection", index=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    created_by = Column(String(128), nullable=True, index=True)
    total_message_count = Column(Integer, nullable=False, default=0)
    total_link_target_count = Column(Integer, nullable=False, default=0)
    success_item_count = Column(Integer, nullable=False, default=0)
    failed_item_count = Column(Integer, nullable=False, default=0)
    retry_delay_seconds = Column(Integer, nullable=False, default=600)
    request_json = Column(JSONB, nullable=False, default=dict)
    result_json = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PanTransferBatchItem(Base):
    __tablename__ = "pan_transfer_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "link_target_id", name="ux_pan_transfer_batch_items_batch_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("pan_transfer_batches.id"), nullable=False, index=True)
    link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    target_account_id = Column(Integer, ForeignKey("pan_transfer_accounts.id"), nullable=True, index=True)
    platform = Column(String(64), nullable=False, index=True)
    short_title = Column(String(255), nullable=False, default="")
    original_url = Column(Text, nullable=False)
    source_message_count = Column(Integer, nullable=False, default=0)
    source_ref_count = Column(Integer, nullable=False, default=0)
    latest_message_title = Column(String(255), nullable=True)
    latest_message_time = Column(DateTime, nullable=True, index=True)
    latest_link_health = Column(String(32), nullable=False, default="unknown", index=True)
    transfer_status = Column(String(32), nullable=False, default="queued", index=True)
    share_status = Column(String(32), nullable=False, default="pending", index=True)
    validation_status = Column(String(32), nullable=False, default="pending", index=True)
    replacement_status = Column(String(32), nullable=False, default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    locked_by = Column(String(128), nullable=True, index=True)
    locked_at = Column(DateTime, nullable=True, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_validated_at = Column(DateTime, nullable=True)
    new_share_url = Column(Text, nullable=True)
    new_link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PanTransferReplacementLog(Base):
    __tablename__ = "pan_transfer_replacement_logs"

    id = Column(Integer, primary_key=True, index=True)
    batch_item_id = Column(Integer, ForeignKey("pan_transfer_batch_items.id"), nullable=False, index=True)
    old_link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=False, index=True)
    new_link_target_id = Column(Integer, ForeignKey("link_targets.id"), nullable=True, index=True)
    old_url = Column(Text, nullable=False)
    new_url = Column(Text, nullable=True)
    affected_message_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending", index=True)
    operator = Column(String(128), nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class PanTransferExecutionLog(Base):
    __tablename__ = "pan_transfer_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("pan_transfer_batches.id"), nullable=False, index=True)
    batch_item_id = Column(Integer, ForeignKey("pan_transfer_batch_items.id"), nullable=False, index=True)
    level = Column(String(16), nullable=False, default="info", index=True)
    stage = Column(String(32), nullable=False, default="general", index=True)
    message = Column(Text, nullable=False, default="")
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class PanTransferPublishRecord(Base):
    __tablename__ = "pan_transfer_publish_records"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(32), nullable=False, default="batch_item", index=True)
    source_batch_id = Column(Integer, nullable=True, index=True)
    source_batch_item_id = Column(Integer, nullable=True, index=True)
    source_link_target_id = Column(Integer, nullable=True, index=True)
    source_new_link_target_id = Column(Integer, nullable=True, index=True)
    platform = Column(String(64), nullable=False, default="", index=True)
    source_url = Column(Text, nullable=False)
    published_message_id = Column(Integer, nullable=True, index=True)
    published_title = Column(String(255), nullable=False, default="")
    published_description = Column(Text, nullable=True)
    published_tags = Column(JSONB, nullable=False, default=list)
    operator = Column(String(128), nullable=True, index=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    published_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PanTransferSyncTask(Base):
    __tablename__ = "pan_transfer_sync_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_name = Column(String(255), nullable=False, default="")
    status = Column(String(32), nullable=False, default="active", index=True)
    task_state = Column(String(32), nullable=False, default="idle", index=True)
    platform = Column(String(64), nullable=False, default="", index=True)
    source_batch_id = Column(Integer, nullable=True, index=True)
    source_batch_item_id = Column(Integer, nullable=True, index=True)
    source_link_target_id = Column(Integer, nullable=True, index=True)
    source_url = Column(Text, nullable=False)
    source_share_key = Column(String(255), nullable=True, index=True)
    topic_key = Column(String(160), nullable=False, default="", index=True)
    topic_title = Column(String(255), nullable=False, default="")
    work_id = Column(Integer, nullable=True, index=True)
    work_title = Column(String(255), nullable=True)
    publish_record_id = Column(Integer, nullable=True, index=True)
    target_account_id = Column(Integer, nullable=True, index=True)
    target_account_name = Column(String(128), nullable=True)
    fixed_save_path = Column(String(512), nullable=False, default="")
    transfer_layout = Column(String(32), nullable=False, default="independent")
    batch_folder_name = Column(String(120), nullable=True)
    item_folder_mode = Column(String(32), nullable=False, default="auto")
    item_folder_template = Column(String(120), nullable=True)
    share_target_mode = Column(String(32), nullable=False, default="resource_dir")
    current_share_url = Column(Text, nullable=True)
    current_share_link_target_id = Column(Integer, nullable=True, index=True)
    source_link_status = Column(String(32), nullable=False, default="unknown", index=True)
    current_share_status = Column(String(32), nullable=False, default="unknown", index=True)
    last_change_type = Column(String(32), nullable=True, index=True)
    last_candidate_link_target_id = Column(Integer, nullable=True, index=True)
    last_candidate_url = Column(Text, nullable=True)
    last_candidate_title = Column(String(255), nullable=True)
    last_candidate_message_time = Column(DateTime, nullable=True, index=True)
    check_interval_minutes = Column(Integer, nullable=False, default=180)
    last_checked_at = Column(DateTime, nullable=True, index=True)
    next_check_at = Column(DateTime, nullable=True, index=True)
    locked_by = Column(String(128), nullable=True, index=True)
    locked_at = Column(DateTime, nullable=True, index=True)
    last_error_message = Column(Text, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_by = Column(String(128), nullable=True, index=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PanTransferSyncTaskLog(Base):
    __tablename__ = "pan_transfer_sync_task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("pan_transfer_sync_tasks.id"), nullable=False, index=True)
    level = Column(String(16), nullable=False, default="info", index=True)
    stage = Column(String(32), nullable=False, default="general", index=True)
    message = Column(Text, nullable=False, default="")
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class PanTransferFollowTriggerEvent(Base):
    __tablename__ = "pan_transfer_follow_trigger_events"
    __table_args__ = (
        UniqueConstraint("message_id", "event_type", name="ux_pan_transfer_follow_trigger_message_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, default="message_link_received", index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    candidate_title = Column(String(255), nullable=True)
    candidate_episode = Column(Integer, nullable=True, index=True)
    candidate_issue_no = Column(String(32), nullable=True)
    monitor_channel_key = Column(String(255), nullable=True, index=True)
    monitor_chat_id = Column(BigInteger, nullable=True, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    processed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AiProviderConfig(Base):
    __tablename__ = "ai_provider_configs"
    __table_args__ = (
        UniqueConstraint("provider_key", name="ux_ai_provider_configs_provider_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider_key = Column(String(64), nullable=False, index=True)
    display_name = Column(String(128), nullable=False, default="")
    provider_type = Column(String(32), nullable=False, default="openai_compatible", index=True)
    base_url = Column(Text, nullable=False, default="")
    api_key_encrypted = Column(Text, nullable=False, default="")
    api_mode = Column(String(32), nullable=False, default="auto")
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    is_default = Column(Boolean, nullable=False, default=False, index=True)
    priority = Column(Integer, nullable=False, default=100, index=True)
    timeout_seconds = Column(Integer, nullable=False, default=25)
    max_retries = Column(Integer, nullable=False, default=1)
    cooldown_seconds = Column(Integer, nullable=False, default=300)
    cooldown_until = Column(DateTime, nullable=True, index=True)
    health_status = Column(String(32), nullable=False, default="unknown", index=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_checked_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    last_error_message = Column(Text, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class MediaWallCategory(Base):
    __tablename__ = "media_wall_categories"
    __table_args__ = (
        UniqueConstraint("slug", name="ux_media_wall_categories_slug"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(160), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    show_in_tabs = Column(Boolean, nullable=False, default=True, index=True)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    created_by = Column(String(128), nullable=True, index=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MediaWallItem(Base):
    __tablename__ = "media_wall_items"

    id = Column(Integer, primary_key=True, index=True)
    display_title = Column(String(255), nullable=False, index=True)
    metadata_query_title = Column(String(255), nullable=False, index=True)
    visibility = Column(String(32), nullable=False, default="public", index=True)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    sync_task_id = Column(Integer, ForeignKey("pan_transfer_sync_tasks.id"), nullable=True, index=True)
    custom_poster_url = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    metadata_status = Column(String(32), nullable=False, default="not_synced", index=True)
    metadata_last_synced_at = Column(DateTime, nullable=True)
    metadata_last_error = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=True, index=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MediaWallItemCategory(Base):
    __tablename__ = "media_wall_item_categories"
    __table_args__ = (
        UniqueConstraint("item_id", "category_id", name="ux_media_wall_item_categories_item_category"),
    )

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("media_wall_items.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("media_wall_categories.id"), nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class MediaWallLink(Base):
    __tablename__ = "media_wall_links"
    __table_args__ = (
        UniqueConstraint("item_id", "url_fingerprint", name="ux_media_wall_links_item_url"),
    )

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("media_wall_items.id"), nullable=False, index=True)
    platform = Column(String(64), nullable=False, index=True)
    url = Column(Text, nullable=False)
    url_fingerprint = Column(String(64), nullable=False, index=True)
    label = Column(String(120), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    source_type = Column(String(32), nullable=False, default="manual", index=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_status = Column(String(32), nullable=False, default="unknown", index=True)
    invalid_streak = Column(Integer, nullable=False, default=0)
    next_check_at = Column(DateTime, nullable=True, index=True)
    last_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MediaWallSourceConfig(Base):
    __tablename__ = "media_wall_source_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    source_url = Column(Text, nullable=False)
    source_type = Column(String(32), nullable=False, default="source-list")
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    priority = Column(Integer, nullable=False, default=100, index=True)
    timeout_seconds = Column(Integer, nullable=False, default=8)
    last_checked_at = Column(DateTime, nullable=True)
    last_refreshed_at = Column(DateTime, nullable=True)
    last_error_message = Column(Text, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MediaWallImportJob(Base):
    __tablename__ = "media_wall_import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="preview", index=True)
    preview_json = Column(JSONB, nullable=False, default=dict)
    summary_json = Column(JSONB, nullable=False, default=dict)
    created_by = Column(String(128), nullable=True, index=True)
    confirmed_by = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class AiProviderModel(Base):
    __tablename__ = "ai_provider_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="ux_ai_provider_models_provider_model"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("ai_provider_configs.id"), nullable=False, index=True)
    model_id = Column(String(255), nullable=False, index=True)
    label = Column(String(255), nullable=False, default="")
    owned_by = Column(String(255), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    is_preferred = Column(Boolean, nullable=False, default=False, index=True)
    last_refreshed_at = Column(DateTime, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AiRouteProfile(Base):
    __tablename__ = "ai_route_profiles"
    __table_args__ = (
        UniqueConstraint("route_key", name="ux_ai_route_profiles_route_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    route_key = Column(String(128), nullable=False, index=True)
    display_name = Column(String(128), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    output_mode = Column(String(32), nullable=False, default="text")
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    max_attempts = Column(Integer, nullable=False, default=3)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class AiRouteStep(Base):
    __tablename__ = "ai_route_steps"
    __table_args__ = (
        UniqueConstraint("route_profile_id", "step_index", name="ux_ai_route_steps_profile_index"),
    )

    id = Column(Integer, primary_key=True, index=True)
    route_profile_id = Column(Integer, ForeignKey("ai_route_profiles.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False, default=1)
    provider_id = Column(Integer, ForeignKey("ai_provider_configs.id"), nullable=False, index=True)
    model_id = Column(String(255), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


class AiCallEvent(Base):
    __tablename__ = "ai_call_events"

    id = Column(Integer, primary_key=True, index=True)
    route_key = Column(String(128), nullable=False, index=True)
    route_profile_id = Column(Integer, ForeignKey("ai_route_profiles.id"), nullable=True, index=True)
    route_step_id = Column(Integer, ForeignKey("ai_route_steps.id"), nullable=True, index=True)
    provider_id = Column(Integer, ForeignKey("ai_provider_configs.id"), nullable=True, index=True)
    provider_label = Column(String(128), nullable=True)
    model_id = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="success", index=True)
    error_type = Column(String(64), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


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
    trigger_source = Column(String(32), nullable=False, default="manual", index=True)
    task_mode = Column(String(32), nullable=False, default="time_range", index=True)
    scope_label = Column(String(255), nullable=True)
    plan_id = Column(Integer, ForeignKey("link_check_plans.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LinkCheckDetails(Base):
    __tablename__ = "link_check_details"

    id = Column(Integer, primary_key=True, index=True)
    check_time = Column(DateTime, nullable=False, index=True)
    message_id = Column(Integer, nullable=False, index=True)
    netdisk_type = Column(String(50), index=True)
    url = Column(Text)
    normalized_url = Column(Text, nullable=True, index=True)
    is_valid = Column(Boolean, nullable=False)
    response_time = Column(Float)
    error_reason = Column(String(200))
    action_taken = Column(String(50), default="none")
    created_at = Column(DateTime, default=datetime.utcnow)


class ForegroundLinkHealthCandidate(Base):
    __tablename__ = "foreground_link_health_candidates"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "netdisk_type",
            "normalized_url_hash",
            name="ux_foreground_link_health_message_target",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    netdisk_type = Column(String(50), nullable=False, index=True)
    url = Column(Text, nullable=False)
    normalized_url = Column(Text, nullable=False)
    normalized_url_hash = Column(String(64), nullable=False, index=True)
    candidate_status = Column(String(32), nullable=False, default="pending", index=True)
    invalid_observations = Column(Integer, nullable=False, default=0)
    first_invalid_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_checked_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_reason = Column(String(200), nullable=True)
    last_checker = Column(String(100), nullable=True)
    last_response_time = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LinkCheckPlan(Base):
    __tablename__ = "link_check_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, default="默认巡检")
    plan_mode = Column(String(32), nullable=False, default="backfill")
    is_enabled = Column(Boolean, nullable=False, default=False, index=True)
    schedule_hour = Column(Integer, nullable=False, default=1)
    schedule_minute = Column(Integer, nullable=False, default=0)
    schedule_priority = Column(Integer, nullable=False, default=100)
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    cycle_days = Column(Integer, nullable=False, default=7)
    batch_link_target = Column(Integer, nullable=False, default=900)
    max_batches_per_run = Column(Integer, nullable=False, default=3)
    max_concurrent = Column(Integer, nullable=False, default=5)
    traversal_order = Column(String(16), nullable=False, default="newest_first")
    overlap_message_count = Column(Integer, nullable=False, default=200)
    cleanup_mode = Column(String(32), nullable=False, default="none")
    cleanup_min_consecutive_invalid_runs = Column(Integer, nullable=False, default=2)
    next_run_at = Column(DateTime, nullable=True, index=True)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(32), nullable=True)
    last_error_message = Column(Text, nullable=True)
    cursor_message_id = Column(Integer, nullable=True)
    window_lower_message_id = Column(Integer, nullable=True)
    window_upper_message_id = Column(Integer, nullable=True)
    completed_through_message_id = Column(Integer, nullable=True)
    cycle_started_at = Column(DateTime, nullable=True)
    cycle_completed_at = Column(DateTime, nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(128), nullable=True)


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
    schedule_priority = Column(Integer, nullable=False, default=100)
    schedule_weekday = Column(Integer, nullable=True)
    schedule_day = Column(Integer, nullable=True)
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    retention_count = Column(Integer, nullable=False, default=1)
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


class AccountBatch(Base):
    __tablename__ = "account_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_name = Column(String(128), nullable=False)
    batch_code = Column(String(64), nullable=False, unique=True, index=True)
    source_type = Column(String(32), nullable=False, default="admin_bulk", index=True)
    provider_scope = Column(String(32), nullable=False, default="local")
    default_role = Column(String(32), nullable=False, default="user")
    validity_mode = Column(String(32), nullable=False, default="duration")
    validity_unit = Column(String(16), nullable=True)
    validity_value = Column(Integer, nullable=True)
    fixed_expires_at = Column(DateTime, nullable=True)
    default_session_limit_override = Column(Integer, nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    max_accounts = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String(128), nullable=True)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    display_name = Column(String(128), nullable=False, default="")
    email = Column(String(255), nullable=True, default="")
    role = Column(String(32), nullable=False, default="user", index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    account_source = Column(String(32), nullable=False, default="local", index=True)
    source_batch_id = Column(Integer, ForeignKey("account_batches.id"), nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    must_change_password = Column(Boolean, nullable=False, default=False)
    session_limit_override = Column(Integer, nullable=True)
    is_admin_exempt = Column(Boolean, nullable=True)
    last_login_at = Column(DateTime, nullable=True, index=True)
    last_seen_at = Column(DateTime, nullable=True, index=True)
    status_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(128), nullable=True)
    updated_by = Column(String(128), nullable=True)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="ux_auth_identities_provider_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    provider_user_id = Column(String(255), nullable=False, index=True)
    login_name = Column(String(255), nullable=True)
    password_hash = Column(Text, nullable=True)
    identity_status = Column(String(32), nullable=False, default="active", index=True)
    linked_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True, index=True)
    extra_json = Column(JSONB, nullable=False, default=dict)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(128), nullable=False, unique=True, index=True)
    account_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False, index=True)
    identity_id = Column(Integer, ForeignKey("auth_identities.id"), nullable=True, index=True)
    client_instance_hash = Column(String(128), nullable=True, index=True)
    login_provider = Column(String(32), nullable=False, default="local", index=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    device_label = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoke_reason = Column(String(64), nullable=True)
    extra_json = Column(JSONB, nullable=False, default=dict)


DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"options": "-c timezone=Asia/Shanghai"},
    pool_size=max(1, int(getattr(settings, "DB_POOL_SIZE", 3) or 3)),
    max_overflow=max(0, int(getattr(settings, "DB_MAX_OVERFLOW", 3) or 3)),
    pool_timeout=max(5, int(getattr(settings, "DB_POOL_TIMEOUT", 30) or 30)),
    pool_recycle=max(300, int(getattr(settings, "DB_POOL_RECYCLE", 1800) or 1800)),
    pool_pre_ping=True,
    pool_use_lifo=True,
    echo=False,
    pool_reset_on_return="commit",
)

_channel_schema_lock = threading.RLock()
_channel_schema_checked = False
_message_monitor_schema_lock = threading.RLock()
_message_monitor_schema_checked = False
_runtime_storage_lock = threading.RLock()
_runtime_storage_checked = False


def create_tables():
    Base.metadata.create_all(bind=engine)
    ensure_channel_parser_profile_column()
    ensure_message_monitor_source_columns()
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


def ensure_message_monitor_source_columns() -> None:
    global _message_monitor_schema_checked
    if _message_monitor_schema_checked:
        return

    with _message_monitor_schema_lock:
        if _message_monitor_schema_checked:
            return

        inspector = inspect(engine)
        try:
            columns = {column["name"] for column in inspector.get_columns("messages")}
        except Exception:
            columns = set()

        if not columns:
            return

        pending_alters = {
            "monitor_channel_config_id": "ALTER TABLE messages ADD COLUMN monitor_channel_config_id INTEGER",
            "monitor_chat_id": "ALTER TABLE messages ADD COLUMN monitor_chat_id BIGINT",
            "monitor_channel_key": "ALTER TABLE messages ADD COLUMN monitor_channel_key VARCHAR(255)",
            "monitor_channel_title": "ALTER TABLE messages ADD COLUMN monitor_channel_title VARCHAR(255)",
            "monitor_message_id": "ALTER TABLE messages ADD COLUMN monitor_message_id INTEGER",
        }

        with engine.begin() as connection:
            for column_name, sql in pending_alters.items():
                if column_name in columns:
                    continue
                connection.execute(text(sql))

        _message_monitor_schema_checked = True


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
                LinkCheckPlan.__table__,
                BackupSettings.__table__,
                BackupRecord.__table__,
                BackupTarget.__table__,
                BackupRun.__table__,
                AccountBatch.__table__,
                UserAccount.__table__,
                AuthIdentity.__table__,
                AuthSession.__table__,
                LinkTarget.__table__,
                MessageLinkRef.__table__,
                LinkClickEvent.__table__,
                LinkTargetDailyStat.__table__,
                ForegroundLinkHealthCandidate.__table__,
                ChannelDailyStat.__table__,
                ResourceCandidateProfile.__table__,
                ResourceCandidateLog.__table__,
                ResourceWork.__table__,
                ResourceWorkAlias.__table__,
                ResourceWorkBinding.__table__,
                ResourceRecognitionTask.__table__,
                PanTransferAccount.__table__,
                LearningChannelConfig.__table__,
                LearningResourceAutomationTask.__table__,
                LearningResourceAutomationTaskChannel.__table__,
                LearningResourceAutomationTaskTarget.__table__,
                LearningResourceCategory.__table__,
                LearningResourceItem.__table__,
                LearningResourceItemCategory.__table__,
                LearningResourceLink.__table__,
                LearningResourceTransferJob.__table__,
                LearningResourceImportJob.__table__,
                LearningResourceProcessLog.__table__,
                PanTransferBatch.__table__,
                PanTransferBatchItem.__table__,
                PanTransferReplacementLog.__table__,
                PanTransferExecutionLog.__table__,
                PanTransferPublishRecord.__table__,
                PanTransferSyncTask.__table__,
                PanTransferSyncTaskLog.__table__,
                PanTransferFollowTriggerEvent.__table__,
                MediaWallCategory.__table__,
                MediaWallItem.__table__,
                MediaWallItemCategory.__table__,
                MediaWallLink.__table__,
                MediaWallSourceConfig.__table__,
                MediaWallImportJob.__table__,
                AiProviderConfig.__table__,
                AiProviderModel.__table__,
                AiRouteProfile.__table__,
                AiRouteStep.__table__,
                AiCallEvent.__table__,
            ],
        )
        ensure_message_monitor_source_columns()
        _ensure_system_settings_columns()
        _ensure_link_check_columns()
        _ensure_backup_target_columns()
        _ensure_backup_management_indexes()
        _ensure_message_monitor_indexes()
        _ensure_channel_daily_stats_indexes()
        _ensure_resource_ops_indexes()
        _ensure_pan_transfer_columns()
        _ensure_learning_resource_columns()
        _ensure_learning_automation_tasks()
        _ensure_ai_center_columns()
        _ensure_media_wall_visibility()
        _ensure_media_wall_metadata_columns()
        _ensure_media_wall_link_columns()
        _ensure_pan_transfer_indexes()
        _ensure_link_check_indexes()
        _runtime_storage_checked = True


def _ensure_learning_resource_columns() -> None:
    inspector = inspect(engine)
    try:
        item_columns = {column["name"] for column in inspector.get_columns("learning_resource_items")}
    except Exception:
        item_columns = set()
    try:
        transfer_job_columns = {column["name"] for column in inspector.get_columns("learning_resource_transfer_jobs")}
    except Exception:
        transfer_job_columns = set()

    if not item_columns and not transfer_job_columns:
        return

    with engine.begin() as connection:
        if "tags" not in item_columns and engine.dialect.name == "postgresql":
            connection.execute(
                text("ALTER TABLE learning_resource_items ADD COLUMN tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]")
            )
        if "source_message_id" in transfer_job_columns:
            connection.execute(
                text("ALTER TABLE learning_resource_transfer_jobs ALTER COLUMN source_message_id DROP NOT NULL")
            )
        if engine.dialect.name != "postgresql":
            return
        if "task_id" not in transfer_job_columns:
            connection.execute(
                text("ALTER TABLE learning_resource_transfer_jobs ADD COLUMN task_id INTEGER")
            )
        if "supersedes_job_id" not in transfer_job_columns:
            connection.execute(
                text("ALTER TABLE learning_resource_transfer_jobs ADD COLUMN supersedes_job_id INTEGER")
            )
        connection.execute(
            text("ALTER TABLE learning_resource_links DROP CONSTRAINT IF EXISTS ux_learning_resource_links_resource_fingerprint")
        )
        connection.execute(
            text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'ux_learning_resource_links_resource_fingerprint_target'
                    ) THEN
                        ALTER TABLE learning_resource_links
                        ADD CONSTRAINT ux_learning_resource_links_resource_fingerprint_target
                        UNIQUE (resource_id, url_fingerprint, target_account_id);
                    END IF;
                END $$;
            """)
        )
        connection.execute(
            text("ALTER TABLE learning_resource_transfer_jobs DROP CONSTRAINT IF EXISTS ux_learning_resource_transfer_jobs_resource_source")
        )
        connection.execute(
            text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'ux_learning_resource_transfer_jobs_resource_source_target'
                    ) THEN
                        ALTER TABLE learning_resource_transfer_jobs
                        ADD CONSTRAINT ux_learning_resource_transfer_jobs_resource_source_target
                        UNIQUE (resource_id, source_link_target_id, target_account_id);
                    END IF;
                END $$;
            """)
        )
        connection.execute(
            text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_learning_resource_transfer_jobs_task_id'
                    ) THEN
                        ALTER TABLE learning_resource_transfer_jobs
                        ADD CONSTRAINT fk_learning_resource_transfer_jobs_task_id
                        FOREIGN KEY (task_id) REFERENCES learning_resource_automation_tasks(id)
                        ON DELETE SET NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_learning_resource_transfer_jobs_supersedes_job_id'
                    ) THEN
                        ALTER TABLE learning_resource_transfer_jobs
                        ADD CONSTRAINT fk_learning_resource_transfer_jobs_supersedes_job_id
                        FOREIGN KEY (supersedes_job_id) REFERENCES learning_resource_transfer_jobs(id)
                        ON DELETE SET NULL;
                    END IF;
                END $$;
            """)
        )


def _ensure_learning_automation_tasks() -> None:
    if engine.dialect.name != "postgresql":
        return
    inspector = inspect(engine)
    try:
        task_columns = {column["name"] for column in inspector.get_columns("learning_resource_automation_tasks")}
    except Exception:
        task_columns = set()
    if not task_columns:
        return

    with engine.begin() as connection:
        configs = connection.execute(
            text("""
                SELECT id, channel_key, channel_title, is_enabled, target_account_id,
                       save_root, backfill_policy, transfer_policy, auto_create_category_dirs,
                       created_by, updated_by
                FROM learning_channel_configs
                ORDER BY id
            """)
        ).mappings().all()
        for config in configs:
            task = connection.execute(
                text("SELECT id FROM learning_resource_automation_tasks WHERE legacy_config_id = :config_id"),
                {"config_id": int(config["id"])},
            ).mappings().first()
            if task is None:
                root_name = str(config["save_root"] or "").strip()
                task_status = "running" if bool(config["is_enabled"]) else "paused"
                task = connection.execute(
                    text("""
                        INSERT INTO learning_resource_automation_tasks
                            (name, is_enabled, transfer_policy, backfill_policy, status,
                             legacy_config_id, last_enqueued_at, last_success_at,
                             pending_count, failed_count, last_error_message,
                             created_by, updated_by, created_at, updated_at)
                        VALUES
                            (:name, :is_enabled, :transfer_policy, :backfill_policy, :status,
                             :legacy_config_id, NULL, NULL, 0, 0, NULL,
                             :created_by, :updated_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        RETURNING id
                    """),
                    {
                        "name": str(config["channel_title"] or config["channel_key"] or "学习资料自动转存")[:255],
                        "is_enabled": bool(config["is_enabled"]),
                        "transfer_policy": "automatic" if str(config["transfer_policy"] or "") == "quark_only" else str(config["transfer_policy"] or "automatic"),
                        "backfill_policy": str(config["backfill_policy"] or "new_messages_only"),
                        "status": task_status,
                        "legacy_config_id": int(config["id"]),
                        "created_by": config["created_by"],
                        "updated_by": config["updated_by"],
                    },
                ).mappings().first()
            task_id = int(task["id"])
            channel = connection.execute(
                text("""
                    SELECT id FROM channels
                    WHERE lower(trim(both '@' from coalesce(username, ''))) = lower(trim(both '@' from :channel_key))
                    ORDER BY id
                    LIMIT 1
                """),
                {"channel_key": str(config["channel_key"] or "")},
            ).mappings().first()
            if channel is not None:
                connection.execute(
                    text("""
                        INSERT INTO learning_resource_automation_task_channels
                            (task_id, channel_id, is_enabled, last_processed_message_id,
                             created_at, updated_at)
                        VALUES (:task_id, :channel_id, :is_enabled, NULL,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (task_id, channel_id) DO NOTHING
                    """),
                    {
                        "task_id": task_id,
                        "channel_id": int(channel["id"]),
                        "is_enabled": bool(config["is_enabled"]),
                    },
                )
            account_id = config["target_account_id"]
            if account_id is not None:
                account = connection.execute(
                    text("SELECT is_enabled, default_save_root FROM pan_transfer_accounts WHERE id = :account_id"),
                    {"account_id": int(account_id)},
                ).mappings().first()
                root_name = str(config["save_root"] or (account["default_save_root"] if account is not None else "") or "").strip()
                root_id = f"path:{root_name}" if root_name else "0"
                target_status = "ready" if account is not None and bool(account["is_enabled"]) and root_name else "waiting_account"
                connection.execute(
                    text("""
                        INSERT INTO learning_resource_automation_task_targets
                            (task_id, target_account_id, save_root_id, save_root_name,
                             auto_create_category_dirs, is_enabled, status,
                             created_at, updated_at)
                        VALUES (:task_id, :account_id, :root_id, :root_name,
                                :auto_create, :is_enabled, :target_status,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (task_id, target_account_id, save_root_id) DO NOTHING
                    """),
                    {
                        "task_id": task_id,
                        "account_id": int(account_id),
                        "root_id": root_id,
                        "root_name": root_name,
                        "auto_create": bool(config["auto_create_category_dirs"]),
                        "is_enabled": bool(config["is_enabled"]),
                        "target_status": target_status,
                    },
                )


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
        "schedule_priority": "ALTER TABLE backup_targets ADD COLUMN schedule_priority INTEGER NOT NULL DEFAULT 100",
    }
    with engine.begin() as connection:
        for column_name, sql in pending_alters.items():
            if column_name in columns:
                continue
            connection.execute(text(sql))


def _ensure_ai_center_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("ai_provider_configs")}
    except Exception:
        columns = set()

    if not columns or "updated_by" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE ai_provider_configs ADD COLUMN updated_by VARCHAR(128)"))


def _ensure_media_wall_visibility() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("media_wall_items")}
    except Exception:
        columns = set()

    if not columns or "visibility" not in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE media_wall_items SET visibility = 'public' WHERE visibility = 'draft'")
        )
        connection.execute(
            text("ALTER TABLE media_wall_items ALTER COLUMN visibility SET DEFAULT 'public'")
        )


def _ensure_media_wall_metadata_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("media_wall_items")}
    except Exception:
        columns = set()

    if not columns:
        return

    pending_alters = {
        "metadata_json": "ALTER TABLE media_wall_items ADD COLUMN metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "metadata_status": "ALTER TABLE media_wall_items ADD COLUMN metadata_status VARCHAR(32) NOT NULL DEFAULT 'not_synced'",
        "metadata_last_synced_at": "ALTER TABLE media_wall_items ADD COLUMN metadata_last_synced_at TIMESTAMP",
        "metadata_last_error": "ALTER TABLE media_wall_items ADD COLUMN metadata_last_error TEXT",
    }
    with engine.begin() as connection:
        for column_name, sql in pending_alters.items():
            if column_name not in columns:
                connection.execute(text(sql))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_media_wall_items_metadata_status ON media_wall_items (metadata_status)")
        )


def _ensure_media_wall_link_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("media_wall_links")}
    except Exception:
        columns = set()

    if not columns:
        return

    pending_alters = {
        "invalid_streak": "ALTER TABLE media_wall_links ADD COLUMN invalid_streak INTEGER NOT NULL DEFAULT 0",
        "next_check_at": "ALTER TABLE media_wall_links ADD COLUMN next_check_at TIMESTAMP",
        "last_error_message": "ALTER TABLE media_wall_links ADD COLUMN last_error_message TEXT",
    }
    with engine.begin() as connection:
        for column_name, sql in pending_alters.items():
            if column_name in columns:
                continue
            connection.execute(text(sql))


def _ensure_link_check_columns() -> None:
    inspector = inspect(engine)
    try:
        stats_columns = {column["name"] for column in inspector.get_columns("link_check_stats")}
    except Exception:
        stats_columns = set()

    try:
        detail_columns = {column["name"] for column in inspector.get_columns("link_check_details")}
    except Exception:
        detail_columns = set()

    try:
        plan_columns = {column["name"] for column in inspector.get_columns("link_check_plans")}
    except Exception:
        plan_columns = set()

    with engine.begin() as connection:
        stats_pending_alters = {
            "trigger_source": "ALTER TABLE link_check_stats ADD COLUMN trigger_source VARCHAR(32) NOT NULL DEFAULT 'manual'",
            "task_mode": "ALTER TABLE link_check_stats ADD COLUMN task_mode VARCHAR(32) NOT NULL DEFAULT 'time_range'",
            "scope_label": "ALTER TABLE link_check_stats ADD COLUMN scope_label VARCHAR(255)",
            "plan_id": "ALTER TABLE link_check_stats ADD COLUMN plan_id INTEGER",
        }
        for column_name, sql in stats_pending_alters.items():
            if column_name in stats_columns:
                continue
            connection.execute(text(sql))

        detail_pending_alters = {
            "normalized_url": "ALTER TABLE link_check_details ADD COLUMN normalized_url TEXT",
        }
        for column_name, sql in detail_pending_alters.items():
            if column_name in detail_columns:
                continue
            connection.execute(text(sql))

        plan_pending_alters = {
            "plan_mode": "ALTER TABLE link_check_plans ADD COLUMN plan_mode VARCHAR(32) NOT NULL DEFAULT 'backfill'",
            "schedule_priority": "ALTER TABLE link_check_plans ADD COLUMN schedule_priority INTEGER NOT NULL DEFAULT 100",
            "overlap_message_count": "ALTER TABLE link_check_plans ADD COLUMN overlap_message_count INTEGER NOT NULL DEFAULT 200",
            "window_lower_message_id": "ALTER TABLE link_check_plans ADD COLUMN window_lower_message_id INTEGER",
            "window_upper_message_id": "ALTER TABLE link_check_plans ADD COLUMN window_upper_message_id INTEGER",
            "completed_through_message_id": "ALTER TABLE link_check_plans ADD COLUMN completed_through_message_id INTEGER",
        }
        for column_name, sql in plan_pending_alters.items():
            if column_name in plan_columns:
                continue
            connection.execute(text(sql))


def _ensure_link_check_indexes() -> None:
    statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_link_check_details_normalized_url_check_time
        ON link_check_details (normalized_url, check_time DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_check_stats_trigger_source_check_time
        ON link_check_stats (trigger_source, check_time DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_check_plans_enabled_next_run
        ON link_check_plans (is_enabled, next_run_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_check_plans_enabled_next_run_priority
        ON link_check_plans (is_enabled, next_run_at, schedule_priority, id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_foreground_link_health_candidates_status_checked
        ON foreground_link_health_candidates (candidate_status, last_checked_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_media_wall_links_due_check
        ON media_wall_links (next_check_at, source_type, is_enabled)
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_backup_management_indexes() -> None:
    statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_backup_targets_enabled_next_run
        ON backup_targets (is_enabled, next_run_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_backup_targets_enabled_next_run_priority
        ON backup_targets (is_enabled, next_run_at, schedule_priority)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_backup_runs_target_started_at
        ON backup_runs (target_id, started_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_backup_runs_status_created_at
        ON backup_runs (status, created_at, id)
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


def _ensure_message_monitor_indexes() -> None:
    statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_messages_timestamp_desc
        ON messages (timestamp DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_messages_monitor_channel_config_timestamp
        ON messages (monitor_channel_config_id, timestamp DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_messages_monitor_channel_key_timestamp
        ON messages (monitor_channel_key, timestamp DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_messages_monitor_chat_message
        ON messages (monitor_chat_id, monitor_message_id DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_messages_tags_gin
        ON messages USING GIN (tags)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_messages_netdisk_types_gin
        ON messages USING GIN (netdisk_types)
        """,
    )

    for statement in statements:
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
        except Exception:
            logger.warning("failed to create message search index", exc_info=True)

    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception:
        logger.warning("pg_trgm is unavailable; substring search indexes were skipped", exc_info=True)
        return

    trigram_statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_messages_title_trgm
        ON messages USING GIN (title gin_trgm_ops)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_messages_description_trgm
        ON messages USING GIN (description gin_trgm_ops)
        """,
    )
    for statement in trigram_statements:
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
        except Exception:
            logger.warning("failed to create message trigram search index", exc_info=True)


def _ensure_channel_daily_stats_indexes() -> None:
    statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_channel_daily_stats_channel_config_date
        ON channel_daily_stats (monitor_channel_config_id, stat_date DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_channel_daily_stats_channel_key_date
        ON channel_daily_stats (monitor_channel_key, stat_date DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_channel_daily_stats_date_last_message
        ON channel_daily_stats (stat_date DESC, last_message_at DESC)
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_resource_ops_indexes() -> None:
    statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_resource_candidate_profiles_status_updated
        ON resource_candidate_profiles (operation_status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_candidate_profiles_value_status_updated
        ON resource_candidate_profiles (value_status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_candidate_logs_target_created
        ON resource_candidate_logs (link_target_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_targets_platform_last_seen_at
        ON link_targets (platform, last_seen_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_message_link_refs_target_message
        ON message_link_refs (link_target_id, message_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_click_events_target_clicked_at
        ON link_click_events (link_target_id, clicked_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_click_events_ref_clicked_at
        ON link_click_events (link_ref_id, clicked_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_click_events_stat_date_target
        ON link_click_events (stat_date, link_target_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_click_events_session_target_date
        ON link_click_events (session_key, link_target_id, stat_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_link_target_daily_stats_target_date
        ON link_target_daily_stats (link_target_id, stat_date DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_works_provider_media_year
        ON resource_works (provider, media_type, release_year)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_work_aliases_normalized_alias
        ON resource_work_aliases (normalized_alias)
        """,
        """
        DROP INDEX IF EXISTS ix_resource_work_bindings_status_next_retry
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_work_bindings_work_updated
        ON resource_work_bindings (work_id, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_recognition_tasks_status_priority
        ON resource_recognition_tasks (status, priority DESC, last_enqueued_at ASC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_recognition_tasks_retry
        ON resource_recognition_tasks (status, next_retry_at ASC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_resource_recognition_tasks_locked_at
        ON resource_recognition_tasks (locked_at ASC)
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_pan_transfer_indexes() -> None:
    statements = (
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_accounts_platform_enabled_default
        ON pan_transfer_accounts (platform, is_enabled DESC, is_default DESC, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_batches_status_created
        ON pan_transfer_batches (status, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_batch_items_batch_status
        ON pan_transfer_batch_items (batch_id, transfer_status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_batch_items_target_status
        ON pan_transfer_batch_items (link_target_id, transfer_status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_batch_items_status_retry
        ON pan_transfer_batch_items (transfer_status, next_retry_at ASC, updated_at ASC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_batch_items_locked_at
        ON pan_transfer_batch_items (locked_at ASC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_replacement_logs_batch_item_created
        ON pan_transfer_replacement_logs (batch_item_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_execution_logs_batch_item_created
        ON pan_transfer_execution_logs (batch_item_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_execution_logs_batch_stage_created
        ON pan_transfer_execution_logs (batch_id, stage, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_publish_records_published_at
        ON pan_transfer_publish_records (published_at DESC, id DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_publish_records_source_batch_item
        ON pan_transfer_publish_records (source_batch_item_id, published_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_sync_tasks_status_next_check
        ON pan_transfer_sync_tasks (status, next_check_at ASC, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_sync_tasks_work_updated
        ON pan_transfer_sync_tasks (work_id, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_sync_tasks_source_link
        ON pan_transfer_sync_tasks (source_link_target_id, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_sync_task_logs_task_created
        ON pan_transfer_sync_task_logs (task_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_follow_trigger_events_queue
        ON pan_transfer_follow_trigger_events (status, next_retry_at ASC, created_at ASC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_pan_transfer_follow_trigger_events_message
        ON pan_transfer_follow_trigger_events (message_id, created_at DESC)
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_pan_transfer_columns() -> None:
    inspector = inspect(engine)
    try:
        batch_columns = {column["name"] for column in inspector.get_columns("pan_transfer_batches")}
    except Exception:
        batch_columns = set()
    try:
        item_columns = {column["name"] for column in inspector.get_columns("pan_transfer_batch_items")}
    except Exception:
        item_columns = set()
    try:
        sync_task_columns = {column["name"] for column in inspector.get_columns("pan_transfer_sync_tasks")}
    except Exception:
        sync_task_columns = set()

    if not batch_columns and not item_columns and not sync_task_columns:
        return

    pending_batch_alters = {
        "retry_delay_seconds": "ALTER TABLE pan_transfer_batches ADD COLUMN retry_delay_seconds INTEGER NOT NULL DEFAULT 600",
    }
    pending_item_alters = {
        "attempt_count": "ALTER TABLE pan_transfer_batch_items ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
        "max_attempts": "ALTER TABLE pan_transfer_batch_items ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
        "next_retry_at": "ALTER TABLE pan_transfer_batch_items ADD COLUMN next_retry_at TIMESTAMP WITHOUT TIME ZONE",
        "locked_by": "ALTER TABLE pan_transfer_batch_items ADD COLUMN locked_by VARCHAR(128)",
        "locked_at": "ALTER TABLE pan_transfer_batch_items ADD COLUMN locked_at TIMESTAMP WITHOUT TIME ZONE",
        "started_at": "ALTER TABLE pan_transfer_batch_items ADD COLUMN started_at TIMESTAMP WITHOUT TIME ZONE",
        "finished_at": "ALTER TABLE pan_transfer_batch_items ADD COLUMN finished_at TIMESTAMP WITHOUT TIME ZONE",
        "last_validated_at": "ALTER TABLE pan_transfer_batch_items ADD COLUMN last_validated_at TIMESTAMP WITHOUT TIME ZONE",
    }
    pending_sync_task_alters = {
        "publish_record_id": "ALTER TABLE pan_transfer_sync_tasks ADD COLUMN publish_record_id INTEGER",
    }
    with engine.begin() as connection:
        for column_name, sql in pending_batch_alters.items():
            if column_name in batch_columns:
                continue
            connection.execute(text(sql))
        for column_name, sql in pending_item_alters.items():
            if column_name in item_columns:
                continue
            connection.execute(text(sql))
        for column_name, sql in pending_sync_task_alters.items():
            if column_name in sync_task_columns:
                continue
            connection.execute(text(sql))

