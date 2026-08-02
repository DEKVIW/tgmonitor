import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ApiOutlined, DeleteOutlined, ExperimentOutlined, PlusOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons'

import AppLogTerminal from '@/components/common/AppLogTerminal'
import {
  clearAiCallEvents,
  createAiProvider,
  deleteAiProvider,
  getAiCenterOverview,
  listAiCallEvents,
  listAiProviders,
  listAiRoutes,
  refreshAiProviderModels,
  testAiProvider,
  testAiRoute,
  updateAiProvider,
  updateAiRoute,
} from '@/api/aiCenter'
import type {
  AiCenterCallEventItem,
  AiCenterOverviewResponse,
  AiCenterProviderItem,
  AiCenterProviderUpsertRequest,
  AiCenterRouteItem,
  AiCenterRouteTestRequest,
  AiCenterRouteUpsertRequest,
} from '@/types/aiCenter'
import { formatServerDateTime } from '@/utils/dateTime'
import './Admin.css'
import './AiCenterAdminRuntime.css'

const { Title, Paragraph, Text } = Typography

const formatDateTime = (value?: string | null, format = 'YYYY-MM-DD HH:mm') =>
  value ? formatServerDateTime(value, format, 'Asia/Shanghai') : '-'

const getErrorMessage = (error: any, fallback: string) => error?.response?.data?.detail || fallback

const PROVIDER_HEALTH_COLOR: Record<string, string> = {
  healthy: 'success',
  degraded: 'warning',
  unknown: 'default',
}

const PROVIDER_HEALTH_LABELS: Record<string, string> = {
  healthy: '健康',
  degraded: '波动',
  unknown: '未知',
}

const EVENT_STATUS_LABELS: Record<string, string> = {
  success: '成功',
  error: '失败',
  skipped: '跳过',
}

const API_MODE_LABELS: Record<string, string> = {
  auto: '自动识别',
  chat_completions: '对话补全',
  responses: '统一响应',
}

const OUTPUT_MODE_LABELS: Record<string, string> = {
  text: '文本',
  json: 'JSON',
}

const ROUTE_REASON_LABELS: Record<string, string> = {
  route_disabled: '路由已停用',
  route_missing: '路由不存在',
  no_enabled_step: '没有启用步骤',
  no_enabled_provider_step: '没有可用的提供方步骤',
}

const CAPABILITY_OPTIONS = [
  { label: '中文理解', value: 'chinese' },
  { label: '结构化输出', value: 'structured_output' },
  { label: '实体抽取', value: 'entity_extraction' },
  { label: '标题抽取', value: 'title_extraction' },
  { label: '推理判断', value: 'reasoning' },
  { label: '低延迟', value: 'low_latency' },
  { label: '低成本', value: 'low_cost' },
]

const SELECTION_MODE_OPTIONS = [
  { label: '自动优选', value: 'automatic' },
  { label: '严格按步骤', value: 'manual_steps' },
]

const OPTIMIZATION_GOAL_OPTIONS = [
  { label: '平衡', value: 'balanced' },
  { label: '质量优先', value: 'quality' },
  { label: '稳定优先', value: 'stability' },
  { label: '速度优先', value: 'speed' },
  { label: '成本优先', value: 'cost' },
]

const SELECTION_MODE_LABELS: Record<string, string> = Object.fromEntries(
  SELECTION_MODE_OPTIONS.map((item) => [item.value, item.label])
)

const OPTIMIZATION_GOAL_LABELS: Record<string, string> = Object.fromEntries(
  OPTIMIZATION_GOAL_OPTIONS.map((item) => [item.value, item.label])
)

const CAPABILITY_LABELS: Record<string, string> = Object.fromEntries(
  CAPABILITY_OPTIONS.map((item) => [item.value, item.label])
)

const ROUTE_TEST_PRESETS: Record<string, AiCenterRouteTestRequest> = {
  resource_ops_title_extract: {
    system_prompt:
      '你是影视剧名称提取助手。只返回核心作品名，不要返回季数、集数、年份、画质、字幕、演员、更新状态。',
    user_prompt: '月鳞绮纪(2026) 60FPS S01E01-E22 更23集 鞠婧祎 曾舜晞',
  },
  pan_transfer_follow_identity_extract: {
    system_prompt:
      '请从输入内容中抽取追更身份，输出 JSON：core_title, aliases, year, season, current_episode, confidence, reason。',
    user_prompt: '任务标题：月鳞绮纪(2026) 60FPS S01E01-E22；来源标题：月鳞绮纪‎ (2026) DV HQ 60帧 /集 更22集',
  },
  pan_transfer_follow_candidate_judge: {
    system_prompt:
      '请判断候选消息是否与当前任务属于同一作品且更新更晚，输出 JSON：same_work, is_newer, candidate_episode, current_episode, confidence, reason。',
    user_prompt:
      '当前任务：月鳞绮纪(2026) 60FPS S01E01-E22\n候选消息：月鳞绮纪‎ (2026) DV HQ 60帧 5.1 /集 更23集',
  },
}

