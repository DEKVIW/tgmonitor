from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _serialize_shanghai_local_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=_SHANGHAI_TZ)
    else:
        normalized = value.astimezone(_SHANGHAI_TZ)
    return normalized.isoformat()


def _normalize_text(value: str | None, *, field_name: str, allow_empty: bool = False) -> str:
    normalized = (value or "").strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class PanTransferBaseModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={
            datetime: _serialize_datetime,
        }
    )


class PanTransferAccountItem(PanTransferBaseModel):
    id: int
    platform: str
    account_name: str
    auth_type: str
    default_save_root: str = ""
    default_share_mode: str = "public"
    default_share_passcode: str | None = None
    default_share_expire_days: int | None = None
    is_enabled: bool = True
    is_default: bool = False
    credential_configured: bool = False
    last_validated_at: datetime | None = None
    last_error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PanTransferAccountListResponse(PanTransferBaseModel):
    items: list[PanTransferAccountItem]
    total: int


class PanTransferAccountCreateRequest(PanTransferBaseModel):
    platform: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=128)
    auth_type: str = Field(default="cookie", min_length=1, max_length=32)
    credential_value: str = Field(min_length=1, max_length=20000)
    default_save_root: str = Field(default="", max_length=255)
    default_share_mode: str = Field(default="public", min_length=1, max_length=32)
    default_share_passcode: str | None = Field(default=None, max_length=32)
    default_share_expire_days: int | None = Field(default=None, ge=1, le=3650)
    is_enabled: bool = True
    is_default: bool = False

    @field_validator("platform", "account_name", "auth_type", "credential_value", "default_save_root", "default_share_mode")
    @classmethod
    def validate_text_fields(cls, value: str, info) -> str:
        return _normalize_text(value, field_name=info.field_name, allow_empty=info.field_name == "default_save_root")

    @field_validator("default_share_passcode")
    @classmethod
    def validate_passcode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value, field_name="default_share_passcode", allow_empty=True)
        return normalized or None

    @model_validator(mode="after")
    def validate_default_enabled(self) -> "PanTransferAccountCreateRequest":
        if self.is_default and not self.is_enabled:
            raise ValueError("default account must be enabled")
        return self


class PanTransferAccountUpdateRequest(PanTransferBaseModel):
    platform: str | None = Field(default=None, max_length=64)
    account_name: str | None = Field(default=None, max_length=128)
    auth_type: str | None = Field(default=None, max_length=32)
    credential_value: str | None = Field(default=None, max_length=20000)
    clear_credential: bool = False
    default_save_root: str | None = Field(default=None, max_length=255)
    default_share_mode: str | None = Field(default=None, max_length=32)
    default_share_passcode: str | None = Field(default=None, max_length=32)
    default_share_expire_days: int | None = Field(default=None, ge=1, le=3650)
    is_enabled: bool | None = None
    is_default: bool | None = None

    @field_validator("platform", "account_name", "auth_type", "credential_value", "default_save_root", "default_share_mode")
    @classmethod
    def validate_optional_text_fields(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _normalize_text(
            value,
            field_name=info.field_name,
            allow_empty=info.field_name in {"default_save_root", "credential_value"},
        )

    @field_validator("default_share_passcode")
    @classmethod
    def validate_optional_passcode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value, field_name="default_share_passcode", allow_empty=True)
        return normalized or None


class PanTransferDeleteResponse(PanTransferBaseModel):
    id: int
    platform: str
    deleted: bool = True


