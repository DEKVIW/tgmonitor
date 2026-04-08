/**
 * 认证相关类型定义
 */

export interface LoginRequest {
  username: string
  password: string
  turnstile_token?: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface LinuxDoPublicAuthConfig {
  visible: boolean
  mode: 'hidden' | 'existing_only' | 'open'
  status_summary: string
  batch_name?: string | null
  remaining_accounts?: number | null
}

export interface PublicAuthProvidersResponse {
  linuxdo: LinuxDoPublicAuthConfig
}

export interface UserInfo {
  username: string
  name: string
  email?: string
  role: string
}

export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

export interface ChangeUsernameRequest {
  new_username: string
}

export interface LinuxDoLoginStartRequest {
  redirect_uri: string
  turnstile_token?: string
}

export interface LinuxDoLoginStartResponse {
  authorize_url: string
}

export interface LinuxDoLoginExchangeRequest {
  code: string
  state: string
  redirect_uri: string
}

