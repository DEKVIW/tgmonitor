export interface AiCenterOverviewResponse {
  total_providers: number
  enabled_providers: number
  default_provider_id?: number | null
  default_provider_label?: string | null
  total_routes: number
  ready_routes: number
  recent_success_count_24h: number
  recent_failure_count_24h: number
  legacy_migration_applied: boolean
  generated_at: string
}

export interface AiCenterProviderModelItem {
  id: number
  provider_id: number
  model_id: string
  label: string
  owned_by?: string | null
  is_enabled: boolean
  is_preferred: boolean
  capabilities: string[]
  route_allowlist: string[]
  priority_bias: number
  quality_score: number
  speed_score: number
  cost_score: number
  stability_score: number
  notes?: string | null
  recent_success_count: number
  recent_error_count: number
  recent_empty_response_count: number
  last_event_at?: string | null
  extra_json: Record<string, any>
  last_refreshed_at?: string | null
  created_at: string
  updated_at: string
}

export interface AiCenterProviderModelUpsertRequest {
  id?: number | null
  model_id: string
  label?: string
  owned_by?: string | null
  is_enabled: boolean
  is_preferred: boolean
  capabilities: string[]
  route_allowlist: string[]
  priority_bias: number
  quality_score: number
  speed_score: number
  cost_score: number
  stability_score: number
  notes?: string | null
  extra_json?: Record<string, any>
}

export interface AiCenterProviderItem {
  id: number
  provider_key: string
  display_name: string
  provider_type: string
  base_url: string
  api_mode: string
  is_enabled: boolean
  is_default: boolean
  priority: number
  timeout_seconds: number
  max_retries: number
  cooldown_seconds: number
  cooldown_until?: string | null
  health_status: string
  consecutive_failures: number
  last_checked_at?: string | null
  last_success_at?: string | null
  last_failure_at?: string | null
  last_error_message?: string | null
  has_api_key: boolean
  model_count: number
  enabled_model_count: number
  preferred_model_id?: string | null
  updated_by?: string | null
  extra_json: Record<string, any>
  models: AiCenterProviderModelItem[]
  created_at: string
  updated_at: string
}

export interface AiCenterProviderListResponse {
  items: AiCenterProviderItem[]
  total: number
}

export interface AiCenterProviderUpsertRequest {
  provider_key: string
  display_name: string
  base_url: string
  api_mode: string
  api_key?: string | null
  clear_api_key?: boolean
  is_enabled: boolean
  is_default: boolean
  priority: number
  timeout_seconds: number
  max_retries: number
  cooldown_seconds: number
  extra_json?: Record<string, any>
  models?: AiCenterProviderModelUpsertRequest[]
}

export interface AiCenterProviderTestRequest {
  model_id?: string | null
  sample_text?: string | null
}

export interface AiCenterProviderTestResponse {
  provider_id: number
  provider_label?: string | null
  model_id?: string | null
  used_api_mode?: string | null
  text: string
  ok: boolean
}

export interface AiCenterRouteStepItem {
  id: number
  step_index: number
  provider_id: number
  provider_key?: string | null
  provider_label?: string | null
  provider_enabled: boolean
  provider_health_status: string
  model_id?: string | null
  model_label?: string | null
  is_enabled: boolean
  extra_json: Record<string, any>
  created_at: string
  updated_at: string
}

export interface AiCenterRouteItem {
  id: number
  route_key: string
  display_name: string
  description: string
  output_mode: string
  is_enabled: boolean
  max_attempts: number
  selection_mode: string
  optimization_goal: string
  preferred_capabilities: string[]
  allow_same_provider_model_failover: boolean
  allow_cross_provider_failover: boolean
  updated_by?: string | null
  extra_json: Record<string, any>
  steps: AiCenterRouteStepItem[]
  configured_step_count: number
  enabled_step_count: number
  candidate_count: number
  is_ready: boolean
  ready_reason?: string | null
  ready_provider_label?: string | null
  ready_model_id?: string | null
  selection_summary?: string | null
  created_at: string
  updated_at: string
}

export interface AiCenterRouteListResponse {
  items: AiCenterRouteItem[]
  total: number
}

export interface AiCenterRouteStepUpsertRequest {
  id?: number | null
  provider_id: number
  model_id?: string | null
  is_enabled: boolean
  extra_json?: Record<string, any>
}

export interface AiCenterRouteUpsertRequest {
  display_name: string
  description: string
  output_mode: string
  is_enabled: boolean
  max_attempts: number
  selection_mode: string
  optimization_goal: string
  preferred_capabilities: string[]
  allow_same_provider_model_failover: boolean
  allow_cross_provider_failover: boolean
  extra_json?: Record<string, any>
  steps: AiCenterRouteStepUpsertRequest[]
}

export interface AiCenterRouteReadinessResponse {
  route_key: string
  is_ready: boolean
  reason?: string | null
  provider_label?: string | null
  model_id?: string | null
  selection_mode: string
  optimization_goal: string
  candidate_count: number
  selection_summary?: string | null
  step_count: number
  enabled_step_count: number
}

export interface AiCenterRouteTestRequest {
  system_prompt: string
  user_prompt: string
}

export interface AiCenterRouteTestResponse {
  route_key: string
  provider_id?: number | null
  provider_label?: string | null
  model_id?: string | null
  used_api_mode?: string | null
  duration_ms?: number | null
  text: string
  event_id?: number | null
  selection_summary?: string | null
  attempt_trace: Record<string, any>[]
  ok: boolean
}

export interface AiCenterCallEventItem {
  id: number
  route_key: string
  route_profile_id?: number | null
  route_step_id?: number | null
  provider_id?: number | null
  provider_label?: string | null
  model_id?: string | null
  status: string
  error_type?: string | null
  error_message?: string | null
  duration_ms?: number | null
  used_api_mode?: string | null
  selection_mode?: string | null
  selection_summary?: string | null
  attempt_index?: number | null
  candidate_score?: number | null
  extra_json: Record<string, any>
  created_at: string
}

export interface AiCenterCallEventListResponse {
  items: AiCenterCallEventItem[]
  total: number
  limit: number
}

export interface AiCenterCallEventClearResponse {
  deleted_count: number
}

export interface AiCenterDeleteResponse {
  id: number
  deleted: boolean
}
