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

export interface ActivityHeatmapCell {
  date: string
  hour: number
  message_count: number
}

export interface ActivityHeatmapResponse {
  dates: string[]
  hours: number[]
  cells: ActivityHeatmapCell[]
  max_count: number
}

export interface AdminChannelMatrixRow {
  row_key: string
  monitor_channel_config_id?: number | null
  monitor_channel_key?: string | null
  monitor_channel_title: string
  total_messages: number
  total_links: number
  message_counts: Record<string, number>
  link_counts: Record<string, number>
  trend: number[]
}

export interface AdminChannelMatrixResponse {
  days: number
  dates: string[]
  rows: AdminChannelMatrixRow[]
  available_since?: string | null
  max_daily_messages: number
}

