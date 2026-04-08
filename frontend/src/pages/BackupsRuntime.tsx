import { useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  TimePicker,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  FileExcelOutlined,
  FolderOpenOutlined,
  InboxOutlined,
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
  deleteBackupTargetRemoteFile,
  getBackupTargetRemoteFiles,
  getBackupTargets,
  runBackupTarget,
  testBackupTarget,
  updateBackupTarget,
} from '@/api/backup'
import HintTooltip from '@/components/common/HintTooltip'
import type { BackupRemoteFile, BackupTarget, BackupTargetPayload } from '@/types/backup'
import './BackupsRuntime.css'

const { Text, Title } = Typography

type FormValues = Omit<BackupTargetPayload, 'schedule_hour' | 'schedule_minute'> & { schedule_time: Dayjs }

const weekdays = [
  { label: '周一', value: 0 },
  { label: '周二', value: 1 },
  { label: '周三', value: 2 },
  { label: '周四', value: 3 },
  { label: '周五', value: 4 },
  { label: '周六', value: 5 },
  { label: '周日', value: 6 },
]

const defaults = (): FormValues => ({
  name: '',
  target_kind: 'local',
  provider: 'local',
  is_enabled: true,
  backup_mode: 'full',
  schedule_enabled: false,
  schedule_kind: 'manual',
  schedule_time: dayjs().hour(3).minute(0).second(0),
  schedule_priority: 100,
  schedule_weekday: 0,
  schedule_day: 1,
  timezone: 'Asia/Shanghai',
  retention_count: 10,
  local_dir: 'data/backups',
  webdav_base_url: '',
  webdav_username: '',
  webdav_password: '',
  clear_webdav_password: false,
  webdav_root_path: '',
  webdav_timeout_seconds: 60,
  webdav_verify_ssl: true,
  include_env_file: false,
  include_runtime_data: true,
  export_range_kind: 'days',
  export_range_days: 7,
})

const label = (title: string, hint: string) => (
  <div className="backup-runtime-label">
    <Text strong>{title}</Text>
    <HintTooltip content={hint} />
  </div>
)

const ellipsis = (text?: string | null, className?: string) => {
  const value = text?.trim() || '-'
  return (
    <Tooltip title={value}>
      <span className={`backup-runtime-ellipsis ${className || ''}`}>{value}</span>
    </Tooltip>
  )
}

const parseBackendDateTime = (value?: string | null) => {
  const normalized = value?.trim()
  if (!normalized) {
    return null
  }

  const hasTimezoneSuffix = /([zZ]|[+-]\d{2}:\d{2})$/.test(normalized)
  const parsed = dayjs(hasTimezoneSuffix ? normalized : `${normalized}Z`)
  return parsed.isValid() ? parsed : null
}

