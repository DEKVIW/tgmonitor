/**
 * 消息相关类型定义
 */

export interface MessageResponse {
  id: number
  timestamp: string
  title?: string
  description?: string
  links?: Record<string, any>
  tracked_links?: MessageTrackedLink[]
  tags?: string[]
  source?: string
  channel?: string
  group_name?: string
  bot?: string
  created_at: string
  netdisk_types?: string[]
}

export interface MessageTrackedLink {
  link_ref_id: number
  link_target_id: number
  provider_label: string
  link_label?: string | null
  display_text: string
  target_url: string
  redirect_url: string
}

export interface MessageListResponse {
  messages: MessageResponse[]
  total: number
  page: number
  page_size: number
  max_page: number
}

export type MessageSortMode = 'relevance' | 'newest'

export interface MessageFilters {
  search_query?: string
  sort_mode?: MessageSortMode
  time_range?: string
  selected_tags?: string[]
  selected_netdisks?: string[]
  min_content_length?: number
  has_links_only?: boolean
  page?: number
  page_size?: number
}

export interface TagStatsResponse {
  tag: string
  count: number
}

