export interface PanTransferAccountItem {
  id: number
  platform: string
  account_name: string
  auth_type: string
  default_save_root: string
  default_share_mode: 'private' | 'public' | string
  default_share_passcode?: string | null
  default_share_expire_days?: number | null
  is_enabled: boolean
  is_default: boolean
  credential_configured: boolean
  last_validated_at?: string | null
  last_error_message?: string | null
  created_at: string
  updated_at: string
}

export interface PanTransferAccountListResponse {
  items: PanTransferAccountItem[]
  total: number
}

export interface PanTransferAccountCreateRequest {
  platform: string
  account_name: string
  auth_type: string
  credential_value: string
  default_save_root?: string
  default_share_mode?: 'private' | 'public' | string
  default_share_passcode?: string | null
  default_share_expire_days?: number | null
  is_enabled?: boolean
  is_default?: boolean
}

export interface PanTransferAccountUpdateRequest {
  platform?: string
  account_name?: string
  auth_type?: string
  credential_value?: string | null
  clear_credential?: boolean
  default_save_root?: string
  default_share_mode?: 'private' | 'public' | string
  default_share_passcode?: string | null
  default_share_expire_days?: number | null
  is_enabled?: boolean
  is_default?: boolean
}

export interface PanTransferDeleteResponse {
  id: number
  platform: string
  deleted: boolean
}

export interface PanTransferPreviewItem {
  link_target_id: number
  platform: string
  short_title: string
  original_url: string
  share_key?: string | null
  latest_link_health: 'healthy' | 'invalid' | 'unknown' | string
  latest_link_health_label: string
  latest_link_health_reason?: string | null
  impact_message_count: number
  source_ref_count: number
  latest_message_time?: string | null
  latest_message_title?: string | null
  work_title?: string | null
  recommended_account_id?: number | null
  recommended_account_name?: string | null
}

export interface PanTransferManualPreviewRequest {
  selection_mode: 'recent_messages' | 'time_range' | string
  direction: 'newest_first' | 'oldest_first' | string
  recent_message_count?: number | null
  range_start?: string | null
  range_end?: string | null
  search_keyword?: string | null
  platforms?: string[]
  health_filter?: 'all' | 'healthy_only' | 'exclude_invalid' | string
  only_healthy?: boolean
  page?: number
  page_size?: number
}

export interface PanTransferManualPreviewResponse {
  selection_mode: string
  direction: string
  requested_message_count?: number | null
  effective_message_count: number
  truncated: boolean
  range_start?: string | null
  range_end?: string | null
  platforms: string[]
  health_filter: string
  only_healthy: boolean
  matched_link_ref_count: number
  unique_link_target_count: number
  healthy_count: number
  invalid_count: number
  unknown_count: number
  page: number
  page_size: number
  total: number
  can_start: boolean
  items: PanTransferPreviewItem[]
}

export interface PanTransferAccountValidationResponse {
  account_id: number
  platform: string
  account_name: string
  ok: boolean
  checked_at: string
  detail_message: string
  remote_user?: string | null
  payload: Record<string, unknown>
}

export interface PanTransferBatchCreateRequest extends PanTransferManualPreviewRequest {
  selected_link_target_ids?: number[]
  start_immediately?: boolean
  max_attempts?: number | null
  retry_delay_seconds?: number | null
  target_account_ids_by_platform?: Record<string, number>
  transfer_layout?: 'independent' | 'batch_archive' | string
  batch_folder_name?: string | null
  item_folder_mode?: 'auto' | 'custom' | string
  item_folder_template?: string | null
  share_target_mode?: 'resource_dir' | 'content_root' | string
}

export interface PanTransferMessagePublishRequest {
  title: string
  description?: string | null
  tags?: string[]
}

export interface PanTransferMessagePublishResponse {
  message_id: number
  title: string
  source_url: string
  link_target_id?: number | null
  published_at: string
  reused_existing_target: boolean
}

export interface PanTransferManualPublishRequest {
  platform: string
  source_url: string
  title: string
  description?: string | null
  tags?: string[]
}

export interface PanTransferLinkDirectoryPreviewRequest {
  url: string
  entry_id?: string | null
  entry_path?: string | null
  entry_name?: string | null
}

export interface PanTransferLinkDirectoryEntry {
  name: string
  is_dir: boolean
  size_bytes?: number | null
  updated_at?: string | null
  entry_id?: string | null
  path?: string | null
}

export interface PanTransferLinkDirectoryPreviewResponse {
  url: string
  platform: string
  supported: boolean
  item_count: number
  truncated: boolean
  current_entry_id?: string | null
  current_path?: string | null
  current_name?: string | null
  message?: string | null
  items: PanTransferLinkDirectoryEntry[]
}

