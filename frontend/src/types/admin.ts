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

export interface SystemConfigResponse {
  public_dashboard_enabled: boolean
  link_check_default_max_concurrent: number
  link_check_max_allowed_concurrent: number
  link_check_max_allowed_links: number
  link_check_poll_interval_seconds: number
  monitor_channel_refresh_interval_seconds: number
  monitor_db_write_max_retries: number
  monitor_db_write_retry_delay_seconds: number
}

export interface SystemConfigUpdate {
  public_dashboard_enabled: boolean
  link_check_default_max_concurrent: number
  link_check_max_allowed_concurrent: number
  link_check_max_allowed_links: number
  link_check_poll_interval_seconds: number
  monitor_channel_refresh_interval_seconds: number
  monitor_db_write_max_retries: number
  monitor_db_write_retry_delay_seconds: number
}

export interface PublicSystemConfigResponse {
  public_dashboard_enabled: boolean
}

export interface UserResponse {
  username: string
  name: string
  email: string
  role: string
}

export interface UserCreate {
  username: string
  password: string
  name?: string
  email?: string
  role?: string
}

export interface UserUpdate {
  name?: string
  email?: string
  role?: string
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

export interface MaintenanceResult {
  success: boolean
  fixed_count?: number
  deleted_count?: number
  deleted_details?: number
  deleted_stats?: number
  cutoff_time?: string
  errors?: string[]
  error?: string
}

export interface ClearOldDataRequest {
  days: number
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
  period: string
  max_concurrent: number
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

