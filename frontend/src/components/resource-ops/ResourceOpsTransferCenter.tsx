export { default } from './transfer-center/ResourceOpsTransferCenterMain'
/*
import { useEffect, useMemo, useState } from 'react'
import type { Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'

import {
  createPanTransferAccount,
  deletePanTransferAccount,
  listPanTransferAccounts,
  previewManualPanTransfer,
  updatePanTransferAccount,
} from '@/api/panTransfer'
import type {
  PanTransferAccountCreateRequest,
  PanTransferAccountItem,
  PanTransferAccountUpdateRequest,
  PanTransferManualPreviewRequest,
  PanTransferManualPreviewResponse,
  PanTransferPreviewItem,
} from '@/types/panTransfer'
import { formatServerDateTime } from '@/utils/dateTime'

import './ResourceOpsTransferCenter.css'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

type PreviewDraft = {
  selectionMode: 'recent_messages' | 'time_range'
  direction: 'newest_first' | 'oldest_first'
  recentMessageCount: number
  range: [Dayjs, Dayjs] | null
  platforms: string[]
  onlyHealthy: boolean
}

type ApiError = {
  response?: {
    data?: {
      detail?: string
    }
  }
  errorFields?: unknown
}

const PLATFORM_OPTIONS = [
  { label: '百度网盘', value: '百度网盘' },
  { label: '夸克网盘', value: '夸克网盘' },
]

const SHARE_MODE_OPTIONS = [
  { label: '转存后继续分享', value: 'public' },
  { label: '仅转存不分享', value: 'private' },
]

const DEFAULT_PREVIEW_DRAFT: PreviewDraft = {
  selectionMode: 'recent_messages',
  direction: 'newest_first',
  recentMessageCount: 200,
  range: null,
  platforms: [],
  onlyHealthy: false,
}

const buildPreviewPayload = (
  draft: PreviewDraft,
  pagination?: { page?: number; pageSize?: number }
): PanTransferManualPreviewRequest => ({
  selection_mode: draft.selectionMode,
  direction: draft.direction,
  recent_message_count: draft.selectionMode === 'recent_messages' ? draft.recentMessageCount : undefined,
  range_start: draft.selectionMode === 'time_range' && draft.range ? draft.range[0].format('YYYY-MM-DD') : undefined,
  range_end: draft.selectionMode === 'time_range' && draft.range ? draft.range[1].format('YYYY-MM-DD') : undefined,
  platforms: draft.platforms,
  only_healthy: draft.onlyHealthy,
  page: pagination?.page || 1,
  page_size: pagination?.pageSize || 50,
})

const healthColor = (status: string) => {
  if (status === 'healthy') return 'success'
  if (status === 'invalid') return 'error'
  return 'default'
}

const formatDateTime = (value?: string | null) =>
  value ? formatServerDateTime(value, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai') : '-'

const getErrorMessage = (error: unknown, fallback: string) =>
  (error as ApiError)?.response?.data?.detail || fallback

const ResourceOpsTransferCenter = () => {
  const [accounts, setAccounts] = useState<PanTransferAccountItem[]>([])
  const [accountsLoading, setAccountsLoading] = useState(false)
  const [accountModalOpen, setAccountModalOpen] = useState(false)
  const [accountSaving, setAccountSaving] = useState(false)
  const [editingAccount, setEditingAccount] = useState<PanTransferAccountItem | null>(null)
  const [previewDraft, setPreviewDraft] = useState<PreviewDraft>(DEFAULT_PREVIEW_DRAFT)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewData, setPreviewData] = useState<PanTransferManualPreviewResponse | null>(null)
  const [lastPreviewPayload, setLastPreviewPayload] = useState<PanTransferManualPreviewRequest | null>(null)
  const [accountForm] = Form.useForm()

  const loadAccounts = async () => {
    setAccountsLoading(true)
    try {
      const response = await listPanTransferAccounts()
      setAccounts(response.items)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '加载网盘账号失败'))
    } finally {
      setAccountsLoading(false)
    }
  }

  useEffect(() => {
    void loadAccounts()
  }, [])

  const openCreateModal = () => {
    setEditingAccount(null)
    accountForm.resetFields()
    accountForm.setFieldsValue({
      platform: PLATFORM_OPTIONS[0].value,
      account_name: '',
      auth_type: 'cookie',
      credential_value: '',
      default_save_root: '',
      default_share_mode: 'public',
      default_share_passcode: '',
      default_share_expire_days: undefined,
      is_enabled: true,
      is_default: false,
    })
    setAccountModalOpen(true)
  }

  const openEditModal = (account: PanTransferAccountItem) => {
    setEditingAccount(account)
    accountForm.resetFields()
    accountForm.setFieldsValue({
      platform: account.platform,
      account_name: account.account_name,
      auth_type: account.auth_type,
      credential_value: '',
      default_save_root: account.default_save_root,
      default_share_mode: account.default_share_mode,
      default_share_passcode: account.default_share_passcode || '',
      default_share_expire_days: account.default_share_expire_days || undefined,
      is_enabled: account.is_enabled,
      is_default: account.is_default,
    })
    setAccountModalOpen(true)
  }

  const closeAccountModal = () => {
    setAccountModalOpen(false)
    setEditingAccount(null)
    accountForm.resetFields()
  }

  const handleSaveAccount = async () => {
    try {
      const values = await accountForm.validateFields()
      setAccountSaving(true)

      if (editingAccount) {
        const payload: PanTransferAccountUpdateRequest = {
          platform: values.platform,
          account_name: values.account_name,
          auth_type: values.auth_type,
          default_save_root: values.default_save_root || '',
          default_share_mode: values.default_share_mode,
          default_share_passcode: values.default_share_passcode || null,
          default_share_expire_days: values.default_share_expire_days || null,
          is_enabled: Boolean(values.is_enabled),
          is_default: Boolean(values.is_default),
        }
        if (values.credential_value) {
          payload.credential_value = values.credential_value
        }
        await updatePanTransferAccount(editingAccount.id, payload)
        message.success('账号配置已更新')
      } else {
        const payload: PanTransferAccountCreateRequest = {
          platform: values.platform,
          account_name: values.account_name,
          auth_type: values.auth_type,
          credential_value: values.credential_value,
          default_save_root: values.default_save_root || '',
          default_share_mode: values.default_share_mode,
          default_share_passcode: values.default_share_passcode || null,
          default_share_expire_days: values.default_share_expire_days || null,
          is_enabled: Boolean(values.is_enabled),
          is_default: Boolean(values.is_default),
        }
        await createPanTransferAccount(payload)
        message.success('账号配置已创建')
      }

      closeAccountModal()
      await loadAccounts()
    } catch (error: unknown) {
      if ((error as ApiError)?.errorFields) {
        return
      }
      message.error(getErrorMessage(error, '保存账号配置失败'))
    } finally {
      setAccountSaving(false)
    }
  }

  const handleDeleteAccount = async (account: PanTransferAccountItem) => {
    try {
      await deletePanTransferAccount(account.id)
      message.success('账号配置已删除')
      await loadAccounts()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除账号配置失败'))
    }
  }

  const runPreview = async (payload: PanTransferManualPreviewRequest) => {
    setPreviewLoading(true)
    try {
      const response = await previewManualPanTransfer(payload)
      setPreviewData(response)
      setLastPreviewPayload(payload)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '生成转存预览失败'))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handlePreview = async () => {
    if (previewDraft.selectionMode === 'time_range' && !previewDraft.range) {
      message.warning('请选择时间范围')
      return
    }
    await runPreview(buildPreviewPayload(previewDraft))
  }

  const handlePreviewTableChange = async (pagination: TablePaginationConfig) => {
    if (!lastPreviewPayload) {
      return
    }
    await runPreview({
      ...lastPreviewPayload,
      page: pagination.current || 1,
      page_size: pagination.pageSize || lastPreviewPayload.page_size || 50,
    })
  }

  const enabledPlatforms = useMemo(
    () => new Set(accounts.filter((item) => item.is_enabled).map((item) => item.platform)),
    [accounts]
  )

  const missingPlatforms = useMemo(
    () => PLATFORM_OPTIONS.filter((item) => !enabledPlatforms.has(item.value)),
    [enabledPlatforms]
  )

  const accountColumns: ColumnsType<PanTransferAccountItem> = [
    {
      title: '平台 / 账号',
      dataIndex: 'account_name',
      key: 'account_name',
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">{record.account_name}</span>
          <span className="resource-ops-transfer-title-sub">{record.platform}</span>
        </div>
      ),
    },
    {
      title: '默认策略',
      key: 'strategy',
      render: (_, record) => (
        <div className="resource-ops-transfer-account-tags">
          <Tag color={record.default_share_mode === 'public' ? 'blue' : 'default'}>
            {record.default_share_mode === 'public' ? '转存后分享' : '仅转存'}
          </Tag>
          {record.default_save_root ? <Tag>{record.default_save_root}</Tag> : null}
          {record.is_default ? <Tag color="gold">默认账号</Tag> : null}
        </div>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 180,
      render: (_, record) => (
        <Space wrap>
          <Tag color={record.is_enabled ? 'success' : 'default'}>{record.is_enabled ? '启用' : '停用'}</Tag>
          <Tag color={record.credential_configured ? 'processing' : 'warning'}>
            {record.credential_configured ? '凭据已配置' : '缺少凭据'}
          </Tag>
        </Space>
      ),
    },
    {
      title: '最近更新',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除这个账号配置吗？" onConfirm={() => void handleDeleteAccount(record)}>
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const previewColumns = useMemo<ColumnsType<PanTransferPreviewItem>>(
    () => [
      {
        title: '标题',
        dataIndex: 'short_title',
        key: 'short_title',
        render: (_, record) => (
          <div className="resource-ops-transfer-title-cell">
            <span className="resource-ops-transfer-title-main">{record.short_title}</span>
            <span className="resource-ops-transfer-title-sub">
              {record.latest_message_title || record.work_title || '暂无补充标题'}
            </span>
          </div>
        ),
      },
      {
        title: '平台',
        dataIndex: 'platform',
        key: 'platform',
        width: 110,
        render: (value: string) => <Tag>{value}</Tag>,
      },
      {
        title: '原链',
        dataIndex: 'original_url',
        key: 'original_url',
        render: (value: string) => (
          <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
            {value}
          </a>
        ),
      },
      {
        title: '原链健康',
        dataIndex: 'latest_link_health',
        key: 'latest_link_health',
        width: 120,
        render: (_, record) => (
          <Tag color={healthColor(record.latest_link_health)} title={record.latest_link_health_reason || undefined}>
            {record.latest_link_health_label}
          </Tag>
        ),
      },
      {
        title: '影响消息数',
        dataIndex: 'impact_message_count',
        key: 'impact_message_count',
        width: 110,
      },
      {
        title: '推荐账号',
        dataIndex: 'recommended_account_name',
        key: 'recommended_account_name',
        width: 160,
        render: (value?: string | null) => value || <Text type="secondary">未配置</Text>,
      },
      {
        title: '最近消息时间',
        dataIndex: 'latest_message_time',
        key: 'latest_message_time',
        width: 180,
        render: (value?: string | null) =>
          value ? formatDateTime(value) : <Text type="secondary">-</Text>,
      },
    ],
    []
  )

  return (
    <div className="resource-ops-transfer-stack">
      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head">
          <div>
            <Title level={4}>网盘账号</Title>
            <p>先为可转存平台配置账号、默认保存目录和默认分享策略。凭据只做加密存储，不在列表回显。</p>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void loadAccounts()} loading={accountsLoading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
              新增账号
            </Button>
          </Space>
        </div>

        <div className="resource-ops-transfer-summary">
          <div className="resource-ops-transfer-summary-item">
            <span>账号总数</span>
            <strong>{accounts.length}</strong>
            <small>当前先支持百度网盘和夸克网盘</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>已启用账号</span>
            <strong>{accounts.filter((item) => item.is_enabled).length}</strong>
            <small>预览会优先推荐启用且被设为默认的账号</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>已设默认平台数</span>
            <strong>{new Set(accounts.filter((item) => item.is_default).map((item) => item.platform)).size}</strong>
            <small>建议每个平台至少保留一个默认账号</small>
          </div>
        </div>

        {missingPlatforms.length > 0 ? (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message="仍有平台未配置可用账号"
            description={`当前缺少：${missingPlatforms.map((item) => item.label).join('、')}。没有账号也能预览，但还不能进入后续真实转存。`}
          />
        ) : null}

        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          loading={accountsLoading}
          dataSource={accounts}
          columns={accountColumns}
          pagination={false}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无网盘账号配置" /> }}
        />
      </Card>

      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head">
          <div>
            <Title level={4}>手动批量转存预览</Title>
            <p>按消息范围选出原始网盘链接，再按唯一原链去重。当前这一轮只把筛选和预览做准确，真实转存执行下一步接上。</p>
          </div>
          <Button type="primary" onClick={() => void handlePreview()} loading={previewLoading}>
            生成预览
          </Button>
        </div>

        <Alert
          type="info"
          showIcon
          message="当前阶段"
          description="本轮先落地账号配置和手动预览能力，不执行真实转存，也不会修改原数据库链接。"
          style={{ marginBottom: 16 }}
        />

        <div className="resource-ops-transfer-toolbar">
          <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
            <label>选择方式</label>
            <Segmented
              block
              value={previewDraft.selectionMode}
              options={[
                { label: '最近消息', value: 'recent_messages' },
                { label: '时间范围', value: 'time_range' },
              ]}
              onChange={(value) =>
                setPreviewDraft((current) => ({ ...current, selectionMode: value as PreviewDraft['selectionMode'] }))
              }
            />
          </div>

          <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
            <label>遍历方向</label>
            <Select
              value={previewDraft.direction}
              options={[
                { label: '最新优先', value: 'newest_first' },
                { label: '最早优先', value: 'oldest_first' },
              ]}
              onChange={(value) =>
                setPreviewDraft((current) => ({ ...current, direction: value as PreviewDraft['direction'] }))
              }
            />
          </div>

          {previewDraft.selectionMode === 'recent_messages' ? (
            <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
              <label>最近消息数</label>
              <InputNumber
                min={1}
                max={3000}
                value={previewDraft.recentMessageCount}
                onChange={(value) =>
                  setPreviewDraft((current) => ({ ...current, recentMessageCount: Number(value || 1) }))
                }
                style={{ width: '100%' }}
              />
            </div>
          ) : (
            <div className="resource-ops-transfer-field">
              <label>时间范围</label>
              <RangePicker
                style={{ width: '100%' }}
                value={previewDraft.range}
                onChange={(value) =>
                  setPreviewDraft((current) => ({ ...current, range: (value as [Dayjs, Dayjs] | null) ?? null }))
                }
              />
            </div>
          )}

          <div className="resource-ops-transfer-field">
            <label>平台多选</label>
            <Select
              mode="multiple"
              allowClear
              value={previewDraft.platforms}
              placeholder="留空表示百度与夸克全部参与"
              options={PLATFORM_OPTIONS}
              onChange={(value) => setPreviewDraft((current) => ({ ...current, platforms: value }))}
            />
          </div>

          <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
            <label>筛选</label>
            <div className="resource-ops-transfer-inline-switch">
              <Switch
                checked={previewDraft.onlyHealthy}
                onChange={(checked) => setPreviewDraft((current) => ({ ...current, onlyHealthy: checked }))}
              />
              <span>只看健康原链</span>
            </div>
          </div>
        </div>

        {previewData ? (
          <>
            <div className="resource-ops-transfer-summary">
              <div className="resource-ops-transfer-summary-item">
                <span>命中消息</span>
                <strong>{previewData.effective_message_count}</strong>
                <small>
                  {previewData.selection_mode === 'time_range' ? '范围内实际扫到的消息数' : '本次纳入扫描的最近消息数'}
                </small>
              </div>
              <div className="resource-ops-transfer-summary-item">
                <span>唯一原链</span>
                <strong>{previewData.unique_link_target_count}</strong>
                <small>按唯一 link target 去重后的可处理项</small>
              </div>
              <div className="resource-ops-transfer-summary-item">
                <span>影响消息数</span>
                <strong>{previewData.matched_link_ref_count}</strong>
                <small>这些原链在当前预览范围内覆盖到的引用记录总数</small>
              </div>
              <div className="resource-ops-transfer-summary-item">
                <span>健康分布</span>
                <strong>
                  {previewData.healthy_count} / {previewData.invalid_count} / {previewData.unknown_count}
                </strong>
                <small>正常 / 失效 / 未知</small>
              </div>
            </div>

            {previewData.truncated ? (
              <Alert
                style={{ marginTop: 16 }}
                type="warning"
                showIcon
                message="时间范围过大，预览已自动截断"
                description="时间范围模式下，为了控制扫描成本，当前最多扫描 3000 条带链接消息。后续可以继续补分页游标式执行。"
              />
            ) : null}

            <Table
              style={{ marginTop: 16 }}
              rowKey="link_target_id"
              loading={previewLoading}
              dataSource={previewData.items}
              columns={previewColumns}
              onChange={handlePreviewTableChange}
              pagination={{
                current: previewData.page,
                pageSize: previewData.page_size,
                total: previewData.total,
                showSizeChanger: true,
              }}
              scroll={{ x: 1100 }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无符合条件的原链" /> }}
            />
          </>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先选择范围并生成预览" />
        )}
      </Card>

      <Modal
        open={accountModalOpen}
        title={editingAccount ? '编辑网盘账号' : '新增网盘账号'}
        onCancel={closeAccountModal}
        onOk={() => void handleSaveAccount()}
        confirmLoading={accountSaving}
        destroyOnHidden
      >
        <Form form={accountForm} layout="vertical">
          <Form.Item label="平台" name="platform" rules={[{ required: true, message: '请选择平台' }]}> 
            <Select options={PLATFORM_OPTIONS} />
          </Form.Item>

          <Form.Item label="账号名称" name="account_name" rules={[{ required: true, message: '请输入账号名称' }]}> 
            <Input placeholder="例如：百度主账号 A" />
          </Form.Item>

          <Form.Item label="认证方式" name="auth_type" rules={[{ required: true }]} initialValue="cookie">
            <Select options={[{ label: 'Cookie', value: 'cookie' }]} />
          </Form.Item>

          <Form.Item
            label={editingAccount ? '凭据内容（留空表示保持不变）' : '凭据内容'}
            name="credential_value"
            rules={editingAccount ? [] : [{ required: true, message: '请输入凭据内容' }]}
          >
            <Input.TextArea rows={4} placeholder="当前先支持 Cookie 文本，后续再扩展更多登录方式。" />
          </Form.Item>

          <div className="resource-ops-transfer-form-tip">凭据会按系统密钥加密存储，列表页不会回显明文。</div>

          <Form.Item label="默认保存目录" name="default_save_root">
            <Input placeholder="例如：TG镜像/影视" />
          </Form.Item>

          <Form.Item label="默认分享策略" name="default_share_mode">
            <Select options={SHARE_MODE_OPTIONS} />
          </Form.Item>

          <Form.Item label="默认提取码" name="default_share_passcode">
            <Input placeholder="可留空" />
          </Form.Item>

          <Form.Item label="默认失效天数" name="default_share_expire_days">
            <InputNumber min={1} max={3650} style={{ width: '100%' }} placeholder="可留空" />
          </Form.Item>

          <Form.Item label="状态" style={{ marginBottom: 0 }}>
            <Space>
              <Form.Item name="is_enabled" valuePropName="checked" noStyle>
                <Switch />
              </Form.Item>
              <span>启用账号</span>
              <Form.Item name="is_default" valuePropName="checked" noStyle>
                <Switch />
              </Form.Item>
              <span>设为默认</span>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default ResourceOpsTransferCenter
*/
