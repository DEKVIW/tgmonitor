/**
 * 管理相关类型定义
 */

export interface CredentialResponse {
  id: number
  api_id: string
  api_hash: string
}

export interface CredentialCreate {
  api_id: string
  api_hash: string
}

export interface ChannelResponse {
  id: number
  username: string
  parser_profile?: string | null
  effective_parser_profile: string
  title?: string | null
  telegram_id?: number | null
  channel_type?: string | null
  resolution_status?: string | null
  resolution_error?: string | null
}

export interface ChannelCreate {
  username: string
  parser_profile?: string | null
}

export interface FooterBuilderSection {
  id: string
  title: string
  html: string
  span: number
}

export interface SystemConfigResponse {
  site_name: string
  site_title: string
  site_description: string
  site_keywords: string
  brand_icon: string
  site_favicon_url: string
  public_dashboard_enabled: boolean
  public_ads_enabled: boolean
  public_feed_top_ad_html_desktop: string
  public_feed_top_ad_html_mobile: string
  public_feed_inline_ad_html_desktop: string
  public_feed_inline_ad_html_mobile: string
  public_feed_inline_every_n: number
  footer_builder_enabled: boolean
  footer_builder_sections: FooterBuilderSection[]
  footer_builder_bottom_html: string
  umami_enabled: boolean
  umami_script_url: string
  umami_website_id: string
  umami_host_url: string
  umami_share_url: string
  link_check_default_max_concurrent: number
  link_check_max_allowed_concurrent: number
  link_check_max_allowed_links: number
  link_check_poll_interval_seconds: number
  monitor_channel_refresh_interval_seconds: number
  monitor_db_write_max_retries: number
  monitor_db_write_retry_delay_seconds: number
}

export interface SystemConfigUpdate {
  site_name: string
  site_title: string
  site_description: string
  site_keywords: string
  brand_icon: string
  site_favicon_url: string
  public_dashboard_enabled: boolean
  public_ads_enabled: boolean
  public_feed_top_ad_html_desktop: string
  public_feed_top_ad_html_mobile: string
  public_feed_inline_ad_html_desktop: string
  public_feed_inline_ad_html_mobile: string
  public_feed_inline_every_n: number
  footer_builder_enabled: boolean
  footer_builder_sections: FooterBuilderSection[]
  footer_builder_bottom_html: string
  umami_enabled: boolean
  umami_script_url: string
  umami_website_id: string
  umami_host_url: string
  umami_share_url: string
  link_check_default_max_concurrent: number
  link_check_max_allowed_concurrent: number
  link_check_max_allowed_links: number
  link_check_poll_interval_seconds: number
  monitor_channel_refresh_interval_seconds: number
  monitor_db_write_max_retries: number
  monitor_db_write_retry_delay_seconds: number
}

export interface PublicSystemConfigResponse {
  site_name: string
  site_title: string
  site_description: string
  site_keywords: string
  brand_icon: string
  site_favicon_url: string
  public_dashboard_enabled: boolean
  public_ads_enabled: boolean
  public_feed_top_ad_html_desktop: string
  public_feed_top_ad_html_mobile: string
  public_feed_inline_ad_html_desktop: string
  public_feed_inline_ad_html_mobile: string
  public_feed_inline_every_n: number
  footer_builder_enabled: boolean
  footer_builder_sections: FooterBuilderSection[]
  footer_builder_bottom_html: string
  umami_enabled: boolean
  umami_script_url: string
  umami_website_id: string
  umami_host_url: string
}

export interface UserResponse {
  id?: number
  username: string
  name: string
  email: string
  role: string
  display_name?: string | null
  status?: string
  effective_status?: string
  account_source?: string
  expires_at?: string | null
  remaining_days?: number | null
  session_limit?: number | null
  session_limit_override?: number | null
  active_session_count?: number
  must_change_password?: boolean
  last_login_at?: string | null
  last_seen_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  source_batch_id?: number | null
  status_reason?: string | null
  identity_status?: string | null
}

export interface UserCreate {
  username: string
  password: string
  name?: string
  email?: string
  role?: string
  status?: string
  validity_mode?: 'permanent' | 'duration' | 'fixed_at' | null
  validity_unit?: 'day' | 'month' | 'year' | null
  validity_value?: number | null
  fixed_expires_at?: string | null
  session_limit_override?: number | null
}

export interface UserUpdate {
  name?: string
  email?: string
  role?: string
  status?: string
  validity_mode?: 'permanent' | 'duration' | 'fixed_at' | null
  validity_unit?: 'day' | 'month' | 'year' | null
  validity_value?: number | null
  fixed_expires_at?: string | null
  session_limit_override?: number | null
}

