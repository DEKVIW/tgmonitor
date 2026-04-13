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

export const startPanTransferBatch = async (batchId: number): Promise<PanTransferBatchDetailResponse> => {
  const response = await apiClient.post<PanTransferBatchDetailResponse>(`/admin/pan-transfer/batches/${batchId}/start`)
  return response.data
}

export const deletePanTransferBatch = async (batchId: number): Promise<PanTransferDeleteResponse> => {
  const response = await apiClient.delete<PanTransferDeleteResponse>(`/admin/pan-transfer/batches/${batchId}`)
  return response.data
}