const fmtTime = (value?: string | null) => {
  const parsed = parseBackendDateTime(value)
  return parsed ? parsed.format('YYYY-MM-DD HH:mm:ss') : '-'
}
const fmtMode = (value?: string | null) => (value === 'media_export' ? '影视导出' : '完整备份')
const fmtKind = (value: BackupTarget['target_kind']) => (value === 'webdav' ? 'WebDAV' : '本地目录')
const fmtSize = (value?: number | null) => {
  if (!value || value <= 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 2)} ${units[index]}`
}

const fmtSchedule = (values: {
  schedule_enabled: boolean
  schedule_kind: string
  schedule_hour: number
  schedule_minute: number
  schedule_weekday?: number | null
  schedule_day?: number | null
  schedule_priority: number
}) => {
  if (!values.schedule_enabled) return '手动执行'
  const time = `${String(values.schedule_hour).padStart(2, '0')}:${String(values.schedule_minute).padStart(2, '0')}`
  let text = `每天 ${time}`
  if (values.schedule_kind === 'weekly') text = `${weekdays.find((item) => item.value === values.schedule_weekday)?.label || '每周'} ${time}`
  if (values.schedule_kind === 'monthly') text = `每月 ${values.schedule_day || 1} 日 ${time}`
  return `${text} · 顺位 ${values.schedule_priority}`
}

const toPayload = (values: FormValues): BackupTargetPayload => ({
  ...values,
  provider: values.target_kind === 'local' ? 'local' : values.provider === 'local' ? 'generic_webdav' : values.provider,
  schedule_hour: values.schedule_time.hour(),
  schedule_minute: values.schedule_time.minute(),
})

const toFormValues = (target: BackupTarget): FormValues => ({
  ...defaults(),
  ...target,
  schedule_time: dayjs().hour(target.schedule_hour).minute(target.schedule_minute).second(0),
  webdav_password: '',
  clear_webdav_password: false,
})

const buildContent = (values: Pick<FormValues, 'backup_mode' | 'export_range_kind' | 'export_range_days' | 'include_runtime_data' | 'include_env_file'>) => {
  if (values.backup_mode === 'media_export') return values.export_range_kind === 'days' ? `最近 ${values.export_range_days || '-'} 天影视数据` : '全部影视数据'
  return ['数据库快照', values.include_runtime_data ? '站点运行数据' : '', values.include_env_file ? '.env' : ''].filter(Boolean).join(' + ')
}

const buildTargetContent = (target: BackupTarget) =>
  buildContent({
    backup_mode: target.backup_mode,
    export_range_kind: target.export_range_kind,
    export_range_days: target.export_range_days,
    include_runtime_data: target.include_runtime_data,
    include_env_file: target.include_env_file,
  })

const issues = (values: FormValues) => {
  const list: string[] = []
  if (!values.name.trim()) list.push('填写目标名称')
  if (values.target_kind === 'local' && !values.local_dir.trim()) list.push('填写本地目录')
  if (values.target_kind === 'webdav' && !values.webdav_base_url.trim()) list.push('填写 WebDAV 地址')
  if (values.backup_mode === 'media_export' && values.export_range_kind === 'days' && !values.export_range_days) list.push('填写导出天数')
  return list
}

const statusTag = (status?: string | null) => {
  const value = (status || '').toLowerCase()
  if (value === 'success') return <Tag color="success">成功</Tag>
  if (value === 'failed') return <Tag color="error">失败</Tag>
  if (value === 'running') return <Tag color="processing">运行中</Tag>
  if (value === 'pending') return <Tag color="gold">排队中</Tag>
  return <Tag>{status || '未执行'}</Tag>
}

export default function BackupsRuntime() {
  const [form] = Form.useForm<FormValues>()
  const [draftValues, setDraftValues] = useState<FormValues>(defaults())
  const current = useMemo(() => draftValues, [draftValues])
  const [targets, setTargets] = useState<BackupTarget[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [editing, setEditing] = useState<BackupTarget | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [runningId, setRunningId] = useState<number | null>(null)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [remoteTarget, setRemoteTarget] = useState<BackupTarget | null>(null)
  const [remoteFiles, setRemoteFiles] = useState<BackupRemoteFile[]>([])
  const [remoteLoading, setRemoteLoading] = useState(false)
  const [deletingRemote, setDeletingRemote] = useState<string | null>(null)

  const hasActive = useMemo(
    () => targets.some((item) => ['pending', 'running'].includes((item.active_run_status || '').toLowerCase())),
    [targets],
  )
  const checkIssues = useMemo(() => issues(current), [current])

  const syncValues = (values: FormValues) => {
    setDraftValues(values)
    form.setFieldsValue(values)
  }

  const setValues = (patch: Partial<FormValues>) => {
    syncValues({
      ...current,
      ...patch,
    })
  }

  const loadTargets = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setTargets(await getBackupTargets())
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载备份目标失败')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const loadRemoteFiles = async (target: BackupTarget, silent = false) => {
    if (!silent) setRemoteLoading(true)
    try {
      setRemoteFiles(await getBackupTargetRemoteFiles(target.id))
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载远端文件失败')
    } finally {
      if (!silent) setRemoteLoading(false)
    }
  }

  useEffect(() => { void loadTargets() }, [])
  useEffect(() => {
    if (!hasActive) return undefined
    const timer = window.setInterval(() => void loadTargets(true), 8000)
    return () => window.clearInterval(timer)
  }, [hasActive])

  const openCreate = () => {
    setEditing(null)
    const nextValues = defaults()
    form.resetFields()
    syncValues(nextValues)
    setDrawerOpen(true)
  }

  const openEdit = (target: BackupTarget) => {
    setEditing(target)
    const nextValues = toFormValues(target)
    form.resetFields()
    syncValues(nextValues)
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setEditing(null)
    const nextValues = defaults()
    form.resetFields()
    syncValues(nextValues)
  }

  const save = async () => {
    try {
      await form.validateFields()
      const values = { ...defaults(), ...current, ...form.getFieldsValue(true) } as FormValues
      setSubmitting(true)
      if (editing) {
        await updateBackupTarget(editing.id, toPayload(values))
        message.success('备份目标已更新')
      } else {
        await createBackupTarget(toPayload(values))
        message.success('备份目标已创建')
      }
      closeDrawer()
      await loadTargets(true)
    } catch (error: any) {
      if (!error?.errorFields) message.error(error.response?.data?.detail || '保存备份目标失败')
    } finally {
      setSubmitting(false)
    }
  }

  const run = async (target: BackupTarget) => {
    setRunningId(target.id)
    try {
      const result = await runBackupTarget(target.id)
      message[result.reused_existing ? 'info' : 'success'](result.reused_existing ? '该目标已有排队或运行任务，已复用' : '已加入备份队列')
      await loadTargets(true)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '启动备份失败')
    } finally {
      setRunningId(null)
    }
  }

  const test = async (target: BackupTarget) => {
    setTestingId(target.id)
    try {
      const result = await testBackupTarget(target.id)
      message.success(result.message)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '测试连接失败')
    } finally {
      setTestingId(null)
    }
  }

  const remove = async (target: BackupTarget) => {
    try {
      await deleteBackupTarget(target.id)
      message.success('备份目标已删除')
      await loadTargets(true)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除备份目标失败')
    }
  }

  const remoteColumns: TableProps<BackupRemoteFile>['columns'] = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      width: '48%',
      render: (_value, record) => (
        <div className="backup-runtime-file-cell">
          {ellipsis(record.name, 'backup-runtime-file-name')}
          <div className="backup-runtime-file-tags">
            {record.backup_mode ? <Tag>{fmtMode(record.backup_mode)}</Tag> : null}
            {record.range_label ? <Tag color="blue">{record.range_label}</Tag> : null}
            {record.file_format ? <Tag>{record.file_format.toUpperCase()}</Tag> : null}
          </div>
        </div>
      ),
    },
    {
      title: '备份时间',
      dataIndex: 'backup_time',
      key: 'backup_time',
      width: 220,
      render: (_value, record) => (
        <div className="backup-runtime-file-time">
          <span>{fmtTime(record.backup_time || record.modified_at)}</span>
          {record.backup_time && record.modified_at && record.backup_time !== record.modified_at ? <Text type="secondary">文件修改: {fmtTime(record.modified_at)}</Text> : null}
        </div>
      ),
    },
    { title: '大小', dataIndex: 'size_bytes', key: 'size_bytes', width: 140, align: 'right', render: (value) => fmtSize(value) },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      align: 'right',
      render: (_value, record) => (
        <Popconfirm title="确认删除这个远端文件？" onConfirm={() => void (async () => {
          if (!remoteTarget) return
          setDeletingRemote(record.remote_path)
          try {
            await deleteBackupTargetRemoteFile(remoteTarget.id, record.remote_path)
            message.success('远端文件已删除')
            await loadRemoteFiles(remoteTarget, true)
          } catch (error: any) {
            message.error(error.response?.data?.detail || '删除远端文件失败')
          } finally {
            setDeletingRemote(null)
          }
        })()}>
          <Button type="link" danger loading={deletingRemote === record.remote_path}>删除</Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="backup-runtime-page">
      <Card className="backup-runtime-hero-card" variant="outlined">
        <div className="backup-runtime-hero">
          <div className="backup-runtime-hero-copy">
            <Title level={3} className="backup-runtime-page-title">备份管理</Title>
            <p className="backup-runtime-hero-subtitle">统一管理本地与 WebDAV 目标。自动计划会按执行顺位串行排队，避免多个目标同时抢传输带宽。</p>
            <div className="backup-runtime-tag-row">
              <Tag color={targets.length ? 'processing' : 'default'}>{targets.length} 个目标</Tag>
              <Tag color={targets.filter((item) => item.is_enabled).length ? 'blue' : 'default'}>{targets.filter((item) => item.is_enabled).length} 个启用中</Tag>
              <Tag color={targets.filter((item) => item.schedule_enabled && item.is_enabled).length ? 'cyan' : 'default'}>{targets.filter((item) => item.schedule_enabled && item.is_enabled).length} 个自动计划</Tag>
              <Tag color={hasActive ? 'gold' : 'success'}>{hasActive ? '有任务排队或运行中' : '当前空闲'}</Tag>
            </div>
          </div>
          <div className="backup-runtime-hero-actions">
            <Button icon={<ReloadOutlined />} onClick={() => void loadTargets()} loading={loading || submitting}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加目标</Button>
          </div>
        </div>
      </Card>

      {targets.length === 0 ? (
        <Card className="backup-runtime-empty-card" loading={loading} variant="outlined">
          <Empty description="还没有备份目标">
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加第一个目标</Button>
          </Empty>
        </Card>
      ) : (
        <section className="backup-runtime-target-grid">
          {targets.map((target) => (
            <Card
              key={target.id}
              className="backup-runtime-target-card"
              loading={loading}
              variant="outlined"
              title={<div className="backup-runtime-target-title">{ellipsis(target.name, 'backup-runtime-target-name')}<div className="backup-runtime-tag-row">{statusTag(target.active_run_status || target.last_status)}<Tag>{fmtKind(target.target_kind)}</Tag><Tag color="blue">{fmtMode(target.backup_mode)}</Tag></div></div>}
              extra={<div className="backup-runtime-target-actions">
                <Button size="small" icon={<PlayCircleOutlined />} loading={runningId === target.id} onClick={() => void run(target)} disabled={target.has_active_run}>立即执行</Button>
                <Button size="small" icon={<CheckCircleOutlined />} loading={testingId === target.id} onClick={() => void test(target)}>测试连接</Button>
                {target.target_kind === 'webdav' ? <Button size="small" icon={<LinkOutlined />} onClick={() => void (setRemoteTarget(target), loadRemoteFiles(target))}>远端文件</Button> : null}
                <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(target)}>编辑</Button>
                <Popconfirm title="确认删除这个备份目标？" onConfirm={() => void remove(target)}><Button size="small" icon={<DeleteOutlined />} danger>删除</Button></Popconfirm>
              </div>}
            >
              <div className="backup-runtime-target-meta">
                <div className="backup-runtime-target-meta-row"><span className="backup-runtime-target-meta-key"><FolderOpenOutlined />位置</span><div className="backup-runtime-target-meta-value">{ellipsis(target.target_kind === 'local' ? target.local_dir : `${target.webdav_base_url}${target.webdav_root_path ? ` / ${target.webdav_root_path}` : ''}`)}</div></div>
                <div className="backup-runtime-target-meta-row"><span className="backup-runtime-target-meta-key"><DatabaseOutlined />内容</span><div className="backup-runtime-target-meta-value">{ellipsis(buildTargetContent(target))}</div></div>
                <div className="backup-runtime-target-meta-row"><span className="backup-runtime-target-meta-key"><ClockCircleOutlined />计划</span><div className="backup-runtime-target-meta-value">{ellipsis(fmtSchedule(target))}</div></div>
                <div className="backup-runtime-target-meta-row"><span className="backup-runtime-target-meta-key"><SafetyCertificateOutlined />保留</span><div className="backup-runtime-target-meta-value">{target.retention_count > 0 ? `最多 ${target.retention_count} 份` : '不限份数'}</div></div>
                <div className="backup-runtime-target-meta-row"><span className="backup-runtime-target-meta-key"><InboxOutlined />最近备份</span><div className="backup-runtime-target-meta-value">{fmtTime(target.last_run_at)}</div></div>
              </div>
              {target.last_error_message ? <Alert className="backup-runtime-inline-alert" type="error" showIcon message={target.last_error_message} /> : null}
            </Card>
          ))}
        </section>
      )}

      <Drawer
        title={editing ? '编辑备份目标' : '添加备份目标'}
        open={drawerOpen}
        width={1120}
        onClose={closeDrawer}
        destroyOnClose
        className="backup-runtime-drawer"
        extra={<Space>{editing && current.target_kind === 'webdav' ? <Button icon={<CheckCircleOutlined />} loading={testingId === editing.id} onClick={() => void test(editing)}>测试连接</Button> : null}<Button onClick={closeDrawer}>取消</Button><Button type="primary" loading={submitting} onClick={() => void save()}>保存</Button></Space>}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={defaults()}
          onValuesChange={(_, allValues) => {
            setDraftValues((previous) => ({
              ...previous,
              ...(allValues as Partial<FormValues>),
            }))
          }}
        >
          <div className="backup-runtime-editor-layout">
            <div className="backup-runtime-editor-main">
              <section className="backup-runtime-panel">
                <div className="backup-runtime-section-head">{label('基础方案', '先定位置和数据，再补连接与执行计划，整条配置路径更顺。')}</div>
                <div className="backup-runtime-grid backup-runtime-grid--two">
                  <div className="backup-runtime-field-card">{label('目标名称', '给目标起一个好识别的名字。')}<Form.Item name="name" rules={[{ required: true, message: '请填写目标名称' }]} noStyle><Input placeholder="例如：主站 WebDAV 每日完整备份" /></Form.Item></div>
                  <div className="backup-runtime-switch-card"><div className="backup-runtime-switch-copy">{label('启用目标', '关闭后保留配置，但不会参与自动计划。')}</div><Switch checked={current.is_enabled} onChange={(checked) => setValues({ is_enabled: checked })} /></div>
                </div>
                <div className="backup-runtime-choice-grid">
                  <button type="button" className={`backup-runtime-choice-card ${current.target_kind === 'local' ? 'is-active' : ''}`} onClick={() => setValues({ target_kind: 'local', provider: 'local' })}><FolderOpenOutlined className="backup-runtime-choice-icon" /><span className="backup-runtime-choice-title">本地目录</span><span className="backup-runtime-choice-description">直接写入服务器目录，适合快速落盘。</span></button>
                  <button type="button" className={`backup-runtime-choice-card ${current.target_kind === 'webdav' ? 'is-active' : ''}`} onClick={() => setValues({ target_kind: 'webdav', provider: current.provider === 'local' ? 'generic_webdav' : current.provider })}><CloudUploadOutlined className="backup-runtime-choice-icon" /><span className="backup-runtime-choice-title">WebDAV</span><span className="backup-runtime-choice-description">上传到 NAS、坚果云或其他兼容 WebDAV 的远端。</span></button>
                  <button type="button" className={`backup-runtime-choice-card ${current.backup_mode === 'full' ? 'is-active' : ''}`} onClick={() => setValues({ backup_mode: 'full' })}><DatabaseOutlined className="backup-runtime-choice-icon" /><span className="backup-runtime-choice-title">完整备份</span><span className="backup-runtime-choice-description">固定包含数据库快照，可附带运行数据和 .env。</span></button>
                  <button type="button" className={`backup-runtime-choice-card ${current.backup_mode === 'media_export' ? 'is-active' : ''}`} onClick={() => setValues({ backup_mode: 'media_export', export_range_days: current.export_range_days || 7 })}><FileExcelOutlined className="backup-runtime-choice-icon" /><span className="backup-runtime-choice-title">影视数据导出</span><span className="backup-runtime-choice-description">导出 Excel，只保留影视信息和网盘链接。</span></button>
                </div>
              </section>

              <section className="backup-runtime-panel">
                <div className="backup-runtime-section-head">{label('连接配置', '目录只会在测试连接或实际备份时创建，保存配置本身不会建目录。')}</div>
                {current.target_kind === 'local' ? (
                  <div className="backup-runtime-field-card">{label('本地目录', '支持相对路径和绝对路径。')}<Form.Item name="local_dir" rules={[{ required: true, message: '请填写本地目录' }]} noStyle><Input placeholder="data/backups" /></Form.Item></div>
                ) : (
                  <>
                    <div className="backup-runtime-inline-fields">
                      <div className="backup-runtime-field-card backup-runtime-field-card--grow">{label('WebDAV 地址', '例如 https://dav.example.com/remote.php/dav/files/name。')}<Form.Item name="webdav_base_url" rules={[{ required: true, message: '请填写 WebDAV 地址' }]} noStyle><Input placeholder="https://dav.example.com/path" /></Form.Item></div>
                      <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label('远端子目录', '可选，留空则直接写当前根地址。')}<Form.Item name="webdav_root_path" noStyle><Input placeholder="tg-monitor/backups" /></Form.Item></div>
                      <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label('用户名', '匿名 WebDAV 可留空。')}<Form.Item name="webdav_username" noStyle><Input placeholder="username" /></Form.Item></div>
                      <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label(editing?.webdav_password_configured ? '密码（留空保持不变）' : '密码', '保存后会加密写入数据库。')}<Form.Item name="webdav_password" noStyle><Input.Password placeholder={editing?.webdav_password_configured ? '留空保持原密码' : 'password'} /></Form.Item></div>
                      <div className="backup-runtime-field-card backup-runtime-field-card--tiny">{label('超时秒数', '连接检查和上传的超时时间。')}<Form.Item name="webdav_timeout_seconds" noStyle><InputNumber min={5} max={600} style={{ width: '100%' }} /></Form.Item></div>
                      <div className="backup-runtime-switch-card backup-runtime-switch-card--compact"><div className="backup-runtime-switch-copy">{label('校验证书', '公网环境建议开启。')}</div><Switch checked={current.webdav_verify_ssl} onChange={(checked) => setValues({ webdav_verify_ssl: checked })} /></div>
                      {editing?.webdav_password_configured ? <div className="backup-runtime-switch-card backup-runtime-switch-card--compact"><div className="backup-runtime-switch-copy">{label('清空已存密码', '仅在需要移除旧密码时开启。')}</div><Switch checked={current.clear_webdav_password} onChange={(checked) => setValues({ clear_webdav_password: checked })} /></div> : <div className="backup-runtime-inline-note backup-runtime-inline-note--compact">新增目标请先保存，再测试连接。</div>}
                    </div>
                  </>
                )}
              </section>

              <section className="backup-runtime-panel">
                <div className="backup-runtime-section-head">{label('备份内容', '完整备份固定包含数据库快照，附加项只保留真正需要选择的内容。')}</div>
                {current.backup_mode === 'full' ? (
                  <>
                    <div className="backup-runtime-base-note"><DatabaseOutlined /><span>基础内容始终包含数据库快照。</span></div>
                    <div className="backup-runtime-grid backup-runtime-grid--two">
                      <div className="backup-runtime-switch-card"><div className="backup-runtime-switch-copy">{label('站点运行数据', '会打包 data/，并自动排除 data/backups。')}</div><Switch checked={current.include_runtime_data} onChange={(checked) => setValues({ include_runtime_data: checked })} /></div>
                      <div className="backup-runtime-switch-card"><div className="backup-runtime-switch-copy">{label('.env 文件', '只在确实需要保留环境变量时开启。')}</div><Switch checked={current.include_env_file} onChange={(checked) => setValues({ include_env_file: checked })} /></div>
                    </div>
                  </>
                ) : (
                  <div className="backup-runtime-field-card">
                    {label('导出范围', '可导出全部数据，或只导出最近 N 天；选择最近 N 天后会在右侧直接输入。')}
                    <div className="backup-runtime-export-inline">
                      <Form.Item name="export_range_kind" noStyle>
                        <Select
                          className="backup-runtime-export-select"
                          options={[
                            { label: '全部数据', value: 'all' },
                            { label: '最近 N 天', value: 'days' },
                          ]}
                          onChange={(value) => setValues({ export_range_kind: value })}
                        />
                      </Form.Item>
                      {current.export_range_kind === 'days' ? (
                        <>
                          <span className="backup-runtime-export-text">最近</span>
                          <Form.Item name="export_range_days" rules={[{ required: true, message: '请填写导出天数' }]} noStyle>
                            <InputNumber min={1} max={3650} className="backup-runtime-export-input" />
                          </Form.Item>
                          <span className="backup-runtime-export-text">天</span>
                        </>
                      ) : null}
                    </div>
                  </div>
                )}
              </section>

              <section className="backup-runtime-panel">
                <div className="backup-runtime-plan-head">
                  <div className="backup-runtime-section-head">{label('执行计划', '同一时刻到点的目标会按执行顺位串行排队，数值越小越先执行。')}</div>
                  <div className="backup-runtime-plan-switch">
                    <span className="backup-runtime-plan-switch-label">自动计划</span>
                    <Switch checked={current.schedule_enabled} onChange={(checked) => setValues({ schedule_enabled: checked, schedule_kind: checked && current.schedule_kind === 'manual' ? 'daily' : checked ? current.schedule_kind : 'manual' })} />
                  </div>
                </div>
                <div className="backup-runtime-inline-fields">
                  {current.schedule_enabled ? <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label('频率', '支持每天、每周、每月。')}<Form.Item name="schedule_kind" noStyle><Select options={[{ label: '每天', value: 'daily' }, { label: '每周', value: 'weekly' }, { label: '每月', value: 'monthly' }]} onChange={(value) => setValues({ schedule_kind: value })} /></Form.Item></div> : null}
                  {current.schedule_enabled ? <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label('执行时间', '按 24 小时制设置。')}<Form.Item name="schedule_time" noStyle><TimePicker format="HH:mm" minuteStep={5} style={{ width: '100%' }} onChange={(value) => value && setValues({ schedule_time: value })} /></Form.Item></div> : null}
                  {current.schedule_enabled && current.schedule_kind === 'weekly' ? <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label('星期', '每周计划执行的日期。')}<Form.Item name="schedule_weekday" noStyle><Select options={weekdays} onChange={(value) => setValues({ schedule_weekday: value })} /></Form.Item></div> : null}
                  {current.schedule_enabled && current.schedule_kind === 'monthly' ? <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label('日期', '每月计划执行的日期。')}<Form.Item name="schedule_day" noStyle><InputNumber min={1} max={31} style={{ width: '100%' }} onChange={(value) => setValues({ schedule_day: Number(value || 1) })} /></Form.Item></div> : null}
                  {current.schedule_enabled ? <div className="backup-runtime-field-card backup-runtime-field-card--compact">{label('执行顺位', '多个目标同一时间到点时按此排队。')}<Form.Item name="schedule_priority" noStyle><InputNumber min={1} max={9999} style={{ width: '100%' }} /></Form.Item></div> : null}
                  <div className="backup-runtime-field-card backup-runtime-field-card--tiny">{label('最多保留', '超出数量的旧备份会自动清理；0 表示不限份数。')}<Form.Item name="retention_count" noStyle><InputNumber min={0} max={3650} style={{ width: '100%' }} /></Form.Item></div>
                </div>
              </section>
            </div>

            <aside className="backup-runtime-editor-aside">
              <Card className="backup-runtime-summary-card" variant="outlined">
                <div className="backup-runtime-summary-top"><div className="backup-runtime-summary-title">当前方案</div><div className="backup-runtime-tag-row"><Tag>{fmtKind(current.target_kind)}</Tag><Tag color="blue">{fmtMode(current.backup_mode)}</Tag><Tag color={current.schedule_enabled ? 'processing' : 'default'}>{current.schedule_enabled ? '自动计划' : '手动执行'}</Tag></div></div>
                <div className="backup-runtime-summary-name">{current.name.trim() || '未命名备份目标'}</div>
                <div className="backup-runtime-summary-list">
                  <div className="backup-runtime-summary-row"><span>存储位置</span><strong>{current.target_kind === 'local' ? current.local_dir || '待填写' : `${current.webdav_base_url || '待填写'}${current.webdav_root_path ? ` / ${current.webdav_root_path}` : ''}`}</strong></div>
                  <div className="backup-runtime-summary-row"><span>备份内容</span><strong>{buildContent(current)}</strong></div>
                  <div className="backup-runtime-summary-row"><span>执行计划</span><strong>{fmtSchedule({ ...current, schedule_hour: current.schedule_time.hour(), schedule_minute: current.schedule_time.minute() })}</strong></div>
                  <div className="backup-runtime-summary-row"><span>保留策略</span><strong>{current.retention_count > 0 ? `最多 ${current.retention_count} 份` : '不限份数'}</strong></div>
                </div>
                {checkIssues.length === 0 ? <Alert className="backup-runtime-summary-alert" type="success" showIcon message="配置结构已完整" description="保存后即可测试连接、查看远端文件或手动加入队列。" /> : <Alert className="backup-runtime-summary-alert" type="warning" showIcon message="还差几步" description={checkIssues.join('、')} />}
                <div className="backup-runtime-summary-tips">
                  <div className="backup-runtime-summary-tip"><ThunderboltOutlined /><span>完整备份固定带数据库快照，不再单独放开关。</span></div>
                  <div className="backup-runtime-summary-tip"><SafetyCertificateOutlined /><span>WebDAV 目录只会在测试连接或首次备份时创建。</span></div>
                  <div className="backup-runtime-summary-tip"><InboxOutlined /><span>远端文件列表支持长文件名省略显示，悬停可看全名。</span></div>
                </div>
              </Card>
            </aside>
          </div>
        </Form>
      </Drawer>

      <Modal
        title={<div className="backup-runtime-modal-title"><span>远端文件</span>{remoteTarget ? <Text type="secondary">{remoteTarget.name}</Text> : null}</div>}
        open={Boolean(remoteTarget)}
        width={960}
        onCancel={() => { setRemoteTarget(null); setRemoteFiles([]) }}
        footer={<Space>{remoteTarget ? <Button icon={<ReloadOutlined />} loading={remoteLoading} onClick={() => void loadRemoteFiles(remoteTarget)}>刷新列表</Button> : null}<Button onClick={() => setRemoteTarget(null)}>关闭</Button></Space>}
      >
        {remoteTarget ? <div className="backup-runtime-modal-stack">
          <div className="backup-runtime-modal-summary"><span>远端目录</span>{ellipsis(remoteTarget.webdav_root_path || '/')}</div>
          <Table rowKey="remote_path" loading={remoteLoading} dataSource={remoteFiles} columns={remoteColumns} pagination={remoteFiles.length > 12 ? { pageSize: 12 } : false} locale={{ emptyText: '远端目录暂无备份文件' }} scroll={{ x: 760 }} />
        </div> : null}
      </Modal>
    </div>
  )
}
