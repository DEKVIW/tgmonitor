import apiClient from '@/utils/api'
import type {
  ResourceOpsAiModelListResponse,
  ResourceOpsAiProviderDraftRequest,
  ResourceOpsAiTestRequest,
  ResourceOpsAiTestResponse,
  ResourceOpsCandidateDetailResponse,
  ResourceOpsCandidateListResponse,
  ResourceOpsCandidateQuery,
  ResourceOpsCatalogStatusResponse,
  ResourceOpsOverviewResponse,
  ResourceOpsPlatformDistributionResponse,
  ResourceOpsRecognitionRunResponse,
  ResourceOpsRetentionRunResponse,
  ResourceOpsRuntimeSettingsResponse,
  ResourceOpsRuntimeSettingsUpdateRequest,
  ResourceOpsTrendResponse,
  ResourceOpsWorkbenchDetailResponse,
  ResourceOpsWorkbenchListResponse,
  ResourceOpsWorkbenchQuery,
  ResourceOpsWorkbenchUpdateRequest,
} from '@/types/resourceOps'

export const getResourceOpsOverview = async (): Promise<ResourceOpsOverviewResponse> => {
  const response = await apiClient.get<ResourceOpsOverviewResponse>('/admin/resource-ops/overview')
  return response.data
}

export const getResourceOpsTrend = async (days: number = 30): Promise<ResourceOpsTrendResponse> => {
  const response = await apiClient.get<ResourceOpsTrendResponse>(`/admin/resource-ops/trend?days=${days}`)
  return response.data
}

export const getResourceOpsPlatformDistribution = async (
  days: number = 30
): Promise<ResourceOpsPlatformDistributionResponse> => {
  const response = await apiClient.get<ResourceOpsPlatformDistributionResponse>(
    `/admin/resource-ops/platforms?days=${days}`
  )
  return response.data
}

export const getResourceOpsCatalogStatus = async (): Promise<ResourceOpsCatalogStatusResponse> => {
  const response = await apiClient.get<ResourceOpsCatalogStatusResponse>('/admin/resource-ops/catalog/status')
  return response.data
}

export const syncResourceOpsCatalog = async (
  batchSize: number = 500
): Promise<ResourceOpsCatalogStatusResponse> => {
  const response = await apiClient.post<ResourceOpsCatalogStatusResponse>(
    `/admin/resource-ops/catalog/sync?batch_size=${batchSize}`
  )
  return response.data
}

export const listResourceOpsCandidates = async (
  query: ResourceOpsCandidateQuery = {}
): Promise<ResourceOpsCandidateListResponse> => {
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    params.set(key, String(value))
  })
  const search = params.toString()
  const response = await apiClient.get<ResourceOpsCandidateListResponse>(
    `/admin/resource-ops/candidates${search ? `?${search}` : ''}`
  )
  return response.data
}

export const getResourceOpsCandidateDetail = async (
  linkTargetId: number
): Promise<ResourceOpsCandidateDetailResponse> => {
  const response = await apiClient.get<ResourceOpsCandidateDetailResponse>(
    `/admin/resource-ops/candidates/${linkTargetId}`
  )
  return response.data
}

export const listResourceOpsWorkbenchItems = async (
  query: ResourceOpsWorkbenchQuery = {}
): Promise<ResourceOpsWorkbenchListResponse> => {
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    params.set(key, String(value))
  })
  const search = params.toString()
  const response = await apiClient.get<ResourceOpsWorkbenchListResponse>(
    `/admin/resource-ops/workbench/items${search ? `?${search}` : ''}`
  )
  return response.data
}

export const getResourceOpsWorkbenchDetail = async (
  linkTargetId: number
): Promise<ResourceOpsWorkbenchDetailResponse> => {
  const response = await apiClient.get<ResourceOpsWorkbenchDetailResponse>(
    `/admin/resource-ops/workbench/items/${linkTargetId}`
  )
  return response.data
}

export const updateResourceOpsWorkbenchItem = async (
  linkTargetId: number,
  payload: ResourceOpsWorkbenchUpdateRequest
): Promise<ResourceOpsWorkbenchDetailResponse> => {
  const response = await apiClient.put<ResourceOpsWorkbenchDetailResponse>(
    `/admin/resource-ops/workbench/items/${linkTargetId}`,
    payload
  )
  return response.data
}

export const getResourceOpsRuntimeSettings = async (): Promise<ResourceOpsRuntimeSettingsResponse> => {
  const response = await apiClient.get<ResourceOpsRuntimeSettingsResponse>('/admin/resource-ops/settings')
  return response.data
}

export const updateResourceOpsRuntimeSettings = async (
  payload: ResourceOpsRuntimeSettingsUpdateRequest
): Promise<ResourceOpsRuntimeSettingsResponse> => {
  const response = await apiClient.put<ResourceOpsRuntimeSettingsResponse>('/admin/resource-ops/settings', payload)
  return response.data
}

export const listResourceOpsAiModels = async (
  payload: ResourceOpsAiProviderDraftRequest
): Promise<ResourceOpsAiModelListResponse> => {
  const response = await apiClient.post<ResourceOpsAiModelListResponse>('/admin/resource-ops/ai/models', payload)
  return response.data
}

export const testResourceOpsAiConnection = async (
  payload: ResourceOpsAiTestRequest
): Promise<ResourceOpsAiTestResponse> => {
  const response = await apiClient.post<ResourceOpsAiTestResponse>('/admin/resource-ops/ai/test', payload)
  return response.data
}

export const syncResourceOpsRecognition = async (
): Promise<ResourceOpsRecognitionRunResponse> => {
  const response = await apiClient.post<ResourceOpsRecognitionRunResponse>('/admin/resource-ops/recognition/pending')
  return response.data
}

export const syncResourceOpsRecognitionFull = async (
): Promise<ResourceOpsRecognitionRunResponse> => {
  const response = await apiClient.post<ResourceOpsRecognitionRunResponse>('/admin/resource-ops/recognition/all')
  return response.data
}

export const runResourceOpsRetention = async (): Promise<ResourceOpsRetentionRunResponse> => {
  const response = await apiClient.post<ResourceOpsRetentionRunResponse>('/admin/resource-ops/maintenance/run')
  return response.data
}
