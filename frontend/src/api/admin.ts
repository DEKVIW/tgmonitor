/**
 * 管理相关API
 */

import apiClient from '@/utils/api'
import {
  CredentialResponse,
  CredentialCreate,
  ChannelResponse,
  ChannelCreate,
  SystemConfigResponse,
  SystemConfigUpdate,
  UserResponse,
  UserCreate,
  UserUpdate,
  PasswordChange,
  UsernameChange,
  RoleChange,
  BulkRandomCreateRequest,
  BulkCreateResponse,
  BulkUsernamesRequest,
  BulkSimpleResponse,
  BulkResetResponse,
  MaintenanceResult,
  ClearOldDataRequest,
  ChannelDiagnosisResult,
  MonitorTestResult,
  LinkCheckTaskCreate,
  LinkCheckTaskStatus,
  LinkCheckTaskHistory,
  LinkCheckTaskResult
} from '@/types/admin'

/**
 * 获取API凭据列表
 */
export const getCredentials = async (): Promise<CredentialResponse[]> => {
  const response = await apiClient.get<CredentialResponse[]>('/admin/credentials')
  return response.data
}

/**
 * 添加API凭据
 */
export const createCredential = async (data: CredentialCreate): Promise<CredentialResponse> => {
  const response = await apiClient.post<CredentialResponse>('/admin/credentials', data)
  return response.data
}

/**
 * 删除API凭据
 */
export const deleteCredential = async (id: number): Promise<void> => {
  await apiClient.delete(`/admin/credentials/${id}`)
}

/**
 * 获取频道列表
 */
export const getChannels = async (): Promise<ChannelResponse[]> => {
  const response = await apiClient.get<ChannelResponse[]>('/admin/channels')
  return response.data
}

/**
 * 添加频道
 */
export const createChannel = async (data: ChannelCreate): Promise<ChannelResponse> => {
  const response = await apiClient.post<ChannelResponse>('/admin/channels', data)
  return response.data
}

/**
 * 编辑频道
 */
export const updateChannel = async (id: number, data: ChannelCreate): Promise<ChannelResponse> => {
  const response = await apiClient.put<ChannelResponse>(`/admin/channels/${id}`, data)
  return response.data
}

/**
 * 删除频道
 */
export const deleteChannel = async (id: number): Promise<void> => {
  await apiClient.delete(`/admin/channels/${id}`)
}

/**
 * 诊断所有频道
 */
export const diagnoseChannels = async (): Promise<ChannelDiagnosisResult> => {
  const response = await apiClient.post<ChannelDiagnosisResult>('/admin/channels/diagnose')
  return response.data
}

/**
 * 测试监控功能
 */
export const testMonitor = async (): Promise<MonitorTestResult> => {
  const response = await apiClient.post<MonitorTestResult>('/admin/channels/test-monitor')
  return response.data
}

/**
 * 开始链接检测任务
 */
export const startLinkCheckTask = async (data: LinkCheckTaskCreate): Promise<LinkCheckTaskStatus> => {
  const response = await apiClient.post<LinkCheckTaskStatus>('/admin/link-check/start', data)
  return response.data
}

/**
 * 获取任务状态
 */
export const getLinkCheckTaskStatus = async (taskId: string): Promise<LinkCheckTaskStatus> => {
  const response = await apiClient.get<LinkCheckTaskStatus>(`/admin/link-check/tasks/${taskId}`)
  return response.data
}

/**
 * 获取检测历史
 */
export const getLinkCheckHistory = async (limit: number = 20): Promise<LinkCheckTaskHistory[]> => {
  const response = await apiClient.get<LinkCheckTaskHistory[]>(`/admin/link-check/tasks?limit=${limit}`)
  return response.data
}

/**
 * 获取检测结果
 */
export const getLinkCheckResult = async (checkTime: string): Promise<LinkCheckTaskResult> => {
  const response = await apiClient.get<LinkCheckTaskResult>(`/admin/link-check/tasks/${checkTime}/result`)
  return response.data
}

/**
 * 获取系统配置
 */
export const getSystemConfig = async (): Promise<SystemConfigResponse> => {
  const response = await apiClient.get<SystemConfigResponse>('/admin/config')
  return response.data
}

/**
 * 更新系统配置
 */