const emptyProviderModelDraft = () => ({
  model_id: '',
  label: '',
  is_enabled: true,
  is_preferred: false,
  capabilities: [] as string[],
  route_allowlist: [] as string[],
  priority_bias: 0,
  quality_score: 50,
  speed_score: 50,
  cost_score: 50,
  stability_score: 50,
  notes: '',
  extra_json: {},
})

const emptyProviderDraft = (): AiCenterProviderUpsertRequest => ({
  provider_key: '',
  display_name: '',
  base_url: '',
  api_mode: 'auto',
  api_key: '',
  clear_api_key: false,
  is_enabled: true,
  is_default: false,
  priority: 100,
  timeout_seconds: 25,
  max_retries: 1,
  cooldown_seconds: 300,
  extra_json: {},
  models: [],
})

const getSelectionModeLabel = (value?: string | null) => SELECTION_MODE_LABELS[value || ''] || value || '-'

const getOptimizationGoalLabel = (value?: string | null) => OPTIMIZATION_GOAL_LABELS[value || ''] || value || '-'

const getCapabilityLabel = (value: string) => CAPABILITY_LABELS[value] || value

const getProviderHealthLabel = (value?: string | null) => PROVIDER_HEALTH_LABELS[value || ''] || value || '-'

const getEventStatusLabel = (value?: string | null) => EVENT_STATUS_LABELS[value || ''] || value || '-'

const getApiModeLabel = (value?: string | null) => API_MODE_LABELS[value || ''] || value || '-'

const getOutputModeLabel = (value?: string | null) => OUTPUT_MODE_LABELS[value || ''] || value || '-'

const getRouteReasonLabel = (value?: string | null) => ROUTE_REASON_LABELS[value || ''] || value || '请检查步骤与提供方状态'

const renderTextWithTooltip = (value?: string | null, className: string = 'ai-center-ellipsis') => {
  const text = value?.trim() ? value : '-'
  if (text === '-') {
    return <span className={className}>-</span>
  }
  return (
    <Tooltip title={text}>
      <span className={className}>{text}</span>
    </Tooltip>
  )
}

const getEventLogTone = (record: AiCenterCallEventItem) => {
  if (record.status === 'error') return 'error' as const
  if (record.status === 'success') return 'success' as const
  return 'warning' as const
}

const buildEventLogSummary = (record: AiCenterCallEventItem) => {
  const note =
    record.error_message ||
    (record.candidate_score != null ? `候选评分 ${record.candidate_score.toFixed(1)}` : record.selection_summary || '')
  const chain = [record.provider_label || '未绑定提供方', record.model_id || '自动模型', getApiModeLabel(record.used_api_mode)]
    .filter(Boolean)
    .join(' / ')
  const meta = [
    record.selection_mode ? getSelectionModeLabel(record.selection_mode) : '',
    record.attempt_index ? `第 ${record.attempt_index} 次` : '',
    record.duration_ms ? `${record.duration_ms} ms` : '',
  ].filter(Boolean)
  const details = [chain, meta.join(' · ')].filter(Boolean).join(' · ')
  return note ? `${details} -> ${note}` : details || '调用已记录'
}

const buildEventLogLine = (record: AiCenterCallEventItem) =>
  `[${formatDateTime(record.created_at, 'HH:mm:ss')}] [${record.route_key}] [${getEventStatusLabel(record.status)}] ${buildEventLogSummary(record)}`

