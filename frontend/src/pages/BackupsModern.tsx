import { useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  TimePicker,
  Typography,
  message,
} from 'antd'
import type { CollapseProps } from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  FileExcelOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  createBackupTarget,
  deleteBackupTarget,
  getBackupRuns,
  getBackupTargets,
  runBackupTarget,
  testBackupTarget,
  updateBackupTarget,
} from '@/api/backup'
import HintTooltip from '@/components/common/HintTooltip'
import type { BackupRun, BackupTarget, BackupTargetPayload } from '@/types/backup'
import './BackupsModern.css'

const { Text, Title } = Typography

type BackupTargetFormValues = Omit<BackupTargetPayload, 'schedule_hour' | 'schedule_minute'> & {
  schedule_time: Dayjs
}

type QuickTemplate = {
  key: string
  title: string
  description: string
  badge: string
  values: Partial<BackupTargetFormValues>
}

const PROVIDER_OPTIONS = [
  { label: '通用 WebDAV', value: 'generic_webdav' },
  { label: '坚果云', value: 'jianguoyun' },
  { label: 'Nextcloud', value: 'nextcloud' },
  { label: '群晖 NAS', value: 'synology' },
  { label: 'InfiniCLOUD', value: 'infinicloud' },
  { label: 'AList', value: 'alist' },
  { label: 'OpenList', value: 'openlist' },
  { label: 'ownCloud', value: 'owncloud' },
]

const WEEKDAY_OPTIONS = [
  { label: '周一', value: 0 },
  { label: '周二', value: 1 },
  { label: '周三', value: 2 },
  { label: '周四', value: 3 },
  { label: '周五', value: 4 },
  { label: '周六', value: 5 },
  { label: '周日', value: 6 },
]

const createDefaultValues = (): BackupTargetFormValues => ({
  name: '',
  target_kind: 'local',
  provider: 'local',
  is_enabled: true,
  backup_mode: 'full',
  schedule_enabled: false,
  schedule_kind: 'manual',
  schedule_time: dayjs().hour(3).minute(0).second(0),
  schedule_weekday: 0,
  schedule_day: 1,
  timezone: 'Asia/Shanghai',
  retention_count: 10,
  retention_days: 30,
  local_dir: 'data/backups',
  webdav_base_url: '',
  webdav_username: '',
  webdav_password: '',
  clear_webdav_password: false,
  webdav_root_path: '',
  webdav_timeout_seconds: 60,
  webdav_verify_ssl: true,
  include_database: true,
  include_users_json: true,
  include_env_file: false,
  include_runtime_data: true,
  export_range_kind: 'all',
  export_range_days: 30,
})

const QUICK_TEMPLATES: QuickTemplate[] = [
  {
    key: 'local-full',
    title: '本地完整备份',
    description: '适合先把数据库和运行文件沉淀到服务器本地目录。',
    badge: '本地',
    values: {
      target_kind: 'local',
      provider: 'local',
      backup_mode: 'full',
      local_dir: 'data/backups',
      schedule_enabled: false,
      schedule_kind: 'manual',
      include_database: true,
      include_users_json: true,
      include_runtime_data: true,
      include_env_file: false,
    },
  },
  {
    key: 'webdav-full',
    title: 'WebDAV 完整备份',
    description: '适合把完整归档同步到坚果云、NAS 或通用 WebDAV。',
    badge: 'WebDAV',
    values: {
      target_kind: 'webdav',
      provider: 'generic_webdav',
      backup_mode: 'full',
      schedule_enabled: true,
      schedule_kind: 'daily',
      schedule_time: dayjs().hour(3).minute(0).second(0),
      include_database: true,
      include_users_json: true,
      include_runtime_data: true,
      include_env_file: false,
    },
  },
  {
    key: 'webdav-export',
    title: 'WebDAV 影视导出',
    description: '适合定期生成资源 Excel 表格并推到云盘目录。',
    badge: '导出',
    values: {
      target_kind: 'webdav',
      provider: 'generic_webdav',
      backup_mode: 'media_export',
      schedule_enabled: true,
      schedule_kind: 'daily',
      schedule_time: dayjs().hour(6).minute(0).second(0),
      export_range_kind: 'days',
      export_range_days: 30,
    },
  },
]

const createLabel = (title: string, hint: string) => (
  <div className="backup-modern-label">
    <Text strong>{title}</Text>
    <HintTooltip content={hint} />
  </div>
)

const createSectionTitle = (step: string, title: string, hint: string) => (
  <div className="backup-modern-section-heading">
    <div className="backup-modern-section-badge">{step}</div>
    <div className="backup-modern-section-copy">
      <div className="backup-modern-section-title-row">
        <span className="backup-modern-section-title">{title}</span>
        <HintTooltip content={hint} />
      </div>
    </div>
  </div>
)

const formatDateTime = (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '未执行')