export const updateSystemConfig = async (data: SystemConfigUpdate): Promise<SystemConfigResponse> => {
  const response = await apiClient.put<SystemConfigResponse>('/admin/config', data)
  return response.data
}

/**
 * 获取公开系统配置（无需认证）
 */
export const getPublicConfig = async (): Promise<SystemConfigResponse> => {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/config/public`)
  return response.json()
}

/**
 * 获取用户列表
 */
export const getUsers = async (): Promise<UserResponse[]> => {
  const response = await apiClient.get<UserResponse[]>('/admin/users')
  return response.data
}

/**
 * 获取用户信息
 */
export const getUser = async (username: string): Promise<UserResponse> => {
  const response = await apiClient.get<UserResponse>(`/admin/users/${username}`)
  return response.data
}

/**
 * 添加用户
 */
export const createUser = async (data: UserCreate): Promise<UserResponse> => {
  const response = await apiClient.post<UserResponse>('/admin/users', data)
  return response.data
}

/**
 * 更新用户信息
 */
export const updateUser = async (username: string, data: UserUpdate): Promise<UserResponse> => {
  const response = await apiClient.put<UserResponse>(`/admin/users/${username}`, data)
  return response.data
}

/**
 * 修改用户密码
 */
export const changeUserPassword = async (username: string, data: PasswordChange): Promise<void> => {
  await apiClient.put(`/admin/users/${username}/password`, data)
}

/**
 * 修改用户名
 */
export const changeUsername = async (username: string, data: UsernameChange): Promise<void> => {
  await apiClient.put(`/admin/users/${username}/username`, data)
}

/**
 * 修改用户角色
 */
export const changeUserRole = async (username: string, data: RoleChange): Promise<void> => {
  await apiClient.put(`/admin/users/${username}/role`, data)
}

/**
 * 删除用户
 */
export const deleteUser = async (username: string): Promise<void> => {
  await apiClient.delete(`/admin/users/${username}`)
}

/**
 * 批量随机创建用户
 */
export const bulkRandomCreateUsers = async (data: BulkRandomCreateRequest): Promise<BulkCreateResponse> => {
  const response = await apiClient.post<BulkCreateResponse>('/admin/users/bulk/random-create', data)
  return response.data
}

/**
 * 批量删除用户
 */
export const bulkDeleteUsers = async (data: BulkUsernamesRequest): Promise<BulkSimpleResponse> => {
  const response = await apiClient.post<BulkSimpleResponse>('/admin/users/bulk/delete', data)
  return response.data
}

/**
 * 批量重置密码
 */
export const bulkResetPasswords = async (data: BulkUsernamesRequest): Promise<BulkResetResponse> => {
  const response = await apiClient.post<BulkResetResponse>('/admin/users/bulk/reset-password', data)
  return response.data
}

/**
 * 导出用户列表（JSON）
 */
export const exportUsers = async (): Promise<UserResponse[]> => {
  const response = await apiClient.get<UserResponse[]>('/admin/users/export-all')
  return response.data
}

/**
 * 获取可用角色列表
 */
export const getAvailableRoles = async (): Promise<Record<string, string>> => {
  const response = await apiClient.get<Record<string, string>>('/admin/users/roles/available')
  return response.data
}

/**
 * 修复Tags脏数据
 */
export const fixTags = async (): Promise<MaintenanceResult> => {
  const response = await apiClient.post<MaintenanceResult>('/admin/maintenance/fix-tags')
  return response.data
}

/**
 * 链接去重
 */
export const dedupLinks = async (): Promise<MaintenanceResult> => {
  const response = await apiClient.post<MaintenanceResult>('/admin/maintenance/dedup-links')
  return response.data
}

/**
 * 清空链接检测数据
 */
export const clearLinkCheckData = async (): Promise<MaintenanceResult> => {
  const response = await apiClient.post<MaintenanceResult>('/admin/maintenance/clear-link-check-data')
  return response.data
}

/**
 * 清空旧链接检测数据
 */
export const clearOldLinkCheckData = async (data: ClearOldDataRequest): Promise<MaintenanceResult> => {
  const response = await apiClient.post<MaintenanceResult>('/admin/maintenance/clear-old-link-check-data', data)
  return response.data
}

