/**
 * 统计信息页面
 */

import { useState, useEffect } from 'react'
import { Card, Spin, Alert, Row, Col } from 'antd'
import {
  getStatisticsOverview,
  getDailyTrend,
  getDedupStats,
  getNetdiskDistribution,
} from '@/api/statistics'
import StatisticsOverview from '@/components/statistics/StatisticsOverview'
import TrendChart from '@/components/statistics/TrendChart'
import DedupChart from '@/components/statistics/DedupChart'
import NetdiskChart from '@/components/statistics/NetdiskChart'
import {
  StatisticsOverview as StatisticsOverviewType,
  DailyTrendResponse,
  DedupStatsResponse,
  NetdiskDistributionResponse,
} from '@/types/statistics'
import './Statistics.css'

const Statistics = () => {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<StatisticsOverviewType | null>(null)
  const [dailyTrend, setDailyTrend] = useState<DailyTrendResponse | null>(null)
  const [dedupStats, setDedupStats] = useState<DedupStatsResponse | null>(null)
  const [netdiskDist, setNetdiskDist] = useState<NetdiskDistributionResponse | null>(null)

  // 加载统计数据
  const loadStatistics = async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, trendData, dedupData, netdiskData] = await Promise.all([
        getStatisticsOverview(),
        getDailyTrend(10),
        getDedupStats(10),
        getNetdiskDistribution(24),
      ])

      setOverview(overviewData)
      setDailyTrend(trendData)
      setDedupStats(dedupData)
      setNetdiskDist(netdiskData)
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载统计信息失败')
    } finally {
      setLoading(false)
    }
  }

  // 初始加载
  useEffect(() => {
    loadStatistics()
  }, [])

  if (loading && !overview) {
    return (
      <div className="statistics-loading">
        <Spin size="large" tip="正在加载统计信息...">
          <div style={{ width: 1, height: 160 }} />
        </Spin>
      </div>
    )
  }

  if (error) {
    return <Alert message="错误" description={error} type="error" showIcon />
  }

  return (
    <div className="statistics-page">
      {/* 总体统计 */}
      {overview && <StatisticsOverview data={overview} />}

      {/* 图表区域 */}
      <div className="statistics-charts">
        <Row gutter={[16, 16]}>
          {/* 每日趋势 */}
          <Col xs={24} lg={12}>
            <Card className="chart-card" variant="outlined">
              {dailyTrend && <TrendChart data={dailyTrend} />}
            </Card>
          </Col>

          {/* 去重统计 */}
          <Col xs={24} lg={12}>
            <Card className="chart-card" variant="outlined">
              {dedupStats && <DedupChart data={dedupStats} />}
            </Card>
          </Col>

          {/* 网盘分布 */}
          <Col xs={24}>
            <Card className="chart-card" variant="outlined">
              {netdiskDist && <NetdiskChart data={netdiskDist} />}
            </Card>
          </Col>
        </Row>
      </div>
    </div>
  )
}

export default Statistics

