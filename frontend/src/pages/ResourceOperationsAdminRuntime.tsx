import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Collapse, Empty, Input, InputNumber, Row, Select, Space, Table, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType, TableProps } from 'antd/es/table'
import { DatabaseOutlined, InfoCircleOutlined, LinkOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons'

import {
  getResourceOpsCatalogStatus,
  getResourceOpsOverview,
  getResourceOpsPlatformDistribution,
  getResourceOpsRuntimeSettings,
  getResourceOpsTrend,
  getResourceOpsWorkbenchDetail,
  listResourceOpsAiModels,
  listResourceOpsWorkbenchItems,
  runResourceOpsRetention,
  syncResourceOpsCatalog,
  syncResourceOpsRecognition,
  syncResourceOpsRecognitionFull,
  testResourceOpsAiConnection,
  updateResourceOpsRuntimeSettings,
  updateResourceOpsWorkbenchItem,
} from '@/api/resourceOps'
import ResourceOpsPlatformChart from '@/components/resource-ops/ResourceOpsPlatformChart'
import ResourceOpsRecognitionQueuePanel from '@/components/resource-ops/ResourceOpsRecognitionQueuePanel'
import ResourceOpsTrendChart from '@/components/resource-ops/ResourceOpsTrendChart'
import ResourceOpsWorkbenchDrawerTopic from '@/components/resource-ops/ResourceOpsWorkbenchDrawerTopic'
import type {
  ResourceOpsAiModelItem,
  ResourceOpsAiTestResponse,
  ResourceOpsCatalogStatusResponse,
  ResourceOpsOverviewResponse,
  ResourceOpsPlatformDistributionResponse,
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

const formatNumber = (value?: number | null) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))
const formatResourceOpsDateTime = (value?: string | null) =>
  formatServerDateTime(value, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai')
const RESOURCE_OPS_TAB_STORAGE_KEY = 'resource-ops-active-tab'
const RESOURCE_OPS_TAB_KEYS = new Set(['overview', 'workbench'])

const getInitialResourceOpsTab = () => {
  if (typeof window === 'undefined') {
    return 'overview'
  }
  const saved = window.sessionStorage.getItem(RESOURCE_OPS_TAB_STORAGE_KEY)
  return saved && RESOURCE_OPS_TAB_KEYS.has(saved) ? saved : 'overview'
}

const buildSettingsDraft = (response: ResourceOpsRuntimeSettingsResponse): ResourceOpsRuntimeSettingsUpdateRequest => ({
  auto_recognition_enabled: response.auto_recognition_enabled,
  ai_base_url: response.ai_base_url,
  ai_model: response.ai_model,
  retention_click_event_days: response.retention_click_event_days,
  retention_daily_stat_days: response.retention_daily_stat_days,
  retention_candidate_log_days: response.retention_candidate_log_days,
  cleanup_interval_hours: response.cleanup_interval_hours,
})

const workColor = (status: string) => (status === 'matched' ? 'success' : status === 'error' ? 'error' : 'default')
const healthColor = (status: string) => (status === 'invalid' ? 'error' : status === 'warning' ? 'processing' : 'success')
const operationColor = (status: string) =>
  status === 'ready_to_mirror' ? 'success' : status === 'observing' ? 'processing' : status === 'ignored' ? 'default' : 'gold'

const ResourceOperationsAdminRuntime = () => {
  const [activeTab, setActiveTab] = useState(getInitialResourceOpsTab)
  const [overview, setOverview] = useState<ResourceOpsOverviewResponse | null>(null)
  const [trend, setTrend] = useState<ResourceOpsTrendResponse | null>(null)
  const [platforms, setPlatforms] = useState<ResourceOpsPlatformDistributionResponse | null>(null)
  const [catalog, setCatalog] = useState<ResourceOpsCatalogStatusResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [catalogSyncing, setCatalogSyncing] = useState(false)

  const [runtimeSettings, setRuntimeSettings] = useState<ResourceOpsRuntimeSettingsResponse | null>(null)
  const [settingsDraft, setSettingsDraft] = useState<ResourceOpsRuntimeSettingsUpdateRequest | null>(null)
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [maintenanceSaving, setMaintenanceSaving] = useState(false)
  const [pendingRunLoading, setPendingRunLoading] = useState(false)
  const [allRunLoading, setAllRunLoading] = useState(false)
  const [retentionRunning, setRetentionRunning] = useState(false)
  const [aiModelsLoading, setAiModelsLoading] = useState(false)
  const [aiTesting, setAiTesting] = useState(false)
  const [aiApiKeyInput, setAiApiKeyInput] = useState('')
  const [aiTestInput, setAiTestInput] = useState('')
  const [aiModelOptions, setAiModelOptions] = useState<ResourceOpsAiModelItem[]>([])
  const [aiTestResult, setAiTestResult] = useState<ResourceOpsAiTestResponse | null>(null)

  const [workbenchLoading, setWorkbenchLoading] = useState(false)
  const [workbenchVisited, setWorkbenchVisited] = useState(false)
  const [workbenchData, setWorkbenchData] = useState<ResourceOpsWorkbenchListResponse | null>(null)
  const [workbenchFilters, setWorkbenchFilters] = useState<ResourceOpsWorkbenchQuery>({
    page: 1,
    page_size: 20,
    sort_by: 'topic_clicks_total',
    sort_order: 'desc',
  })
  const [keywordInput, setKeywordInput] = useState('')

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailSaving, setDetailSaving] = useState(false)
  const [detailData, setDetailData] = useState<ResourceOpsWorkbenchDetailResponse | null>(null)

  const patchDraft = <K extends keyof ResourceOpsRuntimeSettingsUpdateRequest>(key: K, value: ResourceOpsRuntimeSettingsUpdateRequest[K]) => {
    setSettingsDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const aiDraft = () => ({
    base_url: settingsDraft?.ai_base_url || runtimeSettings?.ai_base_url || '',
    api_key: aiApiKeyInput || undefined,
    use_saved_api_key: !aiApiKeyInput,
  })

  const loadSavedModels = async (response: ResourceOpsRuntimeSettingsResponse) => {
    if (!response.ai_base_url || !response.ai_api_key_configured) {
      setAiModelOptions([])
      return
    }
    try {
      const result = await listResourceOpsAiModels({ base_url: response.ai_base_url, use_saved_api_key: true })
      setAiModelOptions(result.models)
    } catch {
      setAiModelOptions([])
    }
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
      message.error(error.response?.data?.detail || '加载资源运营概览失败')
    } finally {
      setSummaryLoading(false)
    }
  }

  const loadSettings = async (options?: { refreshModels?: boolean; silent?: boolean }) => {
    if (!options?.silent) {
      setSettingsLoading(true)
    }
    try {
      const response = await getResourceOpsRuntimeSettings()
      setRuntimeSettings(response)
      setSettingsDraft(buildSettingsDraft(response))
      if (options?.refreshModels) {
        void loadSavedModels(response)
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载资源运营配置失败')
    } finally {
      if (!options?.silent) {
        setSettingsLoading(false)
      }
    }
  }

  const loadWorkbench = async (filters = workbenchFilters, options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setWorkbenchLoading(true)
    }
    try {
      setWorkbenchData(await listResourceOpsWorkbenchItems(filters))
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载候选资源工作台失败')
    } finally {
      if (!options?.silent) {
        setWorkbenchLoading(false)
      }
    }
  }

  useEffect(() => {
    void Promise.all([loadOverview(), loadSettings({ refreshModels: true })])
  }, [])

  useEffect(() => {
    if (activeTab !== 'workbench') return
    setWorkbenchVisited(true)
    void loadWorkbench(workbenchFilters)
  }, [activeTab, workbenchFilters.page, workbenchFilters.page_size, workbenchFilters.platform, workbenchFilters.operation_status, workbenchFilters.value_status, workbenchFilters.health_status, workbenchFilters.keyword, workbenchFilters.sort_by, workbenchFilters.sort_order])

  useEffect(() => {
    if (!RESOURCE_OPS_TAB_KEYS.has(activeTab)) {
      setActiveTab('overview')
      return
    }
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(RESOURCE_OPS_TAB_STORAGE_KEY, activeTab)
    }
  }, [activeTab])

  const bindingSummary = runtimeSettings?.binding_summary || null
  const recognitionStatus = runtimeSettings?.recognition_status || null

  useEffect(() => {
    const shouldPoll =
      Boolean(recognitionStatus?.is_running) ||
      Boolean((bindingSummary?.pending_count || 0) > 0) ||
      Boolean(!recognitionStatus?.worker_alive && (bindingSummary?.pending_count || 0) > 0)

    if (!shouldPoll) {
      return
    }
    const timer = window.setTimeout(() => {
      void loadSettings({ silent: true })
      if (workbenchVisited) {
        void loadWorkbench(workbenchFilters, { silent: true })
      }
    }, 2500)
    return () => window.clearTimeout(timer)
  }, [bindingSummary?.pending_count, recognitionStatus?.is_running, recognitionStatus?.worker_alive, workbenchVisited, workbenchFilters])

  const overviewMetricItems = useMemo(
    () => [
      { label: '近 30 天点击', value: overview ? formatNumber(overview.clicks_last_30_days) : '--', hint: '站内真实点击热度' },
      { label: '近 30 天会话', value: overview ? formatNumber(overview.unique_sessions_last_30_days) : '--', hint: '去重后的访问会话' },
      { label: '已索引资源', value: overview ? formatNumber(overview.unique_link_targets) : '--', hint: '当前可跟踪的唯一网盘资源' },
      { label: '高优先候选', value: overview ? formatNumber(overview.high_priority_candidates) : '--', hint: '更值得优先评估和转存的资源' },
    ],
    [overview]
  )

  const workbenchSummaryItems = useMemo(() => {
    const summary = workbenchData?.summary
    if (!summary) return []
    return [
      { label: '候选主题', value: summary.total_candidates, hint: '当前工作台内的主题数' },
      { label: '优先推进', value: summary.priority_count, hint: '价值和热度都更高' },
      { label: '待转存', value: summary.ready_to_mirror_count, hint: '已进入执行池' },
      { label: '观察中', value: summary.observing_count, hint: '先看热度和更新情况' },
    ]
  }, [workbenchData])

  const recognitionSummaryItems = useMemo(() => {
    if (!bindingSummary) return []
    return [
      { label: '主题数', value: workbenchData?.summary.total_candidates || 0, hint: '工作台当前展示的主题行数' },
      { label: '待处理', value: bindingSummary.pending_count, hint: '新点击和异常重试都会先进入这里' },
      { label: '已归并', value: bindingSummary.matched_count, hint: `${bindingSummary.match_rate}% 链接目标已归并` },
      { label: '异常', value: bindingSummary.error_count, hint: 'AI 调用失败或返回空结果' },
    ]
  }, [bindingSummary, workbenchData])

  const recognitionQueueSummaryItems = useMemo(() => {
    if (!bindingSummary) return []
    return [
      { label: '主题数', value: workbenchData?.summary.total_candidates || 0, hint: '工作台当前展示的主题行数' },
      {
        label: '待处理',
        value: bindingSummary.pending_count,
        hint: `排队 ${bindingSummary.queued_count} / 处理中 ${bindingSummary.processing_count} / 重试 ${bindingSummary.retry_wait_count}`,
      },
      { label: '已归并', value: bindingSummary.matched_count, hint: `${bindingSummary.match_rate}% 链接目标已归并` },
      { label: '异常', value: bindingSummary.failed_count, hint: `队列失败 ${bindingSummary.failed_count}，绑定异常 ${bindingSummary.binding_error_count}` },
    ]
  }, [bindingSummary, workbenchData])
  void recognitionSummaryItems

  const platformOptions = useMemo(() => {
    const values = new Set((workbenchData?.items || []).map((item) => item.platform).filter(Boolean))
    return Array.from(values).map((platform) => ({ label: platform, value: platform }))
  }, [workbenchData])

  const handleRefresh = async () => {
    await Promise.all([loadOverview(), loadSettings(), workbenchVisited ? loadWorkbench() : Promise.resolve()])
  }

  const handleSyncCatalog = async () => {
    setCatalogSyncing(true)
    try {
      const result = await syncResourceOpsCatalog(500)
      setCatalog(result)
      message.success(
        result.processed_messages
          ? `本次补录 ${result.processed_messages} 条历史消息，更新 ${result.indexed_links || 0} 条索引`
          : '当前没有需要补录的历史消息'
      )
      await Promise.all([loadOverview(), workbenchVisited ? loadWorkbench() : Promise.resolve()])
    } catch (error: any) {
      message.error(error.response?.data?.detail || '补录历史目录失败')
    } finally {
      setCatalogSyncing(false)
    }
  }

  const handleLoadAiModels = async () => {
    if (!settingsDraft?.ai_base_url && !runtimeSettings?.ai_base_url) {
      message.warning('请先填写 AI Base URL')
      return
    }
    setAiModelsLoading(true)
    try {
      const result = await listResourceOpsAiModels(aiDraft())
      setAiModelOptions(result.models)
      if (!settingsDraft?.ai_model && result.models[0]?.id) patchDraft('ai_model', result.models[0].id)
      message.success(`已加载 ${result.count} 个模型`)
    } catch (error: any) {
      setAiModelOptions([])
      message.error(error.response?.data?.detail || '加载 AI 模型失败')
    } finally {
      setAiModelsLoading(false)
    }
  }

  const handleTestAiConnection = async () => {
    setAiTesting(true)
    try {
      const result = await testResourceOpsAiConnection({
        ...aiDraft(),
        model: settingsDraft?.ai_model || '',
        sample_text: aiTestInput.trim() || undefined,
      })
      setAiTestResult(result)
      message.success('AI 识别测试通过')
    } catch (error: any) {
      setAiTestResult(null)
      message.error(error.response?.data?.detail || 'AI 识别测试失败')
    } finally {
      setAiTesting(false)
    }
  }

  const handleSaveSettings = async () => {
    if (!settingsDraft) return
    setSettingsSaving(true)
    try {
      const payload: ResourceOpsRuntimeSettingsUpdateRequest = { ...settingsDraft }
      if (aiApiKeyInput) payload.ai_api_key = aiApiKeyInput
      const response = await updateResourceOpsRuntimeSettings(payload)
      setRuntimeSettings(response)
      setSettingsDraft(buildSettingsDraft(response))
      setAiApiKeyInput('')
      setAiTestResult(null)
      void loadSavedModels(response)
      message.success('配置已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存配置失败')
    } finally {
      setSettingsSaving(false)
    }
  }

  const handleSaveMaintenanceSettings = async () => {
    if (!settingsDraft) return
    setMaintenanceSaving(true)
    try {
      const response = await updateResourceOpsRuntimeSettings({
        auto_recognition_enabled: settingsDraft.auto_recognition_enabled,
        ai_base_url: settingsDraft.ai_base_url,
        ai_model: settingsDraft.ai_model,
        retention_click_event_days: settingsDraft.retention_click_event_days,
        retention_daily_stat_days: settingsDraft.retention_daily_stat_days,
        retention_candidate_log_days: settingsDraft.retention_candidate_log_days,
        cleanup_interval_hours: settingsDraft.cleanup_interval_hours,
      })
      setRuntimeSettings(response)
      setSettingsDraft(buildSettingsDraft(response))
      message.success('维护配置已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存维护配置失败')
    } finally {
      setMaintenanceSaving(false)
    }
  }

  const handleRunRecognition = async (mode: 'pending' | 'all') => {
    if (mode === 'pending') {
      setPendingRunLoading(true)
    } else {
      setAllRunLoading(true)
    }
    try {
      const runner = mode === 'all' ? syncResourceOpsRecognitionFull : syncResourceOpsRecognition
      const result = await runner()
      setRuntimeSettings((current) =>
        current
          ? {
              ...current,
              recognition_status: result.recognition_status,
              binding_summary: result.binding_summary,
            }
          : current
      )
      message.success(mode === 'all' ? '全部扫描已加入队列' : '待处理任务已加入队列')
      await Promise.all([
        loadSettings({ silent: true }),
        workbenchVisited ? loadWorkbench(workbenchFilters, { silent: true }) : Promise.resolve(),
      ])
    } catch (error: any) {
      message.error(error.response?.data?.detail || '执行作品归并失败')
    } finally {
      if (mode === 'pending') {
        setPendingRunLoading(false)
      } else {
        setAllRunLoading(false)
      }
    }
  }

  const handleRunRetention = async () => {
    setRetentionRunning(true)
    try {
      const result = await runResourceOpsRetention()
      message.success(
        `本次清理点击 ${result.deleted_click_events} 条、日统计 ${result.deleted_daily_stats} 条、候选日志 ${result.deleted_candidate_logs} 条`
      )
      await loadSettings({ silent: true })
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
      setDetailData(await getResourceOpsWorkbenchDetail(item.link_target_id))
    } catch (error: any) {
      setDetailData(null)
      message.error(error.response?.data?.detail || '加载候选资源详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const saveDetail = async (payload: ResourceOpsWorkbenchUpdateRequest) => {
    if (!detailData) return
    setDetailSaving(true)
    try {
      const response = await updateResourceOpsWorkbenchItem(detailData.item.link_target_id, payload)
      setDetailData(response)
      message.success('策略已保存')
      if (workbenchVisited) await loadWorkbench()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存策略失败')
    } finally {
      setDetailSaving(false)
    }
  }

  const workbenchColumns = useMemo<ColumnsType<ResourceOpsWorkbenchItem>>(
    () => [
      {
        title: '资源',
        key: 'topic_title',
        width: 260,
        sorter: true,
        render: (_, record) => (
          <div className="resource-ops-resource-cell">
            <span className="resource-ops-resource-title resource-ops-ellipsis" title={record.topic_title}>
              {record.topic_title}
            </span>
          </div>
        ),
      },
      {
        title: (
          <span className="resource-ops-column-title">
            热度
            <Tooltip title="主数字为累计点击；副行依次是 7 天 / 30 天点击和最近活动时间。">
              <InfoCircleOutlined />
            </Tooltip>
          </span>
        ),
        key: 'topic_clicks_total',
        sorter: true,
        width: 190,
        render: (_, record) => (
          <div className="resource-ops-score-cell">
            <strong>{formatNumber(record.topic_clicks_total)}</strong>
            <small>
              {formatNumber(record.topic_clicks_7d)} / {formatNumber(record.topic_clicks_30d)}
            </small>
            <small>{formatResourceOpsDateTime(record.topic_last_activity_at)}</small>
          </div>
        ),
      },
      {
        title: (
          <span className="resource-ops-column-title">
            归并
            <Tooltip title="只看当前主题已归并多少条原始消息；不再在表格里堆原始标题。">
              <InfoCircleOutlined />
            </Tooltip>
          </span>
        ),
        key: 'work_match_status',
        width: 180,
        render: (_, record) => (
          <div className="resource-ops-status-cell">
            <Tag color={workColor(record.work_match_status)}>{record.work_match_status_label}</Tag>
            <small>
              {record.work_match_status === 'matched'
                ? `已归并 ${formatNumber(record.topic_message_count)} 条消息`
                : record.work_match_status === 'error'
                  ? `异常待重试 ${formatNumber(record.topic_message_count)} 条消息`
                  : `待处理 ${formatNumber(record.topic_message_count)} 条消息`}
            </small>
            <small>{formatResourceOpsDateTime(record.work_matched_at || record.work_last_attempted_at)}</small>
          </div>
        ),
      },
      {
        title: '运营',
        key: 'overall_score',
        sorter: true,
        width: 220,
        render: (_, record) => (
          <div className="resource-ops-status-cell">
            <Space wrap size={[6, 6]}>
              <Tag color={operationColor(record.operation_status)}>{record.operation_status_label}</Tag>
              <Tag color={record.value_status_source === 'manual' ? 'gold' : 'default'}>{record.effective_value_status_label}</Tag>
              <Tag color={record.resource_kind_source === 'manual' ? 'cyan' : 'default'}>{record.effective_resource_kind_label}</Tag>
            </Space>
            <small>综合分 {record.overall_score.toFixed(1)}</small>
            <small title={record.suggested_action}>{record.suggested_action}</small>
          </div>
        ),
      },
      {
        title: '健康',
        key: 'latest_link_health',
        width: 180,
        render: (_, record) => (
          <div className="resource-ops-status-cell">
            <Tag color={healthColor(record.latest_link_health)}>{record.latest_link_health_label}</Tag>
            <small>失效 {record.invalid_checks_30d} / 检测 {record.total_checks_30d}</small>
            <small title={record.latest_link_health_reason || ''}>{record.latest_link_health_reason || '暂无检测说明'}</small>
          </div>
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 88,
        fixed: 'right',
        render: (_, record) => (
          <Button type="link" onClick={() => void openDetail(record)}>
            查看
          </Button>
        ),
      },
    ],
    []
  )

  const handleWorkbenchTableChange: TableProps<ResourceOpsWorkbenchItem>['onChange'] = (pagination, _filters, sorter) => {
    const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter
    const sortBy =
      activeSorter && activeSorter.order
        ? String(activeSorter.columnKey || workbenchFilters.sort_by || 'topic_clicks_total')
        : workbenchFilters.sort_by
    const sortOrder =
      activeSorter && activeSorter.order ? (activeSorter.order === 'ascend' ? 'asc' : 'desc') : workbenchFilters.sort_order
    setWorkbenchFilters((current) => ({
      ...current,
      page: pagination.current || 1,
      page_size: pagination.pageSize || current.page_size,
      sort_by: sortBy,
      sort_order: sortOrder,
    }))
  }

  const handleKeywordSearch = () => {
    setWorkbenchFilters((current) => ({ ...current, page: 1, keyword: keywordInput.trim() || undefined }))
  }

  const handlePatchDraft = (key: keyof ResourceOpsRuntimeSettingsUpdateRequest, value: string | number | boolean) => {
    patchDraft(key as any, value as any)
  }

  const catalogProgress = !catalog?.total_messages_with_links
    ? 0
    : Math.min(100, Math.round((catalog.indexed_messages / catalog.total_messages_with_links) * 100))

  const maintenanceSection = settingsDraft && runtimeSettings ? (
    <Collapse
      ghost
      defaultActiveKey={[]}
      className="resource-ops-runtime-collapse resource-ops-maintenance-collapse"
      items={[
        {
          key: 'maintenance',
          label: (
            <div className="resource-ops-runtime-collapse-head">
              <div className="resource-ops-runtime-collapse-copy">
                <div className="resource-ops-runtime-title">
                  <DatabaseOutlined />
                  <span>维护工具</span>
                </div>
                <small>补录历史目录和清理资源运营附加数据，属于低频辅助操作，放在工作台下方更顺手。</small>
              </div>
              <div className="resource-ops-runtime-collapse-tags">
                <Tag>上次清理 {formatResourceOpsDateTime(runtimeSettings.last_cleanup_at)}</Tag>
                <Tag>上次归并 {formatResourceOpsDateTime(runtimeSettings.last_sync_at)}</Tag>
              </div>
            </div>
          ),
          children: (
            <div className="resource-ops-runtime-card">
              <div className="resource-ops-runtime-meta-grid">
                <div className="resource-ops-runtime-meta-card">
                  <span>上次清理</span>
                  <strong>{formatResourceOpsDateTime(runtimeSettings.last_cleanup_at)}</strong>
                  <small>
                    点击 {formatNumber(runtimeSettings.last_cleanup_summary?.deleted_click_events)} / 日统计{' '}
                    {formatNumber(runtimeSettings.last_cleanup_summary?.deleted_daily_stats)}
                  </small>
                </div>
                <div className="resource-ops-runtime-meta-card">
                  <span>上次归并</span>
                  <strong>{formatResourceOpsDateTime(runtimeSettings.last_sync_at)}</strong>
                  <small>
                    成功 {formatNumber(runtimeSettings.last_sync_summary?.matched_count)} / 异常{' '}
                    {formatNumber(runtimeSettings.last_sync_summary?.error_count)}
                  </small>
                </div>
              </div>

              <div className="resource-ops-runtime-form-grid resource-ops-maintenance-form-grid">
                <div className="resource-ops-form-field resource-ops-form-field-compact">
                  <label>点击事件保留天数</label>
                  <InputNumber
                    min={7}
                    max={3650}
                    value={settingsDraft.retention_click_event_days}
                    onChange={(value) => patchDraft('retention_click_event_days', Number(value || 7))}
                  />
                </div>
                <div className="resource-ops-form-field resource-ops-form-field-compact">
                  <label>日统计保留天数</label>
                  <InputNumber
                    min={30}
                    max={3650}
                    value={settingsDraft.retention_daily_stat_days}
                    onChange={(value) => patchDraft('retention_daily_stat_days', Number(value || 30))}
                  />
                </div>
                <div className="resource-ops-form-field resource-ops-form-field-compact">
                  <label>候选日志保留天数</label>
                  <InputNumber
                    min={7}
                    max={3650}
                    value={settingsDraft.retention_candidate_log_days}
                    onChange={(value) => patchDraft('retention_candidate_log_days', Number(value || 7))}
                  />
                </div>
                <div className="resource-ops-form-field resource-ops-form-field-compact">
                  <label>清理间隔（小时）</label>
                  <InputNumber
                    min={1}
                    max={720}
                    value={settingsDraft.cleanup_interval_hours}
                    onChange={(value) => patchDraft('cleanup_interval_hours', Number(value || 1))}
                  />
                </div>
              </div>

              <Alert
                type="info"
                showIcon
                message="清理范围"
                description="这里只清理资源运营附加数据，不删除消息正文和索引；过期点击事件、日统计、候选日志，以及没有绑定关系的作品别名和作品缓存都会回收。"
              />

              <div className="resource-ops-runtime-savebar">
                <Text type="secondary">保存维护配置后立刻生效，立即清理只会处理资源运营附加数据。</Text>
                <div className="resource-ops-inline-actions resource-ops-inline-actions-tight">
                  <Button loading={retentionRunning} onClick={() => void handleRunRetention()}>
                    立即清理
                  </Button>
                  <Button type="primary" loading={maintenanceSaving} onClick={() => void handleSaveMaintenanceSettings()}>
                    保存维护配置
                  </Button>
                </div>
              </div>
            </div>
          ),
        },
      ]}
    />
  ) : (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无维护配置" />
  )

  return (
    <div className="resource-ops-page">
      <Card className="resource-ops-hero-card">
        <div className="resource-ops-hero-head">
          <div>
            <div className="resource-ops-eyebrow">
              <LinkOutlined />
              <span>资源运营</span>
            </div>
            <Title level={3} className="resource-ops-title">热度、归并、运营策略统一工作台</Title>
            <p className="resource-ops-subtitle">候选资源工作台看热度和价值，AI 只负责把原始标题提取成影视主题并做同名归并。</p>
          </div>
          <Button icon={<ReloadOutlined />} onClick={() => void handleRefresh()}>刷新</Button>
        </div>
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'overview',
            label: '概览',
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

                <Card className="resource-ops-panel-card" loading={summaryLoading}>
                  <div className="resource-ops-catalog-card">
                    <div className="resource-ops-catalog-copy">
                      <span className="resource-ops-catalog-title">历史目录补录进度</span>
                      <strong>{formatNumber(catalog?.indexed_messages)} / {formatNumber(catalog?.total_messages_with_links)}</strong>
                      <small>只补录历史消息对应的资源索引，不改消息正文。</small>
                    </div>
                    <div>
                      <div className="resource-ops-catalog-progress-wrap">
                        <div className="resource-ops-catalog-progress-bar">
                          <div className="resource-ops-catalog-progress-fill" style={{ width: `${catalogProgress}%` }} />
                        </div>
                        <span>{catalogProgress}%</span>
                      </div>
                      <div className="resource-ops-inline-actions">
                        <Button loading={catalogSyncing} icon={<SyncOutlined />} onClick={() => void handleSyncCatalog()}>补录目录</Button>
                      </div>
                    </div>
                  </div>
                </Card>

                <Row gutter={[16, 16]} className="resource-ops-chart-grid">
                  <Col xs={24} xl={14}>
                    <Card className="resource-ops-panel-card" title="近 30 天热度走势" loading={summaryLoading}>
                      {trend ? <ResourceOpsTrendChart data={trend.days} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无趋势数据" />}
                    </Card>
                  </Col>
                  <Col xs={24} xl={10}>
                    <Card className="resource-ops-panel-card" title="平台分布" loading={summaryLoading}>
                      {platforms && platforms.items.length > 0 ? (
                        <ResourceOpsPlatformChart items={platforms.items} />
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无平台数据" />
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
                <ResourceOpsRecognitionQueuePanel
                  loading={settingsLoading}
                  settingsSaving={settingsSaving}
                  pendingRunLoading={pendingRunLoading}
                  allRunLoading={allRunLoading}
                  aiModelsLoading={aiModelsLoading}
                  aiTesting={aiTesting}
                  settingsDraft={settingsDraft}
                  runtimeSettings={runtimeSettings}
                  bindingSummary={bindingSummary}
                  recognitionStatus={recognitionStatus}
                  recognitionSummaryItems={recognitionQueueSummaryItems}
                  aiApiKeyInput={aiApiKeyInput}
                  aiTestInput={aiTestInput}
                  aiModelOptions={aiModelOptions}
                  aiTestResult={aiTestResult}
                  formatNumber={formatNumber}
                  formatDateTime={formatResourceOpsDateTime}
                  onPatchDraft={handlePatchDraft}
                  onAiApiKeyInputChange={setAiApiKeyInput}
                  onAiTestInputChange={setAiTestInput}
                  onLoadAiModels={() => void handleLoadAiModels()}
                  onTestAiConnection={() => void handleTestAiConnection()}
                  onRunRecognition={(mode) => void handleRunRecognition(mode)}
                  onSaveSettings={() => void handleSaveSettings()}
                />

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

                <Card className="resource-ops-panel-card">
                  <div className="resource-ops-table-head">
                    <div>
                      <Title level={4} className="resource-ops-table-title">候选资源工作台</Title>
                      <p className="resource-ops-table-subtitle">表格按 AI 归并后的主题聚合，详情里再看原始消息标题和实际网盘链接。</p>
                    </div>
                    <div className="resource-ops-table-toolbar resource-ops-table-toolbar-compact">
                      <Input.Search className="resource-ops-toolbar-search" placeholder="搜索主题、原始消息标题、分享码" value={keywordInput} allowClear onChange={(event) => setKeywordInput(event.target.value)} onSearch={handleKeywordSearch} />
                      <Select allowClear className="resource-ops-toolbar-select" placeholder="平台" value={workbenchFilters.platform} options={platformOptions} onChange={(value) => setWorkbenchFilters((current) => ({ ...current, page: 1, platform: value }))} />
                      <Select allowClear className="resource-ops-toolbar-select" placeholder="运营" value={workbenchFilters.operation_status} options={[{ label: '待评估', value: 'pending_review' }, { label: '观察中', value: 'observing' }, { label: '待转存', value: 'ready_to_mirror' }, { label: '已忽略', value: 'ignored' }]} onChange={(value) => setWorkbenchFilters((current) => ({ ...current, page: 1, operation_status: value }))} />
                      <Select allowClear className="resource-ops-toolbar-select" placeholder="价值" value={workbenchFilters.value_status} options={[{ label: '继续观察', value: 'observe' }, { label: '值得做', value: 'worth' }, { label: '优先处理', value: 'priority' }, { label: '不值得做', value: 'not_worth' }]} onChange={(value) => setWorkbenchFilters((current) => ({ ...current, page: 1, value_status: value }))} />
                      <Select allowClear className="resource-ops-toolbar-select" placeholder="健康" value={workbenchFilters.health_status} options={[{ label: '正常', value: 'healthy' }, { label: '波动', value: 'warning' }, { label: '失效', value: 'invalid' }]} onChange={(value) => setWorkbenchFilters((current) => ({ ...current, page: 1, health_status: value }))} />
                    </div>
                  </div>

                  <Table rowKey="link_target_id" loading={workbenchLoading} dataSource={workbenchData?.items || []} columns={workbenchColumns} onChange={handleWorkbenchTableChange} pagination={{ current: workbenchFilters.page, pageSize: workbenchFilters.page_size, total: workbenchData?.total || 0, showSizeChanger: true }} scroll={{ x: 1180 }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无候选主题" /> }} />
                </Card>

                {maintenanceSection}
              </div>
            ),
          },
          {
            key: 'settings',
            label: '维护',
            children: (
              <div className="resource-ops-tab-stack">
                <Card className="resource-ops-panel-card" loading={settingsLoading}>
                  {settingsDraft && runtimeSettings ? (
                    <div className="resource-ops-runtime-card">
                      <div className="resource-ops-runtime-card-head">
                        <div>
                          <div className="resource-ops-runtime-title">
                            <DatabaseOutlined />
                            <span>数据保留</span>
                          </div>
                          <p className="resource-ops-runtime-hint">这里只清理资源运营附加数据，不删消息正文和索引。</p>
                        </div>
                      </div>
                      <div className="resource-ops-runtime-meta-grid">
                        <div className="resource-ops-runtime-meta-card">
                          <span>上次清理</span>
                          <strong>{formatResourceOpsDateTime(runtimeSettings.last_cleanup_at)}</strong>
                          <small>点击 {formatNumber(runtimeSettings.last_cleanup_summary?.deleted_click_events)} / 日统计 {formatNumber(runtimeSettings.last_cleanup_summary?.deleted_daily_stats)}</small>
                        </div>
                        <div className="resource-ops-runtime-meta-card">
                          <span>最近归并</span>
                          <strong>{formatResourceOpsDateTime(runtimeSettings.last_sync_at)}</strong>
                          <small>成功 {formatNumber(runtimeSettings.last_sync_summary?.matched_count)} / 异常 {formatNumber(runtimeSettings.last_sync_summary?.error_count)}</small>
                        </div>
                      </div>
                      <div className="resource-ops-runtime-form-grid">
                        <div className="resource-ops-form-field resource-ops-form-field-compact"><label>点击事件保留天数</label><InputNumber min={7} max={3650} value={settingsDraft.retention_click_event_days} onChange={(value) => patchDraft('retention_click_event_days', Number(value || 7))} /></div>
                        <div className="resource-ops-form-field resource-ops-form-field-compact"><label>日统计保留天数</label><InputNumber min={30} max={3650} value={settingsDraft.retention_daily_stat_days} onChange={(value) => patchDraft('retention_daily_stat_days', Number(value || 30))} /></div>
                        <div className="resource-ops-form-field resource-ops-form-field-compact"><label>候选日志保留天数</label><InputNumber min={7} max={3650} value={settingsDraft.retention_candidate_log_days} onChange={(value) => patchDraft('retention_candidate_log_days', Number(value || 7))} /></div>
                        <div className="resource-ops-form-field resource-ops-form-field-compact"><label>清理间隔（小时）</label><InputNumber min={1} max={720} value={settingsDraft.cleanup_interval_hours} onChange={(value) => patchDraft('cleanup_interval_hours', Number(value || 1))} /></div>
                      </div>
                      <Alert type="info" showIcon message="清理范围" description="过期点击事件、日统计、候选日志会按保留窗口回收；没有绑定关系的作品别名和作品缓存也会一起清掉。" />
                      <div className="resource-ops-card-actions">
                        <Button loading={retentionRunning} onClick={() => void handleRunRetention()}>立即清理</Button>
                      </div>
                    </div>
                  ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无维护配置" />}
                </Card>
                <div className="resource-ops-runtime-savebar">
                  <Text type="secondary">保存后立即应用当前维护配置。</Text>
                  <Button type="primary" loading={settingsSaving} onClick={() => void handleSaveSettings()}>保存配置</Button>
                </div>
              </div>
            ),
          },
        ].filter((item) => item.key !== 'settings')}
      />

      <ResourceOpsWorkbenchDrawerTopic open={detailOpen} loading={detailLoading} saving={detailSaving} data={detailData} onClose={() => { setDetailOpen(false); setDetailData(null) }} onSave={saveDetail} />
    </div>
  )
}

export default ResourceOperationsAdminRuntime
