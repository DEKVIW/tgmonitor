import apiClient from '@/utils/api'
import type {
  LearningAdminItem,
  LearningAdminListResponse,
  LearningAdminOverview,
  LearningCategory,
  LearningChannelUpdateResponse,
  LearningDirectory,
  LearningImportConfirmResult,
  LearningImportPreview,
  LearningResourceListResponse,
} from '@/types/learningResources'

export const getPublicLearningCategories = async (): Promise<LearningCategory[]> => {
  const response = await apiClient.get<LearningCategory[]>('/public/learning-resources/categories')
  return response.data
}

export const getPublicLearningResources = async (params: {
  category?: string
  search?: string
  page?: number
  page_size?: number
} = {}): Promise<LearningResourceListResponse> => {
  const query = new URLSearchParams()
  if (params.category) query.set('category', params.category)
  if (params.search) query.set('search', params.search)
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await apiClient.get<LearningResourceListResponse>(`/public/learning-resources${suffix}`)
  return response.data
}

export const getLearningAdminOverview = async (): Promise<LearningAdminOverview> => {
  const response = await apiClient.get<LearningAdminOverview>('/admin/learning-resources/overview')
  return response.data
}

export const getLearningAdminItems = async (params: {
  search?: string
  category?: string
  page?: number
  page_size?: number
} = {}): Promise<LearningAdminListResponse> => {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  if (params.category) query.set('category', params.category)
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await apiClient.get<LearningAdminListResponse>(`/admin/learning-resources/items${suffix}`)
  return response.data
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

export const updateLearningResource = async (
  resourceId: number,
  payload: { display_title: string; category: string; tags: string[]; share_url: string },
): Promise<LearningAdminItem> => {
  const response = await apiClient.patch<LearningAdminItem>(`/admin/learning-resources/items/${resourceId}`, payload)
  return response.data
}

export const deleteLearningResource = async (resourceId: number): Promise<void> => {
  await apiClient.delete(`/admin/learning-resources/items/${resourceId}`)
}

export const deleteAllImportedLearningResources = async (): Promise<{
  deleted_resources: number
  deleted_links: number
  deleted_transfer_jobs: number
  deleted_import_jobs: number
  deleted_batches: number
  deleted_categories: number
}> => {
  const response = await apiClient.delete('/admin/learning-resources/imported')
  return response.data
}

export const getLearningDirectories = async (accountId: number, parentId = '0'): Promise<LearningDirectory[]> => {
  const response = await apiClient.get<{ items: LearningDirectory[] }>(
    `/admin/learning-resources/directories?account_id=${accountId}&parent_id=${encodeURIComponent(parentId)}`,
  )
  return response.data.items
}

export const previewLearningImport = async (file: File): Promise<LearningImportPreview> => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post<LearningImportPreview>('/admin/learning-resources/imports/preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export const confirmLearningImport = async (
  jobId: number,
  payload: { mode: 'direct' | 'transfer' | 'collect'; target_account_id?: number; save_root?: string },
): Promise<LearningImportConfirmResult> => {
  const response = await apiClient.post<LearningImportConfirmResult>(`/admin/learning-resources/imports/${jobId}/confirm`, payload)
  return response.data
}