export interface PasswordChange {
  new_password: string
}

export interface UsernameChange {
  new_username: string
}

export interface RoleChange {
  new_role: string
}

export interface BulkRandomCreateRequest {
  count: number
  prefix?: string
  start_index?: number
  role?: string
  password_length?: number
  validity_mode?: 'permanent' | 'duration' | 'fixed_at' | null
  validity_unit?: 'day' | 'month' | 'year' | null
  validity_value?: number | null
  fixed_expires_at?: string | null
}

export interface BulkRandomCreateResult {
  username: string
  password: string
  role: string
}

export interface BulkFailure {
  username?: string | null
  reason: string
}

export interface BulkCreateResponse {
  successes: BulkRandomCreateResult[]
  failures: BulkFailure[]
}

export interface BulkUsernamesRequest {
  usernames: string[]
  password_length?: number
}

export interface BulkSimpleResponse {
  successes: any[]
  failures: BulkFailure[]
}

export interface BulkResetResponse {
  successes: { username: string; password: string }[]
  failures: BulkFailure[]
}

export interface AccountRuntimeSettings {
  concurrent_session_limit_enabled: boolean
  max_concurrent_sessions_per_account: number
  session_online_window_minutes: number
  session_absolute_ttl_days: number
  admin_exempt_from_session_limit: boolean
  auto_disable_expired_accounts: boolean
  default_account_validity_mode: 'permanent' | 'duration'
  default_account_validity_unit: 'day' | 'month' | 'year'
  default_account_validity_value: number
}

export interface LinuxDoBatchResponse {
  id: number
  batch_name: string
  batch_code: string
  is_enabled: boolean
  default_role: 'admin' | 'user'
  validity_mode: 'permanent' | 'duration' | 'fixed_at'
  validity_unit?: 'day' | 'month' | 'year' | null
  validity_value?: number | null
  fixed_expires_at?: string | null
  starts_at?: string | null
  ends_at?: string | null
  max_accounts?: number | null
  allocated_accounts: number
  remaining_accounts?: number | null
  admission_open: boolean
  status: string
  notes: string
  created_at?: string | null
  created_by?: string | null
}

export interface LinuxDoConfigResponse {
  enabled: boolean
  allow_new_accounts: boolean
  client_id: string
  client_secret_configured: boolean
  configured: boolean
  login_mode: 'hidden' | 'existing_only' | 'open'
  status_summary: string
  bound_account_count: number
  current_batch?: LinuxDoBatchResponse | null
  recent_batches: LinuxDoBatchResponse[]
}

export interface LinuxDoConfigUpdate {
  enabled: boolean
  allow_new_accounts: boolean
  client_id: string
  client_secret: string
  clear_client_secret: boolean
}

export interface LinuxDoBatchUpsert {
  batch_name: string
  is_enabled: boolean
  max_accounts: number
  default_role: 'admin' | 'user'
  validity_mode: 'permanent' | 'duration' | 'fixed_at'
  validity_unit?: 'day' | 'month' | 'year' | null
  validity_value?: number | null
  fixed_expires_at?: string | null
  starts_at?: string | null
  ends_at?: string | null
  notes?: string
}

export interface AccountListResponse {
  items: UserResponse[]
  total: number
  page: number
  page_size: number
  runtime_settings: AccountRuntimeSettings
}

