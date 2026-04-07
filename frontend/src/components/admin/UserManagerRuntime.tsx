import { useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  bulkDeleteAccounts,
  bulkRandomCreateAccounts,
  bulkResetAccountPasswords,
  changeAccountPassword,
  createAccount,
  deleteAccount,
  exportAccounts,
  getAccountAvailableRoles,
  getAccounts,
  updateAccount,
  updateAccountRuntimeSettings,
} from '@/api/admin'
import HintTooltip from '@/components/common/HintTooltip'
import type {
  AccountListQuery,
  AccountListResponse,
  AccountRuntimeSettings,
  BulkCreateResponse,
  BulkResetResponse,
  PasswordChange,
  UserCreate,
  UserResponse,
  UserUpdate,
} from '@/types/admin'
import './UserManagerRuntime.css'

const { Text } = Typography

type UserFormValues = {
  username?: string
  password?: string
  name?: string
  email?: string
  role: string
  status: string
  validity_mode: 'permanent' | 'duration' | 'fixed_at'
  validity_unit?: 'day' | 'month' | 'year'
  validity_value?: number
  fixed_expires_at?: Dayjs | null
  session_limit_override?: number | null
}

type BulkFormValues = {
  count: number
  prefix: string
  start_index: number
  role: string
  password_length: number
  validity_mode: 'permanent' | 'duration' | 'fixed_at'
  validity_unit?: 'day' | 'month' | 'year'
  validity_value?: number
  fixed_expires_at?: Dayjs | null
}

const sourceLabels: Record<string, string> = {
  local: '本地',
  admin_bulk: '批量创建',
}

const statusColorMap: Record<string, string> = {
  active: 'success',
  disabled: 'default',
  locked: 'warning',
  expired: 'error',
}

const validityModeLabels: Record<AccountRuntimeSettings['default_account_validity_mode'], string> = {
  permanent: '永久',
  duration: '按时长',
}

const validityUnitLabels: Record<AccountRuntimeSettings['default_account_validity_unit'], string> = {
  day: '天',
  month: '月',
  year: '年',
}

