export interface ResourceOpsOverviewResponse {
  clicks_last_30_days: number
  unique_sessions_last_30_days: number
  unique_users_last_30_days: number
  clicked_targets_last_30_days: number
  search_clicks_last_30_days: number
  unique_link_targets: number
  indexed_link_refs: number
  indexed_messages: number
  total_messages_with_links: number
  high_priority_candidates: number
  generated_at: string
}

export interface ResourceOpsTrendPoint {
  date: string
  click_count: number
  unique_sessions: number
  clicked_targets: number
}

export interface ResourceOpsTrendResponse {
  days: ResourceOpsTrendPoint[]
  days_window: number
  generated_at: string
}

export interface ResourceOpsPlatformDistributionItem {
  platform: string
  click_count: number
  unique_sessions: number
  active_targets: number
  percentage: number
}

export interface ResourceOpsPlatformDistributionResponse {
  items: ResourceOpsPlatformDistributionItem[]
  days_window: number
  generated_at: string
}

export interface ResourceOpsCandidateItem {
  link_target_id: number
  platform: string
  display_text: string
  target_url: string
  share_key?: string | null
  message_ref_count: number
  message_count: number
  clicks_1d: number
  clicks_3d: number
  clicks_7d: number
  clicks_30d: number
  unique_sessions_30d: number
  unique_users_30d: number
  search_clicks_30d: number
  active_days_30d: number
  burst_ratio: number
  sustained_ratio: number
  heat_type: 'burst' | 'sustained' | 'watch' | 'cold' | string
  heat_label: string
  priority: 'high' | 'medium' | 'watch' | string
  recommendation: string
  score: number
  first_seen_at?: string | null
  last_seen_at?: string | null
  last_message_time?: string | null
  last_clicked_at?: string | null
}

export interface ResourceOpsCandidateListResponse {
  items: ResourceOpsCandidateItem[]
  total: number
  page: number
  page_size: number
}

export interface ResourceOpsCandidateRefItem {
  message_id: number
  message_title: string
  display_text: string
  channel: string
  source: string
  message_timestamp?: string | null
}

export interface ResourceOpsCandidateDetailResponse {
  item: ResourceOpsCandidateItem
  recent_refs: ResourceOpsCandidateRefItem[]
  trend: ResourceOpsTrendPoint[]
}

export interface ResourceOpsCatalogStatusResponse {
  total_messages_with_links: number
  indexed_messages: number
  link_target_count: number
  link_ref_count: number
  cursor_message_id: number
  last_sync_at?: string | null
  is_fully_synced: boolean
  has_more: boolean
  processed_messages?: number | null
  indexed_links?: number | null
  changed?: boolean | null
  batch_size?: number | null
}

export interface ResourceOpsCandidateQuery {
  page?: number
  page_size?: number
  platform?: string
  heat_type?: string
  keyword?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export type ResourceOpsOperationStatus = 'pending_review' | 'observing' | 'ready_to_mirror' | 'ignored'
export type ResourceOpsValueStatus = 'unreviewed' | 'not_worth' | 'observe' | 'worth' | 'priority'
export type ResourceOpsResourceKind = 'unknown' | 'fixed' | 'rolling' | 'stopped'
export type ResourceOpsHealthStatus = 'healthy' | 'warning' | 'invalid' | 'unknown'

export interface ResourceOpsWorkbenchSummary {
  total_candidates: number
  pending_review_count: number
  observing_count: number
  ready_to_mirror_count: number
  ignored_count: number
  priority_count: number
  worth_count: number
  rolling_count: number
  fixed_count: number
  risky_count: number
  generated_at: string
}

export interface ResourceOpsWorkbenchItem {
  link_target_id: number
  platform: string
  display_text: string
  target_url: string
  share_key?: string | null
  topic_title: string
  topic_key: string
  topic_link_target_count: number
  topic_message_count: number
  topic_clicks_7d: number
  topic_clicks_30d: number
  topic_platform_count: number
  topic_latest_message_title?: string | null
  topic_last_clicked_at?: string | null
  topic_last_message_time?: string | null
  topic_last_activity_at?: string | null
  message_ref_count: number
  message_count: number
  recent_ref_count_30d: number
  ref_active_days_30d: number
  clicks_1d: number
  clicks_3d: number
  clicks_7d: number
  clicks_30d: number
  unique_sessions_30d: number
  unique_users_30d: number
  search_clicks_30d: number
  active_days_30d: number
  heat_type: string
  heat_label: string
  demand_score: number
  value_score: number
  cost_score: number
  risk_score: number
  overall_score: number
  auto_value_status: ResourceOpsValueStatus | string
  auto_value_status_label: string
  effective_value_status: ResourceOpsValueStatus | string
  effective_value_status_label: string
  value_status_source: 'auto' | 'manual' | string
  operation_status: ResourceOpsOperationStatus | string
  operation_status_label: string
  auto_resource_kind: ResourceOpsResourceKind | string
  auto_resource_kind_label: string
  effective_resource_kind: ResourceOpsResourceKind | string
  effective_resource_kind_label: string
  resource_kind_source: 'auto' | 'manual' | string
  update_mode: string
  update_mode_label: string
  update_confidence: number
  series_key?: string | null
  latest_link_health: ResourceOpsHealthStatus | string
  latest_link_health_label: string
  latest_link_health_reason?: string | null
  invalid_checks_30d: number
  total_checks_30d: number
  suggested_action: string
  evidence_tags: string[]
  note: string
  updated_by?: string | null
  profile_updated_at?: string | null
  first_seen_at?: string | null
  last_seen_at?: string | null
  last_message_time?: string | null
  last_clicked_at?: string | null
  latest_message_title?: string | null
}

export interface ResourceOpsWorkbenchListResponse {
  items: ResourceOpsWorkbenchItem[]
  total: number
  page: number
  page_size: number
  summary: ResourceOpsWorkbenchSummary
}

export interface ResourceOpsWorkbenchLogItem {
  id: number
  action_type: string
  action_summary: string
  note: string
  operator?: string | null
  created_at: string
  payload: Record<string, any>
}

export interface ResourceOpsWorkbenchDetailResponse {
  item: ResourceOpsWorkbenchItem
  recent_refs: ResourceOpsCandidateRefItem[]
  trend: ResourceOpsTrendPoint[]
  logs: ResourceOpsWorkbenchLogItem[]
  auto_reasons: string[]
}

export interface ResourceOpsWorkbenchQuery {
  page?: number
  page_size?: number
  platform?: string
  heat_type?: string
  operation_status?: ResourceOpsOperationStatus | string
  value_status?: ResourceOpsValueStatus | string
  resource_kind?: ResourceOpsResourceKind | string
  health_status?: ResourceOpsHealthStatus | string
  keyword?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface ResourceOpsWorkbenchUpdateRequest {
  operation_status?: ResourceOpsOperationStatus | string
  value_status?: ResourceOpsValueStatus | string
  manual_resource_kind?: Exclude<ResourceOpsResourceKind, 'unknown'> | '' | null
  note?: string
}
