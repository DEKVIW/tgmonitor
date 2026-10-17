export interface MediaWallCategory {
  id: number
  name: string
  slug: string
  is_enabled: boolean
  show_in_tabs: boolean
  sort_order: number
  created_at?: string | null
  updated_at?: string | null
}

export interface MediaWallProgress {
  episode?: number | null
  label: string
  task_state?: string | null
  share_status?: string | null
  last_checked_at?: string | null
}

export interface MediaWallLink {
  id: number
  platform: string
  url: string
  label?: string | null
  is_primary: boolean
  is_enabled: boolean
  source_type: string
  last_checked_at?: string | null
  last_status: string
  invalid_streak: number
  next_check_at?: string | null
  last_error_message?: string | null
}

export interface MediaWallLinkHealth {
  total: number
  enabled: number
  valid: number
  invalid: number
  pending: number
  uncertain: number
  status: string
}

export interface MediaWallItem {
  id: number
  display_title: string
  metadata_query_title?: string | null
  visibility: string
  sort_order: number
  poster_url?: string | null
  type_name?: string | null
  year?: string | null
  area?: string | null
  remarks?: string | null
  summary?: string | null
  director?: string | null
  actor?: string | null
  progress: MediaWallProgress
  links: MediaWallLink[]
  link_health: MediaWallLinkHealth
  link_count: number
  categories: MediaWallCategory[]
  sync_task_id?: number | null
  last_content_updated_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface MediaWallListResponse {
  items: MediaWallItem[]
  total: number
  page: number
  page_size: number
}

export interface MediaWallItemLinkInput {
  id?: number
  url: string
  label?: string
  source_type?: string
  is_enabled?: boolean
  is_primary?: boolean
}

export interface MediaWallItemInput {
  display_title: string
  metadata_query_title?: string | null
  visibility: string
  sort_order: number
  category_ids: number[]
  sync_task_id?: number | null
  custom_poster_url?: string | null
  links?: MediaWallItemLinkInput[]
}

export interface MediaWallSource {
  id: number
  name: string
  source_url: string
  source_type: string
  is_enabled: boolean
  priority: number
  timeout_seconds: number
  last_checked_at?: string | null
  last_refreshed_at?: string | null
  last_error_message?: string | null
  endpoint_count: number
}

export interface MediaWallSyncTask {
  id: number
  task_name: string
  work_title?: string | null
  topic_title: string
  status: string
  task_state: string
  current_share_url?: string | null
  current_share_status: string
  progress: MediaWallProgress
}

export interface MediaWallImportPreview {
  id: number
  filename: string
  status: string
  records: Array<{ display_title: string; links: Array<{ url: string; platform: string }> }>
  invalid_rows: Array<{ row: number; title?: string; reason: string }>
  total_records: number
  total_links: number
  invalid_count: number
}

export interface MediaWallImportResult {
  job_id: number
  status: string
  created_count: number
  updated_count: number
  link_count: number
}
