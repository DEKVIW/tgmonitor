/**
 * 统计相关API
 */

import apiClient from '@/utils/api'
import {
  StatisticsOverview,
  DailyTrendResponse,
  DedupStatsResponse,
  NetdiskDistributionResponse,
} from '@/types/statistics'

/**
 * 获取总体统计
 */
export const getStatisticsOverview = async (): Promise<StatisticsOverview> => {
  const response = await apiClient.get<StatisticsOverview>('/statistics/overview')
  return response.data
}

/**
 * 获取每日趋势
 */
export const getDailyTrend = async (days: number = 10): Promise<DailyTrendResponse> => {
  const response = await apiClient.get<DailyTrendResponse>(`/statistics/daily-trend?days=${days}`)
  return response.data
}

/**
 * 获取去重统计
 */
export const getDedupStats = async (hours: number = 10): Promise<DedupStatsResponse> => {
  const response = await apiClient.get<DedupStatsResponse>(`/statistics/dedup-stats?hours=${hours}`)
  return response.data
}

/**
 * 获取网盘分布
 */
export const getNetdiskDistribution = async (hours: number = 24): Promise<NetdiskDistributionResponse> => {
  const response = await apiClient.get<NetdiskDistributionResponse>(`/statistics/netdisk-distribution?hours=${hours}`)
  return response.data
}

