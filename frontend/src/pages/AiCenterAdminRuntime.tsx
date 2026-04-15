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
})

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
      message.error(error.response?.data?.detail || '加载 AI 中心失败')
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
            label: model.label || model.model_id,
            value: model.model_id,
          })),
        ])
      ),
    [providers]
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
      message.error(error.response?.data?.detail || '保存 AI 提供方失败')
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
      message.error(error.response?.data?.detail || '刷新模型失败')
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
        content: (
          <div>
            <Paragraph>{`模型: ${result.model_id || '-'}`}</Paragraph>
            <Paragraph>{`模式: ${result.used_api_mode || '-'}`}</Paragraph>
            <Paragraph copyable>{result.text || '(空返回)'}</Paragraph>
          </div>
        ),
      })
      await loadAll()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '测试 provider 失败')
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
          message.error(error.response?.data?.detail || '删除 provider 失败')
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
      message.error(error.response?.data?.detail || '保存路由失败')
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
        width: 720,
        content: (
          <div>
            <Paragraph>{`Provider: ${result.provider_label || '-'}`}</Paragraph>
            <Paragraph>{`模型: ${result.model_id || '-'}`}</Paragraph>
            <Paragraph>{`模式: ${result.used_api_mode || '-'}`}</Paragraph>
            <Paragraph>{`耗时: ${result.duration_ms || 0} ms`}</Paragraph>
            <Paragraph copyable={{ text: result.text }}>{result.text || '(空返回)'}</Paragraph>
          </div>
        ),
      })
      setRouteTestModalOpen(false)
      await loadAll()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '测试路由失败')
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
      title: '状态',
      key: 'status',
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Tag color={PROVIDER_HEALTH_COLOR[record.health_status] || 'default'}>{record.health_status || 'unknown'}</Tag>
          <Text type="secondary">{`模型 ${record.enabled_model_count}/${record.model_count}`}</Text>
          <Text type="secondary">{record.preferred_model_id || '未设置首选模型'}</Text>
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
      title: '当前链路',
      key: 'ready',
      width: 220,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text>{record.ready_provider_label || '未绑定 provider'}</Text>
          <Text type="secondary">{record.ready_model_id || '未绑定模型'}</Text>
          <Text type="secondary">{`步骤 ${record.enabled_step_count}/${record.configured_step_count}`}</Text>
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
    { title: '路由', dataIndex: 'route_key', width: 220 },
    { title: 'Provider', dataIndex: 'provider_label', width: 180, render: (value) => value || '-' },
    { title: '模型', dataIndex: 'model_id', width: 180, render: (value) => value || '-' },
    { title: '结果', dataIndex: 'status', width: 110, render: (value) => <Tag color={EVENT_STATUS_COLOR[value] || 'default'}>{value}</Tag> },
    { title: '耗时', dataIndex: 'duration_ms', width: 100, render: (value) => (value ? `${value} ms` : '-') },
    { title: '错误', dataIndex: 'error_message', render: (value) => value || '-' },
  ]

  const routeSteps = Form.useWatch('steps', routeForm) || []

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          AI 中心
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          统一管理 AI provider、模型刷新、能力路由和最近调用事件。作品归并、追更同步都会从这里取配置。
        </Paragraph>
      </div>

      {overview?.legacy_migration_applied ? (
        <Alert type="info" showIcon message="已检测到旧资源运营 AI 配置，并自动迁移为默认 provider 与路由步骤。" />
      ) : null}

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
        width={760}
      >
        <Form form={providerForm} layout="vertical">
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
        </Form>
      </Modal>

      <Modal
        title={editingRoute ? `配置路由: ${editingRoute.display_name}` : '配置路由'}
        open={routeModalOpen}
        onCancel={() => setRouteModalOpen(false)}
        onOk={() => void saveRoute()}
        confirmLoading={routeSaving}
        width={920}
      >
        <Form form={routeForm} layout="vertical">
          <Row gutter={12}>
            <Col span={12}><Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="output_mode" label="输出模式"><Select options={[{ label: 'text', value: 'text' }, { label: 'json', value: 'json' }]} /></Form.Item></Col>
            <Col span={6}><Form.Item name="max_attempts" label="路由最大尝试"><InputNumber min={1} max={10} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item></Col>
            <Col span={24}><Form.Item name="is_enabled" label="启用路由" valuePropName="checked"><Switch /></Form.Item></Col>
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
