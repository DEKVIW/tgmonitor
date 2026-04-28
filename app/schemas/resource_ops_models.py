from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer


RESOURCE_OPS_LEGACY_LOCAL_TZ = timezone(timedelta(hours=8))


def _serialize_resource_ops_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _serialize_legacy_local_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=RESOURCE_OPS_LEGACY_LOCAL_TZ)
    else:
        normalized = value.astimezone(RESOURCE_OPS_LEGACY_LOCAL_TZ)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_legacy_local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=RESOURCE_OPS_LEGACY_LOCAL_TZ)
    return value.astimezone(RESOURCE_OPS_LEGACY_LOCAL_TZ)


class ResourceOpsBaseModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={
            datetime: _serialize_resource_ops_datetime,
        }
    )


class ResourceOpsTrackClickRequest(ResourceOpsBaseModel):
    link_ref_id: int = Field(ge=1)
    event_token: str | None = Field(default=None, max_length=64)
    session_key: str | None = Field(default=None, max_length=128)
    source_page: str | None = Field(default=None, max_length=64)
    search_query: str | None = Field(default=None, max_length=255)


class ResourceOpsTrackClickResponse(ResourceOpsBaseModel):
    accepted: bool = True
    event_id: int
    event_token: str | None = None
    link_ref_id: int
    link_target_id: int
    redirect_url: str
    redirect_confirmed: bool = False


class ResourceOpsCatalogStatusResponse(ResourceOpsBaseModel):
    total_messages_with_links: int = 0
    indexed_messages: int = 0
    link_target_count: int = 0
    link_ref_count: int = 0
    cursor_message_id: int = 0
    last_sync_at: str | None = None
    is_fully_synced: bool = False
    has_more: bool = False
    processed_messages: int | None = None
    indexed_links: int | None = None
    changed: bool | None = None
    batch_size: int | None = None


class ResourceOpsOverviewResponse(ResourceOpsBaseModel):
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


class ResourceOpsTrendPoint(ResourceOpsBaseModel):
    date: str
    click_count: int = 0
    unique_sessions: int = 0
    clicked_targets: int = 0


class ResourceOpsTrendResponse(ResourceOpsBaseModel):
    days: list[ResourceOpsTrendPoint]
    days_window: int
    generated_at: datetime


class ResourceOpsPlatformDistributionItem(ResourceOpsBaseModel):
    platform: str
    click_count: int = 0
    unique_sessions: int = 0
    active_targets: int = 0
    percentage: float = 0


class ResourceOpsPlatformDistributionResponse(ResourceOpsBaseModel):
    items: list[ResourceOpsPlatformDistributionItem]
    days_window: int
    generated_at: datetime