class PanTransferManualPreviewRequest(PanTransferBaseModel):
    selection_mode: str = Field(default="recent_messages", min_length=1, max_length=32)
    direction: str = Field(default="newest_first", min_length=1, max_length=32)
    recent_message_count: int | None = Field(default=200, ge=1, le=3000)
    range_start: str | None = Field(default=None, max_length=10)
    range_end: str | None = Field(default=None, max_length=10)
    search_keyword: str | None = Field(default=None, max_length=120)
    platforms: list[str] = Field(default_factory=list)
    health_filter: str = Field(default="all", min_length=1, max_length=32)
    only_healthy: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)

    @field_validator("selection_mode", "direction", "health_filter")
    @classmethod
    def validate_mode_fields(cls, value: str, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("range_start", "range_end", "search_keyword")
    @classmethod
    def validate_optional_dates(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name=info.field_name, allow_empty=True) or None

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = _normalize_text(item, field_name="platforms")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    @model_validator(mode="after")
    def validate_selection_payload(self) -> "PanTransferManualPreviewRequest":
        if self.only_healthy:
            self.health_filter = "healthy_only"
        if self.selection_mode == "recent_messages" and self.recent_message_count is None:
            raise ValueError("recent_message_count is required for recent_messages mode")
        if self.selection_mode == "time_range" and (not self.range_start or not self.range_end):
            raise ValueError("range_start and range_end are required for time_range mode")
        return self


class PanTransferPreviewItem(PanTransferBaseModel):
    link_target_id: int
    platform: str
    short_title: str
    original_url: str
    share_key: str | None = None
    latest_link_health: str = "unknown"
    latest_link_health_label: str = "未知"
    latest_link_health_reason: str | None = None
    impact_message_count: int = 0
    source_ref_count: int = 0
    latest_message_time: datetime | None = None
    latest_message_title: str | None = None
    work_title: str | None = None
    recommended_account_id: int | None = None
    recommended_account_name: str | None = None


class PanTransferManualPreviewResponse(PanTransferBaseModel):
    selection_mode: str
    direction: str
    requested_message_count: int | None = None
    effective_message_count: int = 0
    truncated: bool = False
    range_start: str | None = None
    range_end: str | None = None
    platforms: list[str] = Field(default_factory=list)
    health_filter: str = "all"
    only_healthy: bool = False
    matched_link_ref_count: int = 0
    unique_link_target_count: int = 0
    healthy_count: int = 0
    invalid_count: int = 0
    unknown_count: int = 0
    page: int = 1
    page_size: int = 10
    total: int = 0
    can_start: bool = False
    items: list[PanTransferPreviewItem] = Field(default_factory=list)


class PanTransferAccountValidationResponse(PanTransferBaseModel):
    account_id: int
    platform: str
    account_name: str
    ok: bool
    checked_at: datetime
    detail_message: str
    remote_user: str | None = None
    payload: dict = Field(default_factory=dict)


class PanTransferBatchCreateRequest(PanTransferManualPreviewRequest):
    selected_link_target_ids: list[int] = Field(default_factory=list)
    start_immediately: bool = True
    max_attempts: int | None = Field(default=3, ge=1, le=10)
    retry_delay_seconds: int | None = Field(default=600, ge=0, le=86400)
    target_account_ids_by_platform: dict[str, int] = Field(default_factory=dict)
    transfer_layout: str = Field(default="independent", min_length=1, max_length=32)
    batch_folder_name: str | None = Field(default=None, max_length=120)
    item_folder_mode: str = Field(default="auto", min_length=1, max_length=32)
    item_folder_template: str | None = Field(default=None, max_length=120)
    share_target_mode: str = Field(default="resource_dir", min_length=1, max_length=32)

    @field_validator("selected_link_target_ids")
    @classmethod
    def validate_selected_link_target_ids(cls, value: list[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for raw_value in value:
            try:
                item_id = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("selected_link_target_ids must contain integers") from exc
            if item_id <= 0 or item_id in seen:
                continue
            seen.add(item_id)
            normalized.append(item_id)
        return normalized

    @field_validator("transfer_layout", "item_folder_mode", "share_target_mode")
    @classmethod
    def validate_batch_mode_fields(cls, value: str, info) -> str:
        normalized = _normalize_text(value, field_name=info.field_name).lower()
        allowed_map = {
            "transfer_layout": {"independent", "batch_archive"},
            "item_folder_mode": {"auto", "custom"},
            "share_target_mode": {"resource_dir", "content_root"},
        }
        if normalized not in allowed_map[info.field_name]:
            raise ValueError(f"invalid {info.field_name}")
        return normalized

    @field_validator("batch_folder_name", "item_folder_template")
    @classmethod
    def validate_optional_folder_fields(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name=info.field_name, allow_empty=True) or None

    @field_validator("target_account_ids_by_platform")
    @classmethod
    def validate_target_account_ids_by_platform(cls, value: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for raw_platform, raw_account_id in dict(value or {}).items():
            platform = _normalize_text(str(raw_platform or ""), field_name="target_account_ids_by_platform")
            try:
                account_id = int(raw_account_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("target_account_ids_by_platform must contain integer account ids") from exc
            if account_id <= 0:
                raise ValueError("target_account_ids_by_platform must contain positive account ids")
            normalized[platform] = account_id
        return normalized

    @model_validator(mode="after")
    def validate_batch_path_strategy(self) -> "PanTransferBatchCreateRequest":
        if self.transfer_layout == "batch_archive" and not self.batch_folder_name:
            self.batch_folder_name = None
        if self.item_folder_mode == "custom" and not self.item_folder_template:
            raise ValueError("item_folder_template is required when item_folder_mode is custom")
        if self.item_folder_mode != "custom":
            self.item_folder_template = None
        return self


class PanTransferMessagePublishRequest(PanTransferBaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def validate_publish_title(cls, value: str) -> str:
        return _normalize_text(value, field_name="title")

    @field_validator("description")
    @classmethod
    def validate_publish_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name="description", allow_empty=True) or None

    @field_validator("tags")
    @classmethod
    def validate_publish_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in value:
            cleaned = _normalize_text(raw_value, field_name="tags")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned[:64])
        return normalized


class PanTransferMessagePublishResponse(PanTransferBaseModel):
    message_id: int
    title: str
    source_url: str
    link_target_id: int | None = None
    published_at: datetime
    reused_existing_target: bool = False

    @field_serializer("published_at")
    def serialize_published_at(self, value: datetime) -> str:
        return _serialize_shanghai_local_datetime(value)


class PanTransferManualPublishRequest(PanTransferBaseModel):
    platform: str = Field(min_length=1, max_length=64)
    source_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("platform", "source_url", "title")
    @classmethod
    def validate_manual_publish_text(cls, value: str, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("description")
    @classmethod
    def validate_manual_publish_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name="description", allow_empty=True) or None

    @field_validator("tags")
    @classmethod
    def validate_manual_publish_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in value:
            cleaned = _normalize_text(raw_value, field_name="tags")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned[:64])
        return normalized


class PanTransferLinkDirectoryPreviewRequest(PanTransferBaseModel):
    url: str = Field(min_length=1, max_length=2000)
    entry_id: str | None = Field(default=None, max_length=255)
    entry_path: str | None = Field(default=None, max_length=1024)
    entry_name: str | None = Field(default=None, max_length=255)

    @field_validator("url")
    @classmethod
    def validate_preview_url(cls, value: str) -> str:
        return _normalize_text(value, field_name="url")

    @field_validator("entry_id", "entry_path", "entry_name")
    @classmethod
    def validate_optional_preview_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name=info.field_name, allow_empty=True) or None


class PanTransferLinkDirectoryEntry(PanTransferBaseModel):
    name: str
    is_dir: bool = False
    size_bytes: int | None = None
    updated_at: datetime | None = None
    entry_id: str | None = None
    path: str | None = None


class PanTransferLinkDirectoryPreviewResponse(PanTransferBaseModel):
    url: str
    platform: str
    supported: bool = True
    item_count: int = 0
    truncated: bool = False
    current_entry_id: str | None = None
    current_path: str | None = None
    current_name: str | None = None
    message: str | None = None
    items: list[PanTransferLinkDirectoryEntry] = Field(default_factory=list)


class PanTransferPublishRecordItem(PanTransferBaseModel):
    id: int
    source_type: str
    source_batch_id: int | None = None
    source_batch_item_id: int | None = None
    source_link_target_id: int | None = None
    source_new_link_target_id: int | None = None
    platform: str
    source_url: str
    source_original_url: str | None = None
    current_share_url: str | None = None
    published_link_target_id: int | None = None
    published_message_id: int | None = None
    published_title: str
    published_description: str | None = None
    published_tags: list[str] = Field(default_factory=list)
    original_link_status: str | None = None
    original_link_detail_message: str | None = None
    original_link_checked_at: datetime | None = None
    current_share_status: str | None = None
    current_share_detail_message: str | None = None
    current_share_checked_at: datetime | None = None
    published_link_status: str | None = None
    published_link_detail_message: str | None = None
    published_link_checked_at: datetime | None = None
    published_clicks_total: int = 0
    publish_count: int = 1
    can_refresh_share: bool = False
    can_edit: bool = True
    operator: str | None = None
    is_archived: bool = False
    archived_at: datetime | None = None
    publish_rule_enabled: bool = False
    publish_rule_summary: str | None = None
    next_publish_at: datetime | None = None
    extra_json: dict = Field(default_factory=dict)
    published_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_serializer("published_at")
    def serialize_published_at(self, value: datetime) -> str:
        return _serialize_shanghai_local_datetime(value)


class PanTransferPublishRecordListResponse(PanTransferBaseModel):
    items: list[PanTransferPublishRecordItem] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class PanTransferPublishRecordUpdateRequest(PanTransferBaseModel):
    source_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("source_url", "title")
    @classmethod
    def validate_publish_record_required_text(cls, value: str, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("description")
    @classmethod
    def validate_publish_record_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name="description", allow_empty=True) or None

    @field_validator("tags")
    @classmethod
    def validate_publish_record_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in value:
            cleaned = _normalize_text(raw_value, field_name="tags")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned[:64])
        return normalized


class PanTransferPublishRuleUpdateRequest(PanTransferBaseModel):
    enabled: bool = False
    weekdays: list[int] = Field(default_factory=list)
    time_of_day: str | None = Field(default=None, max_length=5)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)

    @field_validator("weekdays")
    @classmethod
    def validate_publish_rule_weekdays(cls, value: list[int]) -> list[int]:
        normalized = sorted({int(day) for day in value})
        for day in normalized:
            if day < 1 or day > 7:
                raise ValueError("weekdays must use 1-7 (Mon-Sun)")
        return normalized

    @field_validator("time_of_day")
    @classmethod
    def validate_publish_rule_time_of_day(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value, field_name="time_of_day", allow_empty=True)
        if not normalized:
            return None
        parts = normalized.split(":")
        if len(parts) != 2:
            raise ValueError("time_of_day must use HH:MM")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError as exc:
            raise ValueError("time_of_day must use HH:MM") from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("time_of_day must use HH:MM")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("timezone")
    @classmethod
    def validate_publish_rule_timezone(cls, value: str) -> str:
        return _normalize_text(value, field_name="timezone")

    @model_validator(mode="after")
    def validate_publish_rule(self) -> "PanTransferPublishRuleUpdateRequest":
        if not self.enabled:
            return self
        if not self.weekdays:
            raise ValueError("weekdays cannot be empty when publish rule is enabled")
        if not self.time_of_day:
            raise ValueError("time_of_day cannot be empty when publish rule is enabled")
        return self


