import apiClient from '@/utils/api'
import type {
  PanTransferAccountCreateRequest,
  PanTransferAccountItem,
  PanTransferAccountListResponse,
  PanTransferAccountValidationResponse,
  PanTransferAccountUpdateRequest,
  PanTransferBatchCreateRequest,
  PanTransferBatchDetailResponse,
  PanTransferBatchListResponse,
  PanTransferFollowTaskCreateRequest,
  PanTransferFollowTaskDetailResponse,
  PanTransferFollowTaskFileDiagnosisRequest,
  PanTransferFollowTaskFileDiagnosisResponse,
  PanTransferFollowTaskListResponse,
  PanTransferFollowTaskSettingsUpdateRequest,
  PanTransferFollowTaskSyncRequest,
  PanTransferFollowTaskSyncResponse,
  PanTransferLinkDirectoryPreviewRequest,
  PanTransferLinkDirectoryPreviewResponse,
  PanTransferManualPublishRequest,
  PanTransferMessagePublishRequest,
  PanTransferMessagePublishResponse,
  PanTransferPublishRetireRequest,
  PanTransferPublishRecordItem,
  PanTransferPublishRecordListResponse,
  PanTransferPublishRuleUpdateRequest,
  PanTransferPublishRecordUpdateRequest,
  PanTransferBatchRetryRequest,
  PanTransferDeleteResponse,
  PanTransferManualPreviewRequest,
  PanTransferManualPreviewResponse,
} from '@/types/panTransfer'

export const listPanTransferAccounts = async (platform?: string): Promise<PanTransferAccountListResponse> => {
  const response = await apiClient.get<PanTransferAccountListResponse>(
    `/admin/pan-transfer/accounts${platform ? `?platform=${encodeURIComponent(platform)}` : ''}`
  )
  return response.data
}

export const createPanTransferAccount = async (
  payload: PanTransferAccountCreateRequest
): Promise<PanTransferAccountItem> => {
  const response = await apiClient.post<PanTransferAccountItem>('/admin/pan-transfer/accounts', payload)
  return response.data
}

export const updatePanTransferAccount = async (
  accountId: number,
  payload: PanTransferAccountUpdateRequest
): Promise<PanTransferAccountItem> => {
  const response = await apiClient.put<PanTransferAccountItem>(`/admin/pan-transfer/accounts/${accountId}`, payload)
  return response.data
}

export const deletePanTransferAccount = async (accountId: number): Promise<PanTransferDeleteResponse> => {
  const response = await apiClient.delete<PanTransferDeleteResponse>(`/admin/pan-transfer/accounts/${accountId}`)
  return response.data
}

export const validatePanTransferAccount = async (
  accountId: number
): Promise<PanTransferAccountValidationResponse> => {
  const response = await apiClient.post<PanTransferAccountValidationResponse>(
    `/admin/pan-transfer/accounts/${accountId}/validate`
  )
  return response.data
}

export const previewManualPanTransfer = async (
  payload: PanTransferManualPreviewRequest
): Promise<PanTransferManualPreviewResponse> => {
  const response = await apiClient.post<PanTransferManualPreviewResponse>('/admin/pan-transfer/preview/manual', payload)
  return response.data
}

export const createManualPanTransferBatch = async (
  payload: PanTransferBatchCreateRequest
): Promise<PanTransferBatchDetailResponse> => {
  const response = await apiClient.post<PanTransferBatchDetailResponse>('/admin/pan-transfer/batches/manual', payload)
  return response.data
}

export const listPanTransferBatches = async (
  page = 1,
  pageSize = 20
): Promise<PanTransferBatchListResponse> => {
  const response = await apiClient.get<PanTransferBatchListResponse>(
    `/admin/pan-transfer/batches?page=${page}&page_size=${pageSize}`
  )
  return response.data
}

export const getPanTransferBatchDetail = async (batchId: number): Promise<PanTransferBatchDetailResponse> => {
  const response = await apiClient.get<PanTransferBatchDetailResponse>(`/admin/pan-transfer/batches/${batchId}`)
  return response.data
}

export const retryPanTransferBatch = async (
  batchId: number,
  payload: PanTransferBatchRetryRequest = {}
): Promise<PanTransferBatchDetailResponse> => {
  const response = await apiClient.post<PanTransferBatchDetailResponse>(
    `/admin/pan-transfer/batches/${batchId}/retry`,
    payload
  )
  return response.data
}