const formatFileSize = (value?: number | null) => {
  if (!value || value <= 0) {
    return '-'
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`
}

const formatMode = (value: BackupTarget['backup_mode'] | BackupRun['backup_mode']) =>
  value === 'media_export' ? '影视导出' : '完整备份'

const formatTargetKind = (value: BackupTarget['target_kind'] | BackupRun['target_kind']) =>
  value === 'webdav' ? 'WebDAV' : '本地'

const formatSchedule = (target: BackupTarget) => {
  if (!target.schedule_enabled) {
    return '手动执行'
  }
  const time = `${String(target.schedule_hour).padStart(2, '0')}:${String(target.schedule_minute).padStart(2, '0')}`
  if (target.schedule_kind === 'daily') {
    return `每天 ${time}`
  }
  if (target.schedule_kind === 'weekly') {
    return `${WEEKDAY_OPTIONS.find((item) => item.value === target.schedule_weekday)?.label || '每周'} ${time}`
  }
  if (target.schedule_kind === 'monthly') {
    return `每月 ${target.schedule_day} 日 ${time}`
  }
  return '手动执行'
}

const statusTag = (status?: string | null) => {
  const normalized = (status || '').toLowerCase()
  if (normalized === 'success') return <Tag color="success">成功</Tag>
  if (normalized === 'failed') return <Tag color="error">失败</Tag>
  if (normalized === 'running') return <Tag color="processing">运行中</Tag>
  if (normalized === 'pending') return <Tag color="gold">排队中</Tag>
  return <Tag>{status || '未执行'}</Tag>
}

const toPayload = (values: BackupTargetFormValues): BackupTargetPayload => ({
  ...values,
  schedule_hour: values.schedule_time.hour(),
  schedule_minute: values.schedule_time.minute(),
})

const toFormValues = (target: BackupTarget): BackupTargetFormValues => ({
  name: target.name,
  target_kind: target.target_kind,
  provider: target.provider,
  is_enabled: target.is_enabled,
  backup_mode: target.backup_mode,
  schedule_enabled: target.schedule_enabled,
  schedule_kind: target.schedule_kind,
  schedule_time: dayjs().hour(target.schedule_hour).minute(target.schedule_minute).second(0),
  schedule_weekday: target.schedule_weekday ?? 0,
  schedule_day: target.schedule_day ?? 1,
  timezone: target.timezone,
  retention_count: target.retention_count,
  retention_days: target.retention_days,
  local_dir: target.local_dir,
  webdav_base_url: target.webdav_base_url,
  webdav_username: target.webdav_username,
  webdav_password: '',
  clear_webdav_password: false,
  webdav_root_path: target.webdav_root_path,
  webdav_timeout_seconds: target.webdav_timeout_seconds,
  webdav_verify_ssl: target.webdav_verify_ssl,
  include_database: target.include_database,
  include_users_json: target.include_users_json,
  include_env_file: target.include_env_file,
  include_runtime_data: target.include_runtime_data,
  export_range_kind: target.export_range_kind,
  export_range_days: target.export_range_days ?? 30,
})

const templateMatches = (template: QuickTemplate, values: BackupTargetFormValues) =>
  template.values.target_kind === values.target_kind && template.values.backup_mode === values.backup_mode

const buildSummaryChecks = (values: BackupTargetFormValues) => {
  const issues: string[] = []
  if (!values.name.trim()) {
    issues.push('填写目标名称')
  }
  if (values.target_kind === 'local' && !values.local_dir.trim()) {
    issues.push('填写本地目录')
  }
  if (values.target_kind === 'webdav' && !values.webdav_base_url.trim()) {
    issues.push('填写 WebDAV 地址')
  }
  if (values.backup_mode === 'media_export' && values.export_range_kind === 'days' && !values.export_range_days) {
    issues.push('填写导出天数')
  }
  if (
    values.backup_mode === 'full' &&
    !values.include_database &&
    !values.include_users_json &&
    !values.include_env_file &&
    !values.include_runtime_data
  ) {
    issues.push('至少勾选一项完整备份内容')
  }
  return issues
}

const buildSummaryContent = (values: BackupTargetFormValues) => {
  if (values.backup_mode === 'media_export') {
    return values.export_range_kind === 'days' ? `最近 ${values.export_range_days || '-'} 天影视数据` : '全部影视数据'
  }

  const items: string[] = []
  if (values.include_database) items.push('数据库')
  if (values.include_users_json) items.push('users.json')
  if (values.include_runtime_data) items.push('data/')
  if (values.include_env_file) items.push('.env')
  return items.length > 0 ? items.join(' + ') : '未选择内容'
}

const buildSummarySchedule = (values: BackupTargetFormValues) => {
  if (!values.schedule_enabled) {
    return '手动执行'
  }
  const time = values.schedule_time?.format('HH:mm') || '03:00'
  if (values.schedule_kind === 'daily') {
    return `每天 ${time}`
  }
  if (values.schedule_kind === 'weekly') {
    return `${WEEKDAY_OPTIONS.find((item) => item.value === values.schedule_weekday)?.label || '每周'} ${time}`
  }
  if (values.schedule_kind === 'monthly') {
    return `每月 ${values.schedule_day || 1} 日 ${time}`
  }
  return '手动执行'
}

const buildSummaryDestination = (values: BackupTargetFormValues) => {
  if (values.target_kind === 'local') {
    return values.local_dir.trim() || '待填写'
  }
  const root = values.webdav_root_path.trim() ? ` / ${values.webdav_root_path.trim()}` : ''
  return `${values.webdav_base_url.trim() || '待填写'}${root}`
}

const buildAdvancedConnectionItems = (
  values: BackupTargetFormValues,
  updateValues: (patch: Partial<BackupTargetFormValues>) => void,
): CollapseProps['items'] => [
  {
    key: 'connection-advanced',
    label: (
      <div className="backup-modern-collapse-label">
        <span>高级连接选项</span>
        <HintTooltip content="只收纳低频设置，避免首次配置时被非关键选项打断。" />
      </div>
    ),
    children: (
      <div className="backup-modern-grid backup-modern-grid--two">
        <div className="backup-modern-field-card">
          {createLabel('超时秒数', '上传和目录检查请求的超时时间。')}
          <Form.Item name="webdav_timeout_seconds" noStyle>
            <InputNumber min={5} max={600} style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <div className="backup-modern-toggle-card">
          <div className="backup-modern-toggle-copy">
            {createLabel('校验证书', '公网环境建议开启，自签名证书环境可按需关闭。')}
          </div>
          <Switch checked={values.webdav_verify_ssl} onChange={(checked) => updateValues({ webdav_verify_ssl: checked })} />
        </div>
        <div className="backup-modern-toggle-card backup-modern-toggle-card--wide">
          <div className="backup-modern-toggle-copy">
            {createLabel('清空已存密码', '只在需要移除已保存的 WebDAV 密码时启用。')}
          </div>
          <Switch checked={values.clear_webdav_password} onChange={(checked) => updateValues({ clear_webdav_password: checked })} />
        </div>
      </div>
    ),
  },
]

const buildAdvancedContentItems = (
  values: BackupTargetFormValues,
  updateValues: (patch: Partial<BackupTargetFormValues>) => void,
): CollapseProps['items'] => [
  {
    key: 'content-advanced',
    label: (
      <div className="backup-modern-collapse-label">
        <span>高级内容选项</span>
        <HintTooltip content="低频内容放到折叠区，减少主流程噪音。" />
      </div>
    ),
    children: (
      <div className="backup-modern-toggle-card">
        <div className="backup-modern-toggle-copy">
          {createLabel('.env 文件', '仅在明确需要保留运行环境变量时启用。')}
        </div>
        <Switch checked={values.include_env_file} onChange={(checked) => updateValues({ include_env_file: checked })} />
      </div>
    ),
  },
]

const BackupsModern = () => {
  const [form] = Form.useForm<BackupTargetFormValues>()
  const [targets, setTargets] = useState<BackupTarget[]>([])
  const [runs, setRuns] = useState<BackupRun[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingTarget, setEditingTarget] = useState<BackupTarget | null>(null)
  const [draftValues, setDraftValues] = useState<BackupTargetFormValues>(createDefaultValues())

  const currentValues = useMemo(
    () => ({
      ...createDefaultValues(),
      ...draftValues,
    }),
    [draftValues],
  )

  const hasActiveRuns = useMemo(
    () => targets.some((target) => target.has_active_run) || runs.some((run) => ['pending', 'running'].includes(run.status)),
    [runs, targets],
  )

  const summaryChecks = useMemo(() => buildSummaryChecks(currentValues), [currentValues])
  const activeTemplateKey = useMemo(
    () => QUICK_TEMPLATES.find((item) => templateMatches(item, currentValues))?.key ?? null,
    [currentValues],
  )

  const loadPageData = async (silent = false) => {
    if (!silent) {
      setLoading(true)
    }
    try {
      const [targetList, runList] = await Promise.all([getBackupTargets(), getBackupRuns({ limit: 30 })])
      setTargets(targetList)
      setRuns(runList)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载备份管理失败')
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    void loadPageData()
  }, [])

  useEffect(() => {
    if (!hasActiveRuns) {
      return undefined
    }
    const timer = window.setInterval(() => {
      void loadPageData(true)
    }, 8000)
    return () => window.clearInterval(timer)
  }, [hasActiveRuns])

  const syncDraft = (values: BackupTargetFormValues) => {
    form.setFieldsValue(values)
    setDraftValues(values)
  }

  const updateValues = (patch: Partial<BackupTargetFormValues>) => {
    syncDraft({
      ...currentValues,
      ...patch,
    })
  }

  const openCreateDrawer = () => {
    const defaults = createDefaultValues()
    setEditingTarget(null)
    syncDraft(defaults)
    setDrawerOpen(true)
  }

  const openEditDrawer = (target: BackupTarget) => {
    const values = toFormValues(target)
    setEditingTarget(target)
    syncDraft(values)
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setEditingTarget(null)
    const defaults = createDefaultValues()
    form.resetFields()
    setDraftValues(defaults)
  }

  const applyTemplate = (template: QuickTemplate) => {
    const nextValues: BackupTargetFormValues = {
      ...currentValues,
      ...template.values,
      name: currentValues.name,
      provider:
        template.values.target_kind === 'local'
          ? 'local'
          : currentValues.provider === 'local'
            ? String(template.values.provider || 'generic_webdav')
            : currentValues.provider,
      schedule_kind:
        template.values.schedule_enabled === false
          ? 'manual'
          : (String(template.values.schedule_kind || currentValues.schedule_kind || 'daily') as BackupTargetFormValues['schedule_kind']),
    }
    syncDraft(nextValues)
  }

  const handleTargetKindChange = (targetKind: BackupTargetFormValues['target_kind']) => {
    updateValues({
      target_kind: targetKind,
      provider: targetKind === 'local' ? 'local' : currentValues.provider === 'local' ? 'generic_webdav' : currentValues.provider,
    })
  }

  const handleBackupModeChange = (backupMode: BackupTargetFormValues['backup_mode']) => {
    updateValues({
      backup_mode: backupMode,
      export_range_kind: backupMode === 'media_export' ? currentValues.export_range_kind : 'all',
      export_range_days: backupMode === 'media_export' ? currentValues.export_range_days : null,
    })
  }

  const handleScheduleEnabledChange = (checked: boolean) => {
    updateValues({
      schedule_enabled: checked,
      schedule_kind: checked && currentValues.schedule_kind === 'manual' ? 'daily' : checked ? currentValues.schedule_kind : 'manual',
    })
  }

  const handleSubmit = async () => {
    try {
      await form.validateFields()
      const values = {
        ...createDefaultValues(),
        ...form.getFieldsValue(true),
      } as BackupTargetFormValues
      setSubmitting(true)
      const payload = toPayload(values)
      if (editingTarget) {
        await updateBackupTarget(editingTarget.id, payload)
        message.success('备份目标已更新')
      } else {
        await createBackupTarget(payload)
        message.success('备份目标已创建')
      }
      closeDrawer()
      await loadPageData(true)
    } catch (error: any) {
      if (error?.errorFields) {
        return
      }
      message.error(error.response?.data?.detail || '保存备份目标失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRun = async (target: BackupTarget) => {
    try {
      const result = await runBackupTarget(target.id)
      message.success(result.reused_existing ? '已复用正在运行的任务' : '备份任务已启动')
      await loadPageData(true)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '启动备份失败')
    }
  }

  const handleTest = async (target: BackupTarget) => {
    try {
      const result = await testBackupTarget(target.id)
      message.success(result.message)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '测试连接失败')
    }
  }

  const handleDelete = async (target: BackupTarget) => {
    try {
      await deleteBackupTarget(target.id)
      message.success('备份目标已删除')
      await loadPageData(true)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除备份目标失败')
    }
  }

  const runColumns = [
    {
      title: '目标',
      dataIndex: 'target_name',
      key: 'target_name',
      render: (_: unknown, record: BackupRun) => (
        <div className="backup-modern-run-cell">
          <div className="backup-modern-run-title">{record.target_name}</div>
          <Text type="secondary">
            {formatTargetKind(record.target_kind)} · {formatMode(record.backup_mode)}
          </Text>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => statusTag(value),
    },
    {
      title: '文件',
      dataIndex: 'file_name',
      key: 'file_name',
      render: (_: unknown, record: BackupRun) => (
        <div className="backup-modern-run-cell">
          <div className="backup-modern-run-title">{record.file_name || '-'}</div>
          <Text type="secondary">{formatFileSize(record.file_size_bytes)}</Text>
        </div>
      ),
    },
    {
      title: '时间',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (_: unknown, record: BackupRun) => (
        <div className="backup-modern-run-cell">
          <div className="backup-modern-run-title">{formatDateTime(record.started_at)}</div>
          <Text type="secondary">{record.duration_seconds ? `${record.duration_seconds.toFixed(1)} 秒` : '-'}</Text>
        </div>
      ),
    },
    {
      title: '位置',
      dataIndex: 'local_path',
      key: 'location',
      render: (_: unknown, record: BackupRun) => (
        <div className="backup-modern-run-cell">
          <div className="backup-modern-run-title">{record.local_path || record.remote_path || '-'}</div>
          {record.remote_url ? (
            <a href={record.remote_url} target="_blank" rel="noreferrer">
              远端地址
            </a>
          ) : (
            <Text type="secondary">{record.trigger_source}</Text>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="backup-modern-page">
      <section className="backup-modern-hero">
        <div>
          <Title level={4} className="backup-modern-title">
            备份管理
          </Title>
          <div className="backup-modern-status-row">
            <Tag color={targets.length > 0 ? 'processing' : 'default'}>{targets.length} 个目标</Tag>
            <Tag color={hasActiveRuns ? 'gold' : 'success'}>{hasActiveRuns ? '有任务运行中' : '当前空闲'}</Tag>
          </div>
        </div>
        <div className="backup-modern-actions">
          <Button icon={<ReloadOutlined />} onClick={() => void loadPageData()} loading={loading || submitting}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
            添加目标
          </Button>
        </div>
      </section>

      {targets.length === 0 ? (
        <Card className="backup-modern-empty-card" loading={loading}>
          <Empty description="还没有备份目标">
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
              添加第一个目标
            </Button>
          </Empty>
        </Card>
      ) : (
        <section className="backup-modern-target-grid">
          {targets.map((target) => (
            <Card
              key={target.id}
              className="backup-modern-target-card"
              loading={loading}
              title={
                <div className="backup-modern-target-card-title">
                  <span>{target.name}</span>
                  <Space size={8}>
                    {statusTag(target.active_run_status || target.last_status)}
                    <Tag>{formatTargetKind(target.target_kind)}</Tag>
                    <Tag color="blue">{formatMode(target.backup_mode)}</Tag>
                  </Space>
                </div>
              }
              extra={
                <Space wrap>
                  <Button icon={<PlayCircleOutlined />} size="small" onClick={() => void handleRun(target)} disabled={target.has_active_run}>
                    立即执行
                  </Button>
                  <Button icon={<CheckCircleOutlined />} size="small" onClick={() => void handleTest(target)}>
                    测试
                  </Button>
                  <Button icon={<EditOutlined />} size="small" onClick={() => openEditDrawer(target)}>
                    编辑
                  </Button>
                  <Popconfirm title="确认删除这个备份目标？" onConfirm={() => void handleDelete(target)}>
                    <Button icon={<DeleteOutlined />} size="small" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              }
            >
              <div className="backup-modern-target-meta">
                <div className="backup-modern-target-meta-row">
                  <span className="backup-modern-target-meta-key">
                    <FolderOpenOutlined /> 位置
                  </span>
                  <span className="backup-modern-target-meta-value">
                    {target.target_kind === 'local' ? target.local_dir : target.webdav_root_path || '/'}
                  </span>
                </div>
                <div className="backup-modern-target-meta-row">
                  <span className="backup-modern-target-meta-key">
                    <ClockCircleOutlined /> 计划
                  </span>
                  <span className="backup-modern-target-meta-value">{formatSchedule(target)}</span>
                </div>
                <div className="backup-modern-target-meta-row">
                  <span className="backup-modern-target-meta-key">
                    <CloudUploadOutlined /> 保留
                  </span>
                  <span className="backup-modern-target-meta-value">
                    {target.retention_count > 0 ? `${target.retention_count} 份` : '不限份数'} / {target.retention_days > 0 ? `${target.retention_days} 天` : '不限天数'}
                  </span>
                </div>
                <div className="backup-modern-target-meta-row">
                  <span className="backup-modern-target-meta-key">
                    <LinkOutlined /> 最近
                  </span>
                  <span className="backup-modern-target-meta-value">{formatDateTime(target.last_run_at)}</span>
                </div>
              </div>

              {target.last_error_message ? (
                <Alert className="backup-modern-target-alert" type="error" showIcon message={target.last_error_message} />
              ) : null}
            </Card>
          ))}
        </section>
      )}

      <section className="backup-modern-run-section">
        <Card title="最近运行记录" extra={<Text type="secondary">{runs.length} 条</Text>} loading={loading}>
          <Table
            rowKey="id"
            dataSource={runs}
            columns={runColumns}
            pagination={false}
            locale={{ emptyText: '暂无运行记录' }}
            scroll={{ x: 960 }}
          />
        </Card>
      </section>

      <Drawer
        title={editingTarget ? '编辑备份目标' : '添加备份目标'}
        open={drawerOpen}
        width={1120}
        onClose={closeDrawer}
        destroyOnClose
        className="backup-modern-drawer"
        extra={
          <Space>
            <Button onClick={closeDrawer}>取消</Button>
            <Button type="primary" onClick={() => void handleSubmit()} loading={submitting}>
              保存
            </Button>
          </Space>
        }
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={createDefaultValues()}
          onValuesChange={(_, allValues) => {
            setDraftValues({
              ...createDefaultValues(),
              ...allValues,
            } as BackupTargetFormValues)
          }}
        >
          <div className="backup-modern-editor-layout">
            <div className="backup-modern-editor-main">
              <section className="backup-modern-panel">
                {createSectionTitle('00', editingTarget ? '快速调整' : '快速开始', '先选一个最接近的模板，再补关键字段，能明显减少第一次配置的负担。')}
                <div className="backup-modern-template-grid">
                  {QUICK_TEMPLATES.map((template) => (
                    <button
                      type="button"
                      key={template.key}
                      className={`backup-modern-template-card ${activeTemplateKey === template.key ? 'is-active' : ''}`}
                      onClick={() => applyTemplate(template)}
                    >
                      <span className="backup-modern-template-badge">{template.badge}</span>
                      <span className="backup-modern-template-title">{template.title}</span>
                      <span className="backup-modern-template-description">{template.description}</span>
                    </button>
                  ))}
                </div>
              </section>

              <section className="backup-modern-panel">
                {createSectionTitle('01', '基础方式', '先确定备份放到哪里，以及这条目标是完整备份还是影视导出。')}
                <div className="backup-modern-grid backup-modern-grid--two">
                  <div className="backup-modern-field-card">
                    {createLabel('目标名称', '给这条目标一个清晰名字，后续在列表里能快速定位。')}
                    <Form.Item name="name" rules={[{ required: true, message: '请填写目标名称' }]} noStyle>
                      <Input placeholder="例如：主站 WebDAV 每日完整备份" />
                    </Form.Item>
                  </div>
                  <div className="backup-modern-toggle-card">
                    <div className="backup-modern-toggle-copy">
                      {createLabel('启用目标', '关闭后保留配置，但不会参与自动执行。')}
                    </div>
                    <Switch checked={currentValues.is_enabled} onChange={(checked) => updateValues({ is_enabled: checked })} />
                  </div>
                </div>

                <div className="backup-modern-choice-grid">
                  <button
                    type="button"
                    className={`backup-modern-choice-card ${currentValues.target_kind === 'local' ? 'is-active' : ''}`}
                    onClick={() => handleTargetKindChange('local')}
                  >
                    <FolderOpenOutlined className="backup-modern-choice-icon" />
                    <span className="backup-modern-choice-title">本地目录</span>
                    <span className="backup-modern-choice-description">直接写入服务器目录，适合先快速落地。</span>
                  </button>
                  <button
                    type="button"
                    className={`backup-modern-choice-card ${currentValues.target_kind === 'webdav' ? 'is-active' : ''}`}
                    onClick={() => handleTargetKindChange('webdav')}
                  >
                    <CloudUploadOutlined className="backup-modern-choice-icon" />
                    <span className="backup-modern-choice-title">WebDAV</span>
                    <span className="backup-modern-choice-description">上传到坚果云、NAS 或其他兼容 WebDAV 的远端。</span>
                  </button>
                </div>

                <div className="backup-modern-choice-grid">
                  <button
                    type="button"
                    className={`backup-modern-choice-card ${currentValues.backup_mode === 'full' ? 'is-active' : ''}`}
                    onClick={() => handleBackupModeChange('full')}
                  >
                    <DatabaseOutlined className="backup-modern-choice-icon" />
                    <span className="backup-modern-choice-title">完整备份</span>
                    <span className="backup-modern-choice-description">归档数据库、运行数据和用户文件，适合恢复与保全。</span>
                  </button>
                  <button
                    type="button"
                    className={`backup-modern-choice-card ${currentValues.backup_mode === 'media_export' ? 'is-active' : ''}`}
                    onClick={() => handleBackupModeChange('media_export')}
                  >
                    <FileExcelOutlined className="backup-modern-choice-icon" />
                    <span className="backup-modern-choice-title">影视数据导出</span>
                    <span className="backup-modern-choice-description">生成 Excel，只保留影视名字、描述、标签和网盘链接。</span>
                  </button>
                </div>
              </section>

              <section className="backup-modern-panel">
                {createSectionTitle('02', '连接配置', '只展示当前目标真正需要填写的连接字段，减少无关干扰。')}
                {currentValues.target_kind === 'local' ? (
                  <div className="backup-modern-grid">
                    <div className="backup-modern-field-card">
                      {createLabel('本地目录', '相对路径会以项目根目录为基准，也可以填绝对路径。')}
                      <Form.Item
                        name="local_dir"
                        rules={[{ required: true, message: '请填写本地目录' }]}
                        noStyle
                      >
                        <Input placeholder="data/backups" />
                      </Form.Item>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="backup-modern-grid backup-modern-grid--two">
                      <div className="backup-modern-field-card">
                        {createLabel('WebDAV 预设', '只是用于识别来源，底层仍按通用 WebDAV 协议执行。')}
                        <Form.Item name="provider" noStyle>
                          <Select options={PROVIDER_OPTIONS} />
                        </Form.Item>
                      </div>
                      <div className="backup-modern-field-card">
                        {createLabel('远端子目录', '可选，保存后会自动递归创建。')}
                        <Form.Item name="webdav_root_path" noStyle>
                          <Input placeholder="tg-monitor/backups" />
                        </Form.Item>
                      </div>
                      <div className="backup-modern-field-card backup-modern-field-card--wide">
                        {createLabel('WebDAV 地址', '填写到目标目录的基础地址，例如 https://dav.example.com/remote.php/dav/files/name。')}
                        <Form.Item
                          name="webdav_base_url"
                          rules={[{ required: true, message: '请填写 WebDAV 地址' }]}
                          noStyle
                        >
                          <Input placeholder="https://dav.example.com/path" />
                        </Form.Item>
                      </div>
                      <div className="backup-modern-field-card">
                        {createLabel('用户名', '用于 Basic Auth；匿名 WebDAV 可留空。')}
                        <Form.Item name="webdav_username" noStyle>
                          <Input placeholder="username" />
                        </Form.Item>
                      </div>
                      <div className="backup-modern-field-card">
                        {createLabel(
                          editingTarget?.webdav_password_configured ? '密码（留空保持不变）' : '密码',
                          '保存后会以加密形式写入数据库；编辑时留空表示保持当前密码。'
                        )}
                        <Form.Item name="webdav_password" noStyle>
                          <Input.Password placeholder={editingTarget?.webdav_password_configured ? '留空保持原密码' : 'password'} />
                        </Form.Item>
                      </div>
                    </div>
                    <Collapse ghost items={buildAdvancedConnectionItems(currentValues, updateValues)} />
                  </>
                )}
              </section>

              <section className="backup-modern-panel">
                {createSectionTitle('03', '备份内容', '只保留与你当前模式相关的内容项，没有关联的字段不再同时出现。')}
                {currentValues.backup_mode === 'full' ? (
                  <>
                    <div className="backup-modern-toggle-grid">
                      <div className="backup-modern-toggle-card">
                        <div className="backup-modern-toggle-copy">
                          {createLabel('数据库', '导出 PostgreSQL SQL 文件，需要运行环境可调用 pg_dump。')}
                        </div>
                        <Switch checked={currentValues.include_database} onChange={(checked) => updateValues({ include_database: checked })} />
                      </div>
                      <div className="backup-modern-toggle-card">
                        <div className="backup-modern-toggle-copy">
                          {createLabel('users.json', '包含后台用户文件。')}
                        </div>
                        <Switch checked={currentValues.include_users_json} onChange={(checked) => updateValues({ include_users_json: checked })} />
                      </div>
                      <div className="backup-modern-toggle-card backup-modern-toggle-card--wide">
                        <div className="backup-modern-toggle-copy">
                          {createLabel('data/ 运行目录', '包含运行数据，默认会排除 data/backups，避免备份套备份。')}
                        </div>
                        <Switch checked={currentValues.include_runtime_data} onChange={(checked) => updateValues({ include_runtime_data: checked })} />
                      </div>
                    </div>
                    <Collapse ghost items={buildAdvancedContentItems(currentValues, updateValues)} />
                  </>
                ) : (
                  <div className="backup-modern-grid backup-modern-grid--two">
                    <div className="backup-modern-field-card">
                      {createLabel('导出范围', '支持全部导出，或只导出最近 N 天的数据。')}
                      <Form.Item name="export_range_kind" noStyle>
                        <Select
                          onChange={(value) =>
                            updateValues({
                              export_range_kind: value,
                            })
                          }
                          options={[
                            { label: '全部数据', value: 'all' },
                            { label: '最近 N 天', value: 'days' },
                          ]}
                        />
                      </Form.Item>
                    </div>
                    {currentValues.export_range_kind === 'days' ? (
                      <div className="backup-modern-field-card">
                        {createLabel('最近天数', '仅导出该时间范围内的影视数据。')}
                        <Form.Item
                          name="export_range_days"
                          rules={[{ required: true, message: '请填写导出天数' }]}
                          noStyle
                        >
                          <InputNumber min={1} max={3650} style={{ width: '100%' }} />
                        </Form.Item>
                      </div>
                    ) : null}
                  </div>
                )}
              </section>

              <section className="backup-modern-panel">
                {createSectionTitle('04', '执行与保留', '先决定是否自动执行，再补时间与保留策略，形成完整闭环。')}
                <div className="backup-modern-toggle-card backup-modern-toggle-card--wide">
                  <div className="backup-modern-toggle-copy">
                    {createLabel('自动计划', '打开后由 tg-api 进程内的调度线程按计划执行。')}
                  </div>
                  <Switch checked={currentValues.schedule_enabled} onChange={handleScheduleEnabledChange} />
                </div>

                {currentValues.schedule_enabled ? (
                  <div className="backup-modern-grid backup-modern-grid--three">
                    <div className="backup-modern-field-card">
                      {createLabel('频率', '支持每天、每周、每月三种自动计划。')}
                      <Form.Item name="schedule_kind" noStyle>
                        <Select
                          onChange={(value) => updateValues({ schedule_kind: value })}
                          options={[
                            { label: '每天', value: 'daily' },
                            { label: '每周', value: 'weekly' },
                            { label: '每月', value: 'monthly' },
                          ]}
                        />
                      </Form.Item>
                    </div>
                    <div className="backup-modern-field-card">
                      {createLabel('执行时间', '按 24 小时制设置。')}
                      <Form.Item name="schedule_time" noStyle>
                        <TimePicker
                          format="HH:mm"
                          minuteStep={5}
                          style={{ width: '100%' }}
                          onChange={(value) => {
                            if (value) {
                              updateValues({ schedule_time: value })
                            }
                          }}
                        />
                      </Form.Item>
                    </div>
                    {currentValues.schedule_kind === 'weekly' ? (
                      <div className="backup-modern-field-card">
                        {createLabel('星期', '每周计划执行的星期。')}
                        <Form.Item name="schedule_weekday" noStyle>
                          <Select onChange={(value) => updateValues({ schedule_weekday: value })} options={WEEKDAY_OPTIONS} />
                        </Form.Item>
                      </div>
                    ) : null}
                    {currentValues.schedule_kind === 'monthly' ? (
                      <div className="backup-modern-field-card">
                        {createLabel('日期', '每月计划执行的日期。')}
                        <Form.Item name="schedule_day" noStyle>
                          <InputNumber
                            min={1}
                            max={31}
                            style={{ width: '100%' }}
                            onChange={(value) => updateValues({ schedule_day: Number(value || 1) })}
                          />
                        </Form.Item>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <div className="backup-modern-grid backup-modern-grid--two">
                  <div className="backup-modern-field-card">
                    {createLabel('保留份数', '超过该份数的历史备份会自动清理；填 0 表示不限份数。')}
                    <Form.Item name="retention_count" noStyle>
                      <InputNumber min={0} max={3650} style={{ width: '100%' }} />
                    </Form.Item>
                  </div>
                  <div className="backup-modern-field-card">
                    {createLabel('保留天数', '超过该天数的历史备份会自动清理；填 0 表示不限天数。')}
                    <Form.Item name="retention_days" noStyle>
                      <InputNumber min={0} max={3650} style={{ width: '100%' }} />
                    </Form.Item>
                  </div>
                </div>
              </section>
            </div>

            <aside className="backup-modern-editor-aside">
              <Card className="backup-modern-summary-card">
                <div className="backup-modern-summary-top">
                  <div className="backup-modern-summary-title">当前方案</div>
                  <div className="backup-modern-summary-tags">
                    <Tag>{formatTargetKind(currentValues.target_kind)}</Tag>
                    <Tag color="blue">{formatMode(currentValues.backup_mode)}</Tag>
                    <Tag color={currentValues.schedule_enabled ? 'processing' : 'default'}>
                      {currentValues.schedule_enabled ? '自动' : '手动'}
                    </Tag>
                  </div>
                </div>

                <div className="backup-modern-summary-name">{currentValues.name.trim() || '未命名备份目标'}</div>

                <div className="backup-modern-summary-list">
                  <div className="backup-modern-summary-row">
                    <span>目标位置</span>
                    <strong>{buildSummaryDestination(currentValues)}</strong>
                  </div>
                  <div className="backup-modern-summary-row">
                    <span>备份内容</span>
                    <strong>{buildSummaryContent(currentValues)}</strong>
                  </div>
                  <div className="backup-modern-summary-row">
                    <span>执行方式</span>
                    <strong>{buildSummarySchedule(currentValues)}</strong>
                  </div>
                  <div className="backup-modern-summary-row">
                    <span>保留策略</span>
                    <strong>
                      {currentValues.retention_count > 0 ? `${currentValues.retention_count} 份` : '不限份数'} / {currentValues.retention_days > 0 ? `${currentValues.retention_days} 天` : '不限天数'}
                    </strong>
                  </div>
                </div>

                {summaryChecks.length === 0 ? (
                  <Alert
                    type="success"
                    showIcon
                    className="backup-modern-summary-alert"
                    message="配置结构已完整"
                    description="现在可以直接保存，保存后就能从目标卡片发起测试或手动执行。"
                  />
                ) : (
                  <Alert
                    type="warning"
                    showIcon
                    className="backup-modern-summary-alert"
                    message="还差几步"
                    description={summaryChecks.join('、')}
                  />
                )}

                <div className="backup-modern-summary-tips">
                  <div className="backup-modern-summary-tip">
                    <ThunderboltOutlined />
                    <span>先决定方式，再填连接，再选内容，最后设计划。</span>
                  </div>
                  <div className="backup-modern-summary-tip">
                    <SafetyCertificateOutlined />
                    <span>低频选项已经收进高级面板，主路径会保持干净。</span>
                  </div>
                  <div className="backup-modern-summary-tip">
                    <ExportOutlined />
                    <span>影视导出文件不会带 `tg-export` 前缀。</span>
                  </div>
                </div>
              </Card>
            </aside>
          </div>
        </Form>
      </Drawer>
    </div>
  )
}

export default BackupsModern