const AiCenterAdminRuntime = () => {
  const [overview, setOverview] = useState<AiCenterOverviewResponse | null>(null)
  const [providers, setProviders] = useState<AiCenterProviderItem[]>([])
  const [routes, setRoutes] = useState<AiCenterRouteItem[]>([])
  const [events, setEvents] = useState<AiCenterCallEventItem[]>([])
  const [eventFilter, setEventFilter] = useState<'all' | 'error' | 'success'>('all')
  const [eventHiddenMarker, setEventHiddenMarker] = useState(0)
  const [loading, setLoading] = useState(true)
  const [eventClearing, setEventClearing] = useState(false)
  const [providerModalOpen, setProviderModalOpen] = useState(false)
  const [providerSaving, setProviderSaving] = useState(false)
  const [providerTestingId, setProviderTestingId] = useState<number | null>(null)
  const [providerRefreshingId, setProviderRefreshingId] = useState<number | null>(null)
  const [providerDeletingId, setProviderDeletingId] = useState<number | null>(null)
  const [editingProvider, setEditingProvider] = useState<AiCenterProviderItem | null>(null)
  const [routeModalOpen, setRouteModalOpen] = useState(false)
  const [routeSaving, setRouteSaving] = useState(false)
  const [editingRoute, setEditingRoute] = useState<AiCenterRouteItem | null>(null)
  const [routeTestModalOpen, setRouteTestModalOpen] = useState(false)
  const [routeTesting, setRouteTesting] = useState(false)
  const [testingRoute, setTestingRoute] = useState<AiCenterRouteItem | null>(null)
  const [providerForm] = Form.useForm<AiCenterProviderUpsertRequest>()
  const [routeForm] = Form.useForm<AiCenterRouteUpsertRequest>()
  const [routeTestForm] = Form.useForm<AiCenterRouteTestRequest>()

  const loadAll = async () => {
    setLoading(true)
    try {
      const [overviewData, providerData, routeData, eventData] = await Promise.all([
        getAiCenterOverview(),
        listAiProviders(),
        listAiRoutes(),
        listAiCallEvents(undefined, 50),
      ])
      setOverview(overviewData)
      setProviders(providerData.items)
      setRoutes(routeData.items)
      setEvents(eventData.items)
    } catch (error: any) {
      message.error(getErrorMessage(error, '加载 AI 中心失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAll()
  }, [])

  useEffect(() => {
    if (events.length <= 0) {
      setEventHiddenMarker(0)
    }
  }, [events.length])

  const providerOptions = useMemo(
    () =>
      providers.map((item) => ({
        label: `${item.display_name} (${item.provider_key})`,
        value: item.id,
      })),
    [providers]
  )

  const providerModelOptions = useMemo(
    () =>
      Object.fromEntries(
        providers.map((provider) => [
          provider.id,
          provider.models.map((model) => ({
            label: model.is_enabled ? model.label || model.model_id : `${model.label || model.model_id}（已停用）`,
            value: model.model_id,
          })),
        ])
      ),
    [providers]
  )

  const routeKeyOptions = useMemo(
    () =>
      routes.map((route) => ({
        label: `${route.display_name} (${route.route_key})`,
        value: route.route_key,
      })),
    [routes]
  )

  const summaryItems = useMemo(
    () => [
      {
        label: '提供方',
        value: `${overview?.enabled_providers || 0}/${overview?.total_providers || 0}`,
        hint: overview?.default_provider_label ? `默认：${overview.default_provider_label}` : '未设置默认提供方',
      },
      {
        label: '可用路由',
        value: `${overview?.ready_routes || 0}/${overview?.total_routes || 0}`,
        hint: routes.length ? `已配置 ${routes.length} 条业务路由` : '暂无路由配置',
      },
      {
        label: '24 小时成功',
        value: String(overview?.recent_success_count_24h || 0),
        hint: '最近成功调用次数',
      },
      {
        label: '24 小时失败',
        value: String(overview?.recent_failure_count_24h || 0),
        hint: '最近失败调用次数',
      },
    ],
    [overview, routes.length]
  )

  const openCreateProvider = () => {
    setEditingProvider(null)
    providerForm.resetFields()
    providerForm.setFieldsValue(emptyProviderDraft())
    setProviderModalOpen(true)
  }

  const openEditProvider = (record: AiCenterProviderItem) => {
    setEditingProvider(record)
    providerForm.setFieldsValue({
      provider_key: record.provider_key,
      display_name: record.display_name,
      base_url: record.base_url,
      api_mode: record.api_mode,
      api_key: '',
      clear_api_key: false,
      is_enabled: record.is_enabled,
      is_default: record.is_default,
      priority: record.priority,
      timeout_seconds: record.timeout_seconds,
      max_retries: record.max_retries,
      cooldown_seconds: record.cooldown_seconds,
      extra_json: record.extra_json,
      models: record.models.map((model) => ({
        id: model.id,
        model_id: model.model_id,
        label: model.label,
        owned_by: model.owned_by || undefined,
        is_enabled: model.is_enabled,
        is_preferred: model.is_preferred,
        capabilities: model.capabilities,
        route_allowlist: model.route_allowlist,
        priority_bias: model.priority_bias,
        quality_score: model.quality_score,
        speed_score: model.speed_score,
        cost_score: model.cost_score,
        stability_score: model.stability_score,
        notes: model.notes || '',
        extra_json: model.extra_json,
      })),
    })
    setProviderModalOpen(true)
  }

  const saveProvider = async () => {
    const values = await providerForm.validateFields()
    setProviderSaving(true)
    try {
      if (editingProvider) {
        await updateAiProvider(editingProvider.id, values)
        message.success('AI 提供方已更新')
      } else {
        await createAiProvider(values)
        message.success('AI 提供方已创建')
      }
      setProviderModalOpen(false)
      setEditingProvider(null)
      providerForm.resetFields()
      await loadAll()
    } catch (error: any) {
      message.error(getErrorMessage(error, '保存 AI 提供方失败'))
    } finally {
      setProviderSaving(false)
    }
  }

  const handleRefreshModels = async (record: AiCenterProviderItem) => {
    setProviderRefreshingId(record.id)
    try {
      await refreshAiProviderModels(record.id)
      message.success(`已刷新 ${record.display_name} 的模型列表`)
      await loadAll()
    } catch (error: any) {
      message.error(getErrorMessage(error, '刷新模型失败'))
    } finally {
      setProviderRefreshingId(null)
    }
  }

  const handleTestProvider = async (record: AiCenterProviderItem) => {
    setProviderTestingId(record.id)
    try {
      const result = await testAiProvider(record.id)
      Modal.info({
        title: `测试通过：${record.display_name}`,
        width: 640,
        content: (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Paragraph>{`模型：${result.model_id || '-'}`}</Paragraph>
            <Paragraph>{`接口模式：${getApiModeLabel(result.used_api_mode)}`}</Paragraph>
            <Paragraph copyable={{ text: result.text }}>{result.text || '(空返回)'}</Paragraph>
          </Space>
        ),
      })
      await loadAll()
    } catch (error: any) {
      message.error(getErrorMessage(error, '测试提供方失败'))
    } finally {
      setProviderTestingId(null)
    }
  }

  const handleDeleteProvider = async (record: AiCenterProviderItem) => {
    Modal.confirm({
      title: `删除提供方：${record.display_name}`,
      content: '删除后会自动移除引用该提供方的路由步骤，历史调用记录会保留但解除提供方关联。',
      okButtonProps: { danger: true },
      okText: '删除',
      cancelText: '取消',
      onOk: async () => {
        setProviderDeletingId(record.id)
        try {
          await deleteAiProvider(record.id)
          message.success('AI 提供方已删除')
          await loadAll()
        } catch (error: any) {
          message.error(getErrorMessage(error, '删除提供方失败'))
        } finally {
          setProviderDeletingId(null)
        }
      },
    })
  }

  const openRouteConfig = (record: AiCenterRouteItem) => {
    setEditingRoute(record)
    routeForm.setFieldsValue({
      display_name: record.display_name,
      description: record.description,
      output_mode: record.output_mode,
      is_enabled: record.is_enabled,
      max_attempts: record.max_attempts,
      selection_mode: record.selection_mode,
      optimization_goal: record.optimization_goal,
      preferred_capabilities: record.preferred_capabilities,
      allow_same_provider_model_failover: record.allow_same_provider_model_failover,
      allow_cross_provider_failover: record.allow_cross_provider_failover,
      extra_json: record.extra_json,
      steps: record.steps.map((step) => ({
        id: step.id,
        provider_id: step.provider_id,
        model_id: step.model_id || undefined,
        is_enabled: step.is_enabled,
        extra_json: step.extra_json,
      })),
    })
    setRouteModalOpen(true)
  }

  const saveRoute = async () => {
    if (!editingRoute) return
    const values = await routeForm.validateFields()
    setRouteSaving(true)
    try {
      await updateAiRoute(editingRoute.route_key, values)
      message.success(`路由 ${editingRoute.display_name} 已更新`)
      setRouteModalOpen(false)
      setEditingRoute(null)
      routeForm.resetFields()
      await loadAll()
    } catch (error: any) {
      message.error(getErrorMessage(error, '保存路由失败'))
    } finally {
      setRouteSaving(false)
    }
  }

  const openRouteTest = (record: AiCenterRouteItem) => {
    setTestingRoute(record)
    routeTestForm.setFieldsValue(ROUTE_TEST_PRESETS[record.route_key] || { system_prompt: '', user_prompt: '' })
    setRouteTestModalOpen(true)
  }

  const runRouteTest = async () => {
    if (!testingRoute) return
    const values = await routeTestForm.validateFields()
    setRouteTesting(true)
    try {
      const result = await testAiRoute(testingRoute.route_key, values)
      Modal.info({
        title: `路由测试通过：${testingRoute.display_name}`,
        width: 820,
        content: (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Paragraph>{`选中链路：${result.provider_label || '-'} / ${result.model_id || '-'}`}</Paragraph>
            <Paragraph>{`接口模式：${getApiModeLabel(result.used_api_mode)}`}</Paragraph>
            <Paragraph>{`耗时：${result.duration_ms || 0} ms`}</Paragraph>
            <Paragraph copyable={{ text: result.text }}>{result.text || '(空返回)'}</Paragraph>
            {result.attempt_trace.length ? (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Text strong>尝试链路</Text>
                {result.attempt_trace.map((item, index) => (
                  <Card key={`${item.provider_id || 'p'}-${item.model_id || 'm'}-${index}`} size="small">
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Text>{`#${item.attempt_index || index + 1} ${item.provider_label || '-'} / ${item.model_id || '自动'}`}</Text>
                      <Text type={item.status === 'error' ? 'danger' : 'secondary'}>
                        {`${getEventStatusLabel(item.status)} · ${item.duration_ms || 0} ms`}
                      </Text>
                      {Array.isArray(item.candidate_reasons) && item.candidate_reasons.length ? (
                        <Text type="secondary">{`打分依据：${item.candidate_reasons.join('，')}`}</Text>
                      ) : null}
                      {item.error_message ? <Text type="danger">{item.error_message}</Text> : null}
                    </Space>
                  </Card>
                ))}
              </Space>
            ) : null}
          </Space>
        ),
      })
      setRouteTestModalOpen(false)
      await loadAll()
    } catch (error: any) {
      message.error(getErrorMessage(error, '测试路由失败'))
    } finally {
      setRouteTesting(false)
    }
  }

  const handleClearEvents = async () => {
    setEventClearing(true)
    try {
      const result = await clearAiCallEvents()
      message.success(`已清空 ${result.deleted_count} 条调用记录`)
      await loadAll()
    } catch (error: any) {
      message.error(getErrorMessage(error, '清空调用记录失败'))
    } finally {
      setEventClearing(false)
    }
  }

  const providerColumns: ColumnsType<AiCenterProviderItem> = [
    {
      title: '提供方',
      key: 'provider',
      width: 240,
      render: (_, record) => (
        <div className="ai-center-cell-stack">
          <div className="ai-center-cell-primary-row">
            <Text strong>{record.display_name}</Text>
            {record.is_default ? <Tag color="processing">默认</Tag> : null}
            {!record.is_enabled ? <Tag>停用</Tag> : null}
          </div>
          {renderTextWithTooltip(record.provider_key, 'ai-center-ellipsis ai-center-cell-secondary')}
        </div>
      ),
    },
    {
      title: '连接信息',
      key: 'connection',
      width: 320,
      render: (_, record) => (
        <div className="ai-center-cell-stack">
          <span className="ai-center-cell-secondary">{`接口模式：${getApiModeLabel(record.api_mode)}`}</span>
          {renderTextWithTooltip(record.base_url, 'ai-center-ellipsis ai-center-cell-secondary')}
        </div>
      ),
    },
    {
      title: '模型池',
      key: 'models',
      width: 360,
      render: (_, record) => (
        <div className="ai-center-cell-stack">
          <span className="ai-center-cell-secondary">{`启用 ${record.enabled_model_count}/${record.model_count}`}</span>
          <span className="ai-center-cell-secondary">{record.preferred_model_id ? `首选：${record.preferred_model_id}` : '首选：未设置'}</span>
          <div className="ai-center-tag-row">
            {record.models.slice(0, 4).map((model) => (
              <Tag key={`${record.id}-${model.model_id}`} color={model.is_enabled ? 'blue' : 'default'}>
                {model.label || model.model_id}
              </Tag>
            ))}
            {record.models.length > 4 ? <Tag>{`+${record.models.length - 4}`}</Tag> : null}
          </div>
        </div>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 260,
      render: (_, record) => (
        <div className="ai-center-cell-stack">
          <div className="ai-center-tag-row">
            <Tag color={PROVIDER_HEALTH_COLOR[record.health_status] || 'default'}>
              {getProviderHealthLabel(record.health_status)}
            </Tag>
          </div>
          <span className="ai-center-cell-secondary">
            {record.cooldown_until ? `冷却至 ${formatDateTime(record.cooldown_until)}` : '当前可参与调度'}
          </span>
          <span className="ai-center-cell-secondary">
            {record.last_success_at ? `最近成功：${formatDateTime(record.last_success_at)}` : '暂无成功记录'}
          </span>
          {record.last_error_message ? (
            <Tooltip title={record.last_error_message}>
              <Text type="danger" className="ai-center-line-clamp-2">
                {record.last_error_message}
              </Text>
            </Tooltip>
          ) : null}
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_, record) => (
        <Space wrap>
          <Button size="small" icon={<SettingOutlined />} onClick={() => openEditProvider(record)}>
            配置
          </Button>
          <Button size="small" icon={<ReloadOutlined />} loading={providerRefreshingId === record.id} onClick={() => void handleRefreshModels(record)}>
            刷新模型
          </Button>
          <Button size="small" icon={<ExperimentOutlined />} loading={providerTestingId === record.id} onClick={() => void handleTestProvider(record)}>
            测试
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} loading={providerDeletingId === record.id} onClick={() => handleDeleteProvider(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const orderedEvents = useMemo(() => [...events].reverse(), [events])

  const filteredEvents = useMemo(
    () =>
      orderedEvents.filter((item) => {
        if (eventFilter === 'error') return item.status === 'error'
        if (eventFilter === 'success') return item.status === 'success'
        return true
      }),
    [eventFilter, orderedEvents]
  )

  const visibleEvents = useMemo(
    () => filteredEvents.filter((item) => item.id > eventHiddenMarker),
    [eventHiddenMarker, filteredEvents]
  )

  const visibleEventLines = useMemo(
    () =>
      visibleEvents.map((item) => ({
        key: item.id,
        text: buildEventLogLine(item),
        tone: getEventLogTone(item),
      })),
    [visibleEvents]
  )

  const routeSteps = Form.useWatch('steps', routeForm) || []

  return (
    <div className="ai-center-page">
      <Card className="ai-center-hero-card" variant="borderless">
        <div className="ai-center-hero-head">
          <div>
            <div className="ai-center-eyebrow">
              <ApiOutlined />
              <span>AI 中心</span>
            </div>
            <Title level={3} className="ai-center-title">
              AI 中心
            </Title>
            <p className="ai-center-subtitle">统一管理 AI 提供方、模型池、能力路由和调用记录。</p>
          </div>
          <Button icon={<ReloadOutlined />} onClick={() => void loadAll()}>
            刷新
          </Button>
        </div>

        <div className="ai-center-summary-grid">
          {summaryItems.map((item) => (
            <div key={item.label} className="ai-center-summary-card">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.hint}</small>
            </div>
          ))}
        </div>
      </Card>

      <Card className="ai-center-panel-card" variant="borderless">
        <div className="ai-center-section-head">
          <div className="ai-center-section-copy">
            <Title level={4} className="ai-center-section-title">
              提供方管理
            </Title>
            <p className="ai-center-section-subtitle">单页查看连接信息、模型池和运行状态，避免双列表格互相挤压。</p>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateProvider}>
            新增提供方
          </Button>
        </div>

        <Table
          rowKey="id"
          className="ai-center-table"
          size="small"
          tableLayout="fixed"
          loading={loading}
          columns={providerColumns}
          dataSource={providers}
          pagination={false}
          scroll={{ x: 1400 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无提供方" /> }}
        />
      </Card>

      <Card className="ai-center-panel-card" variant="borderless" loading={loading}>
        <div className="ai-center-section-head">
          <div className="ai-center-section-copy">
            <Title level={4} className="ai-center-section-title">
              能力路由
            </Title>
            <p className="ai-center-section-subtitle">每条业务路由单独展示策略、当前候选和执行步骤，阅读成本更低。</p>
          </div>
        </div>

        {routes.length ? (
          <div className="ai-center-route-grid">
            {routes.map((route) => {
              const enabledSteps = route.steps.filter((step) => step.is_enabled)
              const candidateLabel =
                route.ready_provider_label || route.ready_model_id
                  ? `${route.ready_provider_label || '未绑定提供方'} / ${route.ready_model_id || '自动'}`
                  : '当前无可用候选'
              return (
                <div key={route.route_key} className="ai-center-route-card">
                  <div className="ai-center-route-card-head">
                    <div className="ai-center-route-card-copy">
                      <div className="ai-center-route-card-title-row">
                        <Text strong>{route.display_name}</Text>
                        <Tag color={route.is_ready ? 'success' : 'warning'}>{route.is_ready ? '已就绪' : '未就绪'}</Tag>
                        {!route.is_enabled ? <Tag>停用</Tag> : null}
                      </div>
                      <div className="ai-center-route-key">{route.route_key}</div>
                      {route.description ? <p className="ai-center-route-desc">{route.description}</p> : null}
                    </div>
                    <Space wrap>
                      <Button size="small" icon={<SettingOutlined />} onClick={() => openRouteConfig(route)}>
                        配置
                      </Button>
                      <Button size="small" icon={<ExperimentOutlined />} onClick={() => openRouteTest(route)}>
                        测试
                      </Button>
                    </Space>
                  </div>

                  <div className="ai-center-route-meta-grid">
                    <div className="ai-center-route-meta-card">
                      <span>选模策略</span>
                      <strong>{getSelectionModeLabel(route.selection_mode)}</strong>
                      <small>{`优化目标：${getOptimizationGoalLabel(route.optimization_goal)} · 输出：${getOutputModeLabel(route.output_mode)}`}</small>
                    </div>
                    <div className="ai-center-route-meta-card">
                      <span>当前候选</span>
                      <strong>{candidateLabel}</strong>
                      <small>{route.is_ready ? `候选 ${route.candidate_count} 个` : getRouteReasonLabel(route.ready_reason)}</small>
                    </div>
                    <div className="ai-center-route-meta-card">
                      <span>执行范围</span>
                      <strong>{`启用步骤 ${route.enabled_step_count}/${route.configured_step_count}`}</strong>
                      <small>{`最大尝试 ${route.max_attempts} 次`}</small>
                    </div>
                  </div>

                  <div className="ai-center-tag-row ai-center-route-tag-row">
                    <Tag color="blue">{getSelectionModeLabel(route.selection_mode)}</Tag>
                    <Tag color="geekblue">{getOptimizationGoalLabel(route.optimization_goal)}</Tag>
                    {route.allow_same_provider_model_failover ? <Tag color="cyan">同提供方模型回退</Tag> : <Tag>固定单模型</Tag>}
                    {route.allow_cross_provider_failover ? <Tag color="purple">跨提供方回退</Tag> : <Tag>按步骤顺序</Tag>}
                    {route.preferred_capabilities.map((item) => (
                      <Tag key={`${route.route_key}-${item}`}>{getCapabilityLabel(item)}</Tag>
                    ))}
                  </div>

                  {route.selection_summary ? (
                    <Tooltip title={route.selection_summary}>
                      <div className="ai-center-route-summary">当前候选已按策略排序，悬停可查看详细摘要。</div>
                    </Tooltip>
                  ) : null}

                  <div className="ai-center-route-steps">
                    {enabledSteps.length ? (
                      enabledSteps.map((step) => (
                        <div key={step.id} className="ai-center-step-item">
                          <span>{`步骤 ${step.step_index}`}</span>
                          <strong>{step.provider_label || '未绑定提供方'}</strong>
                          <small>{step.model_label || step.model_id || '自动选择模型'}</small>
                        </div>
                      ))
                    ) : (
                      <div className="ai-center-empty-inline">暂无可用步骤</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="ai-center-empty-block">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无路由配置" />
          </div>
        )}
      </Card>

      <Card className="ai-center-panel-card" variant="borderless">
        <div className="ai-center-section-head">
          <div className="ai-center-section-copy">
            <Title level={4} className="ai-center-section-title">
              最近调用事件
            </Title>
            <p className="ai-center-section-subtitle">保留最近 50 条调用结果，可手动清空，不影响提供方和路由配置。</p>
          </div>
        </div>

        <AppLogTerminal
          description="统一按时间顺序展示最近 50 条 AI 调用结果，方便排查空响应、模型波动和自动回退是否生效。"
          controls={
            <>
              <Select
                size="small"
                value={eventFilter}
                style={{ minWidth: 160 }}
                options={[
                  { label: '全部调用', value: 'all' },
                  { label: '仅失败', value: 'error' },
                  { label: '仅成功', value: 'success' },
                ]}
                onChange={(value) => setEventFilter(value as 'all' | 'error' | 'success')}
              />
              <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadAll()}>
                刷新
              </Button>
            </>
          }
          items={visibleEventLines}
          emptyText="暂无调用记录"
          isCleared={eventHiddenMarker > 0}
          onClearDisplay={() => setEventHiddenMarker(orderedEvents[orderedEvents.length - 1]?.id || 0)}
          onShowAll={() => setEventHiddenMarker(0)}
          canShowAll={eventHiddenMarker > 0}
          copyPayload={visibleEventLines.map((item) => item.text)}
          copyEmptyText="当前没有可复制的日志"
          copySuccessText="已复制当前日志"
          onClearBackend={() => void handleClearEvents()}
          clearBackendLoading={eventClearing}
          clearBackendDisabled={events.length <= 0}
          clearBackendConfirmTitle="确认清理 AI 调用事件？"
          clearBackendConfirmDescription="只清空调用记录，不会删除提供方、模型池和能力路由配置。"
        />
      </Card>

      <Modal
        title={editingProvider ? `编辑提供方：${editingProvider.display_name}` : '新增提供方'}
        open={providerModalOpen}
        onCancel={() => setProviderModalOpen(false)}
        onOk={() => void saveProvider()}
        confirmLoading={providerSaving}
        width={1120}
        wrapClassName="responsive-modal-root"
        afterClose={() => {
          setEditingProvider(null)
          providerForm.resetFields()
        }}
      >
        <Form form={providerForm} layout="vertical">
          <Row gutter={12}>
            <Col span={12}><Form.Item name="provider_key" label="提供方标识" rules={[{ required: true }]}><Input placeholder="openai_default" /></Form.Item></Col>
            <Col span={12}><Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}><Input placeholder="默认 AI 兼容接口" /></Form.Item></Col>
            <Col span={24}><Form.Item name="base_url" label="基础地址" rules={[{ required: true }]}><Input placeholder="https://example.com/v1" /></Form.Item></Col>
            <Col span={8}><Form.Item name="api_mode" label="接口模式"><Select options={[{ label: '自动识别', value: 'auto' }, { label: '对话补全', value: 'chat_completions' }, { label: '统一响应', value: 'responses' }]} /></Form.Item></Col>
            <Col span={16}><Form.Item name="api_key" label={editingProvider?.has_api_key ? 'API Key（留空表示不修改）' : 'API Key'}><Input.Password placeholder="sk-..." /></Form.Item></Col>
            <Col span={6}><Form.Item name="priority" label="优先级"><InputNumber min={0} max={100000} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="timeout_seconds" label="超时秒数"><InputNumber min={5} max={120} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="max_retries" label="最大重试"><InputNumber min={0} max={5} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={6}><Form.Item name="cooldown_seconds" label="失败冷却"><InputNumber min={0} max={86400} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="is_enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Col>
            <Col span={8}><Form.Item name="is_default" label="设为默认" valuePropName="checked"><Switch /></Form.Item></Col>
            <Col span={8}><Form.Item name="clear_api_key" label="清空已存 API Key" valuePropName="checked"><Switch disabled={!editingProvider?.has_api_key} /></Form.Item></Col>
          </Row>
          <Form.List name="models">
            {(fields, { add, remove }) => (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>模型池</Text>
                  <Button onClick={() => add(emptyProviderModelDraft())}>手动补充模型</Button>
                </Space>
                {fields.map((field) => (
                  <Card
                    key={field.key}
                    size="small"
                    title={<Form.Item noStyle shouldUpdate>{() => <span>{providerForm.getFieldValue(['models', field.name, 'model_id']) || '新模型'}</span>}</Form.Item>}
                    extra={<Button danger size="small" onClick={() => remove(field.name)}>移除</Button>}
                  >
                    <Row gutter={12}>
                      <Col span={8}><Form.Item name={[field.name, 'model_id']} label="模型 ID" rules={[{ required: true }]}><Input placeholder="gpt-5.2" /></Form.Item></Col>
                      <Col span={8}><Form.Item name={[field.name, 'label']} label="显示名称"><Input placeholder="可选" /></Form.Item></Col>
                      <Col span={4}><Form.Item name={[field.name, 'is_enabled']} label="启用" valuePropName="checked"><Switch /></Form.Item></Col>
                      <Col span={4}><Form.Item name={[field.name, 'is_preferred']} label="首选" valuePropName="checked"><Switch /></Form.Item></Col>
                      <Col span={12}><Form.Item name={[field.name, 'capabilities']} label="能力标签"><Select mode="multiple" allowClear options={CAPABILITY_OPTIONS} /></Form.Item></Col>
                      <Col span={12}><Form.Item name={[field.name, 'route_allowlist']} label="限制路由"><Select mode="multiple" allowClear options={routeKeyOptions} placeholder="留空表示全部路由可用" /></Form.Item></Col>
                      <Col span={6}><Form.Item name={[field.name, 'priority_bias']} label="优先偏置"><InputNumber min={-200} max={200} style={{ width: '100%' }} /></Form.Item></Col>
                      <Col span={4}><Form.Item name={[field.name, 'quality_score']} label="质量"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
                      <Col span={4}><Form.Item name={[field.name, 'stability_score']} label="稳定"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
                      <Col span={4}><Form.Item name={[field.name, 'speed_score']} label="速度"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
                      <Col span={4}><Form.Item name={[field.name, 'cost_score']} label="成本"><InputNumber min={0} max={100} style={{ width: '100%' }} /></Form.Item></Col>
                      <Col span={24}><Form.Item name={[field.name, 'notes']} label="备注"><Input placeholder="可选，记录这个模型更适合什么任务" /></Form.Item></Col>
                      <Form.Item name={[field.name, 'id']} hidden><InputNumber /></Form.Item>
                    </Row>
                  </Card>
                ))}
              </Space>
            )}
          </Form.List>
        </Form>
      </Modal>

      <Modal
        title={editingRoute ? `配置路由：${editingRoute.display_name}` : '配置路由'}
        open={routeModalOpen}
        onCancel={() => setRouteModalOpen(false)}
        onOk={() => void saveRoute()}
        confirmLoading={routeSaving}
        width={1040}
        wrapClassName="responsive-modal-root"
        afterClose={() => {
          setEditingRoute(null)
          routeForm.resetFields()
        }}
      >
        <Form form={routeForm} layout="vertical">
          <Row gutter={12}>
            <Col span={12}><Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="output_mode" label="输出模式"><Select options={[{ label: '文本', value: 'text' }, { label: 'JSON', value: 'json' }]} /></Form.Item></Col>
            <Col span={6}><Form.Item name="max_attempts" label="最大尝试次数"><InputNumber min={1} max={10} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item></Col>
            <Col span={24}><Form.Item name="is_enabled" label="启用路由" valuePropName="checked"><Switch /></Form.Item></Col>
            <Col span={6}><Form.Item name="selection_mode" label="选择策略"><Select options={SELECTION_MODE_OPTIONS} /></Form.Item></Col>
            <Col span={6}><Form.Item name="optimization_goal" label="优化目标"><Select options={OPTIMIZATION_GOAL_OPTIONS} /></Form.Item></Col>
            <Col span={12}><Form.Item name="preferred_capabilities" label="偏好能力"><Select mode="multiple" allowClear options={CAPABILITY_OPTIONS} /></Form.Item></Col>
            <Col span={12}><Form.Item name="allow_same_provider_model_failover" label="同提供方模型回退" valuePropName="checked"><Switch /></Form.Item></Col>
            <Col span={12}><Form.Item name="allow_cross_provider_failover" label="跨提供方回退" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                {fields.map((field, index) => {
                  const providerId = routeSteps[index]?.provider_id
                  return (
                    <Card
                      key={field.key}
                      size="small"
                      title={`步骤 ${index + 1}`}
                      extra={<Button danger size="small" onClick={() => remove(field.name)}>移除</Button>}
                    >
                      <Row gutter={12}>
                        <Col span={10}>
                          <Form.Item name={[field.name, 'provider_id']} label="提供方" rules={[{ required: true }]}>
                            <Select options={providerOptions} />
                          </Form.Item>
                        </Col>
                        <Col span={8}>
                          <Form.Item name={[field.name, 'model_id']} label="模型">
                            <Select allowClear options={providerModelOptions[providerId] || []} placeholder="留空表示自动选择模型" />
                          </Form.Item>
                        </Col>
                        <Col span={6}>
                          <Form.Item name={[field.name, 'is_enabled']} label="启用" valuePropName="checked">
                            <Switch />
                          </Form.Item>
                        </Col>
                        <Form.Item name={[field.name, 'id']} hidden><InputNumber /></Form.Item>
                      </Row>
                    </Card>
                  )
                })}
                <Button onClick={() => add({ provider_id: providers[0]?.id, is_enabled: true })}>新增步骤</Button>
              </Space>
            )}
          </Form.List>
        </Form>
      </Modal>

      <Modal
        title={testingRoute ? `测试路由：${testingRoute.display_name}` : '测试路由'}
        open={routeTestModalOpen}
        onCancel={() => setRouteTestModalOpen(false)}
        onOk={() => void runRouteTest()}
        confirmLoading={routeTesting}
        width={820}
        wrapClassName="responsive-modal-root"
        afterClose={() => {
          setTestingRoute(null)
          routeTestForm.resetFields()
        }}
      >
        <Form form={routeTestForm} layout="vertical">
          <Form.Item name="system_prompt" label="系统提示词" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="user_prompt" label="用户输入" rules={[{ required: true }]}><Input.TextArea rows={6} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default AiCenterAdminRuntime
