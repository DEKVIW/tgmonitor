export type BackupTargetKind = 'local' | 'webdav'
export type BackupMode = 'full' | 'media_export'
export type BackupScheduleKind = 'manual' | 'daily' | 'weekly' | 'monthly'
export type BackupExportRangeKind = 'all' | 'days'

export interface BackupTargetPayload {
  name: string
  target_kind: BackupTargetKind
  provider: string
  is_enabled: boolean
  backup_mode: BackupMode
  schedule_enabled: boolean
  schedule_kind: BackupScheduleKind
  schedule_hour: number
  schedule_minute: number
  schedule_priority: number
  schedule_weekday?: number | null
  schedule_day?: number | null
  timezone: string
  retention_count: number
  local_dir: string
  webdav_base_url: string
  webdav_username: string
  webdav_password: string
  clear_webdav_password: boolean
  webdav_root_path: string
  webdav_timeout_seconds: number
  webdav_verify_ssl: boolean
  include_env_file: boolean
  include_runtime_data: boolean
  export_range_kind: BackupExportRangeKind
  export_range_days?: number | null
}

export interface BackupTarget extends Omit<BackupTargetPayload, 'webdav_password' | 'clear_webdav_password'> {
  id: number
  webdav_password_configured: boolean
  last_run_at?: string | null
  next_run_at?: string | null
  last_status?: string | null
  last_error_message?: string | null
  has_active_run: boolean
  active_run_id?: number | null
  active_run_status?: string | null
  extra_json: Record<string, any>
  created_at: string
  updated_at: string
  updated_by?: string | null
}

export interface BackupRun {
  id: number
  target_id?: number | null
  target_name: string
  target_kind: BackupTargetKind
  provider: string
  backup_mode: BackupMode
  trigger_source: string
  status: string
  file_name?: string | null
  file_format?: string | null
  file_size_bytes?: number | null
  sha256?: string | null
  local_path?: string | null
  remote_path?: string | null
  remote_url?: string | null
  item_count?: number | null
  started_at: string
  finished_at?: string | null
  duration_seconds?: number | null
  created_by?: string | null
  error_message?: string | null
  result_json: Record<string, any>
  created_at: string
  reused_existing?: boolean
}

export interface BackupTargetTestResult {
  success: boolean
  target_kind: BackupTargetKind
  message: string
  resolved_path?: string | null
  remote_path?: string | null
}

export interface BackupRemoteFile {
  name: string
  remote_path: string
  remote_url?: string | null
  size_bytes?: number | null
  modified_at?: string | null
  backup_time?: string | null
  backup_mode?: BackupMode | null
  range_label?: string | null
  file_format?: string | null
}

export interface BackupRemoteFileDeleteResult {
  success: boolean
  remote_path: string
}
