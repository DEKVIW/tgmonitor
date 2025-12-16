/**
 * 消息相关API
 */

import apiClient from '@/utils/api'
import { MessageListResponse, MessageResponse, TagStatsResponse } from '@/types/message'
import { MessageFilters } from '@/types/message'

/**
 * 获取消息列表
 */
export const getMessages = async (filters: MessageFilters): Promise<MessageListResponse> => {
  const params = new URLSearchParams()
  
  if (filters.search_query) params.append('search_query', filters.search_query)
  if (filters.time_range) params.append('time_range', filters.time_range)
  if (filters.selected_tags?.length) {
    filters.selected_tags.forEach(tag => params.append('selected_tags', tag))
  }
  if (filters.selected_netdisks?.length) {
    filters.selected_netdisks.forEach(nd => params.append('selected_netdisks', nd))
  }
  if (filters.min_content_length) params.append('min_content_length', filters.min_content_length.toString())
  if (filters.has_links_only) params.append('has_links_only', 'true')
  params.append('page', (filters.page || 1).toString())
  params.append('page_size', (filters.page_size || 100).toString())

  const response = await apiClient.get<MessageListResponse>(`/messages?${params.toString()}`)
  return response.data
}

/**
 * 获取单条消息详情
 */
export const getMessageById = async (id: number): Promise<MessageResponse> => {
  const response = await apiClient.get<MessageResponse>(`/messages/${id}`)
  return response.data
}

/**
 * 获取标签统计
 */
export const getTagStats = async (limit: number = 50): Promise<TagStatsResponse[]> => {
  const response = await apiClient.get<TagStatsResponse[]>(`/messages/tags/stats?limit=${limit}`)
  return response.data
}

