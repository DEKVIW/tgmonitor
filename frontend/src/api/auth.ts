/**
 * 认证相关API
 */

import apiClient from '@/utils/api'
import {
  ChangePasswordRequest,
  ChangeUsernameRequest,
  LinuxDoLoginExchangeRequest,
  LinuxDoLoginStartRequest,
  LinuxDoLoginStartResponse,
  LoginRequest,
  LoginResponse,
  PublicAuthProvidersResponse,
  UserInfo,
} from '@/types/auth'

/**
 * 登录
 */
export const login = async (data: LoginRequest): Promise<LoginResponse> => {
  const response = await apiClient.post<LoginResponse>('/auth/login', data)
  return response.data
}

export const getPublicAuthProviders = async (): Promise<PublicAuthProvidersResponse> => {
  const response = await apiClient.get<PublicAuthProvidersResponse>('/auth/providers/public')
  return response.data
}

export const startLinuxDoLogin = async (
  data: LinuxDoLoginStartRequest
): Promise<LinuxDoLoginStartResponse> => {
  const response = await apiClient.post<LinuxDoLoginStartResponse>('/auth/linuxdo/start', data)
  return response.data
}

export const exchangeLinuxDoLogin = async (data: LinuxDoLoginExchangeRequest): Promise<LoginResponse> => {
  const response = await apiClient.post<LoginResponse>('/auth/linuxdo/exchange', data)
  return response.data
}

/**
 * 获取当前用户信息
 */
export const getCurrentUser = async (): Promise<UserInfo> => {
  const response = await apiClient.get<UserInfo>('/auth/me')
  return response.data
}

export const pingCurrentSession = async (): Promise<UserInfo> => {
  const response = await apiClient.post<UserInfo>('/auth/ping')
  return response.data
}

/**
 * 登出
 */
export const logout = async (): Promise<void> => {
  await apiClient.post('/auth/logout')
}

/**
 * 修改当前用户密码
 */
export const changePassword = async (data: ChangePasswordRequest): Promise<void> => {
  await apiClient.post('/auth/me/password', data)
}

export const changeUsername = async (data: ChangeUsernameRequest): Promise<void> => {
  await apiClient.post('/auth/me/username', data)
}

