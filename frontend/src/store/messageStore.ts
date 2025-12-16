/**
 * 消息状态管理
 */

import { create } from 'zustand'
import { MessageFilters } from '@/types/message'

interface MessageState {
  filters: MessageFilters
  setFilters: (filters: Partial<MessageFilters>) => void
  resetFilters: () => void
  refreshInterval: number
  setRefreshInterval: (value: number) => void
}

const defaultFilters: MessageFilters = {
  search_query: '',
  time_range: '最近24小时',
  selected_tags: [],
  selected_netdisks: [],
  min_content_length: 0,
  has_links_only: false,
  page: 1,
  page_size: 100,
}

export const useMessageStore = create<MessageState>((set) => ({
  filters: defaultFilters,
  refreshInterval: 60,
  
  setFilters: (newFilters: Partial<MessageFilters>) => {
    set((state) => {
      const hasExplicitPage = Object.prototype.hasOwnProperty.call(newFilters, 'page')
      // 若未显式传入 page，则重置到第一页；否则使用传入值
      const nextPage = hasExplicitPage ? newFilters.page : 1
      return {
        filters: { ...state.filters, ...newFilters, page: nextPage ?? state.filters.page },
      }
    })
  },
  
  resetFilters: () => {
    set({ filters: defaultFilters })
  },

  setRefreshInterval: (value: number) => {
    set({ refreshInterval: value })
  },
}))

