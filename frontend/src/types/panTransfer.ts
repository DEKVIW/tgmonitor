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
