/**
 * 认证相关类型定义
 */

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
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

