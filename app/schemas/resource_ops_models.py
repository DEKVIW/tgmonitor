from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ResourceOpsTrackClickRequest(BaseModel):
    link_ref_id: int = Field(ge=1)
    event_token: Optional[str] = Field(default=None, max_length=64)
    session_key: Optional[str] = Field(default=None, max_length=128)
    source_page: Optional[str] = Field(default=None, max_length=64)
    search_query: Optional[str] = Field(default=None, max_length=255)


class ResourceOpsTrackClickResponse(BaseModel):
    accepted: bool = True
    event_id: int
    event_token: Optional[str] = None
    link_ref_id: int
    link_target_id: int
    redirect_url: str
    redirect_confirmed: bool = False


class ResourceOpsCatalogStatusResponse(BaseModel):
    total_messages_with_links: int = 0
    indexed_messages: int = 0
    link_target_count: int = 0
    link_ref_count: int = 0
    cursor_message_id: int = 0
    last_sync_at: Optional[str] = None
    is_fully_synced: bool = False
    has_more: bool = False
    processed_messages: Optional[int] = None
    indexed_links: Optional[int] = None
    changed: Optional[bool] = None
    batch_size: Optional[int] = None


class ResourceOpsOverviewResponse(BaseModel):
    clicks_last_30_days: int = 0
    unique_sessions_last_30_days: int = 0
    unique_users_last_30_days: int = 0
    clicked_targets_last_30_days: int = 0
    search_clicks_last_30_days: int = 0
    unique_link_targets: int = 0
    indexed_link_refs: int = 0
    indexed_messages: int = 0
    total_messages_with_links: int = 0
    high_priority_candidates: int = 0
    generated_at: datetime


class ResourceOpsTrendPoint(BaseModel):
    date: str
    click_count: int = 0
    unique_sessions: int = 0
    clicked_targets: int = 0


class ResourceOpsTrendResponse(BaseModel):
    days: List[ResourceOpsTrendPoint]
    days_window: int
    generated_at: datetime


class ResourceOpsPlatformDistributionItem(BaseModel):
    platform: str
    click_count: int = 0
    unique_sessions: int = 0
    active_targets: int = 0
    percentage: float = 0


class ResourceOpsPlatformDistributionResponse(BaseModel):
    items: List[ResourceOpsPlatformDistributionItem]
    days_window: int
    generated_at: datetime


class ResourceOpsCandidateItem(BaseModel):
    link_target_id: int
    platform: str
    display_text: str
    target_url: str
    share_key: Optional[str] = None
    message_ref_count: int = 0
    message_count: int = 0
    clicks_1d: int = 0
    clicks_3d: int = 0
    clicks_7d: int = 0
    clicks_30d: int = 0
    unique_sessions_30d: int = 0
    unique_users_30d: int = 0
    search_clicks_30d: int = 0
    active_days_30d: int = 0
    burst_ratio: float = 0
    sustained_ratio: float = 0
    heat_type: str
    heat_label: str
    priority: str
    recommendation: str
    score: float = 0
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_message_time: Optional[datetime] = None
    last_clicked_at: Optional[datetime] = None


class ResourceOpsCandidateListResponse(BaseModel):
    items: List[ResourceOpsCandidateItem]
    total: int
    page: int
    page_size: int


class ResourceOpsCandidateRefItem(BaseModel):
    message_id: int
    message_title: str = ""
    display_text: str = ""
    channel: str = ""
    source: str = ""
    message_timestamp: Optional[datetime] = None


class ResourceOpsCandidateDetailResponse(BaseModel):
    item: ResourceOpsCandidateItem
    recent_refs: List[ResourceOpsCandidateRefItem]
    trend: List[ResourceOpsTrendPoint]


class ResourceOpsWorkbenchSummaryResponse(BaseModel):
    total_candidates: int = 0
    pending_review_count: int = 0
    observing_count: int = 0
    ready_to_mirror_count: int = 0
    ignored_count: int = 0
    priority_count: int = 0
    worth_count: int = 0
    rolling_count: int = 0
    fixed_count: int = 0
    risky_count: int = 0
    generated_at: datetime


class ResourceOpsWorkbenchItem(BaseModel):
    link_target_id: int
    platform: str
    display_text: str
    target_url: str
    share_key: Optional[str] = None
    topic_title: str
    topic_key: str
    topic_link_target_count: int = 1
    topic_message_count: int = 0
    topic_clicks_7d: int = 0
    topic_clicks_30d: int = 0
    topic_platform_count: int = 1
    topic_latest_message_title: Optional[str] = None
    topic_last_clicked_at: Optional[datetime] = None
    topic_last_message_time: Optional[datetime] = None
    topic_last_activity_at: Optional[datetime] = None
    message_ref_count: int = 0
    message_count: int = 0
    recent_ref_count_30d: int = 0
    ref_active_days_30d: int = 0
    clicks_1d: int = 0
    clicks_3d: int = 0
    clicks_7d: int = 0
    clicks_30d: int = 0
    unique_sessions_30d: int = 0
    unique_users_30d: int = 0
    search_clicks_30d: int = 0
    active_days_30d: int = 0
    heat_type: str
    heat_label: str
    demand_score: float = 0
    value_score: float = 0
    cost_score: float = 0
    risk_score: float = 0
    overall_score: float = 0
    auto_value_status: str
    auto_value_status_label: str
    effective_value_status: str
    effective_value_status_label: str
    value_status_source: str
    operation_status: str
    operation_status_label: str
    auto_resource_kind: str
    auto_resource_kind_label: str
    effective_resource_kind: str
    effective_resource_kind_label: str
    resource_kind_source: str
    update_mode: str
    update_mode_label: str
    update_confidence: float = 0
    series_key: Optional[str] = None
    latest_link_health: str
    latest_link_health_label: str
    latest_link_health_reason: Optional[str] = None
    invalid_checks_30d: int = 0
    total_checks_30d: int = 0
    suggested_action: str
    evidence_tags: List[str] = Field(default_factory=list)
    note: str = ""
    updated_by: Optional[str] = None
    profile_updated_at: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_message_time: Optional[datetime] = None
    last_clicked_at: Optional[datetime] = None
    latest_message_title: Optional[str] = None


class ResourceOpsWorkbenchListResponse(BaseModel):
    items: List[ResourceOpsWorkbenchItem]
    total: int
    page: int
    page_size: int
    summary: ResourceOpsWorkbenchSummaryResponse


class ResourceOpsWorkbenchLogItem(BaseModel):
    id: int
    action_type: str
    action_summary: str
    note: str = ""
    operator: Optional[str] = None
    created_at: datetime
    payload: Dict[str, object] = Field(default_factory=dict)


class ResourceOpsWorkbenchDetailResponse(BaseModel):
    item: ResourceOpsWorkbenchItem
    recent_refs: List[ResourceOpsCandidateRefItem]
    trend: List[ResourceOpsTrendPoint]
    logs: List[ResourceOpsWorkbenchLogItem] = Field(default_factory=list)
    auto_reasons: List[str] = Field(default_factory=list)


class ResourceOpsWorkbenchUpdateRequest(BaseModel):
    operation_status: Optional[str] = None
    value_status: Optional[str] = None
    manual_resource_kind: Optional[str] = None
    note: Optional[str] = None
