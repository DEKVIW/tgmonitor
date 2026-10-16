import apiClient from '@/utils/api'
import type {
  MediaWallCategory,
  MediaWallImportPreview,
  MediaWallImportResult,
  MediaWallItem,
  MediaWallItemInput,
  MediaWallLink,
  MediaWallSource,
  MediaWallSyncTask,
  MediaWallListResponse,
} from '@/types/mediaWall'

export const getPublicMediaWallCategories = async (): Promise<MediaWallCategory[]> => {
  const response = await apiClient.get<MediaWallCategory[]>('/public/media-wall/categories')
  return response.data
}

export const getPublicMediaWall = async (params: {
  category?: string
  search?: string
  page?: number
  page_size?: number
} = {}): Promise<MediaWallListResponse> => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await apiClient.get<MediaWallListResponse>(`/public/media-wall${suffix}`)
  return response.data
}

export const getPublicMediaWallItem = async (itemId: number): Promise<MediaWallItem> => {
  const response = await apiClient.get<MediaWallItem>(`/public/media-wall/items/${itemId}`)
  return response.data
}

export const getMediaWallCategories = async (): Promise<MediaWallCategory[]> => {
  const response = await apiClient.get<MediaWallCategory[]>('/admin/media-wall/categories')
  return response.data
}

export const createMediaWallCategory = async (payload: { name: string; slug?: string; sort_order: number; is_enabled: boolean }): Promise<MediaWallCategory> => {
  const response = await apiClient.post<MediaWallCategory>('/admin/media-wall/categories', payload)
  return response.data
}

export const updateMediaWallCategory = async (id: number, payload: { name: string; slug?: string; sort_order: number; is_enabled: boolean }): Promise<MediaWallCategory> => {
  const response = await apiClient.put<MediaWallCategory>(`/admin/media-wall/categories/${id}`, payload)
  return response.data
}

export const disableMediaWallCategory = async (id: number): Promise<MediaWallCategory> => {
  const response = await apiClient.delete<MediaWallCategory>(`/admin/media-wall/categories/${id}`)
  return response.data
}

export const getMediaWallItems = async (params: { search?: string; visibility?: string; category_id?: number } = {}): Promise<MediaWallItem[]> => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await apiClient.get<MediaWallItem[]>(`/admin/media-wall/items${suffix}`)
  return response.data
}

export const createMediaWallItem = async (payload: MediaWallItemInput): Promise<MediaWallItem> => {
  const response = await apiClient.post<MediaWallItem>('/admin/media-wall/items', payload)
  return response.data
}

export const updateMediaWallItem = async (id: number, payload: MediaWallItemInput): Promise<MediaWallItem> => {
  const response = await apiClient.put<MediaWallItem>(`/admin/media-wall/items/${id}`, payload)
  return response.data
}

export const deleteMediaWallItem = async (id: number): Promise<MediaWallItem> => {
    const response = await apiClient.delete<MediaWallItem>(`/admin/media-wall/items/${id}`)
    return response.data
}

export const deleteMediaWallItems = async (itemIds: number[]): Promise<{ deleted_ids: number[]; deleted_count: number }> => {
  const response = await apiClient.post<{ deleted_ids: number[]; deleted_count: number }>('/admin/media-wall/items/bulk-delete', {
    item_ids: itemIds,
  })
  return response.data
}

export const addMediaWallLink = async (itemId: number, payload: { url: string; label?: string; source_type?: string; is_primary?: boolean }): Promise<MediaWallLink> => {
  const response = await apiClient.post<MediaWallLink>(`/admin/media-wall/items/${itemId}/links`, payload)
  return response.data
}

export const updateMediaWallLink = async (linkId: number, payload: { url: string; label?: string; is_enabled: boolean; is_primary: boolean }): Promise<MediaWallLink> => {
  const response = await apiClient.put<MediaWallLink>(`/admin/media-wall/links/${linkId}`, payload)
  return response.data
}

export const getMediaWallSyncTasks = async (): Promise<MediaWallSyncTask[]> => {
  const response = await apiClient.get<MediaWallSyncTask[]>('/admin/media-wall/sync-tasks')
  return response.data
}

export const getMediaWallSources = async (): Promise<MediaWallSource[]> => {
  const response = await apiClient.get<MediaWallSource[]>('/admin/media-wall/sources')
  return response.data
}

export const createMediaWallSource = async (payload: Omit<MediaWallSource, 'id' | 'last_checked_at' | 'last_refreshed_at' | 'last_error_message' | 'endpoint_count'>): Promise<MediaWallSource> => {
  const response = await apiClient.post<MediaWallSource>('/admin/media-wall/sources', payload)
  return response.data
}

export const updateMediaWallSource = async (id: number, payload: Omit<MediaWallSource, 'id' | 'last_checked_at' | 'last_refreshed_at' | 'last_error_message' | 'endpoint_count'>): Promise<MediaWallSource> => {
  const response = await apiClient.put<MediaWallSource>(`/admin/media-wall/sources/${id}`, payload)
  return response.data
}

export const testMediaWallSource = async (id: number, refresh = false): Promise<{ source: MediaWallSource; ok: boolean; endpoint_count: number; error?: string | null }> => {
  const response = await apiClient.post<{ source: MediaWallSource; ok: boolean; endpoint_count: number; error?: string | null }>(`/admin/media-wall/sources/${id}/${refresh ? 'refresh' : 'test'}`)
  return response.data
}

export const previewMediaWallImport = async (file: File): Promise<MediaWallImportPreview> => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post<MediaWallImportPreview>('/admin/media-wall/imports/preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export const confirmMediaWallImport = async (jobId: number, payload: { category_ids: number[]; visibility: string }): Promise<MediaWallImportResult> => {
  const response = await apiClient.post<MediaWallImportResult>(`/admin/media-wall/imports/${jobId}/confirm`, payload)
  return response.data
}
