from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LearningCategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    sort_order: int = 0
    resource_count: int = 0


class LearningResourceResponse(BaseModel):
    id: int
    display_title: str
    category: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    share_url: str
    platform: str
    updated_at: datetime | None = None
    created_at: datetime | None = None


class LearningResourceListResponse(BaseModel):
    items: list[LearningResourceResponse]
    total: int
    page: int = 1
    page_size: int = 50


class LearningChannelAdminResponse(BaseModel):
    channel_id: int
    channel_key: str
    channel_title: str
    config_id: int | None = None
    is_enabled: bool = False
    target_account_id: int | None = None
    save_root: str = ""
    backfill_policy: str = "new_messages_only"
    last_processed_message_id: int | None = None
    last_error_message: str | None = None


class LearningAccountAdminResponse(BaseModel):
    id: int
    platform: str
    account_name: str
    default_save_root: str
    is_enabled: bool


class LearningCategoryAdminResponse(BaseModel):
    id: int
    name: str
    slug: str
    directory_name: str
    is_enabled: bool
    show_in_tabs: bool
    sort_order: int
    resource_count: int = 0


class LearningAdminOverviewResponse(BaseModel):
    channels: list[LearningChannelAdminResponse]
    accounts: list[LearningAccountAdminResponse]
    categories: list[LearningCategoryAdminResponse]


class LearningChannelUpdateRequest(BaseModel):
    is_enabled: bool | None = None
    target_account_id: int | None = Field(default=None, ge=1)
    save_root: str | None = Field(default=None, max_length=255)
    channel_title: str | None = Field(default=None, max_length=255)


class LearningChannelUpdateResponse(BaseModel):
    channel_id: int
    channel_key: str
    config_id: int
    is_enabled: bool
    target_account_id: int | None = None
    save_root: str = ""


class LearningResourceAdminResponse(BaseModel):
    id: int
    display_title: str
    status: str
    category: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    share_url: str | None = None
    platform: str = ""
    source_channel_key: str = ""
    latest_source_at: datetime | None = None
    updated_at: datetime | None = None


class LearningResourceAdminListResponse(BaseModel):
    items: list[LearningResourceAdminResponse]
    total: int
    page: int = 1
    page_size: int = 50


class LearningResourceVisibilityRequest(BaseModel):
    visible: bool


class LearningResourceUpdateRequest(BaseModel):
    display_title: str = Field(min_length=1, max_length=255)
    category: str = Field(default="待分类", max_length=120)
    tags: list[str] = Field(default_factory=list)
    share_url: str = Field(default="", max_length=2048)


class LearningResourceDeleteResponse(BaseModel):
    deleted_resources: int = 0
    deleted_links: int = 0
    deleted_transfer_jobs: int = 0
    deleted_import_jobs: int = 0
    deleted_batches: int = 0
    deleted_categories: int = 0


class LearningDirectoryResponse(BaseModel):
    id: str
    name: str
    is_dir: bool = True


class LearningDirectoryListResponse(BaseModel):
    account_id: int
    parent_id: str
    items: list[LearningDirectoryResponse]


class LearningImportPreviewResponse(BaseModel):
    id: int
    filename: str
    status: str
    records: list[dict[str, Any]] = Field(default_factory=list)
    invalid_rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    valid_count: int = 0
    total_records: int = 0
    total_links: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0


class LearningImportConfirmRequest(BaseModel):
    mode: str = Field(default="direct", min_length=1, max_length=32)
    target_account_id: int | None = Field(default=None, ge=1)
    save_root: str | None = Field(default=None, max_length=255)


class LearningImportConfirmResponse(BaseModel):
    job_id: int
    status: str
    mode: str
    created_count: int = 0
    link_count: int = 0
    queued_count: int = 0
    batch_id: int | None = None
