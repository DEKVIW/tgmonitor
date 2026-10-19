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
  category?: { id: number; name: string; slug: string } | null
  tags: string[]
  share_url: string
  platform: string
  updated_at?: string | null
  created_at?: string | null
}

export interface LearningResourceListResponse {
  items: LearningResource[]
  total: number
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
}

export interface LearningAdminItem {
  id: number
  display_title: string
  status: string
  category?: { id: number; name: string; slug: string } | null
  share_url?: string | null
  latest_source_at?: string | null
  updated_at?: string | null
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
