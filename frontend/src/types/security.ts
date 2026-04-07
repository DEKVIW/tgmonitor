export type SearchChallengeScope = 'guest_only' | 'all_users'
export type DomainChallengeAction = 'managed_challenge' | 'js_challenge' | 'challenge'
export type DomainChallengeExpressionMode = 'recommended' | 'custom'
export type DomainChallengeSyncStatus = 'never' | 'success' | 'error'

export interface PublicSecurityConfigResponse {
  turnstile_ready: boolean
  turnstile_site_key: string
  login_challenge_enabled: boolean
  search_challenge_enabled: boolean
  search_challenge_scope: SearchChallengeScope
  search_challenge_clearance_ttl_seconds: number
}

export interface SecurityConfigResponse extends PublicSecurityConfigResponse {
  turnstile_secret_configured: boolean
  cloudflare_zone_id: string
  cloudflare_api_token_configured: boolean
  domain_access_challenge_enabled: boolean
  domain_access_challenge_action: DomainChallengeAction
  domain_access_challenge_expression_mode: DomainChallengeExpressionMode
  domain_access_challenge_expression_custom: string
  domain_access_recommended_expression: string
  domain_access_rule_id: string
  domain_access_ruleset_id: string
  domain_access_last_synced_at?: string | null
  domain_access_last_sync_status: DomainChallengeSyncStatus
  domain_access_last_sync_message: string
}

export interface SecurityConfigUpdate {
  turnstile_site_key: string
  turnstile_secret: string
  clear_turnstile_secret: boolean
  login_challenge_enabled: boolean
  search_challenge_enabled: boolean
  search_challenge_scope: SearchChallengeScope
  search_challenge_clearance_ttl_seconds: number
  cloudflare_zone_id: string
  cloudflare_api_token: string
  clear_cloudflare_api_token: boolean
  domain_access_challenge_enabled: boolean
  domain_access_challenge_action: DomainChallengeAction
  domain_access_challenge_expression_mode: DomainChallengeExpressionMode
  domain_access_challenge_expression_custom: string
}

export interface SecurityChallengeVerifyRequest {
  action: 'search'
  turnstile_token: string
}

export interface SecurityChallengeVerifyResponse {
  clearance_token: string
  expires_at: string
  ttl_seconds: number
}

export interface DomainChallengeSyncResponse {
  success: boolean
  status: DomainChallengeSyncStatus
  message: string
  synced_at?: string | null
  ruleset_id: string
  rule_id: string
  config: SecurityConfigResponse
}

export interface SearchChallengeClearance {
  clearance_token: string
  expires_at: string
  ttl_seconds: number
}