class PanTransferFollowTaskCreateRequest(PanTransferBaseModel):
    task_name: str | None = Field(default=None, max_length=255)
    check_interval_minutes: int | None = Field(default=360, ge=15, le=10080)
    automation: dict = Field(default_factory=dict)

    @field_validator("task_name")
    @classmethod
    def validate_follow_task_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name="task_name", allow_empty=True) or None


class PanTransferFollowTaskSyncSelectionEntry(PanTransferBaseModel):
    name: str = Field(min_length=1, max_length=255)
    is_dir: bool = False
    entry_id: str | None = Field(default=None, max_length=255)
    path: str | None = Field(default=None, max_length=1024)

    @field_validator("name")
    @classmethod
    def validate_selection_name(cls, value: str) -> str:
        return _normalize_text(value, field_name="name")

    @field_validator("entry_id", "path")
    @classmethod
    def validate_optional_selection_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name=info.field_name, allow_empty=True) or None


class PanTransferFollowTaskSyncRequest(PanTransferBaseModel):
    source_kind: str = Field(default="current", min_length=1, max_length=32)
    sync_mode: str = Field(default="standard", min_length=1, max_length=32)
    selected_entries: list[PanTransferFollowTaskSyncSelectionEntry] = Field(default_factory=list)
    selection_parent_entry_id: str | None = Field(default=None, max_length=255)
    selection_parent_path: str | None = Field(default=None, max_length=1024)
    selection_parent_name: str | None = Field(default=None, max_length=255)
    confirm_full_replace: bool = False
    reuse_existing_share_if_valid: bool = True
    update_publish_record: bool = True

    @field_validator("source_kind", "sync_mode")
    @classmethod
    def validate_follow_sync_mode_fields(cls, value: str, info) -> str:
        normalized = _normalize_text(value, field_name=info.field_name).lower()
        allowed_map = {
            "source_kind": {"current", "candidate"},
            "sync_mode": {"standard", "incremental", "replace_all"},
        }
        if normalized not in allowed_map[info.field_name]:
            raise ValueError(f"invalid {info.field_name}")
        return normalized

    @field_validator("selection_parent_entry_id", "selection_parent_path", "selection_parent_name")
    @classmethod
    def validate_follow_sync_parent_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name=info.field_name, allow_empty=True) or None

    @field_validator("selected_entries")
    @classmethod
    def validate_selected_entries(
        cls,
        value: list[PanTransferFollowTaskSyncSelectionEntry],
    ) -> list[PanTransferFollowTaskSyncSelectionEntry]:
        normalized: list[PanTransferFollowTaskSyncSelectionEntry] = []
        seen: set[tuple[str, str, str]] = set()
        for entry in value:
            entry_id = str(entry.entry_id or "").strip()
            path = str(entry.path or "").strip()
            dedupe_key = (entry_id, path, f"{entry.name}:{int(entry.is_dir)}")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(entry)
        return normalized

    @model_validator(mode="after")
    def validate_follow_sync_payload(self) -> "PanTransferFollowTaskSyncRequest":
        if self.sync_mode == "standard":
            if self.selected_entries:
                raise ValueError("selected_entries are only supported for incremental or replace_all mode")
            if self.confirm_full_replace:
                raise ValueError("confirm_full_replace is only supported for replace_all mode")
            return self
        if not self.selected_entries:
            raise ValueError("selected_entries cannot be empty for manual follow sync")
        if self.sync_mode == "replace_all" and not self.confirm_full_replace:
            raise ValueError("confirm_full_replace is required for replace_all mode")
        return self