class ResourceOpsCandidateItem(ResourceOpsBaseModel):
    link_target_id: int
    platform: str
    display_text: str
    target_url: str
    share_key: str | None = None
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
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_message_time: datetime | None = None
    last_clicked_at: datetime | None = None

    @field_serializer("first_seen_at", "last_seen_at", "last_message_time", when_used="json")
    def serialize_legacy_local_candidate_datetimes(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _serialize_legacy_local_datetime(value)


class ResourceOpsCandidateListResponse(ResourceOpsBaseModel):
    items: list[ResourceOpsCandidateItem]
    total: int
    page: int
    page_size: int


class ResourceOpsCandidateRefItem(ResourceOpsBaseModel):
    message_id: int
    message_title: str = ""
    display_text: str = ""
    channel: str = ""
    source: str = ""
    message_timestamp: datetime | None = None
    links: list[dict[str, Any]] = Field(default_factory=list)

    @field_serializer("message_timestamp", when_used="json")
    def serialize_legacy_local_message_timestamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _serialize_legacy_local_datetime(value)


class ResourceOpsCandidateDetailResponse(ResourceOpsBaseModel):
    item: ResourceOpsCandidateItem
    recent_refs: list[ResourceOpsCandidateRefItem]
    trend: list[ResourceOpsTrendPoint]


class ResourceOpsWorkbenchSummaryResponse(ResourceOpsBaseModel):
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


class ResourceOpsWorkbenchItem(ResourceOpsBaseModel):
    link_target_id: int
    platform: str
    display_text: str
    target_url: str
    share_key: str | None = None
    topic_title: str
    topic_key: str
    topic_link_target_count: int = 1
    topic_message_count: int = 0
    topic_clicks_total: int = 0
    topic_clicks_7d: int = 0
    topic_clicks_30d: int = 0
    topic_platform_count: int = 1
    topic_latest_message_title: str | None = None
    topic_last_clicked_at: datetime | None = None
    topic_last_message_time: datetime | None = None
    topic_last_activity_at: datetime | None = None
    message_ref_count: int = 0
    message_count: int = 0
    recent_ref_count_30d: int = 0
    ref_active_days_30d: int = 0
    clicks_total: int = 0
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
    series_key: str | None = None
    latest_link_health: str
    latest_link_health_label: str
    latest_link_health_reason: str | None = None
    checked_link_target_count: int = 0
    healthy_link_target_count: int = 0
    warning_link_target_count: int = 0
    invalid_link_target_count: int = 0
    unknown_link_target_count: int = 0
    invalid_checks_30d: int = 0
    total_checks_30d: int = 0
    suggested_action: str
    evidence_tags: list[str] = Field(default_factory=list)
    note: str = ""
    updated_by: str | None = None
    profile_updated_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_message_time: datetime | None = None
    last_clicked_at: datetime | None = None
    latest_message_title: str | None = None
    work_id: int | None = None
    work_title: str | None = None
    work_canonical_title: str | None = None
    work_original_title: str | None = None
    work_provider: str | None = None
    work_media_type: str | None = None
    work_release_year: int | None = None
    work_poster_url: str | None = None
    work_detail_url: str | None = None
    work_match_status: str = "pending"
    work_match_status_label: str = "待识别"
    work_match_source: str = "pending"
    work_match_reason: str | None = None
    work_query_title: str | None = None
    work_candidate_title: str | None = None
    work_season_hint: str | int | None = None
    work_year_hint: int | None = None
    work_last_attempted_at: datetime | None = None
    work_matched_at: datetime | None = None

    @field_serializer(
        "first_seen_at",
        "last_seen_at",
        "last_message_time",
        "topic_last_message_time",
        when_used="json",
    )
    def serialize_legacy_local_workbench_datetimes(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _serialize_legacy_local_datetime(value)

    @field_serializer("topic_last_activity_at", when_used="json")
    def serialize_topic_last_activity_at(self, value: datetime | None) -> str | None:
        normalized_click = _normalize_utc_datetime(self.topic_last_clicked_at)
        normalized_message = _normalize_legacy_local_datetime(self.topic_last_message_time)
        candidates = [candidate for candidate in [normalized_click, normalized_message] if candidate is not None]
        if candidates:
            return max(candidates).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if value is None:
            return None
        return _serialize_resource_ops_datetime(value)


class ResourceOpsWorkbenchListResponse(ResourceOpsBaseModel):
    items: list[ResourceOpsWorkbenchItem]
    total: int
    page: int
    page_size: int
    summary: ResourceOpsWorkbenchSummaryResponse


class ResourceOpsWorkbenchLogItem(ResourceOpsBaseModel):
    id: int
    action_type: str
    action_summary: str
    note: str = ""
    operator: str | None = None
    created_at: datetime
    payload: dict[str, object] = Field(default_factory=dict)


class ResourceOpsWorkbenchDetailResponse(ResourceOpsBaseModel):
    item: ResourceOpsWorkbenchItem
    recent_refs: list[ResourceOpsCandidateRefItem]
    trend: list[ResourceOpsTrendPoint]
    logs: list[ResourceOpsWorkbenchLogItem] = Field(default_factory=list)
    auto_reasons: list[str] = Field(default_factory=list)


class ResourceOpsWorkbenchUpdateRequest(ResourceOpsBaseModel):
    operation_status: str | None = None
    value_status: str | None = None
    manual_resource_kind: str | None = None
    note: str | None = None


class ResourceOpsWorkBindingSummaryResponse(ResourceOpsBaseModel):
    total_candidates: int = 0
    matched_count: int = 0
    pending_count: int = 0
    queued_count: int = 0
    processing_count: int = 0
    retry_wait_count: int = 0
    done_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    binding_error_count: int = 0
    match_rate: float = 0


class ResourceOpsRecognitionStatusResponse(ResourceOpsBaseModel):
    worker_state: str = "idle"
    worker_alive: bool = False
    is_running: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    last_heartbeat_at: str | None = None
    last_processed_at: str | None = None
    current_link_target_id: int | None = None
    current_title: str | None = None
    current_source: str | None = None
    last_error: str | None = None
    logs: list[str] = Field(default_factory=list)


class ResourceOpsRuntimeSettingsUpdateRequest(ResourceOpsBaseModel):
    auto_recognition_enabled: bool = False
    retention_click_event_days: int = Field(default=90, ge=7, le=3650)
    retention_daily_stat_days: int = Field(default=365, ge=30, le=3650)
    retention_candidate_log_days: int = Field(default=180, ge=7, le=3650)
    cleanup_interval_hours: int = Field(default=24, ge=1, le=720)


class ResourceOpsRuntimeSettingsResponse(ResourceOpsBaseModel):
    auto_recognition_enabled: bool = False
    ai_route_key: str = ""
    ai_route_ready: bool = False
    ai_route_provider_label: str | None = None
    ai_route_model: str | None = None
    retention_click_event_days: int = 90
    retention_daily_stat_days: int = 365
    retention_candidate_log_days: int = 180
    cleanup_interval_hours: int = 24
    last_sync_at: str | None = None
    last_sync_summary: dict[str, Any] = Field(default_factory=dict)
    last_cleanup_at: str | None = None
    last_cleanup_summary: dict[str, Any] = Field(default_factory=dict)
    recognition_status: ResourceOpsRecognitionStatusResponse
    binding_summary: ResourceOpsWorkBindingSummaryResponse


class ResourceOpsRecognitionRunResponse(ResourceOpsBaseModel):
    accepted: bool = True
    mode: str = "pending"
    message: str = ""
    recognition_status: ResourceOpsRecognitionStatusResponse
    binding_summary: ResourceOpsWorkBindingSummaryResponse


class ResourceOpsRetentionRunResponse(ResourceOpsBaseModel):
    deleted_click_events: int = 0
    deleted_daily_stats: int = 0
    deleted_candidate_logs: int = 0
    deleted_orphan_aliases: int = 0
    deleted_orphan_works: int = 0
    retention_click_event_days: int = 90
    retention_daily_stat_days: int = 365
    retention_candidate_log_days: int = 180
