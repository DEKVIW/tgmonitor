import apiClient from '@/utils/api'
import type {
  LearningAdminItem,
  LearningAdminOverview,
  LearningCategory,
  LearningChannelUpdateResponse,
  LearningResourceListResponse,
} from '@/types/learningResources'

export const getPublicLearningCategories = async (): Promise<LearningCategory[]> => {
  const response = await apiClient.get<LearningCategory[]>('/public/learning-resources/categories')
  return response.data
}

export const getPublicLearningResources = async (params: {
  category?: string
  search?: string
} = {}): Promise<LearningResourceListResponse> => {
  const query = new URLSearchParams()
  if (params.category) query.set('category', params.category)
  if (params.search) query.set('search', params.search)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await apiClient.get<LearningResourceListResponse>(`/public/learning-resources${suffix}`)
  return response.data
}

export const getLearningAdminOverview = async (): Promise<LearningAdminOverview> => {
  const response = await apiClient.get<LearningAdminOverview>('/admin/learning-resources/overview')
  return response.data
}

export const getLearningAdminItems = async (search?: string): Promise<LearningAdminItem[]> => {
  const suffix = search ? `?search=${encodeURIComponent(search)}` : ''
  const response = await apiClient.get<{ items: LearningAdminItem[] }>(`/admin/learning-resources/items${suffix}`)
  return response.data.items
}

export const updateLearningChannel = async (
  channelId: number,
  payload: {
    is_enabled?: boolean
    target_account_id?: number
    save_root?: string
    channel_title?: string
  },
): Promise<LearningChannelUpdateResponse> => {
  const response = await apiClient.put<LearningChannelUpdateResponse>(`/admin/learning-resources/channels/${channelId}`, payload)
  return response.data
}

export const updateLearningVisibility = async (resourceId: number, visible: boolean): Promise<LearningAdminItem> => {
  const response = await apiClient.patch<LearningAdminItem>(`/admin/learning-resources/items/${resourceId}/visibility`, { visible })
  return response.data
}

export const retryLearningResource = async (resourceId: number): Promise<LearningAdminItem> => {
  const response = await apiClient.post<LearningAdminItem>(`/admin/learning-resources/items/${resourceId}/retry`)
  return response.data
}
