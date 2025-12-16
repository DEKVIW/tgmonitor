/**
 * 统计相关类型定义
 */

export interface StatisticsOverview {
  total_messages: number
  today_messages: number
  total_links: number
}

export interface DailyTrendItem {
  date: string
  messages: number
  links: number
}

export interface DailyTrendResponse {
  days: DailyTrendItem[]
}

export interface DedupStatsItem {
  hour: string
  deleted_count: number
}

export interface DedupStatsResponse {
  hours: DedupStatsItem[]
}

export interface NetdiskDistributionItem {
  netdisk_name: string
  link_count: number
  percentage: number
}

export interface NetdiskDistributionResponse {
  distribution: NetdiskDistributionItem[]
}