export interface PanTransferPublishRecordItem {
  id: number
  source_type: string
  source_batch_id?: number | null
  source_batch_item_id?: number | null
  source_link_target_id?: number | null
  source_new_link_target_id?: number | null
  platform: string
  source_url: string
  source_original_url?: string | null
  current_share_url?: string | null
  published_link_target_id?: number | null
  published_message_id?: number | null
  published_title: string
  published_description?: string | null
  published_tags: string[]
  original_link_status?: string | null
  original_link_detail_message?: string | null
  original_link_checked_at?: string | null
  current_share_status?: string | null
  current_share_detail_message?: string | null
  current_share_checked_at?: string | null
  published_link_status?: string | null
  published_link_detail_message?: string | null
  published_link_checked_at?: string | null
  published_clicks_total: number
  publish_count: number
  can_refresh_share: boolean
  can_offline: boolean
  can_reclaim: boolean
  can_republish: boolean
  frontend_online: boolean
  can_edit: boolean
  operator?: string | null
  is_archived: boolean
  archived_at?: string | null
  lifecycle_state: string
  lifecycle_label?: string | null
  lifecycle_summary?: string | null
  retired_at?: string | null
  resource_path?: string | null
  resource_account_name?: string | null
  publish_rule_enabled: boolean
  publish_rule_summary?: string | null
  next_publish_at?: string | null
  extra_json: Record<string, unknown>
  published_at: string
  created_at: string
  updated_at: string
}

export interface PanTransferPublishRecordListResponse {
  items: PanTransferPublishRecordItem[]
  page: number
  page_size: number
  total: number
}

export interface PanTransferPublishRecordUpdateRequest {
  source_url: string
  title: string
  description?: string | null
  tags?: string[]
}

export interface PanTransferPublishRetireRequest {
  mode: 'archive' | 'offline_frontend' | 'reclaim_resource' | string
}

export interface PanTransferPublishRuleUpdateRequest {
  enabled: boolean
  weekdays: number[]
  time_of_day?: string | null
  timezone?: string
}

export interface PanTransferFollowTaskCreateRequest {
  task_name?: string | null
  check_interval_minutes?: number | null
  candidate_policy?: PanTransferFollowTaskCandidatePolicy | null
  automation?: Record<string, unknown>
}

export interface PanTransferFollowTaskCandidatePolicy {
  lookback_days: number
  max_recall_candidates: number
  max_judge_candidates: number
}

export interface PanTransferFollowTaskSettingsUpdateRequest {
  check_interval_minutes?: number | null
  candidate_policy?: Partial<PanTransferFollowTaskCandidatePolicy> | null
}

export interface PanTransferFollowTaskSyncSelectionEntry {
  name: string
  is_dir: boolean
  entry_id?: string | null
  path?: string | null
}

export interface PanTransferFollowTaskSyncRequest {
  source_kind?: 'current' | 'candidate' | string
  sync_mode?: 'standard' | 'incremental' | 'replace_all' | string
  selected_entries?: PanTransferFollowTaskSyncSelectionEntry[]
  selection_parent_entry_id?: string | null
  selection_parent_path?: string | null
  selection_parent_name?: string | null
  confirm_full_replace?: boolean
  reuse_existing_share_if_valid?: boolean
  update_publish_record?: boolean
}

