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
    work_id: Optional[int] = None
    work_title: Optional[str] = None
    work_canonical_title: Optional[str] = None
    work_original_title: Optional[str] = None
    work_provider: Optional[str] = None
    work_media_type: Optional[str] = None
    work_release_year: Optional[int] = None
    work_poster_url: Optional[str] = None
    work_detail_url: Optional[str] = None
    work_match_status: str = "pending"
    work_match_status_label: str = "待识别"
    work_match_source: str = "pending"
    work_confidence: float = 0
    work_match_reason: Optional[str] = None
    work_query_title: Optional[str] = None
    work_candidate_title: Optional[str] = None
    work_season_hint: Optional[str] = None
    work_year_hint: Optional[int] = None
    work_last_attempted_at: Optional[datetime] = None
    work_matched_at: Optional[datetime] = None


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


class ResourceOpsWorkBindingSummaryResponse(BaseModel):
    total_tracked_targets: int = 0
    matched_count: int = 0
    pending_count: int = 0
    no_match_count: int = 0
    low_confidence_count: int = 0
    error_count: int = 0
    match_rate: float = 0


class ResourceOpsRuntimeSettingsUpdateRequest(BaseModel):
    auto_bind_enabled: bool = False
    sync_batch_size: int = Field(default=12, ge=1, le=100)
    sync_interval_minutes: int = Field(default=30, ge=5, le=1440)
    min_confidence: float = Field(default=0.72, ge=0.4, le=0.99)
    retry_cooldown_hours: int = Field(default=24, ge=1, le=720)
    tmdb_enabled: bool = False
    tmdb_language: str = Field(default="zh-CN", max_length=32)
    tmdb_api_key: Optional[str] = Field(default=None, max_length=512)
    tmdb_read_access_token: Optional[str] = Field(default=None, max_length=4096)
    bangumi_enabled: bool = False
    bangumi_user_agent: str = Field(default="TGMonitor/1.0", max_length=255)
    retention_click_event_days: int = Field(default=90, ge=7, le=3650)
    retention_daily_stat_days: int = Field(default=365, ge=30, le=3650)
    retention_candidate_log_days: int = Field(default=180, ge=7, le=3650)
    cleanup_interval_hours: int = Field(default=24, ge=1, le=720)


class ResourceOpsRuntimeSettingsResponse(BaseModel):
    auto_bind_enabled: bool = False
    sync_batch_size: int = 12
    sync_interval_minutes: int = 30
    min_confidence: float = 0.72
    retry_cooldown_hours: int = 24
    tmdb_enabled: bool = False
    tmdb_language: str = "zh-CN"
    tmdb_api_key_configured: bool = False
    tmdb_read_access_token_configured: bool = False
    tmdb_provider_ready: bool = False
    bangumi_enabled: bool = False
    bangumi_user_agent: str = "TGMonitor/1.0"
    bangumi_provider_ready: bool = False
    retention_click_event_days: int = 90
    retention_daily_stat_days: int = 365
    retention_candidate_log_days: int = 180
    cleanup_interval_hours: int = 24
    last_sync_at: Optional[str] = None
    last_sync_summary: Dict[str, Any] = Field(default_factory=dict)
    last_cleanup_at: Optional[str] = None
    last_cleanup_summary: Dict[str, Any] = Field(default_factory=dict)
    binding_summary: ResourceOpsWorkBindingSummaryResponse


class ResourceOpsRecognitionRunResponse(BaseModel):
    processed_count: int = 0
    matched_count: int = 0
    no_match_count: int = 0
    low_confidence_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    started_at: str
    finished_at: str
    items: List[Dict[str, Any]] = Field(default_factory=list)
    binding_summary: ResourceOpsWorkBindingSummaryResponse


class ResourceOpsRetentionRunResponse(BaseModel):
    deleted_click_events: int = 0
    deleted_daily_stats: int = 0
    deleted_candidate_logs: int = 0
    deleted_orphan_aliases: int = 0
    deleted_orphan_works: int = 0
    retention_click_event_days: int = 90
    retention_daily_stat_days: int = 365
    retention_candidate_log_days: int = 180
