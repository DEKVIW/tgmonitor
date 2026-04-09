import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
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
  getResourceOpsTrend,
  getResourceOpsWorkbenchDetail,
  listResourceOpsWorkbenchItems,
  syncResourceOpsCatalog,
  updateResourceOpsWorkbenchItem,
} from '@/api/resourceOps'
import ResourceOpsPlatformChart from '@/components/resource-ops/ResourceOpsPlatformChart'
import ResourceOpsTrendChart from '@/components/resource-ops/ResourceOpsTrendChart'
import ResourceOpsWorkbenchDrawerRuntime from '@/components/resource-ops/ResourceOpsWorkbenchDrawerRuntime'
import type {
  ResourceOpsCatalogStatusResponse,
  ResourceOpsOverviewResponse,
  ResourceOpsPlatformDistributionResponse,
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

const valueToneMap: Record<string, string> = {
  priority: 'gold',
  worth: 'blue',
  observe: 'default',
  not_worth: 'default',
}

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

const formatNumber = (value?: number | null) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))

const getWorkbenchTopicSubtitle = (record: ResourceOpsWorkbenchItem) => {
  const latestTitle = record.topic_latest_message_title || record.latest_message_title
  if (latestTitle) {
    return latestTitle
  }
  if (record.share_key) {
    return `${record.platform} · ${record.share_key}`
  }
  return record.platform
}

