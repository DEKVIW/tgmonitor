/**
 * 管理相关API
 */

import apiClient from '@/utils/api'
import {
  CredentialResponse,
  CredentialCreate,
  ChannelResponse,
  ChannelCreate,
  ChannelSampleResponse,
  PublicSystemConfigResponse,
  SystemConfigResponse,
  SystemConfigUpdate,
  AccountListQuery,
  AccountListResponse,
  AccountRuntimeSettings,
  LinuxDoBatchUpsert,
  LinuxDoConfigResponse,
  LinuxDoConfigUpdate,
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
  DedupRuntimeSettingsResponse,
  DedupRuntimeSettingsUpdate,
  MaintenanceResult,
  ClearOldDataRequest,
  ChannelDiagnosisResult,
  MonitorTestResult,
  LinkCheckDateRange,
  LinkCheckPlanCreate,
  LinkCheckPlanDeleteResult,
  LinkCheckPlanResponse,
  LinkCheckPlanUpdate,
  LinkCheckPreviewRequest,
  LinkCheckPreviewResponse,
  LinkCheckTaskCreate,
  LinkCheckTaskStatus,
  LinkCheckTaskHistory,
  LinkCheckTaskResult,
  LinkCleanupApplyRequest,
  LinkCleanupResult,
  LinkCheckHistoryBatchDeleteRequest,
  LinkCheckHistoryBatchDeleteResult,
  LinkCheckHistoryDeleteResult,
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

export const getChannelSamples = async (
  channelId: number,
  params: { limit?: number; page?: number; page_size?: number; only_with_links?: boolean } = {}
): Promise<ChannelSampleResponse> => {
  const search = new URLSearchParams()

  if (params.limit !== undefined) {
    search.set('limit', String(params.limit))
  }
  if (params.page !== undefined) {
    search.set('page', String(params.page))
  }
  if (params.page_size !== undefined) {
    search.set('page_size', String(params.page_size))
  }
  if (params.only_with_links !== undefined) {
    search.set('only_with_links', String(params.only_with_links))
  }

  const query = search.toString()
  const response = await apiClient.get<ChannelSampleResponse>(
    `/admin/channels/${channelId}/samples${query ? `?${query}` : ''}`
  )
  return response.data
}

/**
 * 开始链接检测任务
 */
export const startLinkCheckTask = async (data: LinkCheckTaskCreate): Promise<LinkCheckTaskStatus> => {
  const response = await apiClient.post<LinkCheckTaskStatus>('/admin/link-check/start', data)
  return response.data
}

export const previewLinkCheckTask = async (
  data: LinkCheckPreviewRequest
): Promise<LinkCheckPreviewResponse> => {
  const response = await apiClient.post<LinkCheckPreviewResponse>('/admin/link-check/preview', data)
  return response.data
}

export const getLinkCheckDateRange = async (): Promise<LinkCheckDateRange> => {
  const response = await apiClient.get<LinkCheckDateRange>('/admin/link-check/date-range')
  return response.data
}

export const getLinkCheckPlans = async (): Promise<LinkCheckPlanResponse[]> => {
  const response = await apiClient.get<LinkCheckPlanResponse[]>('/admin/link-check/plans')
  return response.data
}

export const createLinkCheckPlan = async (data: LinkCheckPlanCreate): Promise<LinkCheckPlanResponse> => {
  const response = await apiClient.post<LinkCheckPlanResponse>('/admin/link-check/plans', data)
  return response.data
}

export const updateLinkCheckPlanById = async (
  planId: number,
  data: LinkCheckPlanUpdate
): Promise<LinkCheckPlanResponse> => {
  const response = await apiClient.put<LinkCheckPlanResponse>(`/admin/link-check/plans/${planId}`, data)
  return response.data
}

export const deleteLinkCheckPlan = async (planId: number): Promise<LinkCheckPlanDeleteResult> => {
  const response = await apiClient.delete<LinkCheckPlanDeleteResult>(`/admin/link-check/plans/${planId}`)
  return response.data
}

export const getLinkCheckPlan = async (): Promise<LinkCheckPlanResponse> => {
  const response = await apiClient.get<LinkCheckPlanResponse>('/admin/link-check/plan')
  return response.data
}

export const updateLinkCheckPlan = async (
  data: LinkCheckPlanUpdate
): Promise<LinkCheckPlanResponse> => {
  const response = await apiClient.put<LinkCheckPlanResponse>('/admin/link-check/plan', data)
  return response.data
}

export const getActiveLinkCheckTask = async (): Promise<LinkCheckTaskStatus> => {
  const response = await apiClient.get<LinkCheckTaskStatus>('/admin/link-check/active')
  return response.data
}

/**
 * 获取任务状态
 */
export const getLinkCheckTaskStatus = async (taskId: string): Promise<LinkCheckTaskStatus> => {
  const response = await apiClient.get<LinkCheckTaskStatus>(`/admin/link-check/tasks/${taskId}`)
  return response.data
}

export const stopLinkCheckTask = async (taskId: string): Promise<LinkCheckTaskStatus> => {
  const response = await apiClient.post<LinkCheckTaskStatus>(`/admin/link-check/tasks/${taskId}/stop`)
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
 * 应用死链清理
 */
export const applyLinkCheckCleanup = async (
  checkTime: string,
  data: LinkCleanupApplyRequest
): Promise<LinkCleanupResult> => {
  const response = await apiClient.post<LinkCleanupResult>(`/admin/link-check/tasks/${checkTime}/cleanup`, data)
  return response.data
}

export const deleteLinkCheckHistory = async (checkTime: string): Promise<LinkCheckHistoryDeleteResult> => {
  const response = await apiClient.delete<LinkCheckHistoryDeleteResult>(`/admin/link-check/tasks/${checkTime}/history`)
  return response.data
}

export const deleteLinkCheckHistories = async (
  data: LinkCheckHistoryBatchDeleteRequest
): Promise<LinkCheckHistoryBatchDeleteResult> => {
  const response = await apiClient.post<LinkCheckHistoryBatchDeleteResult>('/admin/link-check/history/delete', data)
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
export const getPublicConfig = async (): Promise<PublicSystemConfigResponse> => {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/config/public`)
  return response.json() as Promise<PublicSystemConfigResponse>
}

export const getAccounts = async (params: AccountListQuery = {}): Promise<AccountListResponse> => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    search.set(key, String(value))
  })
  const query = search.toString()
  const response = await apiClient.get<AccountListResponse>(`/admin/accounts${query ? `?${query}` : ''}`)
  return response.data
}

export const getAccountRuntimeSettings = async (): Promise<AccountRuntimeSettings> => {
  const response = await apiClient.get<AccountRuntimeSettings>('/admin/accounts/settings')
  return response.data
}

export const updateAccountRuntimeSettings = async (
  data: AccountRuntimeSettings
): Promise<AccountRuntimeSettings> => {
  const response = await apiClient.put<AccountRuntimeSettings>('/admin/accounts/settings', data)
  return response.data
}

export const getLinuxDoConfig = async (): Promise<LinuxDoConfigResponse> => {
  const response = await apiClient.get<LinuxDoConfigResponse>('/admin/accounts/linuxdo')
  return response.data
}

export const updateLinuxDoConfig = async (data: LinuxDoConfigUpdate): Promise<LinuxDoConfigResponse> => {
  const response = await apiClient.put<LinuxDoConfigResponse>('/admin/accounts/linuxdo', data)
  return response.data
}

export const createLinuxDoBatch = async (data: LinuxDoBatchUpsert): Promise<LinuxDoConfigResponse> => {
  const response = await apiClient.post<LinuxDoConfigResponse>('/admin/accounts/linuxdo/batches', data)
  return response.data
}

export const updateLinuxDoBatch = async (
  batchId: number,
  data: LinuxDoBatchUpsert
): Promise<LinuxDoConfigResponse> => {
  const response = await apiClient.put<LinuxDoConfigResponse>(`/admin/accounts/linuxdo/batches/${batchId}`, data)
  return response.data
}

export const getAccount = async (username: string): Promise<UserResponse> => {
  const response = await apiClient.get<UserResponse>(`/admin/accounts/${username}`)
  return response.data
}

export const createAccount = async (data: UserCreate): Promise<UserResponse> => {
  const response = await apiClient.post<UserResponse>('/admin/accounts', data)
  return response.data
}

export const updateAccount = async (username: string, data: UserUpdate): Promise<UserResponse> => {
  const response = await apiClient.put<UserResponse>(`/admin/accounts/${username}`, data)
  return response.data
}

export const changeAccountPassword = async (username: string, data: PasswordChange): Promise<void> => {
  await apiClient.put(`/admin/accounts/${username}/password`, data)
}

export const changeAccountUsername = async (username: string, data: UsernameChange): Promise<void> => {
  await apiClient.put(`/admin/accounts/${username}/username`, data)
}

export const changeAccountRole = async (username: string, data: RoleChange): Promise<void> => {
  await apiClient.put(`/admin/accounts/${username}/role`, data)
}

export const deleteAccount = async (username: string): Promise<void> => {
  await apiClient.delete(`/admin/accounts/${username}`)
}

export const bulkRandomCreateAccounts = async (data: BulkRandomCreateRequest): Promise<BulkCreateResponse> => {
  const response = await apiClient.post<BulkCreateResponse>('/admin/accounts/bulk/random-create', data)
  return response.data
}

export const bulkDeleteAccounts = async (data: BulkUsernamesRequest): Promise<BulkSimpleResponse> => {
  const response = await apiClient.post<BulkSimpleResponse>('/admin/accounts/bulk/delete', data)
  return response.data
}

export const bulkResetAccountPasswords = async (data: BulkUsernamesRequest): Promise<BulkResetResponse> => {
  const response = await apiClient.post<BulkResetResponse>('/admin/accounts/bulk/reset-password', data)
  return response.data
}

export const exportAccounts = async (): Promise<UserResponse[]> => {
  const response = await apiClient.get<UserResponse[]>('/admin/accounts/export')
  return response.data
}

export const getAccountAvailableRoles = async (): Promise<Record<string, string>> => {
  const response = await apiClient.get<Record<string, string>>('/admin/accounts/roles/available')
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
export const getDedupRuntimeSettings = async (): Promise<DedupRuntimeSettingsResponse> => {
  const response = await apiClient.get<DedupRuntimeSettingsResponse>('/admin/maintenance/dedup-runtime')
  return response.data
}

export const updateDedupRuntimeSettings = async (
  data: DedupRuntimeSettingsUpdate
): Promise<DedupRuntimeSettingsResponse> => {
  const response = await apiClient.put<DedupRuntimeSettingsResponse>('/admin/maintenance/dedup-runtime', data)
  return response.data
}

export const clearLinkCheckData = async (): Promise<MaintenanceResult> => {
  const response = await apiClient.post<MaintenanceResult>('/admin/maintenance/link-check-data/clear-all')
  return response.data
}

/**
 * 清空旧链接检测数据
 */
export const clearOldLinkCheckData = async (data: ClearOldDataRequest): Promise<MaintenanceResult> => {
  const response = await apiClient.post<MaintenanceResult>('/admin/maintenance/clear-old-link-check-data', data)
  return response.data
}

