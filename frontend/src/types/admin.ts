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
}

export interface ChannelCreate {
  username: string
}

export interface SystemConfigResponse {
  public_dashboard_enabled: boolean
}

export interface SystemConfigUpdate {
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

export interface LinkCheckTaskCreate {
  period: string
  max_concurrent: number
}

export interface LinkCheckTaskStatus {
  task_id: string
  status: string
  progress: number
  period_desc?: string
  total_links?: number
  checked_links?: number
  valid_links?: number
  invalid_links?: number
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
  }>
}