class PanTransferFollowTaskLogItem(PanTransferBaseModel):
    id: int
    task_id: int
    level: str
    stage: str
    message: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class PanTransferFollowTaskRuleAssessment(PanTransferBaseModel):
    rule_key: str = "safe_sync_current"
    rule_label: str = "规则一：安全同步当前原链"
    summary: str = ""
    recommended_source_kind: str | None = None
    recommended_sync_mode: str | None = None
    execution_mode: str = "direct_sync"
    risk_level: str = "info"
    requires_manual_confirmation: bool = False
    can_execute: bool = True


class PanTransferFollowTaskItem(PanTransferBaseModel):
    id: int
    task_name: str
    status: str
    task_state: str
    platform: str
    source_batch_id: int | None = None
    source_batch_item_id: int | None = None
    source_link_target_id: int | None = None
    source_url: str
    source_share_key: str | None = None
    topic_key: str
    topic_title: str
    work_id: int | None = None
    work_title: str | None = None
    publish_record_id: int | None = None
    publish_record_title: str | None = None
    publish_record_message_id: int | None = None
    publish_record_published_at: datetime | None = None
    publish_record_source_url: str | None = None
    target_account_id: int | None = None
    target_account_name: str | None = None
    fixed_save_path: str
    transfer_layout: str
    batch_folder_name: str | None = None
    item_folder_mode: str
    item_folder_template: str | None = None
    share_target_mode: str
    current_share_url: str | None = None
    current_share_link_target_id: int | None = None
    source_link_status: str
    current_share_status: str
    last_change_type: str | None = None
    last_candidate_link_target_id: int | None = None
    last_candidate_url: str | None = None
    last_candidate_title: str | None = None
    last_candidate_message_time: datetime | None = None
    check_interval_minutes: int
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    last_error_message: str | None = None
    last_sync_batch_id: int | None = None
    last_sync_batch_item_id: int | None = None
    last_sync_source_kind: str | None = None
    last_sync_started_at: datetime | None = None
    rule_assessment: PanTransferFollowTaskRuleAssessment = Field(default_factory=PanTransferFollowTaskRuleAssessment)
    extra_json: dict = Field(default_factory=dict)
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("publish_record_published_at")
    def serialize_publish_record_published_at(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _serialize_shanghai_local_datetime(value)


class PanTransferFollowTaskListResponse(PanTransferBaseModel):
    items: list[PanTransferFollowTaskItem] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class PanTransferFollowTaskDetailResponse(PanTransferBaseModel):
    task: PanTransferFollowTaskItem
    logs: list[PanTransferFollowTaskLogItem] = Field(default_factory=list)


class PanTransferFollowTaskSyncResponse(PanTransferBaseModel):
    task: PanTransferFollowTaskItem
    batch_id: int
    batch_item_id: int
    started: bool = True


class PanTransferReplacementLogItem(PanTransferBaseModel):
    id: int
    old_link_target_id: int
    new_link_target_id: int | None = None
    old_url: str
    new_url: str | None = None
    affected_message_count: int = 0
    status: str
    operator: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class PanTransferExecutionLogItem(PanTransferBaseModel):
    id: int
    batch_id: int
    batch_item_id: int
    level: str
    stage: str
    message: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class PanTransferBatchItemResponse(PanTransferBaseModel):
    id: int
    batch_id: int
    link_target_id: int
    target_account_id: int | None = None
    target_account_name: str | None = None
    platform: str
    short_title: str
    original_url: str
    current_original_url: str
    source_message_count: int = 0
    source_ref_count: int = 0
    latest_message_title: str | None = None
    source_message_description: str | None = None
    source_message_tags: list[str] = Field(default_factory=list)
    latest_message_time: datetime | None = None
    latest_link_health: str
    transfer_status: str
    share_status: str
    validation_status: str
    replacement_status: str
    attempt_count: int = 0
    max_attempts: int = 0
    next_retry_at: datetime | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_validated_at: datetime | None = None
    new_share_url: str | None = None
    new_link_target_id: int | None = None
    new_link_target_url: str | None = None
    error_message: str | None = None
    extra_json: dict = Field(default_factory=dict)
    execution_logs: list[PanTransferExecutionLogItem] = Field(default_factory=list)
    replacement_logs: list[PanTransferReplacementLogItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PanTransferBatchSummaryItem(PanTransferBaseModel):
    id: int
    batch_type: str
    source_scope: str
    status: str
    created_by: str | None = None
    total_message_count: int = 0
    total_link_target_count: int = 0
    success_item_count: int = 0
    failed_item_count: int = 0
    retry_delay_seconds: int = 600
    active_item_count: int = 0
    request_json: dict = Field(default_factory=dict)
    result_json: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    can_retry: bool = False
    can_delete: bool = False
    can_cancel: bool = False


class PanTransferBatchListResponse(PanTransferBaseModel):
    items: list[PanTransferBatchSummaryItem] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class PanTransferBatchDetailResponse(PanTransferBaseModel):
    batch: PanTransferBatchSummaryItem
    items: list[PanTransferBatchItemResponse] = Field(default_factory=list)


class PanTransferBatchRetryRequest(PanTransferBaseModel):
    item_ids: list[int] = Field(default_factory=list)

    @field_validator("item_ids")
    @classmethod
    def validate_item_ids(cls, value: list[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for raw_value in value:
            try:
                item_id = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("item_ids must contain integers") from exc
            if item_id <= 0 or item_id in seen:
                continue
            seen.add(item_id)
            normalized.append(item_id)
        return normalized