const formatDateTime = (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—')

const formatExpiry = (record: UserResponse) => {
  if (!record.expires_at) {
    return '永久'
  }
  if ((record.remaining_days ?? 0) <= 0) {
    return '已过期'
  }
  return dayjs(record.expires_at).format('YYYY-MM-DD HH:mm')
}

const formatRemaining = (record: UserResponse) => {
  if (!record.expires_at) {
    return '永久'
  }
  if ((record.remaining_days ?? 0) <= 0) {
    return '0 天'
  }
  return `${record.remaining_days} 天`
}

const buildUserPayload = (values: UserFormValues): UserCreate | UserUpdate => ({
  name: values.name?.trim() || '',
  email: values.email?.trim() || '',
  role: values.role,
  status: values.status,
  validity_mode: values.validity_mode,
  validity_unit: values.validity_mode === 'duration' ? values.validity_unit || 'month' : null,
  validity_value: values.validity_mode === 'duration' ? values.validity_value || 1 : null,
  fixed_expires_at:
    values.validity_mode === 'fixed_at' && values.fixed_expires_at
      ? values.fixed_expires_at.toISOString()
      : null,
  session_limit_override: values.session_limit_override || null,
})

const UserManagerRuntime = () => {
  const [data, setData] = useState<AccountListResponse | null>(null)
  const [query, setQuery] = useState<AccountListQuery>({
    page: 1,
    page_size: 20,
    sort_by: 'created_at',
    sort_order: 'desc',
  })
  const [keywordInput, setKeywordInput] = useState('')
  const [roles, setRoles] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsDraft, setSettingsDraft] = useState<AccountRuntimeSettings | null>(null)
  const [settingsDirty, setSettingsDirty] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null)
  const [editingOpen, setEditingOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkResult, setBulkResult] = useState<BulkCreateResponse | null>(null)
  const [resetResult, setResetResult] = useState<BulkResetResponse | null>(null)
  const [passwordTarget, setPasswordTarget] = useState<UserResponse | null>(null)
  const [form] = Form.useForm<UserFormValues>()
  const [passwordForm] = Form.useForm<PasswordChange>()
  const [bulkForm] = Form.useForm<BulkFormValues>()

  const loadRoles = async () => {
    try {
      const result = await getAccountAvailableRoles()
      setRoles(result)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载角色失败')
    }
  }

  const loadAccounts = async (nextQuery: AccountListQuery = query) => {
    setLoading(true)
    try {
      const result = await getAccounts(nextQuery)
      setData(result)
      if (!settingsDirty || settingsDraft === null) {
        setSettingsDraft(result.runtime_settings)
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载账号列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRoles()
  }, [])

  useEffect(() => {
    void loadAccounts()
  }, [query.page, query.page_size, query.keyword, query.role, query.effective_status, query.account_source, query.sort_by, query.sort_order])

  const resetUserForm = (user?: UserResponse | null) => {
    const defaults = settingsDraft
    form.setFieldsValue({
      username: user?.username,
      password: '',
      name: user?.name || '',
      email: user?.email || '',
      role: user?.role || 'user',
      status: user?.status || 'active',
      validity_mode: user?.expires_at ? 'fixed_at' : defaults?.default_account_validity_mode || 'permanent',
      validity_unit: defaults?.default_account_validity_unit || 'month',
      validity_value: defaults?.default_account_validity_value || 1,
      fixed_expires_at: user?.expires_at ? dayjs(user.expires_at) : null,
      session_limit_override: user?.session_limit_override ?? null,
    })
  }

  const settingsSummary = useMemo(() => {
    if (!settingsDraft) {
      return ''
    }
    const sessionSummary = settingsDraft.concurrent_session_limit_enabled
      ? `默认同在线 ${settingsDraft.max_concurrent_sessions_per_account} 台，在线窗口 ${settingsDraft.session_online_window_minutes} 分钟，会话最长 ${settingsDraft.session_absolute_ttl_days} 天`
      : '当前未限制同时在线设备数'
    const validitySummary = settingsDraft.default_account_validity_mode === 'permanent'
      ? '新账号默认永久有效'
      : `新账号默认 ${settingsDraft.default_account_validity_value}${validityUnitLabels[settingsDraft.default_account_validity_unit]}有效`
    const adminSummary = settingsDraft.admin_exempt_from_session_limit ? '管理员豁免' : '管理员计入'
    return `${sessionSummary}，${adminSummary}，${validitySummary}`
  }, [settingsDraft])

  const updateSettingsDraft = <K extends keyof AccountRuntimeSettings>(
    key: K,
    value: AccountRuntimeSettings[K]
  ) => {
    if (!settingsDraft) {
      return
    }
    setSettingsDraft({
      ...settingsDraft,
      [key]: value,
    })
    setSettingsDirty(true)
  }

  const saveSettings = async () => {
    if (!settingsDraft) {
      return
    }
    setSettingsSaving(true)
    try {
      const updated = await updateAccountRuntimeSettings(settingsDraft)
      setSettingsDraft(updated)
      setSettingsDirty(false)
      message.success('账号运行设置已保存')
      await loadAccounts()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存账号运行设置失败')
    } finally {
      setSettingsSaving(false)
    }
  }

  const handleSubmitUser = async (values: UserFormValues) => {
    try {
      const payload = buildUserPayload(values)
      if (editingUser) {
        await updateAccount(editingUser.username, payload)
        message.success('账号已更新')
      } else {
        await createAccount({
          ...(payload as UserCreate),
          username: values.username || '',
          password: values.password || '',
        })
        message.success('账号已创建')
      }
      setEditingOpen(false)
      setEditingUser(null)
      setSelectedRowKeys([])
      await loadAccounts()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存账号失败')
    }
  }

  const handleDelete = async (username: string) => {
    Modal.confirm({
      title: `确认删除 ${username} ?`,
      content: '删除后该账号的本地登录身份和会话都会被清理。',
      okButtonProps: { danger: true },
      async onOk() {
        try {
          await deleteAccount(username)
          message.success('账号已删除')
          await loadAccounts()
        } catch (error: any) {
          message.error(error.response?.data?.detail || '删除账号失败')
        }
      },
    })
  }

  const handleSavePassword = async (values: PasswordChange) => {
    if (!passwordTarget) {
      return
    }
    try {
      await changeAccountPassword(passwordTarget.username, values)
      message.success('密码已重置')
      setPasswordOpen(false)
      setPasswordTarget(null)
      passwordForm.resetFields()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重置密码失败')
    }
  }

  const handleBulkDelete = async () => {
    if (!selectedRowKeys.length) {
      message.info('请先勾选账号')
      return
    }
    Modal.confirm({
      title: '确认批量删除',
      content: `将删除 ${selectedRowKeys.length} 个账号，此操作不可撤销。`,
      okButtonProps: { danger: true },
      async onOk() {
        try {
          const result = await bulkDeleteAccounts({ usernames: selectedRowKeys as string[] })
          message.success(`批量删除完成，成功 ${result.successes.length} 个`)
          setSelectedRowKeys([])
          await loadAccounts()
        } catch (error: any) {
          message.error(error.response?.data?.detail || '批量删除失败')
        }
      },
    })
  }

  const handleBulkReset = async () => {
    if (!selectedRowKeys.length) {
      message.info('请先勾选账号')
      return
    }
    try {
      const result = await bulkResetAccountPasswords({ usernames: selectedRowKeys as string[] })
      setResetResult(result)
      message.success(`批量重置完成，成功 ${result.successes.length} 个`)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '批量重置失败')
    }
  }

  const handleBulkCreate = async (values: BulkFormValues) => {
    try {
      const result = await bulkRandomCreateAccounts({
        count: values.count,
        prefix: values.prefix,
        start_index: values.start_index,
        role: values.role,
        password_length: values.password_length,
        validity_mode: values.validity_mode,
        validity_unit: values.validity_mode === 'duration' ? values.validity_unit || 'month' : null,
        validity_value: values.validity_mode === 'duration' ? values.validity_value || 1 : null,
        fixed_expires_at:
          values.validity_mode === 'fixed_at' && values.fixed_expires_at
            ? values.fixed_expires_at.toISOString()
            : null,
      })
      setBulkResult(result)
      message.success(`批量创建完成，成功 ${result.successes.length} 个`)
      await loadAccounts()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '批量创建失败')
    }
  }

  const handleExport = async () => {
    try {
      const rows = await exportAccounts()
      const headers = [
        'username',
        'name',
        'email',
        'role',
        'effective_status',
        'account_source',
        'expires_at',
        'remaining_days',
        'active_session_count',
        'last_login_at',
        'last_seen_at',
        'created_at',
      ]
      const csv = [
        headers.join(','),
        ...rows.map((row) =>
          headers
            .map((key) => `"${String(((row as unknown as Record<string, unknown>)[key]) ?? '').replace(/"/g, '""')}"`)
            .join(',')
        ),
      ].join('\n')
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'accounts.csv'
      link.click()
      URL.revokeObjectURL(url)
      message.success('已导出账号列表')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '导出失败')
    }
  }

  const columns: TableProps<UserResponse>['columns'] = [
    { title: '用户名', dataIndex: 'username', key: 'username', sorter: true, width: 160 },
    { title: '昵称', dataIndex: 'name', key: 'name', sorter: true, width: 160 },
    {
      title: '来源',
      dataIndex: 'account_source',
      key: 'account_source',
      sorter: true,
      width: 120,
      render: (value) => <Tag>{sourceLabels[String(value)] || value || '未知'}</Tag>,
    },
    { title: '角色', dataIndex: 'role', key: 'role', sorter: true, width: 110 },
    {
      title: '状态',
      dataIndex: 'effective_status',
      key: 'effective_status',
      sorter: true,
      width: 120,
      render: (value) => <Tag color={statusColorMap[String(value)] || 'default'}>{value || 'unknown'}</Tag>,
    },
    { title: '到期时间', key: 'expires_at', sorter: true, width: 160, render: (_, record) => formatExpiry(record) },
    { title: '剩余', key: 'remaining_days', sorter: true, width: 90, render: (_, record) => formatRemaining(record) },
    { title: '在线会话', dataIndex: 'active_session_count', key: 'active_session_count', sorter: true, width: 110 },
    { title: '最近登录', dataIndex: 'last_login_at', key: 'last_login_at', sorter: true, width: 160, render: formatDateTime },
    { title: '最近活跃', dataIndex: 'last_seen_at', key: 'last_seen_at', sorter: true, width: 160, render: formatDateTime },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', sorter: true, width: 160, render: formatDateTime },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingUser(record)
              resetUserForm(record)
              setEditingOpen(true)
            }}
          >
            编辑
          </Button>
          <Button
            type="link"
            icon={<KeyOutlined />}
            onClick={() => {
              setPasswordTarget(record)
              passwordForm.resetFields()
              setPasswordOpen(true)
            }}
          >
            密码
          </Button>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => void handleDelete(record.username)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const handleTableChange: TableProps<UserResponse>['onChange'] = (pagination, _filters, sorter) => {
    const resolvedSorter = Array.isArray(sorter) ? sorter[0] : sorter
    setQuery((current) => ({
      ...current,
      page: pagination.current || 1,
      page_size: pagination.pageSize || current.page_size || 20,
      sort_by: typeof resolvedSorter?.field === 'string' ? resolvedSorter.field : current.sort_by,
      sort_order: resolvedSorter?.order === 'ascend' ? 'asc' : resolvedSorter?.order === 'descend' ? 'desc' : current.sort_order,
    }))
  }

  return (
    <div className="account-manager-page">
      <Card className="account-manager-settings-card" variant="borderless">
        <div className="account-manager-settings-header">
          <div>
            <Text strong>账号策略</Text>
            <div className="account-manager-settings-summary">{settingsSummary}</div>
          </div>
          <Button type="primary" icon={<SaveOutlined />} onClick={() => void saveSettings()} disabled={!settingsDirty} loading={settingsSaving}>
            保存策略
          </Button>
        </div>
        {settingsDraft ? (
          <div className="account-manager-policy-layout">
            <section className="account-manager-policy-section">
              <div className="account-manager-policy-head">
                <div className="account-manager-policy-heading">
                  <div className="account-manager-policy-title-row">
                    <Text strong>同时在线策略</Text>
                    <HintTooltip content="控制普通账号最多保留多少个活跃会话，以及系统按多久的活跃窗口判断设备仍在线。" />
                  </div>
                  <div className="account-manager-policy-copy">
                    {settingsDraft.concurrent_session_limit_enabled
                      ? `当前按照最近 ${settingsDraft.session_online_window_minutes} 分钟活跃记录统计在线设备，超出上限后会回收更早的旧会话。`
                      : '当前不限制普通账号的同时在线设备数，关闭后旧会话不会因为设备超限而被挤掉。'}
                  </div>
                </div>

                <div className="account-manager-policy-switch">
                  <span
                    className={`account-manager-policy-switch-state ${
                      settingsDraft.concurrent_session_limit_enabled ? 'is-active' : 'is-inactive'
                    }`}
                  >
                    {settingsDraft.concurrent_session_limit_enabled ? '已开启' : '已关闭'}
                  </span>
                  <Switch
                    size="small"
                    checked={settingsDraft.concurrent_session_limit_enabled}
                    onChange={(checked) => updateSettingsDraft('concurrent_session_limit_enabled', checked)}
                  />
                </div>
              </div>

              <div className="account-manager-policy-chip-row">
                <span className="account-manager-policy-chip">
                  最多 {settingsDraft.max_concurrent_sessions_per_account} 台
                </span>
                <span className="account-manager-policy-chip">
                  活跃窗口 {settingsDraft.session_online_window_minutes} 分钟
                </span>
                <span className="account-manager-policy-chip">
                  会话最长 {settingsDraft.session_absolute_ttl_days} 天
                </span>
                <span
                  className={`account-manager-policy-chip ${
                    settingsDraft.admin_exempt_from_session_limit ? 'is-accent' : 'is-muted'
                  }`}
                >
                  {settingsDraft.admin_exempt_from_session_limit ? '管理员豁免' : '管理员计入'}
                </span>
              </div>

              {settingsDraft.concurrent_session_limit_enabled ? (
                <div className="account-manager-policy-fields">
                  <div className="account-manager-policy-field">
                    <div className="account-manager-policy-field-label">
                      <span>设备上限</span>
                      <HintTooltip content="每个普通账号允许同时保留的活跃会话数量，超过后会自动淘汰更早的旧会话。" />
                    </div>
                    <div className="account-manager-policy-control">
                      <InputNumber
                        min={1}
                        max={32}
                        value={settingsDraft.max_concurrent_sessions_per_account}
                        onChange={(value) =>
                          updateSettingsDraft('max_concurrent_sessions_per_account', Number(value || 1))
                        }
                        style={{ width: 104 }}
                      />
                      <span className="account-manager-policy-unit">台</span>
                    </div>
                  </div>

                  <div className="account-manager-policy-field">
                    <div className="account-manager-policy-field-label">
                      <span>在线窗口</span>
                      <HintTooltip content="系统按最近多久的活跃记录判断设备仍在线。窗口越短，用户切设备时越容易腾出旧会话。" />
                    </div>
                    <div className="account-manager-policy-control">
                      <InputNumber
                        min={1}
                        max={1440}
                        value={settingsDraft.session_online_window_minutes}
                        onChange={(value) => updateSettingsDraft('session_online_window_minutes', Number(value || 1))}
                        style={{ width: 104 }}
                      />
                      <span className="account-manager-policy-unit">分钟</span>
                    </div>
                  </div>

                  <div className="account-manager-policy-field">
                    <div className="account-manager-policy-field-label">
                      <span>绝对有效期</span>
                      <HintTooltip content="单个登录会话最长可保留多久。即使一直活跃，超过这个时长后也要重新登录。" />
                    </div>
                    <div className="account-manager-policy-control">
                      <InputNumber
                        min={1}
                        max={3650}
                        value={settingsDraft.session_absolute_ttl_days}
                        onChange={(value) => updateSettingsDraft('session_absolute_ttl_days', Number(value || 1))}
                        style={{ width: 104 }}
                      />
                      <span className="account-manager-policy-unit">天</span>
                    </div>
                  </div>

                  <div className="account-manager-policy-field account-manager-policy-field--switch">
                    <div className="account-manager-policy-field-label">
                      <span>管理员豁免</span>
                      <HintTooltip content="开启后管理员账号不受同时在线上限影响；关闭后管理员也会计入限制。" />
                    </div>
                    <div className="account-manager-policy-inline-switch">
                      <Switch
                        size="small"
                        checked={settingsDraft.admin_exempt_from_session_limit}
                        onChange={(checked) => updateSettingsDraft('admin_exempt_from_session_limit', checked)}
                      />
                      <span>{settingsDraft.admin_exempt_from_session_limit ? '不受上限影响' : '和普通账号一致'}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="account-manager-policy-note">
                  关闭后，系统不会因为设备数超限而回收旧会话；如果后续重新开启，将按当前上限和活跃窗口重新计算。
                </div>
              )}
            </section>

            <section className="account-manager-policy-section">
              <div className="account-manager-policy-head">
                <div className="account-manager-policy-heading">
                  <div className="account-manager-policy-title-row">
                    <Text strong>新账号默认有效期</Text>
                    <HintTooltip content="这里控制后台新建账号和批量创建账号时默认带上的有效期策略，单个账号后续仍可单独覆盖。" />
                  </div>
                  <div className="account-manager-policy-copy">
                    {settingsDraft.default_account_validity_mode === 'permanent'
                      ? '当前默认创建长期账号，适合后续人工单独设置到期时间。'
                      : `当前默认按 ${settingsDraft.default_account_validity_value}${validityUnitLabels[settingsDraft.default_account_validity_unit]} 创建新账号，适合批量发放。`}
                  </div>
                </div>
              </div>

              <div className="account-manager-policy-chip-row">
                <span className="account-manager-policy-chip">
                  {validityModeLabels[settingsDraft.default_account_validity_mode]}
                </span>
                {settingsDraft.default_account_validity_mode === 'duration' ? (
                  <span className="account-manager-policy-chip is-accent">
                    默认 {settingsDraft.default_account_validity_value}
                    {validityUnitLabels[settingsDraft.default_account_validity_unit]}
                  </span>
                ) : (
                  <span className="account-manager-policy-chip is-muted">创建后不自动过期</span>
                )}
              </div>

              <div className="account-manager-policy-fields account-manager-policy-fields--compact">
                <div className="account-manager-policy-field">
                  <div className="account-manager-policy-field-label">
                    <span>默认模式</span>
                    <HintTooltip content="永久表示新账号默认没有到期时间；按时长表示创建时自动算出过期时间。" />
                  </div>
                  <Select
                    value={settingsDraft.default_account_validity_mode}
                    onChange={(value) => updateSettingsDraft('default_account_validity_mode', value)}
                    options={[
                      { value: 'permanent', label: '永久' },
                      { value: 'duration', label: '按时长' },
                    ]}
                    style={{ width: 148 }}
                  />
                </div>

                {settingsDraft.default_account_validity_mode === 'duration' ? (
                  <>
                    <div className="account-manager-policy-field">
                      <div className="account-manager-policy-field-label">
                        <span>默认单位</span>
                        <HintTooltip content="决定默认有效期使用天、月还是年作为单位。" />
                      </div>
                      <Select
                        value={settingsDraft.default_account_validity_unit}
                        onChange={(value) => updateSettingsDraft('default_account_validity_unit', value)}
                        options={[
                          { value: 'day', label: '天' },
                          { value: 'month', label: '月' },
                          { value: 'year', label: '年' },
                        ]}
                        style={{ width: 112 }}
                      />
                    </div>

                    <div className="account-manager-policy-field">
                      <div className="account-manager-policy-field-label">
                        <span>默认时长</span>
                        <HintTooltip content="创建账号时默认写入的有效期数值，例如 30 天、1 月、2 年。" />
                      </div>
                      <div className="account-manager-policy-control">
                        <InputNumber
                          min={1}
                          max={3650}
                          value={settingsDraft.default_account_validity_value}
                          onChange={(value) => updateSettingsDraft('default_account_validity_value', Number(value || 1))}
                          style={{ width: 104 }}
                        />
                        <span className="account-manager-policy-unit">
                          {validityUnitLabels[settingsDraft.default_account_validity_unit]}
                        </span>
                      </div>
                    </div>
                  </>
                ) : null}
              </div>

              {settingsDraft.default_account_validity_mode === 'permanent' ? (
                <div className="account-manager-policy-note account-manager-policy-note--inline">
                  如需临时账号，可在新增账号或批量创建时单独指定有效期，不会受这里的永久默认值限制。
                </div>
              ) : null}
            </section>
          </div>
        ) : null}
      </Card>

      <Card className="account-manager-table-card" variant="borderless">
        <div className="account-manager-toolbar">
          <Space wrap>
            <Input.Search placeholder="搜索用户名/昵称/邮箱" value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} onSearch={() => setQuery((current) => ({ ...current, page: 1, keyword: keywordInput.trim() }))} allowClear />
            <Select allowClear placeholder="角色" value={query.role} onChange={(value) => setQuery((current) => ({ ...current, page: 1, role: value || undefined }))} options={[{ value: 'admin', label: '管理员' }, { value: 'user', label: '普通用户' }]} style={{ width: 140 }} />
            <Select allowClear placeholder="状态" value={query.effective_status} onChange={(value) => setQuery((current) => ({ ...current, page: 1, effective_status: value || undefined }))} options={[{ value: 'active', label: '正常' }, { value: 'disabled', label: '禁用' }, { value: 'locked', label: '锁定' }, { value: 'expired', label: '过期' }]} style={{ width: 140 }} />
            <Select allowClear placeholder="来源" value={query.account_source} onChange={(value) => setQuery((current) => ({ ...current, page: 1, account_source: value || undefined }))} options={[{ value: 'local', label: '本地' }, { value: 'admin_bulk', label: '批量创建' }]} style={{ width: 150 }} />
          </Space>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void loadAccounts()} loading={loading}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingUser(null); resetUserForm(null); setEditingOpen(true) }}>新增账号</Button>
            <Button onClick={() => { bulkForm.setFieldsValue({ count: 10, prefix: 'user', start_index: 1, role: 'user', password_length: 12, validity_mode: settingsDraft?.default_account_validity_mode || 'permanent', validity_unit: settingsDraft?.default_account_validity_unit || 'month', validity_value: settingsDraft?.default_account_validity_value || 1, fixed_expires_at: null }); setBulkResult(null); setBulkOpen(true) }}>批量创建</Button>
            <Button onClick={() => void handleBulkReset()} disabled={!selectedRowKeys.length}>批量重置密码</Button>
            <Button danger onClick={() => void handleBulkDelete()} disabled={!selectedRowKeys.length}>批量删除</Button>
            <Button icon={<ExportOutlined />} onClick={() => void handleExport()}>导出</Button>
          </Space>
        </div>

        <Table
          rowKey="username"
          loading={loading}
          columns={columns}
          dataSource={data?.items || []}
          tableLayout="auto"
          scroll={{ x: 'max-content' }}
          rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
          pagination={{ current: data?.page || 1, pageSize: data?.page_size || 20, total: data?.total || 0, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
          onChange={handleTableChange}
        />
      </Card>

      <Modal title={editingUser ? '编辑账号' : '新增账号'} open={editingOpen} onCancel={() => { setEditingOpen(false); setEditingUser(null) }} footer={null} width={720}>
        <Form form={form} layout="vertical" onFinish={handleSubmitUser}>
          {!editingUser ? <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item> : null}
          {!editingUser ? <Form.Item name="password" label="初始密码" rules={[{ required: true }]}><Input.Password /></Form.Item> : null}
          <div className="account-manager-form-grid">
            <Form.Item name="name" label="昵称"><Input /></Form.Item>
            <Form.Item name="email" label="邮箱"><Input /></Form.Item>
            <Form.Item name="role" label="角色" rules={[{ required: true }]}><Select options={Object.entries(roles).map(([value, label]) => ({ value, label }))} /></Form.Item>
            <Form.Item name="status" label="状态" rules={[{ required: true }]}><Select options={[{ value: 'active', label: '正常' }, { value: 'disabled', label: '禁用' }, { value: 'locked', label: '锁定' }]} /></Form.Item>
            <Form.Item name="session_limit_override" label="单账号上限"><InputNumber min={1} max={32} style={{ width: '100%' }} placeholder="留空走系统默认" /></Form.Item>
            <Form.Item name="validity_mode" label="有效期模式" rules={[{ required: true }]}><Select options={[{ value: 'permanent', label: '永久' }, { value: 'duration', label: '按时长' }, { value: 'fixed_at', label: '固定日期' }]} /></Form.Item>
            <Form.Item noStyle shouldUpdate>{({ getFieldValue }) => getFieldValue('validity_mode') === 'duration' ? <><Form.Item name="validity_unit" label="时长单位"><Select options={[{ value: 'day', label: '天' }, { value: 'month', label: '月' }, { value: 'year', label: '年' }]} /></Form.Item><Form.Item name="validity_value" label="时长数值"><InputNumber min={1} max={3650} style={{ width: '100%' }} /></Form.Item></> : null}</Form.Item>
            <Form.Item noStyle shouldUpdate>{({ getFieldValue }) => getFieldValue('validity_mode') === 'fixed_at' ? <Form.Item name="fixed_expires_at" label="到期时间"><DatePicker showTime style={{ width: '100%' }} /></Form.Item> : null}</Form.Item>
          </div>
          <Space><Button type="primary" htmlType="submit">保存</Button><Button onClick={() => setEditingOpen(false)}>取消</Button></Space>
        </Form>
      </Modal>

      <Modal title="重置密码" open={passwordOpen} onCancel={() => setPasswordOpen(false)} footer={null}>
        <Form form={passwordForm} layout="vertical" onFinish={handleSavePassword}>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 6 }]}><Input.Password /></Form.Item>
          <Space><Button type="primary" htmlType="submit">保存</Button><Button onClick={() => setPasswordOpen(false)}>取消</Button></Space>
        </Form>
      </Modal>

      <Modal title="批量创建账号" open={bulkOpen} onCancel={() => setBulkOpen(false)} footer={null} width={720}>
        <Form form={bulkForm} layout="vertical" onFinish={handleBulkCreate}>
          <div className="account-manager-form-grid">
            <Form.Item name="count" label="数量" rules={[{ required: true }]}><InputNumber min={1} max={500} style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="prefix" label="前缀"><Input /></Form.Item>
            <Form.Item name="start_index" label="起始序号"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="password_length" label="密码长度"><InputNumber min={6} max={32} style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="role" label="角色" rules={[{ required: true }]}><Select options={Object.entries(roles).map(([value, label]) => ({ value, label }))} /></Form.Item>
            <Form.Item name="validity_mode" label="有效期模式" rules={[{ required: true }]}><Select options={[{ value: 'permanent', label: '永久' }, { value: 'duration', label: '按时长' }, { value: 'fixed_at', label: '固定日期' }]} /></Form.Item>
            <Form.Item noStyle shouldUpdate>{({ getFieldValue }) => getFieldValue('validity_mode') === 'duration' ? <><Form.Item name="validity_unit" label="时长单位"><Select options={[{ value: 'day', label: '天' }, { value: 'month', label: '月' }, { value: 'year', label: '年' }]} /></Form.Item><Form.Item name="validity_value" label="时长数值"><InputNumber min={1} max={3650} style={{ width: '100%' }} /></Form.Item></> : null}</Form.Item>
            <Form.Item noStyle shouldUpdate>{({ getFieldValue }) => getFieldValue('validity_mode') === 'fixed_at' ? <Form.Item name="fixed_expires_at" label="到期时间"><DatePicker showTime style={{ width: '100%' }} /></Form.Item> : null}</Form.Item>
          </div>
          <Space><Button type="primary" htmlType="submit">开始创建</Button><Button onClick={() => setBulkOpen(false)}>取消</Button></Space>
        </Form>
        {bulkResult ? <pre className="account-manager-result-panel">{bulkResult.successes.map((item) => `${item.username} / ${item.password}`).join('\n')}</pre> : null}
      </Modal>

      <Modal title="批量重置结果" open={!!resetResult} onCancel={() => setResetResult(null)} footer={null}>
        {resetResult ? <pre className="account-manager-result-panel">{resetResult.successes.map((item) => `${item.username} / ${item.password}`).join('\n')}</pre> : null}
      </Modal>
    </div>
  )
}

export default UserManagerRuntime
