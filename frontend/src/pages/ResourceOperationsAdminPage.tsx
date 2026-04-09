import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
  BranchesOutlined,
  DatabaseOutlined,
  EyeOutlined,
  LinkOutlined,
  ReloadOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'

import {
  getResourceOpsCatalogStatus,
  getResourceOpsOverview,
  getResourceOpsPlatformDistribution,
  getResourceOpsRuntimeSettings,
  getResourceOpsTrend,
  getResourceOpsWorkbenchDetail,
  listResourceOpsWorkbenchItems,
  runResourceOpsRetention,
  syncResourceOpsRecognition,
  syncResourceOpsCatalog,
  updateResourceOpsRuntimeSettings,
  updateResourceOpsWorkbenchItem,
} from '@/api/resourceOps'
import ResourceOpsPlatformChart from '@/components/resource-ops/ResourceOpsPlatformChart'
import ResourceOpsTrendChart from '@/components/resource-ops/ResourceOpsTrendChart'
import ResourceOpsWorkbenchDrawerRuntime from '@/components/resource-ops/ResourceOpsWorkbenchDrawerRuntime'
import type {
  ResourceOpsCatalogStatusResponse,
  ResourceOpsOverviewResponse,
  ResourceOpsPlatformDistributionResponse,
  ResourceOpsRecognitionRunResponse,
  ResourceOpsRetentionRunResponse,
  ResourceOpsRuntimeSettingsResponse,
  ResourceOpsRuntimeSettingsUpdateRequest,
  ResourceOpsTrendResponse,
  ResourceOpsWorkbenchDetailResponse,
  ResourceOpsWorkbenchItem,
  ResourceOpsWorkbenchListResponse,
  ResourceOpsWorkbenchQuery,
  ResourceOpsWorkbenchUpdateRequest,
} from '@/types/resourceOps'
import { formatServerDateTime } from '@/utils/dateTime'

import './ResourceOperations.css'

const { Title, Text } = Typography

const operationToneMap: Record<string, string> = {
  pending_review: 'default',
  observing: 'processing',
  ready_to_mirror: 'success',
  ignored: 'default',
}

const healthToneMap: Record<string, string> = {
  healthy: 'success',
  warning: 'processing',
  invalid: 'error',
  unknown: 'default',
}

const workToneMap: Record<string, string> = {
  matched: 'success',
  pending: 'default',
  no_match: 'default',
  low_confidence: 'processing',
  error: 'error',
}

const formatNumber = (value?: number | null) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))

const getWorkbenchTopicSubtitle = (record: ResourceOpsWorkbenchItem) =>
  record.topic_latest_message_title || record.latest_message_title || record.display_text || record.platform

const getRecognitionPreview = (record: ResourceOpsWorkbenchItem) => {
  if (record.work_title) {
    return `归并：${record.work_title}`
  }
  if (record.work_match_reason) {
    return record.work_match_reason
  }
  return '等待识别'
}

const getRecognitionSourceState = (runtimeSettings: ResourceOpsRuntimeSettingsResponse | null) => {
  if (!runtimeSettings) {
    return []
  }

  return [
    {
      key: 'tmdb',
      label: 'TMDB',
      value: runtimeSettings.tmdb_provider_ready
        ? '已就绪'
        : runtimeSettings.tmdb_enabled
          ? '待凭证'
          : '未启用',
      color: runtimeSettings.tmdb_provider_ready ? 'success' : runtimeSettings.tmdb_enabled ? 'processing' : 'default',
    },
    {
      key: 'bangumi',
      label: 'Bangumi',
      value: runtimeSettings.bangumi_provider_ready
        ? '已就绪'
        : runtimeSettings.bangumi_enabled
          ? '待确认'
          : '未启用',
      color: runtimeSettings.bangumi_provider_ready
        ? 'success'
        : runtimeSettings.bangumi_enabled
          ? 'processing'
          : 'default',
    },
  ]
}