const ResourceOperationsAdmin = () => {
  const [activeTab, setActiveTab] = useState('overview')
  const [overview, setOverview] = useState<ResourceOpsOverviewResponse | null>(null)
  const [trend, setTrend] = useState<ResourceOpsTrendResponse | null>(null)
  const [platforms, setPlatforms] = useState<ResourceOpsPlatformDistributionResponse | null>(null)
  const [catalog, setCatalog] = useState<ResourceOpsCatalogStatusResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

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

  useEffect(() => {
    void loadOverview()
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
    workbenchFilters.health_status,
    workbenchFilters.keyword,
    workbenchFilters.sort_by,
    workbenchFilters.sort_order,
  ])

  const handleRefresh = async () => {
    await Promise.all([loadOverview(), workbenchInitialized ? loadWorkbench() : Promise.resolve()])
  }

  const handleSyncCatalog = async () => {
    setSyncing(true)
    try {
      const result = await syncResourceOpsCatalog(500)
      setCatalog(result)
      message.success(
        result.processed_messages
          ? `本次补录 ${result.processed_messages} 条历史消息，新增或修正 ${result.indexed_links || 0} 条资源索引`
          : '当前没有需要补录的历史消息'
      )
      await loadOverview()
      if (activeTab === 'workbench' || workbenchInitialized) {
        await loadWorkbench()
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '同步资源目录失败')
    } finally {
      setSyncing(false)
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

  const metricItems = useMemo(
    () =>
      overview
        ? [
            { label: '近 30 天点击', value: formatNumber(overview.clicks_last_30_days), hint: '站内真实点击热度' },
            { label: '近 30 天会话', value: formatNumber(overview.unique_sessions_last_30_days), hint: '去重后的访问会话' },
            { label: '已索引资源', value: formatNumber(overview.unique_link_targets), hint: '当前可跟踪的唯一资源链接' },
            { label: '高优先候选', value: formatNumber(overview.high_priority_candidates), hint: '值得优先评估或转存的候选项' },
          ]
        : [],
    [overview]
  )

  const summaryCards = useMemo(() => {
    const summary = workbenchData?.summary
    if (!summary) {
      return []
    }
    return [
      { label: '高优先', value: summary.priority_count, hint: '系统建议优先推进' },
      { label: '待转存', value: summary.ready_to_mirror_count, hint: '已进入执行池' },
      { label: '观察中', value: summary.observing_count, hint: '持续跟踪热度和更新' },
      { label: '持续更新', value: summary.rolling_count, hint: '后续维护成本更高' },
      { label: '风险提醒', value: summary.risky_count, hint: '最近有波动或失效迹象' },
    ]
  }, [workbenchData])

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

  const workbenchColumns: TableProps<ResourceOpsWorkbenchItem>['columns'] = [
    {
      title: '资源主题',
      dataIndex: 'topic_title',
      key: 'topic_title',
      width: 320,
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
            {record.topic_platform_count > 1 ? `${record.topic_platform_count} 个平台` : record.platform}
            {' · '}
            {record.topic_link_target_count} 个链接
          </Text>
        </div>
      ),
    },
    {
      title: '运营状态',
      key: 'operation_status',
      width: 112,
      render: (_, record) => <Tag color={operationToneMap[record.operation_status] || 'default'}>{record.operation_status_label}</Tag>,
    },
    {
      title: '价值',
      key: 'effective_value_status',
      width: 134,
      render: (_, record) => (
        <div className="resource-ops-status-cell">
          <Tag color={valueToneMap[record.effective_value_status] || 'default'}>{record.effective_value_status_label}</Tag>
          <small>{record.value_status_source === 'manual' ? '人工确认' : '系统建议'}</small>
        </div>
      ),
    },
    {
      title: '资源类型',
      key: 'effective_resource_kind',
      width: 164,
      render: (_, record) => (
        <div className="resource-ops-status-cell">
          <Tag>{record.effective_resource_kind_label}</Tag>
          <small>{record.resource_kind_source === 'manual' ? '人工覆盖' : record.update_mode_label}</small>
        </div>
      ),
    },
    {
      title: '主题热度',
      dataIndex: 'topic_clicks_30d',
      key: 'topic_clicks_30d',
      width: 156,
      sorter: true,
      render: (_, record) => (
        <div className="resource-ops-score-cell">
          <strong>{record.topic_clicks_7d} / {record.topic_clicks_30d}</strong>
          <small>{record.heat_label} · 30 天会话 {record.unique_sessions_30d}</small>
        </div>
      ),
    },
    {
      title: '覆盖情况',
      dataIndex: 'topic_message_count',
      key: 'topic_message_count',
      width: 160,
      sorter: true,
      render: (_, record) => (
        <div className="resource-ops-score-cell">
          <strong>{record.topic_link_target_count} 链接 / {record.topic_message_count} 消息</strong>
          <small>近 30 天出现 {record.recent_ref_count_30d} 次</small>
        </div>
      ),
    },
    {
      title: '风险',
      key: 'health',
      width: 150,
      render: (_, record) => (
        <div className="resource-ops-status-cell">
          <Tag color={healthToneMap[record.latest_link_health] || 'default'}>{record.latest_link_health_label}</Tag>
          <small>近 30 天失效 {record.invalid_checks_30d} 次</small>
        </div>
      ),
    },
    {
      title: '最近活动',
      dataIndex: 'topic_last_activity_at',
      key: 'topic_last_activity_at',
      width: 172,
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
      fixed: 'right',
      width: 160,
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
              先看真实需求，再判断哪些资源值得转存和替换
            </Title>
            <p className="resource-ops-subtitle">
              一期把热度、点击和目录索引跑顺，二期开始把“不同链接但同一主题”的资源合并观察，
              让工作台更贴近真正有运营价值的资源主题。
            </p>
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>
              刷新
            </Button>
            <Button type="primary" icon={<SyncOutlined />} loading={syncing} onClick={() => void handleSyncCatalog()}>
              补录一批历史目录
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
                    {metricItems.map((item) => (
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
                        已建立 {formatNumber(catalog?.link_ref_count)} 条资源索引，新消息会实时入库索引，
                        最近补录时间 {formatServerDateTime(catalog?.last_sync_at)}
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
                      <Card className="resource-ops-panel-card" title="近 30 天热度趋势" variant="outlined" loading={summaryLoading}>
                        {trend && trend.days.length > 0 ? (
                          <ResourceOpsTrendChart data={trend.days} />
                        ) : (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无热度趋势数据" />
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

                  <div className="resource-ops-metric-grid resource-ops-metric-grid-compact">
                    {summaryCards.map((item) => (
                      <div key={item.label} className="resource-ops-metric-card">
                        <span className="resource-ops-metric-label">{item.label}</span>
                        <strong className="resource-ops-metric-value">{formatNumber(item.value)}</strong>
                        <small className="resource-ops-metric-hint">{item.hint}</small>
                      </div>
                    ))}
                  </div>

                  <Card className="resource-ops-panel-card" variant="outlined">
                    <div className="resource-ops-table-head">
                      <div>
                        <Title level={4} className="resource-ops-table-title">
                          候选资源工作台
                        </Title>
                        <p className="resource-ops-table-subtitle">
                          这里优先看“资源主题”，而不是单个网盘按钮。相似标题会聚合到同一主题下，方便判断是否值得继续投入。
                        </p>
                      </div>
                      <div className="resource-ops-table-toolbar">
                        <Input.Search
                          value={keywordInput}
                          onChange={(event) => setKeywordInput(event.target.value)}
                          onSearch={() =>
                            setWorkbenchFilters((current) => ({
                              ...current,
                              page: 1,
                              keyword: keywordInput.trim() || undefined,
                            }))
                          }
                          allowClear
                          placeholder="搜索主题、消息标题、分享键或备注"
                          style={{ width: 300 }}
                        />
                        <Select
                          value={workbenchFilters.platform || ''}
                          onChange={(value) => setWorkbenchFilters((current) => ({ ...current, page: 1, platform: value || undefined }))}
                          options={[{ value: '', label: '全部平台' }, ...platformOptions]}
                          style={{ width: 132 }}
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
                          style={{ width: 132 }}
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
                          style={{ width: 132 }}
                        />
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
                        showTotal: (total) => `共 ${formatNumber(total)} 条候选主题`,
                      }}
                      onChange={handleWorkbenchTableChange}
                      locale={{ emptyText: '当前筛选下还没有候选资源' }}
                    />
                  </Card>
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

export default ResourceOperationsAdmin
