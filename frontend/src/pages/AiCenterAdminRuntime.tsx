import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
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
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, ExperimentOutlined, PlusOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons'

import {
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

const { Title, Paragraph, Text } = Typography

const formatDateTime = (value?: string | null) =>
  value ? formatServerDateTime(value, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai') : '-'

const getErrorMessage = (error: any, fallback: string) => error?.response?.data?.detail || fallback

const PROVIDER_HEALTH_COLOR: Record<string, string> = {
  healthy: 'success',
  degraded: 'warning',
  unknown: 'default',
}

const EVENT_STATUS_COLOR: Record<string, string> = {
  success: 'success',
  error: 'error',
  skipped: 'default',
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

const AiCenterAdminRuntime = () => {
  const [overview, setOverview] = useState<AiCenterOverviewResponse | null>(null)
  const [providers, setProviders] = useState<AiCenterProviderItem[]>([])
  const [routes, setRoutes] = useState<AiCenterRouteItem[]>([])
  const [events, setEvents] = useState<AiCenterCallEventItem[]>([])
  const [loading, setLoading] = useState(true)
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

  const openCreateProvider = () => {
    setEditingProvider(null)
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
        title: `Provider 测试成功: ${record.display_name}`,
        width: 640,
        content: (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Paragraph>{`模型: ${result.model_id || '-'}`}</Paragraph>
            <Paragraph>{`模式: ${result.used_api_mode || '-'}`}</Paragraph>
            <Paragraph copyable>{result.text || '(空返回)'}</Paragraph>
          </Space>
        ),
      })
      await loadAll()
    } catch (error: any) {
      message.error(getErrorMessage(error, '测试 provider 失败'))
    } finally {
      setProviderTestingId(null)
    }
  }

  const handleDeleteProvider = async (record: AiCenterProviderItem) => {
    Modal.confirm({
      title: `删除 Provider: ${record.display_name}`,
      content: '删除前请确认这个 provider 没有被路由使用。',
      okButtonProps: { danger: true },
      onOk: async () => {
        setProviderDeletingId(record.id)
        try {
          await deleteAiProvider(record.id)
          message.success('AI 提供方已删除')
          await loadAll()
        } catch (error: any) {
          message.error(getErrorMessage(error, '删除 provider 失败'))
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
        title: `路由测试成功: ${testingRoute.display_name}`,
        width: 820,
        content: (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Paragraph>{`选择摘要: ${result.selection_summary || '-'}`}</Paragraph>
            <Paragraph>{`Provider: ${result.provider_label || '-'}`}</Paragraph>
            <Paragraph>{`模型: ${result.model_id || '-'}`}</Paragraph>
            <Paragraph>{`模式: ${result.used_api_mode || '-'}`}</Paragraph>
            <Paragraph>{`耗时: ${result.duration_ms || 0} ms`}</Paragraph>
            <Paragraph copyable={{ text: result.text }}>{result.text || '(空返回)'}</Paragraph>
            {result.attempt_trace.length ? (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Text strong>尝试链路</Text>
                {result.attempt_trace.map((item, index) => (
                  <Card key={`${item.provider_id || 'p'}-${item.model_id || 'm'}-${index}`} size="small">
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Text>{`#${item.attempt_index || index + 1} ${item.provider_label || '-'} / ${item.model_id || 'auto'}`}</Text>
                      <Text type={item.status === 'error' ? 'danger' : 'secondary'}>
                        {`${item.status || '-'} · ${item.duration_ms || 0} ms`}
                      </Text>
                      <Text type="secondary">{item.selection_summary || '-'}</Text>
                      {Array.isArray(item.candidate_reasons) && item.candidate_reasons.length ? (
                        <Text type="secondary">{`打分依据: ${item.candidate_reasons.join(', ')}`}</Text>
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

  const providerColumns: ColumnsType<AiCenterProviderItem> = [
    {
      title: 'Provider',
      key: 'provider',
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Space size={6}>
            <Text strong>{record.display_name}</Text>
            {record.is_default ? <Tag color="processing">默认</Tag> : null}
            {!record.is_enabled ? <Tag>停用</Tag> : null}
          </Space>
          <Text type="secondary">{record.provider_key}</Text>
          <Text type="secondary">{record.base_url || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '模型池',
      key: 'models',
      width: 260,
      render: (_, record) => (
        <Space direction="vertical" size={6}>
          <Text type="secondary">{`启用 ${record.enabled_model_count}/${record.model_count}`}</Text>
          <Text type="secondary">{record.preferred_model_id ? `首选 ${record.preferred_model_id}` : '未设置首选模型'}</Text>
          <Space wrap size={[4, 4]}>
            {record.models.slice(0, 3).map((model) => (
              <Tag key={`${record.id}-${model.model_id}`} color={model.is_enabled ? 'blue' : 'default'}>
                {model.label || model.model_id}
              </Tag>
            ))}
            {record.models.length > 3 ? <Tag>{`+${record.models.length - 3}`}</Tag> : null}
          </Space>
        </Space>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 220,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Tag color={PROVIDER_HEALTH_COLOR[record.health_status] || 'default'}>{record.health_status || 'unknown'}</Tag>
          <Text type="secondary">{record.cooldown_until ? `冷却至 ${formatDateTime(record.cooldown_until)}` : '当前可参与调度'}</Text>
          <Text type="secondary">{record.last_success_at ? `最近成功 ${formatDateTime(record.last_success_at)}` : '暂无成功记录'}</Text>
          {record.last_error_message ? <Text type="danger">{record.last_error_message}</Text> : null}
        </Space>
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
            刷模型
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

  const routeColumns: ColumnsType<AiCenterRouteItem> = [
    {
      title: '能力路由',
      key: 'route',
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Space size={6}>
            <Text strong>{record.display_name}</Text>
            <Tag color={record.is_ready ? 'success' : 'warning'}>{record.is_ready ? '已就绪' : '未就绪'}</Tag>
          </Space>
          <Text type="secondary">{record.route_key}</Text>
          <Text type="secondary">{record.description || '未填写说明'}</Text>
        </Space>
      ),
    },
    {
      title: '选模策略',
      key: 'strategy',
      width: 320,
      render: (_, record) => (
        <Space direction="vertical" size={6}>
          <Space wrap size={[4, 4]}>
            <Tag color="blue">{getSelectionModeLabel(record.selection_mode)}</Tag>
            <Tag color="geekblue">{getOptimizationGoalLabel(record.optimization_goal)}</Tag>
            {record.allow_same_provider_model_failover ? <Tag color="cyan">同 Provider 模型回退</Tag> : <Tag>固定单模型</Tag>}
            {record.allow_cross_provider_failover ? <Tag color="purple">跨 Provider 回退</Tag> : <Tag>按步骤顺序</Tag>}
          </Space>
          <Space wrap size={[4, 4]}>
            {record.preferred_capabilities.length ? (
              record.preferred_capabilities.map((item) => (
                <Tag key={`${record.route_key}-${item}`}>{getCapabilityLabel(item)}</Tag>
              ))
            ) : (
              <Text type="secondary">未设置偏好能力</Text>
            )}
          </Space>
          <Text type="secondary">{record.selection_summary || '尚未形成候选摘要'}</Text>
        </Space>
      ),
    },
    {
      title: '当前候选',
      key: 'ready',
      width: 240,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text>{record.ready_provider_label || '未绑定 provider'}</Text>
          <Text type="secondary">{record.ready_model_id || '未绑定模型'}</Text>
          <Text type="secondary">{`步骤 ${record.enabled_step_count}/${record.configured_step_count} · 候选 ${record.candidate_count}`}</Text>
          {!record.is_ready && record.ready_reason ? <Text type="danger">{record.ready_reason}</Text> : null}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_, record) => (
        <Space wrap>
          <Button size="small" icon={<SettingOutlined />} onClick={() => openRouteConfig(record)}>
            配置
          </Button>
          <Button size="small" icon={<ExperimentOutlined />} onClick={() => openRouteTest(record)}>
            测试
          </Button>
        </Space>
      ),
    },
  ]

  const eventColumns: ColumnsType<AiCenterCallEventItem> = [
    { title: '时间', dataIndex: 'created_at', width: 160, render: (value) => formatDateTime(value) },
    {
      title: '路由',
      key: 'route',
      width: 220,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text>{record.route_key}</Text>
          <Text type="secondary">
            {record.selection_mode ? `${getSelectionModeLabel(record.selection_mode)} · 第 ${record.attempt_index || 1} 次` : '-'}
          </Text>
        </Space>
      ),
    },
    {
      title: '执行链路',
      key: 'chain',
      width: 280,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text>{record.provider_label || '-'}</Text>
          <Text type="secondary">{`${record.model_id || '-'} / ${record.used_api_mode || '-'}`}</Text>
          <Text type="secondary">{record.selection_summary || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '结果',
      key: 'status',
      width: 140,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Tag color={EVENT_STATUS_COLOR[record.status] || 'default'}>{record.status}</Tag>
          <Text type="secondary">{record.duration_ms ? `${record.duration_ms} ms` : '-'}</Text>
        </Space>
      ),
    },
    {
      title: '错误 / 备注',
      key: 'message',
      render: (_, record) =>
        record.error_message || (record.candidate_score != null ? `候选评分 ${record.candidate_score.toFixed(1)}` : '-'),
    },
  ]

  const routeSteps = Form.useWatch('steps', routeForm) || []

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          AI 中心
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          统一管理 AI Provider、模型池、能力路由和调用事件。作品归并、追更同步等业务只消费这里的配置，不再各自维护一套 AI 参数。
        </Paragraph>
      </div>

      {overview?.legacy_migration_applied ? (
        <Alert type="info" showIcon message="已检测到旧资源运营 AI 配置，并自动迁移为默认 provider 与路由步骤。" />
      ) : null}

      <Alert
        type="info"
        showIcon
        message="自动优选会综合步骤顺序、模型能力标签、质量/稳定/速度/成本评分，以及最近成功率来挑选模型。"
        description="同 Provider 模型回退只在步骤未固定具体模型时生效；跨 Provider 回退开启后，系统会在整个候选池中选择更合适的可用模型。"
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}><Card loading={loading}><Text type="secondary">Provider</Text><Title level={3}>{overview?.enabled_providers || 0}/{overview?.total_providers || 0}</Title></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card loading={loading}><Text type="secondary">可用路由</Text><Title level={3}>{overview?.ready_routes || 0}/{overview?.total_routes || 0}</Title></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card loading={loading}><Text type="secondary">24h 成功调用</Text><Title level={3}>{overview?.recent_success_count_24h || 0}</Title></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card loading={loading}><Text type="secondary">24h 失败调用</Text><Title level={3}>{overview?.recent_failure_count_24h || 0}</Title></Card></Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card
            title="Provider 管理"
            extra={<Button type="primary" icon={<PlusOutlined />} onClick={openCreateProvider}>新增 Provider</Button>}
          >
            <Table rowKey="id" size="small" loading={loading} columns={providerColumns} dataSource={providers} pagination={false} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="能力路由">
            <Table rowKey="route_key" size="small" loading={loading} columns={routeColumns} dataSource={routes} pagination={false} />
          </Card>
        </Col>
      </Row>

      <Card title="最近调用事件" extra={<Button icon={<ReloadOutlined />} onClick={() => void loadAll()}>刷新</Button>}>
        <Table rowKey="id" size="small" loading={loading} columns={eventColumns} dataSource={events} pagination={{ pageSize: 10 }} scroll={{ x: 960 }} />
      </Card>

      <Modal
        title={editingProvider ? `编辑 Provider: ${editingProvider.display_name}` : '新增 Provider'}
        open={providerModalOpen}
        onCancel={() => setProviderModalOpen(false)}
        onOk={() => void saveProvider()}
        confirmLoading={providerSaving}
        width={1120}
      >
        <Form form={providerForm} layout="vertical">
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="Provider 负责连接凭据与模型池。"
            description="模型池里的能力标签、质量/稳定/速度/成本评分会被自动优选路由直接使用；路由白名单可限制某些模型只给特定业务使用。"
          />
          <Row gutter={12}>
            <Col span={12}><Form.Item name="provider_key" label="Provider Key" rules={[{ required: true }]}><Input placeholder="openai_default" /></Form.Item></Col>
            <Col span={12}><Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}><Input placeholder="默认 OpenAI 兼容接口" /></Form.Item></Col>
            <Col span={24}><Form.Item name="base_url" label="Base URL" rules={[{ required: true }]}><Input placeholder="https://example.com/v1" /></Form.Item></Col>
            <Col span={8}><Form.Item name="api_mode" label="接口模式"><Select options={[{ label: 'auto', value: 'auto' }, { label: 'chat_completions', value: 'chat_completions' }, { label: 'responses', value: 'responses' }]} /></Form.Item></Col>
            <Col span={16}><Form.Item name="api_key" label={editingProvider?.has_api_key ? 'API Key（留空表示不改）' : 'API Key'}><Input.Password placeholder="sk-..." /></Form.Item></Col>
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
                      <Col span={8}><Form.Item name={[field.name, 'label']} label="显示名"><Input placeholder="可选" /></Form.Item></Col>
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
        title={editingRoute ? `配置路由: ${editingRoute.display_name}` : '配置路由'}
        open={routeModalOpen}
        onCancel={() => setRouteModalOpen(false)}
        onOk={() => void saveRoute()}
        confirmLoading={routeSaving}
        width={1040}
      >
        <Form form={routeForm} layout="vertical">
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="路由决定业务调用时如何选模型。"
            description="自动优选会把步骤看作候选池并进行打分；严格按步骤会优先遵循步骤顺序。若步骤显式固定模型，则同 Provider 模型回退不会生效。"
          />
          <Row gutter={12}>
            <Col span={12}><Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="output_mode" label="输出模式"><Select options={[{ label: 'text', value: 'text' }, { label: 'json', value: 'json' }]} /></Form.Item></Col>
            <Col span={6}><Form.Item name="max_attempts" label="路由最大尝试"><InputNumber min={1} max={10} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item></Col>
            <Col span={24}><Form.Item name="is_enabled" label="启用路由" valuePropName="checked"><Switch /></Form.Item></Col>
            <Col span={6}><Form.Item name="selection_mode" label="选择策略"><Select options={SELECTION_MODE_OPTIONS} /></Form.Item></Col>
            <Col span={6}><Form.Item name="optimization_goal" label="优化目标"><Select options={OPTIMIZATION_GOAL_OPTIONS} /></Form.Item></Col>
            <Col span={12}><Form.Item name="preferred_capabilities" label="偏好能力"><Select mode="multiple" allowClear options={CAPABILITY_OPTIONS} /></Form.Item></Col>
            <Col span={12}><Form.Item name="allow_same_provider_model_failover" label="同 Provider 模型回退" valuePropName="checked"><Switch /></Form.Item></Col>
            <Col span={12}><Form.Item name="allow_cross_provider_failover" label="跨 Provider 回退" valuePropName="checked"><Switch /></Form.Item></Col>
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
                          <Form.Item name={[field.name, 'provider_id']} label="Provider" rules={[{ required: true }]}>
                            <Select options={providerOptions} />
                          </Form.Item>
                        </Col>
                        <Col span={8}>
                          <Form.Item name={[field.name, 'model_id']} label="模型">
                            <Select allowClear options={providerModelOptions[providerId] || []} placeholder="留空表示自动选首选模型" />
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
        title={testingRoute ? `测试路由: ${testingRoute.display_name}` : '测试路由'}
        open={routeTestModalOpen}
        onCancel={() => setRouteTestModalOpen(false)}
        onOk={() => void runRouteTest()}
        confirmLoading={routeTesting}
        width={820}
      >
        <Form form={routeTestForm} layout="vertical">
          <Form.Item name="system_prompt" label="System Prompt" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="user_prompt" label="User Prompt" rules={[{ required: true }]}><Input.TextArea rows={6} /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}

export default AiCenterAdminRuntime
