/**
 * 统计信息页面
 */

import { useEffect, useState } from 'react'
import { Alert, Card, Col, Row, Spin, Tabs } from 'antd'
import ActivityHeatmap from '@/components/statistics/ActivityHeatmap'
import ChannelMatrixTable from '@/components/statistics/ChannelMatrixTable'
import DedupChart from '@/components/statistics/DedupChart'
import NetdiskChart from '@/components/statistics/NetdiskChart'
import StatisticsOverview from '@/components/statistics/StatisticsOverview'
import TrendChart from '@/components/statistics/TrendChart'
import {
  getActivityHeatmap,
  getAdminChannelMatrix,
  getDailyTrend,
  getDedupStats,
  getNetdiskDistribution,
  getStatisticsOverview,
} from '@/api/statistics'
import { useAuthStore } from '@/store/authStore'
import {
  ActivityHeatmapResponse,
  AdminChannelMatrixResponse,
  DailyTrendResponse,
  DedupStatsResponse,
  NetdiskDistributionResponse,
  StatisticsOverview as StatisticsOverviewType,
} from '@/types/statistics'
import './Statistics.css'

const STATISTICS_TAB_STORAGE_KEY = 'statistics-active-tab'
const STATISTICS_TAB_KEYS = new Set(['overview', 'channels'])

const getInitialStatisticsTab = (isAdmin: boolean) => {
  if (typeof window === 'undefined' || !isAdmin) {
    return 'overview'
  }

  const saved = window.sessionStorage.getItem(STATISTICS_TAB_STORAGE_KEY)
  return saved && STATISTICS_TAB_KEYS.has(saved) ? saved : 'overview'
}

const Statistics = () => {
  const { user, _hasHydrated } = useAuthStore()
  const isAdmin = user?.role === 'admin'

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<StatisticsOverviewType | null>(null)
  const [dailyTrend, setDailyTrend] = useState<DailyTrendResponse | null>(null)
  const [dedupStats, setDedupStats] = useState<DedupStatsResponse | null>(null)
  const [netdiskDist, setNetdiskDist] = useState<NetdiskDistributionResponse | null>(null)
  const [activityHeatmap, setActivityHeatmap] = useState<ActivityHeatmapResponse | null>(null)
  const [activeTab, setActiveTab] = useState(() => getInitialStatisticsTab(Boolean(isAdmin)))
  const [channelMatrixDays, setChannelMatrixDays] = useState(7)
  const [channelMatrixLoading, setChannelMatrixLoading] = useState(false)
  const [channelMatrixError, setChannelMatrixError] = useState<string | null>(null)
  const [channelMatrix, setChannelMatrix] = useState<AdminChannelMatrixResponse | null>(null)

  // 加载统计数据
  const loadStatistics = async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, trendData, dedupData, netdiskData, heatmapData] = await Promise.all([
        getStatisticsOverview(),
        getDailyTrend(10),
        getDedupStats(10),
        getNetdiskDistribution(24),
        getActivityHeatmap(7),
      ])

      setOverview(overviewData)
      setDailyTrend(trendData)
      setDedupStats(dedupData)
      setNetdiskDist(netdiskData)
      setActivityHeatmap(heatmapData)
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载统计信息失败')
    } finally {
      setLoading(false)
    }
  }

  const loadChannelMatrix = async (days = channelMatrixDays) => {
    if (!isAdmin) {
      return
    }

    setChannelMatrixLoading(true)
    setChannelMatrixError(null)
    try {
      setChannelMatrix(await getAdminChannelMatrix(days))
    } catch (err: any) {
      setChannelMatrixError(err.response?.data?.detail || '加载频道统计失败')
    } finally {
      setChannelMatrixLoading(false)
    }
  }

  // 初始加载
  useEffect(() => {
    void loadStatistics()
  }, [])

  useEffect(() => {
    if (!_hasHydrated) {
      return
    }

    if (!isAdmin) {
      setActiveTab('overview')
      return
    }

    if (typeof window !== 'undefined') {
      const nextTab = activeTab && STATISTICS_TAB_KEYS.has(activeTab) ? activeTab : 'overview'
      window.sessionStorage.setItem(STATISTICS_TAB_STORAGE_KEY, nextTab)
    }
  }, [activeTab, isAdmin, _hasHydrated])

  useEffect(() => {
    if (!isAdmin || activeTab !== 'channels') {
      return
    }
    void loadChannelMatrix(channelMatrixDays)
  }, [activeTab, channelMatrixDays, isAdmin])

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

  const overviewContent = (
    <>
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
          <Col xs={24} lg={12}>
            <Card className="chart-card" variant="outlined">
              {netdiskDist && <NetdiskChart data={netdiskDist} />}
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card className="chart-card" variant="outlined">
              {activityHeatmap && <ActivityHeatmap data={activityHeatmap} />}
            </Card>
          </Col>
        </Row>
      </div>
    </>
  )

  return (
    <div className="statistics-page">
      {!isAdmin ? (
        overviewContent
      ) : (
        <Tabs
          className="statistics-admin-tabs"
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'overview',
              label: '总览',
              children: overviewContent,
            },
            {
              key: 'channels',
              label: '频道统计',
              children: (
                <div className="statistics-admin-pane">
                  {channelMatrixError ? (
                    <Alert
                      className="statistics-admin-alert"
                      message="频道统计加载失败"
                      description={channelMatrixError}
                      type="error"
                      showIcon
                    />
                  ) : null}

                  <Card className="chart-card statistics-admin-card" variant="outlined">
                    <ChannelMatrixTable
                      data={channelMatrix}
                      loading={channelMatrixLoading}
                      days={channelMatrixDays}
                      onDaysChange={setChannelMatrixDays}
                      onReload={() => void loadChannelMatrix(channelMatrixDays)}
                    />
                  </Card>
                </div>
              ),
            },
          ]}
        />
      )}
    </div>
  )
}

export default Statistics