export interface PanTransferFollowTaskLogItem {
  id: number
  task_id: number
  level: string
  stage: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export interface PanTransferFollowTaskIdentitySnapshot {
  resource_title?: string | null
  core_title?: string | null
  aliases: string[]
  release_year?: number | null
  season?: number | null
  latest_episode?: number | null
  content_type?: string | null
  search_queries: string[]
  reference_titles: string[]
  reference_message_time?: string | null
  reason?: string | null
  source?: string | null
  identity_error?: string | null
  used_model?: string | null
  used_api_mode?: string | null
  updated_at?: string | null
}

export interface PanTransferFollowTaskCandidateRecallItem {
  link_target_id?: number | null
  message_id?: number | null
  link_ref_id?: number | null
  link_index?: number | null
  title?: string | null
  url?: string | null
  latest_message_time?: string | null
}

export interface PanTransferFollowTaskCandidateRecall {
  queries: string[]
  recall_count: number
  judge_limit: number
  selected_link_target_id?: number | null
  items: PanTransferFollowTaskCandidateRecallItem[]
}

export interface PanTransferFollowTaskCandidateAssessment {
  is_same_work?: boolean | null
  is_newer?: boolean | null
  should_promote?: boolean | null
  confidence?: number | null
  current_episode?: number | null
  candidate_episode?: number | null
  reason?: string | null
  judge_source?: string | null
  used_model?: string | null
  used_api_mode?: string | null
  judge_error?: string | null
  checked_at?: string | null
  candidate_link_target_id?: number | null
  candidate_title?: string | null
  recall_count: number
  queries: string[]
  validation_status?: string | null
  validation_detail_message?: string | null
}

export interface PanTransferFollowTaskRuleAssessment {
  rule_key: string
  rule_label: string
  summary: string
  recommended_source_kind?: string | null
  recommended_sync_mode?: string | null
  execution_mode: string
  risk_level: string
  requires_manual_confirmation: boolean
  can_execute: boolean
}

export interface PanTransferFollowTaskItem {
  id: number
  task_name: string
  status: string
  task_state: string
  platform: string
  source_batch_id?: number | null
  source_batch_item_id?: number | null
  source_link_target_id?: number | null
  source_url: string
  source_share_key?: string | null
  source_message_title?: string | null
  topic_key: string
  topic_title: string
  work_id?: number | null
  work_title?: string | null
  publish_record_id?: number | null
  publish_record_title?: string | null
  publish_record_message_id?: number | null
  publish_record_published_at?: string | null
  publish_record_source_url?: string | null
  target_account_id?: number | null
  target_account_name?: string | null
  fixed_save_path: string
  transfer_layout: string
  batch_folder_name?: string | null
  item_folder_mode: string
  item_folder_template?: string | null
  share_target_mode: string
  current_share_url?: string | null
  current_share_link_target_id?: number | null
  source_link_status: string
  current_share_status: string
  last_change_type?: string | null
  last_candidate_link_target_id?: number | null
  last_candidate_url?: string | null
  last_candidate_title?: string | null
  last_candidate_message_time?: string | null
  check_interval_minutes: number
  last_checked_at?: string | null
  next_check_at?: string | null
  locked_by?: string | null
  locked_at?: string | null
  last_error_message?: string | null
  last_sync_batch_id?: number | null
  last_sync_batch_item_id?: number | null
  last_sync_source_kind?: string | null
  last_sync_started_at?: string | null
  rule_assessment: PanTransferFollowTaskRuleAssessment
  identity_snapshot: PanTransferFollowTaskIdentitySnapshot
  candidate_assessment: PanTransferFollowTaskCandidateAssessment
  candidate_recall: PanTransferFollowTaskCandidateRecall
  candidate_policy: PanTransferFollowTaskCandidatePolicy
  extra_json: Record<string, unknown>
  created_by?: string | null
  updated_by?: string | null
  created_at: string
  updated_at: string
}

export interface PanTransferFollowTaskListResponse {
  items: PanTransferFollowTaskItem[]
  page: number
  page_size: number
  total: number
}

export interface PanTransferFollowTaskDetailResponse {
  task: PanTransferFollowTaskItem
  logs: PanTransferFollowTaskLogItem[]
}

export interface PanTransferFollowTaskSyncResponse {
  task: PanTransferFollowTaskItem
  batch_id: number
  batch_item_id: number
  started: boolean
}

export interface PanTransferReplacementLogItem {
  id: number
  old_link_target_id: number
  new_link_target_id?: number | null
  old_url: string
  new_url?: string | null
  affected_message_count: number
  status: string
  operator?: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface PanTransferExecutionLogItem {
  id: number
  batch_id: number
  batch_item_id: number
  level: string
  stage: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export interface PanTransferBatchItem {
  id: number
  batch_id: number
  link_target_id: number
  target_account_id?: number | null
  target_account_name?: string | null
  platform: string
  short_title: string
  original_url: string
  current_original_url: string
  source_message_count: number
  source_ref_count: number
  latest_message_title?: string | null
  source_message_description?: string | null
  source_message_tags: string[]
  latest_message_time?: string | null
  latest_link_health: string
  transfer_status: string
  share_status: string
  validation_status: string
  replacement_status: string
  attempt_count: number
  max_attempts: number
  next_retry_at?: string | null
  locked_by?: string | null
  locked_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  last_validated_at?: string | null
  new_share_url?: string | null
  new_link_target_id?: number | null
  new_link_target_url?: string | null
  error_message?: string | null
  extra_json: Record<string, unknown>
  execution_logs: PanTransferExecutionLogItem[]
  replacement_logs: PanTransferReplacementLogItem[]
  created_at: string
  updated_at: string
}

export interface PanTransferBatchSummaryItem {
  id: number
  batch_type: string
  source_scope: string
  status: string
  created_by?: string | null
  total_message_count: number
  total_link_target_count: number
  success_item_count: number
  failed_item_count: number
  retry_delay_seconds: number
  active_item_count: number
  request_json: Record<string, unknown>
  result_json: Record<string, unknown>
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
  can_retry: boolean
  can_delete: boolean
  can_cancel: boolean
}

export interface PanTransferBatchListResponse {
  items: PanTransferBatchSummaryItem[]
  page: number
  page_size: number
  total: number
}

export interface PanTransferBatchDetailResponse {
  batch: PanTransferBatchSummaryItem
  items: PanTransferBatchItem[]
}

export interface PanTransferBatchRetryRequest {
  item_ids?: number[]
}