export interface AccountListQuery {
  page?: number
  page_size?: number
  keyword?: string
  role?: string
  effective_status?: string
  account_source?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface MaintenanceResult {
  success: boolean
  fixed_count?: number
  deleted_count?: number
  deleted_details?: number
  deleted_stats?: number
  cutoff_time?: string
  errors?: string[]
  error?: string
  status?: string
  run_time?: string
  trigger_source?: string
  scope_mode?: string
  scope_label?: string
  lookback_hours?: number | null
  scanned_messages?: number
  scanned_links?: number
  unique_links?: number
  kept_messages?: number
  duplicate_candidate_count?: number
  duplicate_group_count?: number
  duration_seconds?: number
}

export interface ClearOldDataRequest {
  days: number
}

export interface DedupRunSummary {
  run_time?: string | null
  trigger_source?: string | null
  scope_mode: 'all_history' | 'recent_hours' | string
  scope_label: string
  lookback_hours?: number | null
  scanned_messages: number
  scanned_links: number
  unique_links: number
  kept_messages: number
  duplicate_candidate_count: number
  duplicate_group_count: number
  deleted_count: number
  duration_seconds: number
}

export interface DedupRuntimeSettingsResponse {
  enabled: boolean
  scope_mode: 'all_history' | 'recent_hours' | string
  scope_label: string
  lookback_hours: number
  schedule_interval_hours: number
  schedule_minute: number
  timezone: string
  stats_retention_hours: number
  next_run_at?: string | null
  last_run_at?: string | null
  last_status?: string | null
  last_error_message?: string | null
  last_run_summary: Partial<DedupRunSummary>
  status_summary: string
}

export interface DedupRuntimeSettingsUpdate {
  enabled: boolean
  scope_mode: 'all_history' | 'recent_hours'
  lookback_hours: number
  schedule_interval_hours: number
  schedule_minute: number
  timezone: string
  stats_retention_hours: number
}

export interface ChannelDiagnosisResult {
  valid_channels: Array<{
    username: string
    title: string
    id: number
    type: string
    participants_count?: number
  }>
  invalid_channels: Array<{
    username: string
    error: string
    type: string
  }>
}

export interface MonitorTestResult {
  success: boolean
  channels_tested?: number
  message_received?: boolean
  message?: string
  error?: string
}

export interface ChannelSampleEntity {
  type: string
  url: string
  text?: string | null
}

export interface ParsedMessageRecord {
  title: string
  description: string
  links: Record<string, Array<Record<string, any>>>
  tags: string[]
  source: string
  channel: string
  group_name: string
  bot: string
}

export interface ChannelSampleButtonLink {
  text?: string | null
  url: string
}

export interface ChannelSampleWebpagePreview {
  url?: string | null
  title?: string | null
  description?: string | null
  site_name?: string | null
  author?: string | null
  type?: string | null
  display_url?: string | null
}

export interface ChannelSampleParserDebug {
  parsed_records: ParsedMessageRecord[]
  diagnostics: Record<string, any>
  extracted_link_count: number
}

export interface ChannelMessageSample {
  message_id: number
  timestamp: string
  message_link?: string | null
  text: string
  text_length: number
  has_media: boolean
  media_kind?: string | null
  grouped_id?: number | null
  post_author?: string | null
  raw_urls: string[]
  entity_urls: ChannelSampleEntity[]
  button_links: ChannelSampleButtonLink[]
  webpage_preview?: ChannelSampleWebpagePreview | null
  raw_message: Record<string, any>
  parser_debug: ChannelSampleParserDebug
  button_urls?: string[]
  webpage_url?: string | null
  parsed_records?: ParsedMessageRecord[]
  diagnostics?: Record<string, any>
  extracted_link_count?: number
}

export interface ChannelSampleResponse {
  channel_id: number
  username: string
  title?: string | null
  telegram_id?: number | null
  requested_limit: number
  page: number
  page_size: number
  sample_count: number
  has_more: boolean
  inspected_count: number
  only_with_links: boolean
  samples: ChannelMessageSample[]
}

export interface LinkCheckTaskCreate {
  selection_mode: 'smart_count' | 'time_range'
  period?: string | null
  range_start?: string | null
  range_end?: string | null
  target_link_count?: number | null
  direction: 'newest_first' | 'oldest_first'
  max_concurrent: number
}

export interface LinkCheckPreviewRequest {
  selection_mode: 'smart_count' | 'time_range'
  range_start?: string | null
  range_end?: string | null
  target_link_count?: number | null
  direction: 'newest_first' | 'oldest_first'
}

export interface LinkCheckPreviewResponse {
  selection_mode: 'smart_count' | 'time_range'
  direction?: 'newest_first' | 'oldest_first' | null
  scope_label: string
  estimated_messages: number
  estimated_links: number
  range_start?: string | null
  range_end?: string | null
  first_message_time?: string | null
  last_message_time?: string | null
  requested_target_link_count?: number | null
  effective_target_link_count?: number | null
  task_link_limit: number
  recommended_batch_count: number
  recommended_target_link_count: number
  can_start: boolean
  exceeds_task_limit: boolean
  warnings: string[]
}

export interface LinkCheckDateRange {
  min_date?: string | null
  max_date: string
  latest_message_date?: string | null
}

export interface LinkCheckTaskStatus {
  task_id: string
  status: string
  progress: number
  period_desc?: string
  scope_label?: string
  trigger_source?: 'manual' | 'scheduled' | string
  task_mode?: string
  total_messages?: number
  total_links?: number
  checked_links?: number
  valid_links?: number
  invalid_links?: number
  started_at?: string
  updated_at?: string
  current_phase?: string
  current_platform?: string
  stop_requested?: boolean
  reused_existing?: boolean
  status_counts?: Record<string, number>
  check_time?: string
  duration?: number
  logs?: string[]
  error?: string
  plan_id?: number | null
  plan_name?: string | null
  plan_mode?: string | null
}

export interface LinkCheckTaskHistory {
  id: number
  check_time: string
  total_messages: number
  total_links: number
  valid_links: number
  invalid_links: number
  updated_messages?: number
  deleted_messages?: number
  status: string
  duration?: number
  trigger_source?: 'manual' | 'scheduled' | string
  task_mode?: string
  scope_label?: string
  plan_id?: number | null
  plan_name?: string | null
  plan_mode?: string | null
}

export interface LinkCheckTaskResult {
  stats: {
    check_time: string
    total_messages: number
    total_links: number
    valid_links: number
    invalid_links: number
    updated_messages?: number
    deleted_messages?: number
    netdisk_stats?: Record<string, any>
    duration?: number
    status: string
    trigger_source?: 'manual' | 'scheduled' | string
    task_mode?: string
    scope_label?: string
    plan_id?: number | null
    plan_name?: string | null
    plan_mode?: string | null
  }
  details: Array<{
    url: string
    netdisk_type: string
    is_valid: boolean
    response_time?: number
    error_reason?: string
    status?: string
  }>
}

export interface LinkCheckPlanOverview {
  total_messages_with_links: number
  total_links: number
  first_message_time?: string | null
  last_message_time?: string | null
  estimated_links_per_run: number
  estimated_batches_per_cycle: number
  estimated_days_to_complete_cycle: number
  can_finish_within_cycle: boolean
  warnings: string[]
  summary: string
  next_run_at?: string | null
  last_run_at?: string | null
  plan_mode?: 'backfill' | 'frontier' | string | null
  schedule_priority: number
  cursor_message_id?: number | null
  window_lower_message_id?: number | null
  window_upper_message_id?: number | null
  completed_through_message_id?: number | null
  cycle_started_at?: string | null
  cycle_completed_at?: string | null
  task_link_limit: number
  task_concurrency_limit: number
  generated_at?: string | null
  stale?: boolean
  refreshing?: boolean
}

export interface LinkCheckPlanUpdate {
  name?: string | null
  plan_mode: 'backfill' | 'frontier'
  is_enabled: boolean
  schedule_hour: number
  schedule_minute: number
  schedule_priority: number
  timezone: string
  cycle_days: number
  batch_link_target: number
  max_batches_per_run: number
  max_concurrent: number
  traversal_order: 'newest_first' | 'oldest_first'
  overlap_message_count: number
  cleanup_mode: 'none' | 'remove_invalid_links' | 'delete_message_if_empty'
  cleanup_min_consecutive_invalid_runs: number
}

export interface LinkCheckPlanCreate extends LinkCheckPlanUpdate {}

export interface LinkCheckPlanResponse {
  id: number
  name: string
  plan_mode: 'backfill' | 'frontier'
  is_enabled: boolean
  schedule_hour: number
  schedule_minute: number
  schedule_priority: number
  timezone: string
  cycle_days: number
  batch_link_target: number
  max_batches_per_run: number
  max_concurrent: number
  traversal_order: 'newest_first' | 'oldest_first'
  overlap_message_count: number
  cleanup_mode: 'none' | 'remove_invalid_links' | 'delete_message_if_empty'
  cleanup_min_consecutive_invalid_runs: number
  next_run_at?: string | null
  last_run_at?: string | null
  last_status?: string | null
  last_error_message?: string | null
  cursor_message_id?: number | null
  window_lower_message_id?: number | null
  window_upper_message_id?: number | null
  completed_through_message_id?: number | null
  cycle_started_at?: string | null
  cycle_completed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  updated_by?: string | null
  overview: LinkCheckPlanOverview
}

export interface LinkCheckPlanDeleteResult {
  success: boolean
  deleted_plan_id: number
}

export interface LinkCleanupApplyRequest {
  mode: 'remove_invalid_links' | 'delete_message_if_empty'
  dry_run?: boolean
}

export interface LinkCleanupResult {
  success: boolean
  check_time: string
  mode: 'remove_invalid_links' | 'delete_message_if_empty'
  dry_run?: boolean
  total_invalid_details: number
  cleanup_candidates: number
  matched_messages: number
  updated_messages: number
  deleted_messages: number
  removed_links: number
  skipped_messages: number
}

export interface LinkCheckHistoryDeleteResult {
  success: boolean
  check_time: string
  deleted_details: number
  deleted_stats: number
}

export interface LinkCheckHistoryBatchDeleteRequest {
  check_times: string[]
}

export interface LinkCheckHistoryBatchDeleteResult {
  success: boolean
  requested_count: number
  deleted_runs: number
  deleted_details: number
  deleted_stats: number
  missing_check_times: string[]
}