export const cancelPanTransferBatch = async (batchId: number): Promise<PanTransferBatchDetailResponse> => {
  const response = await apiClient.post<PanTransferBatchDetailResponse>(`/admin/pan-transfer/batches/${batchId}/cancel`)
  return response.data
}

export const clearPanTransferBatchLogs = async (batchId: number): Promise<PanTransferBatchDetailResponse> => {
  const response = await apiClient.post<PanTransferBatchDetailResponse>(`/admin/pan-transfer/batches/${batchId}/logs/clear`)
  return response.data
}

export const startPanTransferBatch = async (batchId: number): Promise<PanTransferBatchDetailResponse> => {
  const response = await apiClient.post<PanTransferBatchDetailResponse>(`/admin/pan-transfer/batches/${batchId}/start`)
  return response.data
}

export const deletePanTransferBatch = async (batchId: number): Promise<PanTransferDeleteResponse> => {
  const response = await apiClient.delete<PanTransferDeleteResponse>(`/admin/pan-transfer/batches/${batchId}`)
  return response.data
}

export const publishPanTransferBatchItemMessage = async (
  batchId: number,
  itemId: number,
  payload: PanTransferMessagePublishRequest
): Promise<PanTransferMessagePublishResponse> => {
  const response = await apiClient.post<PanTransferMessagePublishResponse>(
    `/admin/pan-transfer/batches/${batchId}/items/${itemId}/publish`,
    payload
  )
  return response.data
}

export const publishManualPanTransferMessage = async (
  payload: PanTransferManualPublishRequest
): Promise<PanTransferMessagePublishResponse> => {
  const response = await apiClient.post<PanTransferMessagePublishResponse>('/admin/pan-transfer/publishes/manual', payload)
  return response.data
}

export const previewPanTransferLinkDirectory = async (
  payload: PanTransferLinkDirectoryPreviewRequest
): Promise<PanTransferLinkDirectoryPreviewResponse> => {
  const response = await apiClient.post<PanTransferLinkDirectoryPreviewResponse>(
    '/admin/pan-transfer/link-preview',
    payload
  )
  return response.data
}

export const listPanTransferPublishRecords = async (
  page = 1,
  pageSize = 20,
  options?: {
    keyword?: string
    platform?: string
    scope?: 'active' | 'archived' | 'all' | string
    sortBy?: string
    sortOrder?: 'asc' | 'desc' | string
  }
): Promise<PanTransferPublishRecordListResponse> => {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (options?.keyword?.trim()) params.set('keyword', options.keyword.trim())
  if (options?.platform?.trim()) params.set('platform', options.platform.trim())
  if (options?.scope?.trim()) params.set('scope', options.scope.trim())
  if (options?.sortBy?.trim()) params.set('sort_by', options.sortBy.trim())
  if (options?.sortOrder?.trim()) params.set('sort_order', options.sortOrder.trim())
  const response = await apiClient.get<PanTransferPublishRecordListResponse>(
    `/admin/pan-transfer/publishes?${params.toString()}`
  )
  return response.data
}

export const republishPanTransferPublishRecord = async (
  recordId: number
): Promise<PanTransferPublishRecordItem> => {
  const response = await apiClient.post<PanTransferPublishRecordItem>(`/admin/pan-transfer/publishes/${recordId}/republish`)
  return response.data
}

export const updatePanTransferPublishRecord = async (
  recordId: number,
  payload: PanTransferPublishRecordUpdateRequest
): Promise<PanTransferPublishRecordItem> => {
  const response = await apiClient.put<PanTransferPublishRecordItem>(`/admin/pan-transfer/publishes/${recordId}`, payload)
  return response.data
}

export const validatePanTransferPublishRecord = async (
  recordId: number
): Promise<PanTransferPublishRecordItem> => {
  const response = await apiClient.post<PanTransferPublishRecordItem>(`/admin/pan-transfer/publishes/${recordId}/validate`)
  return response.data
}

export const archivePanTransferPublishRecord = async (
  recordId: number
): Promise<PanTransferPublishRecordItem> => {
  const response = await apiClient.post<PanTransferPublishRecordItem>(`/admin/pan-transfer/publishes/${recordId}/archive`)
  return response.data
}