const ResourceOperationsAdminPage = () => {
  const [activeTab, setActiveTab] = useState('overview')
  const [overview, setOverview] = useState<ResourceOpsOverviewResponse | null>(null)
  const [trend, setTrend] = useState<ResourceOpsTrendResponse | null>(null)
  const [platforms, setPlatforms] = useState<ResourceOpsPlatformDistributionResponse | null>(null)
  const [catalog, setCatalog] = useState<ResourceOpsCatalogStatusResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [recognitionRunning, setRecognitionRunning] = useState(false)
  const [retentionRunning, setRetentionRunning] = useState(false)
  const [runtimeSettings, setRuntimeSettings] = useState<ResourceOpsRuntimeSettingsResponse | null>(null)
  const [settingsDraft, setSettingsDraft] = useState<ResourceOpsRuntimeSettingsUpdateRequest | null>(null)
  const [tmdbApiKeyInput, setTmdbApiKeyInput] = useState('')
  const [tmdbTokenInput, setTmdbTokenInput] = useState('')

  const [workbenchInitialized, setWorkbenchInitialized] = useState(false)
  const [workbenchLoading, setWorkbenchLoading] = useState(false)
  const [workbenchData, setWorkbenchData] = useState<ResourceOpsWorkbenchListResponse | null>(null)
  const [workbenchFilters, setWorkbenchFilters] = useState<ResourceOpsWorkbenchQuery>({
    page: 1,
    page_size: 20,
    sort_by: 'topic_clicks_30d',
    sort_order: 'desc',
  })
  const [keywordInput, setKeywordInput] = useState('')

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailSaving, setDetailSaving] = useState(false)
  const [detailData, setDetailData] = useState<ResourceOpsWorkbenchDetailResponse | null>(null)

  const patchSettingsDraft = <K extends keyof ResourceOpsRuntimeSettingsUpdateRequest>(
    key: K,
    value: ResourceOpsRuntimeSettingsUpdateRequest[K]
  ) => {
    setSettingsDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const loadOverview = async () => {
    setSummaryLoading(true)
    try {
      const [overviewData, trendData, platformData, catalogData] = await Promise.all([
        getResourceOpsOverview(),
        getResourceOpsTrend(30),
        getResourceOpsPlatformDistribution(30),
        getResourceOpsCatalogStatus(),
      ])
      setOverview(overviewData)
      setTrend(trendData)
      setPlatforms(platformData)
      setCatalog(catalogData)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载资源运营总览失败')
    } finally {
      setSummaryLoading(false)
    }
  }

  const loadWorkbench = async (nextFilters = workbenchFilters) => {
    setWorkbenchLoading(true)
    try {
      const response = await listResourceOpsWorkbenchItems(nextFilters)
      setWorkbenchData(response)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载候选资源工作台失败')
    } finally {
      setWorkbenchLoading(false)
    }
  }

  const loadRuntimeSettings = async () => {
    setSettingsLoading(true)
    try {
      const response = await getResourceOpsRuntimeSettings()
      setRuntimeSettings(response)
      setSettingsDraft({
        auto_bind_enabled: response.auto_bind_enabled,
        sync_batch_size: response.sync_batch_size,
        sync_interval_minutes: response.sync_interval_minutes,
        min_confidence: response.min_confidence,
        retry_cooldown_hours: response.retry_cooldown_hours,
        tmdb_enabled: response.tmdb_enabled,
        tmdb_language: response.tmdb_language,
        bangumi_enabled: response.bangumi_enabled,
        bangumi_user_agent: response.bangumi_user_agent,
        retention_click_event_days: response.retention_click_event_days,
        retention_daily_stat_days: response.retention_daily_stat_days,
        retention_candidate_log_days: response.retention_candidate_log_days,
        cleanup_interval_hours: response.cleanup_interval_hours,
      })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载作品归并配置失败')
    } finally {
      setSettingsLoading(false)
    }
  }

  useEffect(() => {
    void Promise.all([loadOverview(), loadRuntimeSettings()])
  }, [])

  useEffect(() => {
    if (activeTab !== 'workbench') {
      return
    }
    setWorkbenchInitialized(true)
    void loadWorkbench(workbenchFilters)
  }, [
    activeTab,
    workbenchFilters.page,
    workbenchFilters.page_size,
    workbenchFilters.platform,
    workbenchFilters.operation_status,
    workbenchFilters.value_status,
    workbenchFilters.resource_kind,
    workbenchFilters.keyword,
    workbenchFilters.sort_by,
    workbenchFilters.sort_order,
  ])

  const handleRefresh = async () => {
    await Promise.all([
      loadOverview(),
      loadRuntimeSettings(),
      workbenchInitialized ? loadWorkbench() : Promise.resolve(),
    ])
  }

  const handleSyncCatalog = async () => {
    setSyncing(true)
    try {
      const result = await syncResourceOpsCatalog(500)
      setCatalog(result)
      if (result.processed_messages) {
        message.success(`本次补录 ${result.processed_messages} 条历史消息，新增或修正 ${result.indexed_links || 0} 条目录索引`)
      } else {
        message.success('当前没有需要补录的历史消息')
      }
      await loadOverview()
      if (activeTab === 'workbench' || workbenchInitialized) {
        await loadWorkbench()
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '补录历史目录失败')
    } finally {
      setSyncing(false)
    }
  }

  const handleSaveRuntimeSettings = async () => {
    if (!settingsDraft) {
      return
    }

    setSettingsSaving(true)
    try {
      const payload: ResourceOpsRuntimeSettingsUpdateRequest = { ...settingsDraft }
      if (tmdbApiKeyInput) {
        payload.tmdb_api_key = tmdbApiKeyInput
      }
      if (tmdbTokenInput) {
        payload.tmdb_read_access_token = tmdbTokenInput
      }

      const response = await updateResourceOpsRuntimeSettings(payload)
      setRuntimeSettings(response)
      setSettingsDraft({
        auto_bind_enabled: response.auto_bind_enabled,
        sync_batch_size: response.sync_batch_size,
        sync_interval_minutes: response.sync_interval_minutes,
        min_confidence: response.min_confidence,
        retry_cooldown_hours: response.retry_cooldown_hours,
        tmdb_enabled: response.tmdb_enabled,
        tmdb_language: response.tmdb_language,
        bangumi_enabled: response.bangumi_enabled,
        bangumi_user_agent: response.bangumi_user_agent,
        retention_click_event_days: response.retention_click_event_days,
        retention_daily_stat_days: response.retention_daily_stat_days,
        retention_candidate_log_days: response.retention_candidate_log_days,
        cleanup_interval_hours: response.cleanup_interval_hours,
      })
      setTmdbApiKeyInput('')
      setTmdbTokenInput('')
      message.success('运行配置已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存运行配置失败')
    } finally {
      setSettingsSaving(false)
    }
  }

  const handleRunRecognition = async (force = false) => {
    setRecognitionRunning(true)
    try {
      const result: ResourceOpsRecognitionRunResponse = await syncResourceOpsRecognition(
        settingsDraft?.sync_batch_size || 12,
        force
      )
      message.success(
        `本次识别处理 ${result.processed_count} 条，命中 ${result.matched_count} 条，低置信度 ${result.low_confidence_count} 条`
      )
      await Promise.all([loadRuntimeSettings(), activeTab === 'workbench' ? loadWorkbench() : Promise.resolve()])
    } catch (error: any) {
      message.error(error.response?.data?.detail || '执行作品归并失败')
    } finally {
      setRecognitionRunning(false)
    }
  }

  const handleRunRetention = async () => {
    setRetentionRunning(true)
    try {
      const result: ResourceOpsRetentionRunResponse = await runResourceOpsRetention()
      message.success(
        `本次清理点击事件 ${result.deleted_click_events} 条，日统计 ${result.deleted_daily_stats} 条，候选日志 ${result.deleted_candidate_logs} 条`
      )
      await loadRuntimeSettings()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '执行数据清理失败')
    } finally {
      setRetentionRunning(false)
    }
  }

  const openDetail = async (item: ResourceOpsWorkbenchItem) => {
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      const response = await getResourceOpsWorkbenchDetail(item.link_target_id)
      setDetailData(response)
    } catch (error: any) {
      setDetailData(null)
      message.error(error.response?.data?.detail || '加载候选资源详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const saveDetail = async (payload: ResourceOpsWorkbenchUpdateRequest) => {
    if (!detailData) {
      return
    }

    setDetailSaving(true)
    try {
      const response = await updateResourceOpsWorkbenchItem(detailData.item.link_target_id, payload)
      setDetailData(response)
      message.success('候选资源策略已保存')
      if (activeTab === 'workbench') {
        await loadWorkbench()
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存候选资源策略失败')
    } finally {
      setDetailSaving(false)
    }
  }

  const overviewMetricItems = useMemo(
    () => [
      {
        label: '近 30 天点击',
        value: overview ? formatNumber(overview.clicks_last_30_days) : '--',
        hint: '站内真实点击热度',
      },
      {
        label: '近 30 天会话',
        value: overview ? formatNumber(overview.unique_sessions_last_30_days) : '--',
        hint: '去重后的访问会话',
      },
      {
        label: '已索引资源',
        value: overview ? formatNumber(overview.unique_link_targets) : '--',
        hint: '当前可跟踪的唯一网盘资源',
      },
      {
        label: '高优先主题',
        value: overview ? formatNumber(overview.high_priority_candidates) : '--',
        hint: '更值得优先评估与转存的候选主题',
      },
    ],
    [overview]
  )

  const workbenchSummaryItems = useMemo(() => {
    const summary = workbenchData?.summary
    if (!summary) {
      return []
    }
    return [
      { label: '候选主题', value: summary.total_candidates, hint: '当前工作台收口后的主题数' },
      { label: '优先推进', value: summary.priority_count, hint: '热度和价值都更高' },
      { label: '待转存', value: summary.ready_to_mirror_count, hint: '已进入执行池' },
      { label: '观察中', value: summary.observing_count, hint: '先看热度和更新节奏' },
      { label: '持续更新', value: summary.rolling_count, hint: '后续维护成本更高' },
      { label: '风险提醒', value: summary.risky_count, hint: '近期有波动或失效迹象' },
    ]
  }, [workbenchData])

  const bindingSummaryItems = useMemo(() => {
    const summary = runtimeSettings?.binding_summary
    if (!summary) {
      return []
    }
    return [
      { label: '候选池', value: formatNumber(summary.total_tracked_targets), hint: '仅统计工作台候选池', tone: 'neutral' },
      { label: '已识别', value: formatNumber(summary.matched_count), hint: `覆盖率 ${summary.match_rate}%`, tone: 'success' },
      { label: '待处理', value: formatNumber(summary.pending_count), hint: '待自动或手动跑批', tone: 'accent' },
      { label: '低置信度', value: formatNumber(summary.low_confidence_count), hint: '结果还不够稳', tone: 'warning' },
      { label: '异常', value: formatNumber(summary.error_count), hint: '请求失败或解析异常', tone: 'danger' },
    ]
  }, [runtimeSettings])

  const recognitionSources = useMemo(() => getRecognitionSourceState(runtimeSettings), [runtimeSettings])
  const recognitionReady = Boolean(runtimeSettings?.tmdb_provider_ready || runtimeSettings?.bangumi_provider_ready)

  const catalogProgress = useMemo(() => {
    if (!catalog?.total_messages_with_links) {
      return 0
    }
    return Math.min(100, Math.round((catalog.indexed_messages / catalog.total_messages_with_links) * 100))
  }, [catalog])

  const platformOptions = useMemo(
    () => (platforms?.items || []).map((item) => ({ value: item.platform, label: item.platform })),
    [platforms]
  )

  const workbenchSubtitle = useMemo(() => {
    const total = workbenchData?.summary?.total_candidates || 0
    return `当前候选池共 ${formatNumber(total)} 个资源主题，优先看热度稳定、覆盖面大、风险较高的主题。`
  }, [workbenchData])

  const hasWorkbenchFilters = Boolean(
    workbenchFilters.platform ||
      workbenchFilters.operation_status ||
      workbenchFilters.value_status ||
      workbenchFilters.resource_kind ||
      workbenchFilters.keyword
  )

  const workbenchColumns: TableProps<ResourceOpsWorkbenchItem>['columns'] = [
    {
      title: '资源主题',
      dataIndex: 'topic_title',
      key: 'topic_title',
      width: 360,
      render: (_value, record) => (
        <div className="resource-ops-resource-cell">
          <span className="resource-ops-resource-title resource-ops-ellipsis" title={record.topic_title}>
            {record.topic_title}
          </span>
          <span
            className="resource-ops-resource-subtitle resource-ops-ellipsis"
            title={getWorkbenchTopicSubtitle(record)}
          >
            {getWorkbenchTopicSubtitle(record)}
          </span>
          <Text type="secondary" className="resource-ops-resource-meta">
            {(record.topic_platform_count > 1 ? `${record.topic_platform_count} 个平台` : record.platform) || '未知平台'}
            {' · '}
            {record.topic_link_target_count} 链接 / {record.topic_message_count} 消息
            {' · '}
            30 天会话 {record.unique_sessions_30d}
          </Text>
          <div className="resource-ops-resource-foot">
            <Tag color={workToneMap[record.work_match_status] || 'default'}>{record.work_match_status_label}</Tag>
            <span className="resource-ops-ellipsis" title={getRecognitionPreview(record)}>
              {getRecognitionPreview(record)}
            </span>
          </div>
        </div>
      ),
    },
    {
      title: '策略判断',
      key: 'operation_status',
      width: 168,
      render: (_, record) => (
        <div className="resource-ops-status-cell">
          <Tag color={operationToneMap[record.operation_status] || 'default'}>{record.operation_status_label}</Tag>
          <small>
            {record.effective_value_status_label}
            {' · '}
            {record.effective_resource_kind_label}
          </small>
        </div>
      ),
    },
    {
      title: '主题热度',
      dataIndex: 'topic_clicks_30d',
      key: 'topic_clicks_30d',
      width: 172,
      sorter: true,
      render: (_, record) => (
        <div className="resource-ops-score-cell">
          <strong>{record.topic_clicks_7d} / {record.topic_clicks_30d}</strong>
          <small>
            7 天 / 30 天点击
            {' · '}
            搜索点击 {record.search_clicks_30d}
          </small>
        </div>
      ),
    },
    {
      title: '覆盖情况',
      dataIndex: 'topic_message_count',
      key: 'topic_message_count',
      width: 166,
      sorter: true,
      render: (_, record) => (
        <div className="resource-ops-score-cell">
          <strong>{record.topic_link_target_count} / {record.topic_message_count}</strong>
          <small>
            链接数 / 消息数
            {' · '}
            近 30 天出现 {record.recent_ref_count_30d} 次
          </small>
        </div>
      ),
    },
    {
      title: '风险状态',
      key: 'health',
      width: 168,
      render: (_, record) => (
        <div className="resource-ops-status-cell">
          <Tag color={healthToneMap[record.latest_link_health] || 'default'}>{record.latest_link_health_label}</Tag>
          <small>
            近 30 天失效 {record.invalid_checks_30d} 次
            {' · '}
            {record.update_mode_label}
          </small>
        </div>
      ),
    },
    {
      title: '最近活动',
      dataIndex: 'topic_last_activity_at',
      key: 'topic_last_activity_at',
      width: 176,
      sorter: true,
      render: (_, record) => (
        <div className="resource-ops-score-cell">
          <strong>{formatServerDateTime(record.topic_last_activity_at)}</strong>
          <small>最近关联消息 {formatServerDateTime(record.topic_last_message_time)}</small>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 146,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" icon={<EyeOutlined />} onClick={() => void openDetail(record)}>
            详情
          </Button>
          <Button type="link" icon={<LinkOutlined />} href={record.target_url} target="_blank" rel="noopener noreferrer">
            打开
          </Button>
        </Space>
      ),
    },
  ]

  const handleWorkbenchTableChange: TableProps<ResourceOpsWorkbenchItem>['onChange'] = (pagination, _filters, sorter) => {
    const resolvedSorter = Array.isArray(sorter) ? sorter[0] : sorter
    setWorkbenchFilters((current) => ({
      ...current,
      page: pagination.current || 1,
      page_size: pagination.pageSize || current.page_size,
      sort_by: typeof resolvedSorter?.field === 'string' ? resolvedSorter.field : current.sort_by,
      sort_order:
        resolvedSorter?.order === 'ascend'
          ? 'asc'
          : resolvedSorter?.order === 'descend'
            ? 'desc'
            : current.sort_order,
    }))
  }

  const applyWorkbenchKeyword = () => {
    setWorkbenchFilters((current) => ({
      ...current,
      page: 1,
      keyword: keywordInput.trim() || undefined,
    }))
  }

  const resetWorkbenchFilters = () => {
    setKeywordInput('')
    setWorkbenchFilters((current) => ({
      ...current,
      page: 1,
      platform: undefined,
      operation_status: undefined,
      value_status: undefined,
      resource_kind: undefined,
      keyword: undefined,
    }))
  }

  return (
    <div className="resource-ops-page">
      <Card className="resource-ops-hero-card" variant="outlined">
        <div className="resource-ops-hero-head">
          <div>
            <div className="resource-ops-eyebrow">
              <ThunderboltOutlined />
              <span>资源运营</span>
            </div>
            <Title level={3} className="resource-ops-title">
              先看真实需求，再决定哪些资源值得转存与替换
            </Title>
            <p className="resource-ops-subtitle">
              工作台优先按资源主题聚合，不再盯着单个网盘按钮。热度、覆盖、风险和作品归并放在同一条链路里，方便做更稳的运营判断。
            </p>
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>
              刷新
            </Button>
            <Button type="primary" icon={<SyncOutlined />} loading={syncing} onClick={() => void handleSyncCatalog()}>
              补录历史目录
            </Button>
          </Space>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'overview',
              label: '总览',
              children: (
                <div className="resource-ops-tab-stack">
                  <div className="resource-ops-metric-grid">
                    {overviewMetricItems.map((item) => (
                      <div key={item.label} className="resource-ops-metric-card">
                        <span className="resource-ops-metric-label">{item.label}</span>
                        <strong className="resource-ops-metric-value">{item.value}</strong>
                        <small className="resource-ops-metric-hint">{item.hint}</small>
                      </div>
                    ))}
                  </div>

                  <div className="resource-ops-catalog-card">
                    <div className="resource-ops-catalog-copy">
                      <span className="resource-ops-catalog-title">历史目录补录进度</span>
                      <strong>
                        {formatNumber(catalog?.indexed_messages)} / {formatNumber(catalog?.total_messages_with_links)}
                      </strong>
                      <small>
                        已建立 {formatNumber(catalog?.link_ref_count)} 条目录索引，新消息会实时入库。最近补录时间{' '}
                        {formatServerDateTime(catalog?.last_sync_at)}
                      </small>
                    </div>
                    <div className="resource-ops-catalog-progress-wrap">
                      <div className="resource-ops-catalog-progress-bar">
                        <div className="resource-ops-catalog-progress-fill" style={{ width: `${catalogProgress}%` }} />
                      </div>
                      <span>{catalogProgress}%</span>
                    </div>
                  </div>

                  <Row gutter={[18, 18]}>
                    <Col xs={24} xl={14}>
                      <Card className="resource-ops-panel-card" title="近 30 天热度走势" variant="outlined" loading={summaryLoading}>
                        {trend && trend.days.length > 0 ? (
                          <ResourceOpsTrendChart data={trend.days} />
                        ) : (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无热度走势数据" />
                        )}
                      </Card>
                    </Col>
                    <Col xs={24} xl={10}>
                      <Card className="resource-ops-panel-card" title="平台分布" variant="outlined" loading={summaryLoading}>
                        {platforms && platforms.items.length > 0 ? (
                          <ResourceOpsPlatformChart items={platforms.items} />
                        ) : (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无平台分布数据" />
                        )}
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'workbench',
              label: '候选工作台',
              children: (
                <div className="resource-ops-tab-stack">
                  {catalog && !catalog.is_fully_synced ? (
                    <Alert
                      type="info"
                      showIcon
                      message="历史目录还没有全部补录完成"
                      description="工作台已经可以使用，但想看更完整的候选池，建议继续补录历史消息。"
                    />
                  ) : null}

                  {workbenchSummaryItems.length > 0 ? (
                    <div className="resource-ops-summary-strip">
                      {workbenchSummaryItems.map((item) => (
                        <div key={item.label} className="resource-ops-summary-chip">
                          <span>{item.label}</span>
                          <strong>{formatNumber(item.value)}</strong>
                          <small>{item.hint}</small>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  <Card className="resource-ops-panel-card" variant="outlined">
                    <div className="resource-ops-table-head">
                      <div>
                        <Title level={4} className="resource-ops-table-title">
                          候选资源工作台
                        </Title>
                        <p className="resource-ops-table-subtitle">{workbenchSubtitle}</p>
                      </div>
                      <div className="resource-ops-table-toolbar resource-ops-table-toolbar-compact">
                        <Input.Search
                          className="resource-ops-toolbar-search"
                          value={keywordInput}
                          allowClear
                          placeholder="搜索主题、消息标题、分享键或备注"
                          onChange={(event) => setKeywordInput(event.target.value)}
                          onSearch={applyWorkbenchKeyword}
                        />
                        <Select
                          value={workbenchFilters.platform || ''}
                          onChange={(value) => setWorkbenchFilters((current) => ({ ...current, page: 1, platform: value || undefined }))}
                          options={[{ value: '', label: '全部平台' }, ...platformOptions]}
                          className="resource-ops-toolbar-select"
                        />
                        <Select
                          value={workbenchFilters.operation_status || ''}
                          onChange={(value) =>
                            setWorkbenchFilters((current) => ({ ...current, page: 1, operation_status: value || undefined }))
                          }
                          options={[
                            { value: '', label: '全部状态' },
                            { value: 'pending_review', label: '待评估' },
                            { value: 'observing', label: '观察中' },
                            { value: 'ready_to_mirror', label: '待转存' },
                            { value: 'ignored', label: '已忽略' },
                          ]}
                          className="resource-ops-toolbar-select"
                        />
                        <Select
                          value={workbenchFilters.value_status || ''}
                          onChange={(value) =>
                            setWorkbenchFilters((current) => ({ ...current, page: 1, value_status: value || undefined }))
                          }
                          options={[
                            { value: '', label: '全部价值' },
                            { value: 'priority', label: '高优先' },
                            { value: 'worth', label: '值得做' },
                            { value: 'observe', label: '继续观察' },
                            { value: 'not_worth', label: '暂不处理' },
                          ]}
                          className="resource-ops-toolbar-select"
                        />
                        <Select
                          value={workbenchFilters.resource_kind || ''}
                          onChange={(value) =>
                            setWorkbenchFilters((current) => ({ ...current, page: 1, resource_kind: value || undefined }))
                          }
                          options={[
                            { value: '', label: '全部类型' },
                            { value: 'fixed', label: '固定资源' },
                            { value: 'rolling', label: '持续更新' },
                            { value: 'stopped', label: '已停更' },
                          ]}
                          className="resource-ops-toolbar-select"
                        />
                        <Button onClick={resetWorkbenchFilters} disabled={!hasWorkbenchFilters}>
                          重置
                        </Button>
                      </div>
                    </div>

                    <Table<ResourceOpsWorkbenchItem>
                      rowKey="link_target_id"
                      loading={workbenchLoading}
                      dataSource={workbenchData?.items || []}
                      columns={workbenchColumns}
                      tableLayout="auto"
                      scroll={{ x: 'max-content' }}
                      pagination={{
                        current: workbenchData?.page || workbenchFilters.page,
                        pageSize: workbenchData?.page_size || workbenchFilters.page_size,
                        total: workbenchData?.total || 0,
                        showSizeChanger: true,
                        showTotal: (total) => `共 ${formatNumber(total)} 个候选主题`,
                      }}
                      onChange={handleWorkbenchTableChange}
                      locale={{ emptyText: '当前筛选下还没有候选资源' }}
                    />
                  </Card>

                  <Collapse
                    className="resource-ops-runtime-collapse"
                    items={[
                      {
                        key: 'runtime',
                        label: (
                          <div className="resource-ops-runtime-collapse-head">
                            <div className="resource-ops-runtime-collapse-copy">
                              <span className="resource-ops-runtime-collapse-title">作品归并与数据保留</span>
                              <small>只作用于候选资源工作台，不扫描全量链接，不影响消息入库与前台展示。</small>
                            </div>
                            <div className="resource-ops-runtime-collapse-tags">
                              <Tag color={settingsDraft?.auto_bind_enabled ? 'success' : 'default'}>
                                {settingsDraft?.auto_bind_enabled ? '自动识别已开启' : '自动识别已关闭'}
                              </Tag>
                              <Tag color="blue">
                                已识别 {formatNumber(runtimeSettings?.binding_summary?.matched_count)} /{' '}
                                {formatNumber(runtimeSettings?.binding_summary?.total_tracked_targets)}
                              </Tag>
                              <Tag>上次同步 {formatServerDateTime(runtimeSettings?.last_sync_at)}</Tag>
                            </div>
                          </div>
                        ),
                        children: (
                          <div className="resource-ops-runtime-stack">
                            <div className="resource-ops-runtime-grid">
                              <Card className="resource-ops-panel-card" variant="outlined" loading={settingsLoading}>
                                {settingsDraft ? (
                                  <div className="resource-ops-runtime-card">
                                    <div className="resource-ops-runtime-card-head">
                                      <div>
                                        <div className="resource-ops-runtime-title">
                                          <BranchesOutlined />
                                          <span>作品归并</span>
                                        </div>
                                        <p className="resource-ops-runtime-hint">
                                          自动识别只处理工作台候选池，适合把相似标题逐步归并到同一作品主题下。
                                        </p>
                                      </div>
                                      <Space wrap size={[8, 8]}>
                                        {recognitionSources.map((item) => (
                                          <Tag key={item.key} color={item.color}>
                                            {item.label} {item.value}
                                          </Tag>
                                        ))}
                                      </Space>
                                    </div>

                                    <div className="resource-ops-status-strip">
                                      {bindingSummaryItems.map((item) => (
                                        <div
                                          key={item.label}
                                          className={`resource-ops-status-chip resource-ops-status-chip-${item.tone}`}
                                        >
                                          <span>{item.label}</span>
                                          <strong>{item.value}</strong>
                                          <small>{item.hint}</small>
                                        </div>
                                      ))}
                                    </div>

                                    {!recognitionReady ? (
                                      <Alert
                                        type="warning"
                                        showIcon
                                        message="还没有可用的识别来源"
                                        description="启用自动识别前，请先至少准备一个可用来源。TMDB 需要 API Key 或 Read Token，Bangumi 需要可用 User-Agent。"
                                      />
                                    ) : null}

                                    <div className="resource-ops-runtime-meta-grid">
                                      <div className="resource-ops-runtime-meta-card">
                                        <span>上次运行</span>
                                        <strong>{formatServerDateTime(runtimeSettings?.last_sync_at)}</strong>
                                        <small>
                                          处理 {formatNumber(runtimeSettings?.last_sync_summary?.processed_count)}
                                          {' · '}
                                          命中 {formatNumber(runtimeSettings?.last_sync_summary?.matched_count)}
                                        </small>
                                      </div>
                                      <div className="resource-ops-runtime-meta-card">
                                        <span>运行方式</span>
                                        <strong>{settingsDraft.auto_bind_enabled ? '自动批量识别' : '仅手动触发'}</strong>
                                        <small>
                                          每批 {formatNumber(settingsDraft.sync_batch_size)} 条
                                          {' · '}
                                          间隔 {formatNumber(settingsDraft.sync_interval_minutes)} 分钟
                                        </small>
                                      </div>
                                    </div>

                                    <div className="resource-ops-runtime-subsection">
                                      <div className="resource-ops-runtime-subtitle">调度与阈值</div>
                                      <div className="resource-ops-runtime-form-grid">
                                        <div className="resource-ops-inline-switch">
                                          <div className="resource-ops-inline-switch-copy">
                                            <span>自动识别</span>
                                            <small>按批次后台运行</small>
                                          </div>
                                          <Switch
                                            checked={settingsDraft.auto_bind_enabled}
                                            onChange={(checked) => patchSettingsDraft('auto_bind_enabled', checked)}
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>每批数量</label>
                                          <InputNumber
                                            min={1}
                                            max={100}
                                            value={settingsDraft.sync_batch_size}
                                            onChange={(value) => patchSettingsDraft('sync_batch_size', Number(value || 1))}
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>批次间隔</label>
                                          <InputNumber
                                            min={5}
                                            max={1440}
                                            value={settingsDraft.sync_interval_minutes}
                                            onChange={(value) =>
                                              patchSettingsDraft('sync_interval_minutes', Number(value || 5))
                                            }
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>最低置信度</label>
                                          <InputNumber
                                            min={0.4}
                                            max={0.99}
                                            step={0.01}
                                            value={settingsDraft.min_confidence}
                                            onChange={(value) => patchSettingsDraft('min_confidence', Number(value || 0.4))}
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>重试冷却</label>
                                          <InputNumber
                                            min={1}
                                            max={720}
                                            value={settingsDraft.retry_cooldown_hours}
                                            onChange={(value) =>
                                              patchSettingsDraft('retry_cooldown_hours', Number(value || 1))
                                            }
                                          />
                                        </div>
                                      </div>
                                    </div>

                                    <div className="resource-ops-runtime-subsection">
                                      <div className="resource-ops-runtime-subtitle">识别来源</div>
                                      <div className="resource-ops-runtime-form-grid">
                                        <div className="resource-ops-inline-switch">
                                          <div className="resource-ops-inline-switch-copy">
                                            <span>TMDB</span>
                                            <small>影视通用识别源</small>
                                          </div>
                                          <Switch
                                            checked={settingsDraft.tmdb_enabled}
                                            onChange={(checked) => patchSettingsDraft('tmdb_enabled', checked)}
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>TMDB 语言</label>
                                          <Input
                                            value={settingsDraft.tmdb_language}
                                            onChange={(event) => patchSettingsDraft('tmdb_language', event.target.value)}
                                            placeholder="zh-CN"
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-field-span-2">
                                          <label>TMDB API Key</label>
                                          <Input.Password
                                            value={tmdbApiKeyInput}
                                            onChange={(event) => setTmdbApiKeyInput(event.target.value)}
                                            placeholder={
                                              runtimeSettings?.tmdb_api_key_configured ? '已配置，留空则不修改' : '可选'
                                            }
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-field-span-2">
                                          <label>TMDB Read Token</label>
                                          <Input.Password
                                            value={tmdbTokenInput}
                                            onChange={(event) => setTmdbTokenInput(event.target.value)}
                                            placeholder={
                                              runtimeSettings?.tmdb_read_access_token_configured
                                                ? '已配置，留空则不修改'
                                                : '推荐填写'
                                            }
                                          />
                                        </div>

                                        <div className="resource-ops-inline-switch">
                                          <div className="resource-ops-inline-switch-copy">
                                            <span>Bangumi</span>
                                            <small>更适合动画番剧</small>
                                          </div>
                                          <Switch
                                            checked={settingsDraft.bangumi_enabled}
                                            onChange={(checked) => patchSettingsDraft('bangumi_enabled', checked)}
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-field-span-2">
                                          <label>Bangumi User-Agent</label>
                                          <Input
                                            value={settingsDraft.bangumi_user_agent}
                                            onChange={(event) => patchSettingsDraft('bangumi_user_agent', event.target.value)}
                                            placeholder="TGMonitor/1.0"
                                          />
                                        </div>
                                      </div>
                                    </div>

                                    <div className="resource-ops-card-actions">
                                      <Button loading={recognitionRunning} onClick={() => void handleRunRecognition(false)}>
                                        立即跑一批
                                      </Button>
                                      <Button loading={recognitionRunning} onClick={() => void handleRunRecognition(true)}>
                                        强制重跑
                                      </Button>
                                    </div>
                                  </div>
                                ) : (
                                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无归并配置数据" />
                                )}
                              </Card>
                              <Card className="resource-ops-panel-card" variant="outlined" loading={settingsLoading}>
                                {settingsDraft ? (
                                  <div className="resource-ops-runtime-card">
                                    <div className="resource-ops-runtime-card-head">
                                      <div>
                                        <div className="resource-ops-runtime-title">
                                          <DatabaseOutlined />
                                          <span>数据保留</span>
                                        </div>
                                        <p className="resource-ops-runtime-hint">
                                          这里只清理资源运营附加数据，不会影响消息正文和目录索引本身。
                                        </p>
                                      </div>
                                    </div>

                                    <div className="resource-ops-runtime-meta-grid resource-ops-runtime-meta-grid-side">
                                      <div className="resource-ops-runtime-meta-card">
                                        <span>上次清理</span>
                                        <strong>{formatServerDateTime(runtimeSettings?.last_cleanup_at)}</strong>
                                        <small>
                                          点击 {formatNumber(runtimeSettings?.last_cleanup_summary?.deleted_click_events)}
                                          {' · '}
                                          日统计 {formatNumber(runtimeSettings?.last_cleanup_summary?.deleted_daily_stats)}
                                        </small>
                                      </div>
                                    </div>

                                    <div className="resource-ops-runtime-subsection">
                                      <div className="resource-ops-runtime-subtitle">保留窗口</div>
                                      <div className="resource-ops-runtime-form-grid resource-ops-runtime-form-grid-side">
                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>点击事件</label>
                                          <InputNumber
                                            min={7}
                                            max={3650}
                                            value={settingsDraft.retention_click_event_days}
                                            onChange={(value) =>
                                              patchSettingsDraft('retention_click_event_days', Number(value || 7))
                                            }
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>日统计</label>
                                          <InputNumber
                                            min={30}
                                            max={3650}
                                            value={settingsDraft.retention_daily_stat_days}
                                            onChange={(value) =>
                                              patchSettingsDraft('retention_daily_stat_days', Number(value || 30))
                                            }
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>候选日志</label>
                                          <InputNumber
                                            min={7}
                                            max={3650}
                                            value={settingsDraft.retention_candidate_log_days}
                                            onChange={(value) =>
                                              patchSettingsDraft('retention_candidate_log_days', Number(value || 7))
                                            }
                                          />
                                        </div>

                                        <div className="resource-ops-form-field resource-ops-form-field-compact">
                                          <label>清理间隔</label>
                                          <InputNumber
                                            min={1}
                                            max={720}
                                            value={settingsDraft.cleanup_interval_hours}
                                            onChange={(value) =>
                                              patchSettingsDraft('cleanup_interval_hours', Number(value || 1))
                                            }
                                          />
                                        </div>
                                      </div>
                                    </div>

                                    <div className="resource-ops-runtime-side-note">
                                      <span>清理效果</span>
                                      <small>过期点击事件、日统计、候选日志会按保留窗口裁剪，无绑定作品的别名和作品缓存也会一并回收。</small>
                                    </div>

                                    <div className="resource-ops-card-actions">
                                      <Button loading={retentionRunning} onClick={() => void handleRunRetention()}>
                                        立即清理
                                      </Button>
                                    </div>
                                  </div>
                                ) : (
                                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无保留配置数据" />
                                )}
                              </Card>
                            </div>

                            <div className="resource-ops-runtime-savebar">
                              <Text type="secondary">保存会同时应用作品归并与数据保留参数。</Text>
                              <Button type="primary" loading={settingsSaving} onClick={() => void handleSaveRuntimeSettings()}>
                                保存运行配置
                              </Button>
                            </div>
                          </div>
                        ),
                      },
                    ]}
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <ResourceOpsWorkbenchDrawerRuntime
        open={detailOpen}
        loading={detailLoading}
        saving={detailSaving}
        data={detailData}
        onClose={() => {
          setDetailOpen(false)
          setDetailData(null)
        }}
        onSave={saveDetail}
      />
    </div>
  )
}

export default ResourceOperationsAdminPage
