/**
 * 认证相关API
 */

import apiClient from '@/utils/api'
import { LoginRequest, LoginResponse, UserInfo, ChangePasswordRequest } from '@/types/auth'

/**
 * 登录
 */
export const login = async (data: LoginRequest): Promise<LoginResponse> => {
  const response = await apiClient.post<LoginResponse>('/auth/login', data)
  return response.data
}

/**
 * 获取当前用户信息
 */
export const getCurrentUser = async (): Promise<UserInfo> => {
  const response = await apiClient.get<UserInfo>('/auth/me')
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