export const retirePanTransferPublishRecord = async (
  recordId: number,
  payload: PanTransferPublishRetireRequest
): Promise<PanTransferPublishRecordItem> => {
  const response = await apiClient.post<PanTransferPublishRecordItem>(
    `/admin/pan-transfer/publishes/${recordId}/retire`,
    payload
  )
  return response.data
}

export const deletePanTransferPublishRecord = async (
  recordId: number
): Promise<PanTransferDeleteResponse> => {
  const response = await apiClient.delete<PanTransferDeleteResponse>(`/admin/pan-transfer/publishes/${recordId}`)
  return response.data
}

export const updatePanTransferPublishRule = async (
  recordId: number,
  payload: PanTransferPublishRuleUpdateRequest
): Promise<PanTransferPublishRecordItem> => {
  const response = await apiClient.put<PanTransferPublishRecordItem>(`/admin/pan-transfer/publishes/${recordId}/rule`, payload)
  return response.data
}

export const refreshPanTransferPublishRecordShare = async (
  recordId: number
): Promise<PanTransferPublishRecordItem> => {
  const response = await apiClient.post<PanTransferPublishRecordItem>(`/admin/pan-transfer/publishes/${recordId}/refresh-share`)
  return response.data
}

export const createPanTransferFollowTaskFromBatchItem = async (
  batchId: number,
  itemId: number,
  payload: PanTransferFollowTaskCreateRequest = {}
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskDetailResponse>(
    `/admin/pan-transfer/batches/${batchId}/items/${itemId}/follow`,
    payload
  )
  return response.data
}

export const listPanTransferFollowTasks = async (
  page = 1,
  pageSize = 20,
  status?: string
): Promise<PanTransferFollowTaskListResponse> => {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (status) {
    params.set('status', status)
  }
  const response = await apiClient.get<PanTransferFollowTaskListResponse>(
    `/admin/pan-transfer/follow-tasks?${params.toString()}`
  )
  return response.data
}

export const getPanTransferFollowTaskDetail = async (
  taskId: number
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.get<PanTransferFollowTaskDetailResponse>(`/admin/pan-transfer/follow-tasks/${taskId}`)
  return response.data
}

export const updatePanTransferFollowTaskSettings = async (
  taskId: number,
  payload: PanTransferFollowTaskSettingsUpdateRequest
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.patch<PanTransferFollowTaskDetailResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/settings`,
    payload
  )
  return response.data
}

export const queuePanTransferFollowTaskCheck = async (
  taskId: number
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskDetailResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/queue`
  )
  return response.data
}

export const createPanTransferFollowSyncBatch = async (
  taskId: number,
  payload: PanTransferFollowTaskSyncRequest
): Promise<PanTransferFollowTaskSyncResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskSyncResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/sync`,
    payload
  )
  return response.data
}

export const diagnosePanTransferFollowTaskFiles = async (
  taskId: number,
  payload: PanTransferFollowTaskFileDiagnosisRequest
): Promise<PanTransferFollowTaskFileDiagnosisResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskFileDiagnosisResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/file-diagnosis`,
    payload
  )
  return response.data
}

export const pausePanTransferFollowTask = async (
  taskId: number
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskDetailResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/pause`
  )
  return response.data
}

export const resumePanTransferFollowTask = async (
  taskId: number
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskDetailResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/resume`
  )
  return response.data
}

export const clearPanTransferFollowTaskCandidate = async (
  taskId: number
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskDetailResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/candidate/clear`
  )
  return response.data
}

export const clearPanTransferFollowTaskLogs = async (
  taskId: number
): Promise<PanTransferFollowTaskDetailResponse> => {
  const response = await apiClient.post<PanTransferFollowTaskDetailResponse>(
    `/admin/pan-transfer/follow-tasks/${taskId}/logs/clear`
  )
  return response.data
}

export const deletePanTransferFollowTask = async (taskId: number): Promise<PanTransferDeleteResponse> => {
  const response = await apiClient.delete<PanTransferDeleteResponse>(`/admin/pan-transfer/follow-tasks/${taskId}`)
  return response.data
}
