from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


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
    platforms: list[str] = Field(default_factory=list)
    health_filter: str = Field(default="all", min_length=1, max_length=32)
    only_healthy: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

    @field_validator("selection_mode", "direction", "health_filter")
    @classmethod
    def validate_mode_fields(cls, value: str, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("range_start", "range_end")
    @classmethod
    def validate_optional_dates(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _normalize_text(value, field_name=info.field_name)

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
    page_size: int = 50
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
