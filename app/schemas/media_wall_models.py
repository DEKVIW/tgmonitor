from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class MediaWallCategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    is_enabled: bool
    show_in_tabs: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MediaWallCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, max_length=160)
    sort_order: int = Field(default=0, ge=-100000, le=100000)
    is_enabled: bool = True


class MediaWallCategoryUpdateRequest(MediaWallCategoryCreateRequest):
    is_enabled: bool = True


class MediaWallProgressResponse(BaseModel):
    episode: Optional[int] = None
    label: str
    task_state: Optional[str] = None
    share_status: Optional[str] = None
    last_checked_at: Optional[datetime] = None


class MediaWallLinkResponse(BaseModel):
    id: int
    platform: str
    url: str
    label: Optional[str] = None
    is_primary: bool
    is_enabled: bool
    source_type: str
    last_checked_at: Optional[datetime] = None
    last_status: str
    invalid_streak: int = 0
    next_check_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class MediaWallLinkHealthResponse(BaseModel):
    total: int = 0
    enabled: int = 0
    valid: int = 0
    invalid: int = 0
    pending: int = 0
    uncertain: int = 0
    status: str = "no_links"


class MediaWallLinkCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4000)
    label: Optional[str] = Field(default=None, max_length=120)
    source_type: str = Field(default="manual", max_length=32)
    is_primary: bool = False


class MediaWallLinkUpdateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4000)
    label: Optional[str] = Field(default=None, max_length=120)
    is_enabled: bool = True
    is_primary: bool = False


class MediaWallLinkSyncRequest(MediaWallLinkUpdateRequest):
    id: Optional[int] = None
    source_type: str = Field(default="manual", max_length=32)


class MediaWallItemResponse(BaseModel):
    id: int
    display_title: str
    metadata_query_title: Optional[str] = None
    visibility: str
    sort_order: int
    poster_url: Optional[str] = None
    type_name: Optional[str] = None
    year: Optional[str] = None
    area: Optional[str] = None
    remarks: Optional[str] = None
    summary: Optional[str] = None
    director: Optional[str] = None
    actor: Optional[str] = None
    progress: MediaWallProgressResponse
    links: list[MediaWallLinkResponse]
    link_health: MediaWallLinkHealthResponse
    link_count: int
    categories: list[MediaWallCategoryResponse]
    sync_task_id: Optional[int] = None
    metadata_status: str = "not_synced"
    metadata_last_synced_at: Optional[datetime] = None
    metadata_last_error: Optional[str] = None
    last_content_updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MediaWallItemListResponse(BaseModel):
    items: list[MediaWallItemResponse]
    total: int
    page: int
    page_size: int


class MediaWallItemCreateRequest(BaseModel):
    display_title: str = Field(min_length=1, max_length=255)
    metadata_query_title: Optional[str] = Field(default=None, max_length=255)
    visibility: str = Field(default="public", max_length=32)
    sort_order: int = Field(default=0, ge=-100000, le=100000)
    category_ids: list[int] = Field(default_factory=list)
    sync_task_id: Optional[int] = None
    custom_poster_url: Optional[str] = Field(default=None, max_length=1000)
    links: list[MediaWallLinkCreateRequest] = Field(default_factory=list)


class MediaWallItemUpdateRequest(BaseModel):
    display_title: str = Field(min_length=1, max_length=255)
    metadata_query_title: Optional[str] = Field(default=None, max_length=255)
    visibility: str = Field(default="public", max_length=32)
    sort_order: int = Field(default=0, ge=-100000, le=100000)
    category_ids: list[int] = Field(default_factory=list)
    sync_task_id: Optional[int] = None
    custom_poster_url: Optional[str] = Field(default=None, max_length=1000)
    links: Optional[list[MediaWallLinkSyncRequest]] = None


class MediaWallItemBulkDeleteRequest(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=500)


class MediaWallItemBulkDeleteResponse(BaseModel):
    deleted_ids: list[int]
    deleted_count: int


class MediaWallMetadataSyncResponse(BaseModel):
    status: str
    queued_count: int
    skipped_count: int


class MediaWallSourceResponse(BaseModel):
    id: int
    name: str
    source_url: str
    source_type: str
    is_enabled: bool
    priority: int
    timeout_seconds: int
    last_checked_at: Optional[datetime] = None
    last_refreshed_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    endpoint_count: int = 0


class MediaWallSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_url: str = Field(min_length=1, max_length=4000)
    source_type: str = Field(default="source-list", max_length=32)
    is_enabled: bool = True
    priority: int = Field(default=100, ge=0, le=100000)
    timeout_seconds: int = Field(default=8, ge=2, le=20)


class MediaWallSourceTestResponse(BaseModel):
    source: MediaWallSourceResponse
    ok: bool
    endpoint_count: int = 0
    error: Optional[str] = None


class MediaWallSyncTaskResponse(BaseModel):
    id: int
    task_name: str
    work_title: Optional[str] = None
    topic_title: str
    status: str
    task_state: str
    current_share_url: Optional[str] = None
    current_share_status: str
    progress: MediaWallProgressResponse


class MediaWallImportPreviewResponse(BaseModel):
    id: int
    filename: str
    status: str
    records: list[dict[str, Any]]
    invalid_rows: list[dict[str, Any]]
    total_records: int
    total_links: int
    invalid_count: int


class MediaWallImportConfirmRequest(BaseModel):
    category_ids: list[int] = Field(default_factory=list)
    visibility: str = Field(default="public", max_length=32)


class MediaWallImportConfirmResponse(BaseModel):
    job_id: int
    status: str
    created_count: int
    updated_count: int
    link_count: int
