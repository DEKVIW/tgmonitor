export interface LearningCategory {
  id: number
  name: string
  slug: string
  sort_order: number
  resource_count: number
}

export interface LearningResource {
  id: number
  display_title: string
  status?: string
  category?: { id: number; name: string; slug: string } | null
  tags: string[]
  share_url: string
  platform: string
  source_channel_key?: string
  updated_at?: string | null
  created_at?: string | null
}

export interface LearningResourceListResponse {
  items: LearningResource[]
  total: number
  page: number
  page_size: number
}

export interface LearningChannelConfig {
  channel_id: number
  channel_key: string
  channel_title: string
  config_id?: number | null
  is_enabled: boolean
  target_account_id?: number | null
  save_root: string
  backfill_policy: string
  last_processed_message_id?: number | null
  last_error_message?: string | null
}

export interface LearningChannelUpdateResponse {
  channel_id: number
  channel_key: string
  config_id: number
  is_enabled: boolean
  target_account_id?: number | null
  save_root: string
}

export interface LearningAccount {
  id: number
  platform: string
  account_name: string
  default_save_root: string
  is_enabled: boolean
}

export interface LearningAdminOverview {
  channels: LearningChannelConfig[]
  accounts: LearningAccount[]
  categories: Array<LearningCategory & {
    directory_name: string
    is_enabled: boolean
    show_in_tabs: boolean
  }>
}

export interface LearningAdminItem {
  id: number
  display_title: string
  status: string
  category?: { id: number; name: string; slug: string } | null
  tags: string[]
  share_url?: string | null
  platform: string
  source_channel_key: string
  latest_source_at?: string | null
  updated_at?: string | null
}

export interface LearningAdminListResponse {
  items: LearningAdminItem[]
  total: number
  page: number
  page_size: number
}

export interface LearningDirectory {
  id: string
  name: string
  is_dir: boolean
}

export interface LearningImportRecord {
  display_title: string
  category: string
  tags: string[]
  links: Array<{ url: string; platform: string }>
}

export interface LearningImportPreview {
  id: number
  filename: string
  status: string
  records: LearningImportRecord[]
  invalid_rows: Array<{ row: number; title?: string; reason: string }>
  row_count: number
  valid_count: number
  total_records: number
  total_links: number
  duplicate_count: number
  invalid_count: number
}

export interface LearningImportConfirmResult {
  job_id: number
  status: string
  mode: string
  created_count: number
  link_count: number
  queued_count: number
  batch_id?: number | null
}

export interface LearningAutomationTaskChannel {
  id?: number | null
  channel_id: number
  channel_key?: string
  channel_title?: string
  is_enabled: boolean
  default_category_id?: number | null
  last_processed_message_id?: number | null
  last_processed_telegram_message_id?: number | null
}

export interface LearningAutomationTaskTarget {
  id?: number | null
  target_account_id: number
  account_name?: string
  platform?: string
  save_root_id: string
  save_root_name: string
  auto_create_category_dirs: boolean
  is_enabled: boolean
  status?: string
  last_success_at?: string | null
  last_error_message?: string | null
}

export interface LearningAutomationTask {
  id: number
  name: string
  is_enabled: boolean
  transfer_policy: string
  backfill_policy: string
  status: string
  pending_count: number
  failed_count: number
  last_enqueued_at?: string | null
  last_success_at?: string | null
  last_error_message?: string | null
  created_at?: string | null
  updated_at?: string | null
  channels: LearningAutomationTaskChannel[]
  targets: LearningAutomationTaskTarget[]
}

export interface LearningAutomationTaskListResponse {
  items: LearningAutomationTask[]
  total: number
}

export interface LearningAutomationTaskProcessResponse {
  task_id: number
  mode?: string
  selected_messages: number
  scanned_messages?: number
  valid_messages?: number
  skipped_messages?: number
  message_ids?: number[]
  message_previews?: LearningAutomationSourceMessagePreview[]
  dry_run: boolean
  messages?: number
  resources?: number
  links?: number
  jobs?: number
  skipped_existing?: number
  skipped?: number
  failed?: number
}

export interface LearningAutomationSourceMessagePreview {
  channel: string
  monitor_message_id?: number | null
  message_time?: string | null
  raw_text?: string | null
  raw_text_available: boolean
  resource_titles: string[]
  resource_count: number
  link_count: number
  valid: boolean
}

export interface LearningAutomationSupplementPreview {
  task_id: number
  mode: string
  scanned_messages: number
  selected_messages: number
  valid_messages: number
  skipped_messages: number
  resources: number
  links: number
  message_previews: LearningAutomationSourceMessagePreview[]
}

export interface LearningAutomationSupplementRun {
  id: number
  task_id: number
  mode: string
  status: string
  from_at?: string | null
  to_at?: string | null
  recent_limit?: number | null
  selected_messages: number
  scanned_messages: number
  valid_messages: number
  skipped_messages: number
  resources: number
  links: number
  jobs: number
  skipped_existing: number
  failed: number
  last_error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  paused_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface LearningAutomationRetryResponse {
  task_id: number
  retried_count: number
}

export interface LearningAutomationLog {
  id: number
  stage: string
  level: string
  message: string
  details: Record<string, unknown>
  resource_id?: number | null
  transfer_job_id?: number | null
  source_message_id?: number | null
  created_at?: string | null
}

export interface LearningAutomationLogListResponse {
  items: LearningAutomationLog[]
  total: number
}

export interface LearningAutomationLogClearResponse {
  task_id: number
  deleted_count: number
}
