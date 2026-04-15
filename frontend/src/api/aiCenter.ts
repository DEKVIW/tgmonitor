import apiClient from '@/utils/api'
import type {
  AiCenterCallEventClearResponse,
  AiCenterCallEventListResponse,
  AiCenterOverviewResponse,
  AiCenterProviderItem,
  AiCenterProviderListResponse,
  AiCenterProviderTestRequest,
  AiCenterProviderTestResponse,
  AiCenterProviderUpsertRequest,
  AiCenterRouteItem,
  AiCenterRouteListResponse,
  AiCenterRouteReadinessResponse,
  AiCenterRouteTestRequest,
  AiCenterRouteTestResponse,
  AiCenterRouteUpsertRequest,
  AiCenterDeleteResponse,
} from '@/types/aiCenter'

export const getAiCenterOverview = async (): Promise<AiCenterOverviewResponse> => {
  const response = await apiClient.get<AiCenterOverviewResponse>('/admin/ai-center/overview')
  return response.data
}

export const listAiProviders = async (): Promise<AiCenterProviderListResponse> => {
  const response = await apiClient.get<AiCenterProviderListResponse>('/admin/ai-center/providers')
  return response.data
}

export const createAiProvider = async (payload: AiCenterProviderUpsertRequest): Promise<AiCenterProviderItem> => {
  const response = await apiClient.post<AiCenterProviderItem>('/admin/ai-center/providers', payload)
  return response.data
}

export const updateAiProvider = async (
  providerId: number,
  payload: AiCenterProviderUpsertRequest
): Promise<AiCenterProviderItem> => {
  const response = await apiClient.put<AiCenterProviderItem>(`/admin/ai-center/providers/${providerId}`, payload)
  return response.data
}

export const deleteAiProvider = async (providerId: number): Promise<AiCenterDeleteResponse> => {
  const response = await apiClient.delete<AiCenterDeleteResponse>(`/admin/ai-center/providers/${providerId}`)
  return response.data
}

export const refreshAiProviderModels = async (providerId: number): Promise<AiCenterProviderItem> => {
  const response = await apiClient.post<AiCenterProviderItem>(`/admin/ai-center/providers/${providerId}/models/refresh`)
  return response.data
}

export const testAiProvider = async (
  providerId: number,
  payload: AiCenterProviderTestRequest = {}
): Promise<AiCenterProviderTestResponse> => {
  const response = await apiClient.post<AiCenterProviderTestResponse>(`/admin/ai-center/providers/${providerId}/test`, payload)
  return response.data
}

export const listAiRoutes = async (): Promise<AiCenterRouteListResponse> => {
  const response = await apiClient.get<AiCenterRouteListResponse>('/admin/ai-center/routes')
  return response.data
}

export const getAiRoute = async (routeKey: string): Promise<AiCenterRouteItem> => {
  const response = await apiClient.get<AiCenterRouteItem>(`/admin/ai-center/routes/${encodeURIComponent(routeKey)}`)
  return response.data
}

export const updateAiRoute = async (
  routeKey: string,
  payload: AiCenterRouteUpsertRequest
): Promise<AiCenterRouteItem> => {
  const response = await apiClient.put<AiCenterRouteItem>(`/admin/ai-center/routes/${encodeURIComponent(routeKey)}`, payload)
  return response.data
}

export const getAiRouteReadiness = async (routeKey: string): Promise<AiCenterRouteReadinessResponse> => {
  const response = await apiClient.get<AiCenterRouteReadinessResponse>(
    `/admin/ai-center/routes/${encodeURIComponent(routeKey)}/readiness`
  )
  return response.data
}

export const testAiRoute = async (
  routeKey: string,
  payload: AiCenterRouteTestRequest
): Promise<AiCenterRouteTestResponse> => {
  const response = await apiClient.post<AiCenterRouteTestResponse>(
    `/admin/ai-center/routes/${encodeURIComponent(routeKey)}/test`,
    payload
  )
  return response.data
}

export const listAiCallEvents = async (
  routeKey?: string,
  limit: number = 50
): Promise<AiCenterCallEventListResponse> => {
  const params = new URLSearchParams({
    limit: String(limit),
  })
  if (routeKey) params.set('route_key', routeKey)
  const response = await apiClient.get<AiCenterCallEventListResponse>(`/admin/ai-center/events?${params.toString()}`)
  return response.data
}

export const clearAiCallEvents = async (routeKey?: string): Promise<AiCenterCallEventClearResponse> => {
  const params = new URLSearchParams()
  if (routeKey) params.set('route_key', routeKey)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const response = await apiClient.post<AiCenterCallEventClearResponse>(`/admin/ai-center/events/clear${suffix}`)
  return response.data
}
