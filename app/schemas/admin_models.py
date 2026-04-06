"""Pydantic models used by admin endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.monitor_rules import list_parser_profile_names
from app.utils.channel_utils import dedupe_preserve_order, normalize_channel_username


def _normalize_text(value: str, *, allow_empty: bool = False, field_name: str = "value") -> str:
    normalized = (value or "").strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _normalize_optional_url(value: str, *, field_name: str) -> str:
    normalized = _normalize_text(value, allow_empty=True, field_name=field_name)
    if normalized and not normalized.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")
    return normalized


def _normalize_optional_asset_url(value: str, *, field_name: str) -> str:
    normalized = _normalize_text(value, allow_empty=True, field_name=field_name)
    if normalized and not normalized.startswith(("http://", "https://", "/")):
        raise ValueError(f"{field_name} must start with http://, https:// or /")
    return normalized



def _normalize_usernames(values: List[str]) -> List[str]:
    cleaned = []
    for value in values:
        username = _normalize_text(value, field_name="username")
        if any(ch.isspace() for ch in username):
            raise ValueError("username cannot contain spaces")
        cleaned.append(username)
    cleaned = dedupe_preserve_order(cleaned)
    if not cleaned:
        raise ValueError("at least one username is required")
    return cleaned


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CredentialResponse(ORMModel):
    id: int
    api_id: str
    api_hash: str


class CredentialCreate(BaseModel):
    api_id: str = Field(min_length=1, max_length=64)
    api_hash: str = Field(min_length=1, max_length=256)

    @field_validator("api_id", "api_hash")
    @classmethod
    def validate_credential_fields(cls, value: str) -> str:
        return _normalize_text(value)


class ChannelResponse(ORMModel):
    id: int
    username: str
    parser_profile: Optional[str] = None
    effective_parser_profile: str = "default"
    title: Optional[str] = None
    telegram_id: Optional[int] = None
    channel_type: Optional[str] = None
    resolution_status: Optional[str] = None
    resolution_error: Optional[str] = None


class ChannelCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    parser_profile: Optional[str] = Field(default=None, max_length=64)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_channel_username(value)

    @field_validator("parser_profile")
    @classmethod
    def validate_parser_profile(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = _normalize_text(value, field_name="parser_profile")
        if normalized.lower() == "auto":
            return None
        if normalized not in set(list_parser_profile_names()):
            raise ValueError(f"unsupported parser_profile: {normalized}")
        return normalized


class FooterBuilderSection(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=255)
    html: str = Field(default="", max_length=20000)
    span: int = Field(default=3, ge=1, le=12)

    @field_validator("id", "title", "html")
    @classmethod
    def validate_footer_section_text(cls, value: str, info) -> str:
        return _normalize_text(value, allow_empty=info.field_name != "id", field_name=info.field_name)


class SystemConfigResponse(BaseModel):
    site_name: str
    site_title: str
    site_description: str
    site_keywords: str
    brand_icon: str
    site_favicon_url: str
    public_dashboard_enabled: bool
    public_ads_enabled: bool
    public_feed_top_ad_html_desktop: str
    public_feed_top_ad_html_mobile: str
    public_feed_inline_ad_html_desktop: str
    public_feed_inline_ad_html_mobile: str
    public_feed_inline_every_n: int
    footer_builder_enabled: bool
    footer_builder_sections: List[FooterBuilderSection]
    footer_builder_bottom_html: str
    umami_enabled: bool
    umami_script_url: str
    umami_website_id: str
    umami_host_url: str
    umami_share_url: str
    link_check_default_max_concurrent: int
    link_check_max_allowed_concurrent: int
    link_check_max_allowed_links: int
    link_check_poll_interval_seconds: int
    monitor_channel_refresh_interval_seconds: int
    monitor_db_write_max_retries: int
    monitor_db_write_retry_delay_seconds: float


class SystemConfigUpdate(BaseModel):
    site_name: str = Field(default="TG频道监控", max_length=255)
    site_title: str = Field(default="TG频道监控", max_length=255)
    site_description: str = Field(default="Telegram 频道网盘资源监控与检索", max_length=2000)
    site_keywords: str = Field(default="telegram,网盘,频道监控,资源搜索", max_length=2000)
    brand_icon: str = Field(default="📱", max_length=32)
    site_favicon_url: str = Field(default="/favicon.svg", max_length=1000)
    public_dashboard_enabled: bool
    public_ads_enabled: bool
    public_feed_top_ad_html_desktop: str = Field(default="", max_length=20000)
    public_feed_top_ad_html_mobile: str = Field(default="", max_length=20000)
    public_feed_inline_ad_html_desktop: str = Field(default="", max_length=20000)
    public_feed_inline_ad_html_mobile: str = Field(default="", max_length=20000)
    public_feed_inline_every_n: int = Field(default=8, ge=2, le=999)
    footer_builder_enabled: bool = False
    footer_builder_sections: List[FooterBuilderSection] = Field(default_factory=list, max_length=12)
    footer_builder_bottom_html: str = Field(default="", max_length=20000)
    umami_enabled: bool = False
    umami_script_url: str = Field(default="", max_length=1000)
    umami_website_id: str = Field(default="", max_length=255)
    umami_host_url: str = Field(default="", max_length=1000)
    umami_share_url: str = Field(default="", max_length=1000)
    link_check_default_max_concurrent: int = Field(ge=1, le=10)
    link_check_max_allowed_concurrent: int = Field(ge=1, le=10)
    link_check_max_allowed_links: int = Field(ge=100, le=5000)
    link_check_poll_interval_seconds: int = Field(ge=1, le=30)
    monitor_channel_refresh_interval_seconds: int = Field(ge=10, le=3600)
    monitor_db_write_max_retries: int = Field(ge=1, le=10)
    monitor_db_write_retry_delay_seconds: float = Field(ge=0.1, le=30.0)

    @field_validator(
        "site_description",
        "site_keywords",
        "public_feed_top_ad_html_desktop",
        "public_feed_top_ad_html_mobile",
        "public_feed_inline_ad_html_desktop",
        "public_feed_inline_ad_html_mobile",
        "footer_builder_bottom_html",
    )
    @classmethod
    def validate_system_config_text_fields(cls, value: str) -> str:
        return _normalize_text(value, allow_empty=True)

    @field_validator("site_name", "site_title")
    @classmethod
    def validate_site_text_fields(cls, value: str, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("brand_icon")
    @classmethod
    def validate_brand_icon(cls, value: str) -> str:
        return _normalize_text(value, allow_empty=True, field_name="brand_icon")

    @field_validator("umami_website_id")
    @classmethod
    def validate_umami_text_fields(cls, value: str) -> str:
        return _normalize_text(value, allow_empty=True)

    @field_validator("site_favicon_url")
    @classmethod
    def validate_site_favicon_url(cls, value: str) -> str:
        return _normalize_optional_asset_url(value, field_name="site_favicon_url")

    @field_validator("umami_script_url", "umami_host_url", "umami_share_url")
    @classmethod
    def validate_umami_url_fields(cls, value: str, info) -> str:
        return _normalize_optional_url(value, field_name=info.field_name)

    @field_validator("footer_builder_sections")
    @classmethod
    def validate_footer_builder_sections(cls, value: List[FooterBuilderSection]) -> List[FooterBuilderSection]:
        section_ids = [item.id for item in value]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("footer_builder_sections ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_link_check_config(self) -> "SystemConfigUpdate":
        if self.link_check_default_max_concurrent > self.link_check_max_allowed_concurrent:
            raise ValueError("link_check_default_max_concurrent cannot exceed link_check_max_allowed_concurrent")
        if self.umami_enabled:
            if not self.umami_script_url:
                raise ValueError("umami_script_url is required when umami_enabled is true")
            if not self.umami_website_id:
                raise ValueError("umami_website_id is required when umami_enabled is true")
        return self


class PublicSystemConfigResponse(BaseModel):
    site_name: str
    site_title: str
    site_description: str
    site_keywords: str
    brand_icon: str
    site_favicon_url: str
    public_dashboard_enabled: bool
    public_ads_enabled: bool
    public_feed_top_ad_html_desktop: str
    public_feed_top_ad_html_mobile: str
    public_feed_inline_ad_html_desktop: str
    public_feed_inline_ad_html_mobile: str
    public_feed_inline_every_n: int
    footer_builder_enabled: bool
    footer_builder_sections: List[FooterBuilderSection]
    footer_builder_bottom_html: str
    umami_enabled: bool
    umami_script_url: str
    umami_website_id: str
    umami_host_url: str

class UserResponse(BaseModel):
    username: str
    name: str
    email: str
    role: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(default="", max_length=128)
    email: str = Field(default="", max_length=255)
    role: str = Field(default="user")

    @field_validator("username")
    @classmethod
    def validate_user_username(cls, value: str) -> str:
        username = _normalize_text(value, field_name="username")
        if any(ch.isspace() for ch in username):
            raise ValueError("username cannot contain spaces")
        return username

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _normalize_text(value, field_name="password")

    @field_validator("name", "email")
    @classmethod
    def validate_optional_text_fields(cls, value: str) -> str:
        return _normalize_text(value, allow_empty=True)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = _normalize_text(value, field_name="role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return role


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = None

    @field_validator("name", "email")
    @classmethod
    def validate_update_text_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_text(value, allow_empty=True)

    @field_validator("role")
    @classmethod
    def validate_update_role(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        role = _normalize_text(value, field_name="role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return role


class PasswordChange(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _normalize_text(value, field_name="new_password")


class UsernameChange(BaseModel):
    new_username: str = Field(min_length=1, max_length=64)

    @field_validator("new_username")
    @classmethod
    def validate_new_username(cls, value: str) -> str:
        username = _normalize_text(value, field_name="new_username")
        if any(ch.isspace() for ch in username):
            raise ValueError("new_username cannot contain spaces")
        return username


class RoleChange(BaseModel):
    new_role: str

    @field_validator("new_role")
    @classmethod
    def validate_new_role(cls, value: str) -> str:
        role = _normalize_text(value, field_name="new_role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("new_role must be admin or user")
        return role


class BulkRandomCreateRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=500)
    prefix: str = Field(default="user", min_length=1, max_length=32)
    start_index: int = Field(default=1, ge=1)
    role: str = Field(default="user")
    password_length: int = Field(default=12, ge=6, le=32)

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        prefix = _normalize_text(value, field_name="prefix")
        if any(ch.isspace() for ch in prefix):
            raise ValueError("prefix cannot contain spaces")
        return prefix

    @field_validator("role")
    @classmethod
    def validate_bulk_role(cls, value: str) -> str:
        role = _normalize_text(value, field_name="role").lower()
        if role not in {"admin", "user"}:
            raise ValueError("role must be admin or user")
        return role


class BulkRandomCreateResult(BaseModel):
    username: str
    password: str
    role: str


class BulkFailure(BaseModel):
    username: Optional[str] = None
    reason: str


class BulkCreateResponse(BaseModel):
    successes: List[BulkRandomCreateResult]
    failures: List[BulkFailure]


class BulkUsernamesRequest(BaseModel):
    usernames: List[str]
    password_length: Optional[int] = Field(default=12, ge=6, le=32)

    @model_validator(mode="after")
    def normalize_usernames_list(self) -> "BulkUsernamesRequest":
        self.usernames = _normalize_usernames(self.usernames)
        return self


class BulkResetResult(BaseModel):
    username: str
    password: str


class BulkSimpleResponse(BaseModel):
    successes: List[Any]
    failures: List[BulkFailure]


class MaintenanceResult(BaseModel):
    success: bool
    fixed_count: Optional[int] = None
    deleted_count: Optional[int] = None
    deleted_details: Optional[int] = None
    deleted_stats: Optional[int] = None
    cutoff_time: Optional[str] = None
    errors: Optional[List[str]] = None
    error: Optional[str] = None


class ClearOldDataRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)


class ChannelDiagnosisResult(BaseModel):
    valid_channels: List[Dict[str, Any]]
    invalid_channels: List[Dict[str, Any]]


class MonitorTestResult(BaseModel):
    success: bool
    channels_tested: Optional[int] = None
    message_received: Optional[bool] = None
    message: Optional[str] = None
    error: Optional[str] = None


class ChannelMessageSampleEntity(BaseModel):
    type: str
    url: str
    text: Optional[str] = None


class ChannelMessageSampleButton(BaseModel):
    text: Optional[str] = None
    url: str


class ChannelMessageSampleWebpage(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    site_name: Optional[str] = None
    author: Optional[str] = None
    type: Optional[str] = None
    display_url: Optional[str] = None


class ChannelMessageSampleParserDebug(BaseModel):
    parsed_records: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    extracted_link_count: int = 0


class ChannelMessageSample(BaseModel):
    message_id: int
    timestamp: str
    message_link: Optional[str] = None
    text: str
    text_length: int
    has_media: bool = False
    media_kind: Optional[str] = None
    grouped_id: Optional[int] = None
    post_author: Optional[str] = None
    raw_urls: List[str] = Field(default_factory=list)
    entity_urls: List[ChannelMessageSampleEntity] = Field(default_factory=list)
    button_links: List[ChannelMessageSampleButton] = Field(default_factory=list)
    webpage_preview: Optional[ChannelMessageSampleWebpage] = None
    raw_message: Dict[str, Any] = Field(default_factory=dict)
    extracted_link_count: int = 0
    parser_debug: ChannelMessageSampleParserDebug = Field(
        default_factory=ChannelMessageSampleParserDebug
    )


class ChannelSampleResponse(BaseModel):
    channel_id: int
    username: str
    title: Optional[str] = None
    telegram_id: Optional[int] = None
    requested_limit: int
    page: int = 1
    page_size: int = 10
    sample_count: int
    has_more: bool = False
    inspected_count: int = 0
    only_with_links: bool
    samples: List[ChannelMessageSample] = Field(default_factory=list)


class LinkCheckTaskCreate(BaseModel):
    period: str = Field(min_length=1, max_length=128)
    max_concurrent: int = Field(default=5, ge=1, le=10)

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        return _normalize_text(value, field_name="period")


class LinkCheckTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    period_desc: Optional[str] = None
    total_messages: Optional[int] = None
    total_links: Optional[int] = None
    checked_links: Optional[int] = None
    valid_links: Optional[int] = None
    invalid_links: Optional[int] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    current_phase: Optional[str] = None
    current_platform: Optional[str] = None
    stop_requested: bool = False
    reused_existing: bool = False
    status_counts: Optional[Dict[str, int]] = None
    check_time: Optional[str] = None
    duration: Optional[float] = None
    logs: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class LinkCheckTaskHistory(BaseModel):
    id: int
    check_time: str
    total_messages: int
    total_links: int
    valid_links: int
    invalid_links: int
    updated_messages: Optional[int] = None
    deleted_messages: Optional[int] = None
    status: str
    duration: Optional[float] = None


class LinkCheckTaskResult(BaseModel):
    stats: Dict[str, Any]
    details: List[Dict[str, Any]]


class LinkCheckDateRange(BaseModel):
    min_date: Optional[str] = None
    max_date: str
    latest_message_date: Optional[str] = None


class LinkCleanupApplyRequest(BaseModel):
    mode: str = Field(default="remove_invalid_links")
    dry_run: bool = False

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = _normalize_text(value, field_name="mode").lower()
        if normalized not in {"remove_invalid_links", "delete_message_if_empty"}:
            raise ValueError("mode must be remove_invalid_links or delete_message_if_empty")
        return normalized


class LinkCleanupResult(BaseModel):
    success: bool
    check_time: str
    mode: str
    dry_run: bool = False
    total_invalid_details: int = 0
    cleanup_candidates: int = 0
    matched_messages: int = 0
    updated_messages: int = 0
    deleted_messages: int = 0
    removed_links: int = 0
    skipped_messages: int = 0


class LinkCheckHistoryDeleteResult(BaseModel):
    success: bool
    check_time: str
    deleted_details: int = 0
    deleted_stats: int = 0


class LinkCheckHistoryBatchDeleteRequest(BaseModel):
    check_times: List[str] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def normalize_check_times(self) -> "LinkCheckHistoryBatchDeleteRequest":
        normalized: List[str] = []
        seen: set[str] = set()
        for raw_value in self.check_times:
            value = _normalize_text(raw_value, field_name="check_times")
            if value in seen:
                continue
            normalized.append(value)
            seen.add(value)
        if not normalized:
            raise ValueError("check_times must contain at least one item")
        self.check_times = normalized
        return self


class LinkCheckHistoryBatchDeleteResult(BaseModel):
    success: bool
    requested_count: int = 0
    deleted_runs: int = 0
    deleted_details: int = 0
    deleted_stats: int = 0
    missing_check_times: List[str] = Field(default_factory=list)


