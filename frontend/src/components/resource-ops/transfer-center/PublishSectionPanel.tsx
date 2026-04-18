import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  EditOutlined,
  EyeOutlined,
  LinkOutlined,
  PlusOutlined,
  RedoOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Dropdown,
  Empty,
  Form,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { MenuProps } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import {
  listPanTransferPublishRecords,
  previewPanTransferLinkDirectory,
  publishManualPanTransferMessage,
  refreshPanTransferPublishRecordShare,
  republishPanTransferPublishRecord,
  retirePanTransferPublishRecord,
  updatePanTransferPublishRecord,
  updatePanTransferPublishRule,
  validatePanTransferPublishRecord,
} from '@/api/panTransfer'
import type {
  PanTransferLinkDirectoryEntry,
  PanTransferLinkDirectoryPreviewResponse,
  PanTransferManualPublishRequest,
  PanTransferPublishRetireRequest,
  PanTransferPublishRecordItem,
  PanTransferPublishRecordUpdateRequest,
  PanTransferPublishRuleUpdateRequest,
} from '@/types/panTransfer'
import { formatServerDateTime } from '@/utils/dateTime'

import { PLATFORM_OPTIONS, formatDateTime, getErrorMessage } from './shared'

const { Title, Paragraph, Text } = Typography

const LINK_STATUS_META: Record<string, { tone: string; label: string }> = {
  healthy: { tone: 'success', label: '有效' },
  valid: { tone: 'success', label: '有效' },
  invalid: { tone: 'danger', label: '失效' },
  warning: { tone: 'warning', label: '存疑' },
  unknown: { tone: 'muted', label: '未知' },
  error: { tone: 'danger', label: '异常' },
}

const LIFECYCLE_META: Record<string, { color: string; label: string }> = {
  active: { color: 'success', label: '运营中' },
  archived: { color: 'default', label: '已归档' },
  frontend_offline: { color: 'warning', label: '已下线' },
  resource_reclaimed: { color: 'error', label: '已回收' },
}

const RETIRE_MODE_OPTIONS: Array<{
  value: PanTransferPublishRetireRequest['mode']
  label: string
  description: string
}> = [
  {
    value: 'archive',
    label: '仅归档',
    description: '从活跃列表移到归档，保留前台消息和网盘资源。',
  },
  {
    value: 'offline_frontend',
    label: '下线前台',
    description: '删除前台消息并解除追更绑定，保留网盘资源目录。',
  },
  {
    value: 'reclaim_resource',
    label: '回收资源',
    description: '下线前台并回收网盘资源目录，适合真正释放容量。',
  },
]

type PublishSectionProps = { refreshToken: number }
type QueryState = {
  page: number
  pageSize: number
  keyword: string
  platform?: string
  scope: 'active' | 'archived' | 'all'
  sortBy: string
  sortOrder: 'asc' | 'desc'
}
type PublishLinkChip = {
  key: 'original' | 'current_share' | 'published'
  label: string
  url: string
  status?: string | null
  detailMessage?: string | null
  checkedAt?: string | null
}
type DirectoryTrailItem = {
  key: string
  label: string
  entryId?: string | null
  entryPath?: string | null
}

const WEEKDAY_OPTIONS = [
  { label: '周一', value: 1 },
  { label: '周二', value: 2 },
  { label: '周三', value: 3 },
  { label: '周四', value: 4 },
  { label: '周五', value: 5 },
  { label: '周六', value: 6 },
  { label: '周日', value: 7 },
]

const SORT_FIELD_MAP: Record<string, string> = {
  published_clicks_total: 'published_clicks_total',
  platform: 'platform',
  publish_meta: 'publish_count',
}

const getLinkStatusMeta = (value?: string | null) =>
  LINK_STATUS_META[String(value || '').toLowerCase()] || LINK_STATUS_META.unknown

const formatPublishedAt = (value?: string | null) =>
  value ? formatServerDateTime(value, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai', true) : '-'

const buildDirectoryTrail = (
  fallbackLabel: string,
  trail: DirectoryTrailItem[],
  response: PanTransferLinkDirectoryPreviewResponse
): DirectoryTrailItem[] => {
  const rootItem: DirectoryTrailItem = {
    key: 'root',
    label: fallbackLabel,
  }
  const baseTrail = trail.length > 0 ? [...trail] : [rootItem]
  if (baseTrail[0]?.key !== 'root') {
    baseTrail.unshift(rootItem)
  }
  const currentEntryId = response.current_entry_id || null
  const currentEntryPath = response.current_path || null
  const currentLabel = response.current_name || baseTrail[baseTrail.length - 1]?.label || fallbackLabel
  if (!currentEntryId && !currentEntryPath) {
    return [{ ...rootItem, label: currentLabel || fallbackLabel }]
  }
  const currentKey = currentEntryId || currentEntryPath || currentLabel
  const nextItem: DirectoryTrailItem = {
    key: currentKey,
    label: currentLabel,
    entryId: currentEntryId,
    entryPath: currentEntryPath,
  }
  const existingIndex = baseTrail.findIndex(
    (item) =>
      item.key === currentKey ||
      (Boolean(currentEntryId) && item.entryId === currentEntryId) ||
      (Boolean(currentEntryPath) && item.entryPath === currentEntryPath)
  )
  if (existingIndex >= 0) {
    return [...baseTrail.slice(0, existingIndex), { ...baseTrail[existingIndex], ...nextItem }]
  }
  const lastItem = baseTrail[baseTrail.length - 1]
  if (
    (lastItem?.entryId || null) === currentEntryId &&
    (lastItem?.entryPath || null) === currentEntryPath
  ) {
    return [...baseTrail.slice(0, -1), { ...lastItem, ...nextItem }]
  }
  return [...baseTrail, nextItem]
}

const formatSize = (value?: number | null) => {
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

const copyText = async (value: string, successText: string) => {
  try {
    await navigator.clipboard.writeText(value)
    message.success(successText)
  } catch {
    message.error('复制失败，请检查浏览器权限')
  }
}

const openLink = (url: string) => {
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

const buildLinkItems = (record: PanTransferPublishRecordItem): PublishLinkChip[] => {
  const items: PublishLinkChip[] = []
  if (record.source_original_url) items.push({ key: 'original', label: '原链', url: record.source_original_url, status: record.original_link_status, detailMessage: record.original_link_detail_message, checkedAt: record.original_link_checked_at })
  if (record.current_share_url) items.push({ key: 'current_share', label: '新分享', url: record.current_share_url, status: record.current_share_status, detailMessage: record.current_share_detail_message, checkedAt: record.current_share_checked_at })
  if (record.frontend_online && record.source_url) items.push({ key: 'published', label: '前台', url: record.source_url, status: record.published_link_status, detailMessage: record.published_link_detail_message, checkedAt: record.published_link_checked_at })
  return items
}

const PublishSectionPanel = ({ refreshToken }: PublishSectionProps) => {
  const [records, setRecords] = useState<PanTransferPublishRecordItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState<QueryState>({ page: 1, pageSize: 10, keyword: '', platform: undefined, scope: 'active', sortBy: 'published_at', sortOrder: 'desc' })
  const [keywordInput, setKeywordInput] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [manualOpen, setManualOpen] = useState(false)
  const [manualSaving, setManualSaving] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editSaving, setEditSaving] = useState(false)
  const [ruleOpen, setRuleOpen] = useState(false)
  const [ruleSaving, setRuleSaving] = useState(false)
  const [retireOpen, setRetireOpen] = useState(false)
  const [retireSaving, setRetireSaving] = useState(false)
  const [retireMode, setRetireMode] = useState<PanTransferPublishRetireRequest['mode']>('archive')
  const [retireRecords, setRetireRecords] = useState<PanTransferPublishRecordItem[]>([])
  const [batchActionLoading, setBatchActionLoading] = useState<string | null>(null)
  const [editingRecord, setEditingRecord] = useState<PanTransferPublishRecordItem | null>(null)
  const [ruleRecord, setRuleRecord] = useState<PanTransferPublishRecordItem | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [directoryOpen, setDirectoryOpen] = useState(false)
  const [directoryLoading, setDirectoryLoading] = useState(false)
  const [directoryTitle, setDirectoryTitle] = useState('')
  const [directoryData, setDirectoryData] = useState<PanTransferLinkDirectoryPreviewResponse | null>(null)
  const [directoryLink, setDirectoryLink] = useState<PublishLinkChip | null>(null)
  const [directoryTrail, setDirectoryTrail] = useState<DirectoryTrailItem[]>([])
  const [manualForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [ruleForm] = Form.useForm()

  const selectedRecords = useMemo(
    () => records.filter((record) => selectedRowKeys.includes(record.id)),
    [records, selectedRowKeys]
  )

  const summary = useMemo(() => {
    const manualCount = records.filter((item) => item.source_type === 'manual').length
    const batchCount = records.filter((item) => item.source_type === 'batch_item').length
    const refreshableCount = records.filter((item) => item.can_refresh_share).length
    const ruledCount = records.filter((item) => item.publish_rule_enabled).length
    return { manualCount, batchCount, refreshableCount, ruledCount }
  }, [records])

  const retireBlockedReason = useMemo(() => {
    if (retireRecords.length <= 0) return '请先选择需要退出运营的资源'
    if (retireMode === 'offline_frontend' && retireRecords.some((item) => !item.can_offline)) {
      return '所选资源里包含已下线或当前无法下线前台的记录'
    }
    if (retireMode === 'reclaim_resource' && retireRecords.some((item) => !item.can_reclaim)) {
      return '所选资源里包含无法回收网盘资源的记录'
    }
    return null
  }, [retireMode, retireRecords])

  const loadRecords = async (nextQuery = query) => {
    setLoading(true)
    try {
      const response = await listPanTransferPublishRecords(nextQuery.page, nextQuery.pageSize, {
        keyword: nextQuery.keyword,
        platform: nextQuery.platform,
        scope: nextQuery.scope,
        sortBy: nextQuery.sortBy,
        sortOrder: nextQuery.sortOrder,
      })
      setRecords(response.items)
      setTotal(response.total)
      setSelectedRowKeys((current) =>
        current.filter((key) => response.items.some((record) => record.id === Number(key)))
      )
    } catch (error) {
      message.error(getErrorMessage(error, '加载运营发布资源失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRecords(query)
  }, [refreshToken, query])

  const openManualModal = () => {
    manualForm.resetFields()
    manualForm.setFieldsValue({ platform: PLATFORM_OPTIONS[0]?.value, source_url: '', title: '', description: '', tags: [] })
    setManualOpen(true)
  }

  const openEditModal = (record: PanTransferPublishRecordItem) => {
    setEditingRecord(record)
    editForm.resetFields()
    editForm.setFieldsValue({
      source_url: record.source_url,
      title: record.published_title,
      description: record.published_description || '',
      tags: record.published_tags,
    })
    setEditOpen(true)
  }

  const openRuleModal = (record: PanTransferPublishRecordItem) => {
    const rule = ((record.extra_json || {}).publish_rule as Record<string, unknown> | undefined) || {}
    setRuleRecord(record)
    ruleForm.resetFields()
    ruleForm.setFieldsValue({
      enabled: Boolean(rule.enabled),
      weekdays: Array.isArray(rule.weekdays) ? rule.weekdays.filter((value): value is number => typeof value === 'number') : [],
      time_of_day: typeof rule.time_of_day === 'string' ? rule.time_of_day : '09:00',
    })
    setRuleOpen(true)
  }

  const openRetireModal = (targets: PanTransferPublishRecordItem[]) => {
    if (targets.length <= 0) return
    setRetireRecords(targets)
    setRetireMode('archive')
    setRetireOpen(true)
  }

  const openDirectoryAt = async (item: PublishLinkChip, trail: DirectoryTrailItem[]) => {
    setDirectoryOpen(true)
    setDirectoryLoading(true)
    setDirectoryLink(item)
    setDirectoryTrail(trail)
    setDirectoryTitle(item.label)
    try {
      const current = trail[trail.length - 1]
      const response = await previewPanTransferLinkDirectory({
        url: item.url,
        entry_id: current?.entryId || undefined,
        entry_path: current?.entryPath || undefined,
        entry_name: current?.label || undefined,
      })
      setDirectoryData(response)
      setDirectoryTrail(buildDirectoryTrail(item.label, trail, response))
    } catch (error) {
      setDirectoryOpen(false)
      message.error(getErrorMessage(error, '目录预览失败'))
    } finally {
      setDirectoryLoading(false)
    }
  }

  const handleLinkMenuClick = async (actionKey: string, item: PublishLinkChip) => {
    if (actionKey === 'open') return openLink(item.url)
    if (actionKey === 'copy') return copyText(item.url, '已复制链接')
    if (actionKey === 'preview') return openDirectoryAt(item, [{ key: 'root', label: item.label }])
  }

  const runRecordAction = async (action: string, handler: () => Promise<void>, successText: string) => {
    setBusyAction(action)
    try {
      await handler()
      message.success(successText)
      await loadRecords(query)
    } catch (error) {
      message.error(getErrorMessage(error, `${successText}失败`))
    } finally {
      setBusyAction(null)
    }
  }

  const handleBatchAction = async (
    action: 'republish' | 'validate' | 'refresh'
  ) => {
    if (selectedRecords.length <= 0) return
    setBatchActionLoading(action)
    let successCount = 0
    let failureCount = 0
    try {
      for (const record of selectedRecords) {
        try {
          if (action === 'republish') {
            await republishPanTransferPublishRecord(record.id)
          } else if (action === 'validate') {
            await validatePanTransferPublishRecord(record.id)
          } else {
            if (!record.can_refresh_share) continue
            await refreshPanTransferPublishRecordShare(record.id)
          }
          successCount += 1
        } catch {
          failureCount += 1
        }
      }
      message[failureCount > 0 ? 'warning' : 'success'](
        failureCount > 0
          ? `批量处理完成，成功 ${successCount} 条，失败 ${failureCount} 条`
          : `批量处理完成，共 ${successCount} 条`
      )
      setSelectedRowKeys([])
      await loadRecords(query)
    } finally {
      setBatchActionLoading(null)
    }
  }

  const handleManualPublish = async () => {
    try {
      const values = await manualForm.validateFields()
      setManualSaving(true)
      const payload: PanTransferManualPublishRequest = {
        platform: values.platform,
        source_url: values.source_url,
        title: values.title,
        description: values.description || null,
        tags: Array.isArray(values.tags) ? values.tags : [],
      }
      await publishManualPanTransferMessage(payload)
      message.success('已发布到前台，并已纳入运营发布资源表')
      setManualOpen(false)
      setQuery((current) => ({ ...current, page: 1 }))
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '手动发布失败'))
    } finally {
      setManualSaving(false)
    }
  }

  const handleEditPublish = async () => {
    if (!editingRecord) return
    try {
      const values = await editForm.validateFields()
      setEditSaving(true)
      const payload: PanTransferPublishRecordUpdateRequest = {
        source_url: values.source_url,
        title: values.title,
        description: values.description || null,
        tags: Array.isArray(values.tags) ? values.tags : [],
      }
      await updatePanTransferPublishRecord(editingRecord.id, payload)
      message.success('运营发布资源已更新')
      setEditOpen(false)
      setEditingRecord(null)
      await loadRecords(query)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '更新运营发布资源失败'))
    } finally {
      setEditSaving(false)
    }
  }

  const handleSaveRule = async () => {
    if (!ruleRecord) return
    try {
      const values = await ruleForm.validateFields()
      setRuleSaving(true)
      const payload: PanTransferPublishRuleUpdateRequest = {
        enabled: Boolean(values.enabled),
        weekdays: Array.isArray(values.weekdays) ? values.weekdays : [],
        time_of_day: values.time_of_day || null,
        timezone: 'Asia/Shanghai',
      }
      await updatePanTransferPublishRule(ruleRecord.id, payload)
      message.success(payload.enabled ? '发布规则已保存' : '发布规则已关闭')
      setRuleOpen(false)
      setRuleRecord(null)
      await loadRecords(query)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '保存发布规则失败'))
    } finally {
      setRuleSaving(false)
    }
  }

  const handleRetireRecords = async () => {
    if (retireRecords.length <= 0 || retireBlockedReason) return
    setRetireSaving(true)
    let successCount = 0
    let failureCount = 0
    try {
      for (const record of retireRecords) {
        try {
          await retirePanTransferPublishRecord(record.id, { mode: retireMode })
          successCount += 1
        } catch {
          failureCount += 1
        }
      }
      message[failureCount > 0 ? 'warning' : 'success'](
        failureCount > 0
          ? `退出运营完成，成功 ${successCount} 条，失败 ${failureCount} 条`
          : `退出运营完成，共 ${successCount} 条`
      )
      setRetireOpen(false)
      setRetireRecords([])
      setSelectedRowKeys([])
      await loadRecords(query)
    } finally {
      setRetireSaving(false)
    }
  }

  const directoryColumns: ColumnsType<PanTransferLinkDirectoryEntry> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (_, entry) =>
        entry.is_dir ? (
          <button
            type="button"
            className="resource-ops-transfer-directory-link"
            onClick={() => {
              if (!directoryLink) return
              void openDirectoryAt(directoryLink, [
                ...directoryTrail,
                {
                  key: entry.entry_id || entry.path || `${entry.name}-${directoryTrail.length}`,
                  label: entry.name,
                  entryId: entry.entry_id,
                  entryPath: entry.path,
                },
              ])
            }}
          >
            {entry.name}
          </button>
        ) : (
          <span className="resource-ops-transfer-directory-name">{entry.name}</span>
        ),
    },
    { title: '类型', dataIndex: 'is_dir', key: 'is_dir', width: 88, render: (value: boolean) => <Tag color={value ? 'processing' : 'default'}>{value ? '目录' : '文件'}</Tag> },
    { title: '大小', dataIndex: 'size_bytes', key: 'size_bytes', width: 120, align: 'right', render: (value?: number | null) => formatSize(value) },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 160, render: (value?: string | null) => formatDateTime(value) },
  ]

  const columns: ColumnsType<PanTransferPublishRecordItem> = [
    {
      title: '发布内容',
      dataIndex: 'published_title',
      key: 'published_title',
      width: 300,
      className: 'resource-ops-transfer-col-resource resource-ops-transfer-col-resource-wide',
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <Tooltip title={record.published_title}>
            <button type="button" className="resource-ops-transfer-title-copy" onClick={() => void copyText(record.published_title, '已复制标题')}>
              {record.published_title}
            </button>
          </Tooltip>
        </div>
      ),
    },
    {
      title: '发布',
      key: 'publish_meta',
      width: 220,
      sorter: true,
      render: (_, record) => {
        const lifecycleMeta = LIFECYCLE_META[record.lifecycle_state] || LIFECYCLE_META.active
        return (
          <div className="resource-ops-transfer-validation resource-ops-transfer-validation--publish-meta">
            <div className="resource-ops-transfer-inline-tags">
              <Tag color={lifecycleMeta.color}>{record.lifecycle_label || lifecycleMeta.label}</Tag>
              {record.publish_rule_enabled ? <Tag color="processing">有规则</Tag> : null}
            </div>
            <small>最近发布 {formatPublishedAt(record.published_at)}</small>
            <small>发布次数 {record.publish_count || 1}</small>
            {record.next_publish_at ? <small>下次 {formatDateTime(record.next_publish_at)}</small> : null}
          </div>
        )
      },
    },
    {
      title: '链接',
      key: 'links',
      render: (_, record) => {
        const linkItems = buildLinkItems(record)
        return (
          <div className="resource-ops-transfer-link-stack">
            <div className="resource-ops-transfer-link-row">{linkItems.map((item) => {
              const statusMeta = getLinkStatusMeta(item.status)
              const menu: MenuProps = { items: [{ key: 'open', icon: <LinkOutlined />, label: '访问链接' }, { key: 'copy', icon: <CopyOutlined />, label: '复制链接' }, { key: 'preview', icon: <EyeOutlined />, label: '查看目录' }], onClick: ({ key }) => { void handleLinkMenuClick(String(key), item) } }
              const tip = [item.url, item.detailMessage, item.checkedAt ? `校验: ${formatDateTime(item.checkedAt)}` : ''].filter(Boolean).join('\n')
              return <Dropdown key={`${item.key}-${item.url}`} menu={menu} trigger={['contextMenu']}><Tooltip title={tip}><button type="button" className="resource-ops-transfer-link-chip" onClick={() => openLink(item.url)}><span className="resource-ops-transfer-link-chip-label">{item.label}</span><span className={`resource-ops-transfer-link-chip-status is-${statusMeta.tone}`}>{statusMeta.label}</span></button></Tooltip></Dropdown>
            })}</div>
            <small>{linkItems.length > 0 ? '左键访问，右键可复制或查看目录' : '该资源当前没有在线前台链接'}</small>
          </div>
        )
      },
    },
    { title: '点击', dataIndex: 'published_clicks_total', key: 'published_clicks_total', width: 84, align: 'right', sorter: true, render: (value: number) => <div className="resource-ops-transfer-number-stack resource-ops-transfer-number-stack--compact"><strong>{value || 0}</strong></div> },
    { title: '网盘', dataIndex: 'platform', key: 'platform', width: 90, sorter: true, render: (value: string) => <Tag>{value || '-'}</Tag> },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 120, render: (value?: string | null) => <Text>{value || '-'}</Text> },
    {
      title: '操作',
      key: 'actions',
      width: 124,
      fixed: 'right',
      render: (_, record) => (
        <div className="resource-ops-transfer-action-grid">
          <Tooltip title={record.can_republish ? '发布到前台' : '资源已回收，不能再次发布'}><Button size="small" type="text" disabled={!record.can_republish} loading={busyAction === `republish-${record.id}`} icon={<SendOutlined />} onClick={() => void runRecordAction(`republish-${record.id}`, () => republishPanTransferPublishRecord(record.id).then(() => undefined), '已重新发布到前台')} /></Tooltip>
          <Tooltip title="校验三路链接"><Button size="small" type="text" loading={busyAction === `validate-${record.id}`} icon={<CheckCircleOutlined />} onClick={() => void runRecordAction(`validate-${record.id}`, () => validatePanTransferPublishRecord(record.id).then(() => undefined), '已完成三路链接校验')} /></Tooltip>
          <Tooltip title={record.can_refresh_share ? '重建分享' : '当前资源不支持重建分享'}><Button size="small" type="text" disabled={!record.can_refresh_share} loading={busyAction === `refresh-${record.id}`} icon={<RedoOutlined />} onClick={() => void runRecordAction(`refresh-${record.id}`, () => refreshPanTransferPublishRecordShare(record.id).then(() => undefined), '已重建分享并同步到前台')} /></Tooltip>
          <Tooltip title="编辑发布内容"><Button size="small" type="text" disabled={!record.can_edit} icon={<EditOutlined />} onClick={() => openEditModal(record)} /></Tooltip>
          <Tooltip title="发布规则"><Button size="small" type="text" icon={<ClockCircleOutlined />} onClick={() => openRuleModal(record)} /></Tooltip>
          <Tooltip title="退出运营"><Button size="small" type="text" icon={<StopOutlined />} onClick={() => openRetireModal([record])} /></Tooltip>
        </div>
      ),
    },
  ]

  return (
    <>
      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head"><div><Title level={4}>运营发布</Title><Paragraph className="resource-ops-transfer-copy">这里按“资源”管理，同一资源再次发布到前台时，只更新最近发布时间和发布次数，不再新增主表行。</Paragraph></div><Space><Button onClick={() => void loadRecords(query)}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={openManualModal}>手动新建发布</Button></Space></div>
        <Alert type="info" showIcon style={{ marginBottom: 16 }} message="运营发布已经收敛为资源表" description="支持搜索、排序、批量发布到前台、批量校验三路链接、批量退出运营，以及从链接标签右键直接查看目录。" />
        <div className="resource-ops-transfer-summary">
          <div className="resource-ops-transfer-summary-item"><span>当前页资源数</span><strong>{records.length}</strong><small>同一资源重复发布不再新增主表行</small></div>
          <div className="resource-ops-transfer-summary-item"><span>总资源数</span><strong>{total}</strong><small>可按搜索词、平台、归档状态筛选</small></div>
          <div className="resource-ops-transfer-summary-item"><span>批次发布</span><strong>{summary.batchCount}</strong><small>来自转存中心批次项</small></div>
          <div className="resource-ops-transfer-summary-item"><span>手动发布</span><strong>{summary.manualCount}</strong><small>管理员直接新建</small></div>
          <div className="resource-ops-transfer-summary-item"><span>可重建分享</span><strong>{summary.refreshableCount}</strong><small>可从暂存目录再生成新分享</small></div>
          <div className="resource-ops-transfer-summary-item"><span>已设规则</span><strong>{summary.ruledCount}</strong><small>已配置循环发布规则</small></div>
        </div>
        <div className="resource-ops-transfer-toolbar" style={{ marginTop: 16 }}>
          <Input.Search allowClear className="resource-ops-transfer-field" placeholder="搜索标题、描述、标签、链接、操作人" value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} onSearch={(value) => setQuery((current) => ({ ...current, page: 1, keyword: value.trim() }))} />
          <Select allowClear className="resource-ops-transfer-field resource-ops-transfer-field--compact" placeholder="平台" value={query.platform} options={PLATFORM_OPTIONS} onChange={(value) => setQuery((current) => ({ ...current, page: 1, platform: value || undefined }))} />
          <Segmented options={[{ label: '活跃', value: 'active' }, { label: '已归档', value: 'archived' }, { label: '全部', value: 'all' }]} value={query.scope} onChange={(value) => setQuery((current) => ({ ...current, page: 1, scope: String(value) as QueryState['scope'] }))} />
          <Button onClick={() => { setKeywordInput(''); setQuery((current) => ({ ...current, page: 1, keyword: '', platform: undefined, scope: 'active', sortBy: 'published_at', sortOrder: 'desc' })) }}>重置</Button>
        </div>
        <div className="resource-ops-transfer-bulkbar">
          <div className="resource-ops-transfer-bulkbar-meta">已选择 <strong>{selectedRecords.length}</strong> 条</div>
          <Space wrap size={[8, 8]}>
            <Button disabled={selectedRecords.length <= 0} loading={batchActionLoading === 'republish'} onClick={() => void handleBatchAction('republish')}>批量发布到前台</Button>
            <Button disabled={selectedRecords.length <= 0} loading={batchActionLoading === 'validate'} onClick={() => void handleBatchAction('validate')}>批量校验链接</Button>
            <Button disabled={selectedRecords.filter((item) => item.can_refresh_share).length <= 0} loading={batchActionLoading === 'refresh'} onClick={() => void handleBatchAction('refresh')}>批量重建分享</Button>
            <Button danger disabled={selectedRecords.length <= 0} onClick={() => openRetireModal(selectedRecords)}>批量退出运营</Button>
          </Space>
        </div>
        <Table rowKey="id" style={{ marginTop: 16 }} loading={loading} dataSource={records} columns={columns} rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }} onChange={(tablePagination: TablePaginationConfig, _, sorter) => { const resolvedSorter = Array.isArray(sorter) ? sorter[0] : sorter; setQuery((current) => ({ ...current, page: tablePagination.current || 1, pageSize: tablePagination.pageSize || current.pageSize, sortBy: resolvedSorter && typeof resolvedSorter.field === 'string' ? SORT_FIELD_MAP[resolvedSorter.field] || 'published_at' : current.sortBy, sortOrder: resolvedSorter?.order === 'ascend' ? 'asc' : resolvedSorter?.order === 'descend' ? 'desc' : current.sortOrder })) }} pagination={{ current: query.page, pageSize: query.pageSize, total, showSizeChanger: true }} scroll={{ x: 'max-content' }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运营发布资源" /> }} />
      </Card>
      <Modal open={manualOpen} title="手动新建发布" onCancel={() => setManualOpen(false)} onOk={() => void handleManualPublish()} confirmLoading={manualSaving} okText="确认发布" destroyOnHidden><Form form={manualForm} layout="vertical"><Form.Item label="平台" name="platform" rules={[{ required: true, message: '请选择平台' }]}><Select options={PLATFORM_OPTIONS} /></Form.Item><Form.Item label="分享链接" name="source_url" rules={[{ required: true, message: '请输入分享链接' }]}><Input placeholder="请输入前台最终要展示的链接" /></Form.Item><Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}><Input maxLength={255} placeholder="请输入前台展示标题" /></Form.Item><Form.Item label="描述" name="description"><Input.TextArea rows={4} maxLength={1000} placeholder="可选，补充发布说明" /></Form.Item><Form.Item label="标签" name="tags"><Select mode="tags" tokenSeparators={[',', '，']} open={false} placeholder="可选，输入后回车" /></Form.Item></Form></Modal>
      <Modal open={editOpen} title={editingRecord ? `编辑发布：${editingRecord.published_title}` : '编辑发布'} onCancel={() => { setEditOpen(false); setEditingRecord(null); editForm.resetFields() }} onOk={() => void handleEditPublish()} confirmLoading={editSaving} okText="保存修改" destroyOnHidden><Form form={editForm} layout="vertical"><Form.Item label="前台链接" name="source_url" rules={[{ required: true, message: '请输入前台链接' }]}><Input placeholder="这里修改的是前台当前对外展示的链接" /></Form.Item><Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}><Input maxLength={255} /></Form.Item><Form.Item label="描述" name="description"><Input.TextArea rows={4} maxLength={1000} /></Form.Item><Form.Item label="标签" name="tags"><Select mode="tags" tokenSeparators={[',', '，']} open={false} placeholder="输入后回车" /></Form.Item></Form></Modal>
      <Modal open={ruleOpen} title={ruleRecord ? `发布规则：${ruleRecord.published_title}` : '发布规则'} onCancel={() => { setRuleOpen(false); setRuleRecord(null); ruleForm.resetFields() }} onOk={() => void handleSaveRule()} confirmLoading={ruleSaving} okText="保存规则" destroyOnHidden><Form form={ruleForm} layout="vertical"><Paragraph className="resource-ops-transfer-copy">发布规则默认按中国时间执行，无需单独填写时区。</Paragraph><Form.Item name="enabled" valuePropName="checked"><Checkbox>启用循环发布</Checkbox></Form.Item><Form.Item label="发布星期" name="weekdays"><Checkbox.Group options={WEEKDAY_OPTIONS} /></Form.Item><Form.Item label="发布时间" name="time_of_day" rules={[{ pattern: /^([01]\d|2[0-3]):([0-5]\d)$/, message: '请使用 HH:MM，例如 09:30' }]}><Input placeholder="09:00" /></Form.Item></Form></Modal>
      <Modal open={retireOpen} title={retireRecords.length > 1 ? `批量退出运营（${retireRecords.length} 条）` : retireRecords[0] ? `退出运营：${retireRecords[0].published_title}` : '退出运营'} onCancel={() => { setRetireOpen(false); setRetireRecords([]) }} onOk={() => void handleRetireRecords()} okText="确认执行" okButtonProps={{ danger: retireMode !== 'archive', disabled: Boolean(retireBlockedReason) }} confirmLoading={retireSaving} destroyOnHidden><div className="resource-ops-transfer-modal-stack"><Paragraph className="resource-ops-transfer-copy">退出运营不会直接删主表行，而是按你的选择处理前台消息和网盘资源。</Paragraph><div className="resource-ops-transfer-retire-options">{RETIRE_MODE_OPTIONS.map((option) => <button key={option.value} type="button" className={`resource-ops-transfer-retire-option${retireMode === option.value ? ' is-active' : ''}`} onClick={() => setRetireMode(option.value)}><strong>{option.label}</strong><small>{option.description}</small></button>)}</div>{retireBlockedReason ? <Alert type="warning" showIcon message={retireBlockedReason} /> : null}<Alert type={retireMode === 'reclaim_resource' ? 'error' : retireMode === 'offline_frontend' ? 'warning' : 'info'} showIcon message={retireMode === 'archive' ? '仅归档不会删除前台消息，也不会释放网盘容量。' : retireMode === 'offline_frontend' ? '下线前台会删除前台消息并清掉追更绑定，但保留网盘资源。' : '回收资源会删除前台消息、解除追更绑定，并尝试删除网盘资源目录。'} /></div></Modal>
      <Modal open={directoryOpen} title={directoryTitle ? `${directoryTitle}目录预览` : '目录预览'} onCancel={() => { setDirectoryOpen(false); setDirectoryData(null); setDirectoryLink(null); setDirectoryTrail([]) }} footer={null} width={820} destroyOnHidden><div className="resource-ops-transfer-modal-stack"><Paragraph className="resource-ops-transfer-copy">支持在目录里继续点进子目录查看，像资源管理器一样逐层下钻，不会改动任何现有链接或发布记录。</Paragraph><div className="resource-ops-transfer-directory-meta">{directoryData ? <><Tag>{directoryData.platform}</Tag><Tag color="processing">共 {directoryData.item_count} 项</Tag>{directoryData.truncated ? <Tag color="warning">仅显示前 {directoryData.items.length} 项</Tag> : null}</> : null}</div><div className="resource-ops-transfer-directory-breadcrumbs">{directoryTrail.map((item, index) => <button key={item.key} type="button" className="resource-ops-transfer-directory-crumb" onClick={() => { if (!directoryLink) return; void openDirectoryAt(directoryLink, directoryTrail.slice(0, index + 1)) }}>{item.label}</button>)}</div><Table size="small" rowKey={(entry) => entry.entry_id || entry.path || `${entry.name}-${entry.is_dir ? 'dir' : 'file'}`} loading={directoryLoading} columns={directoryColumns} dataSource={directoryData?.items || []} pagination={false} scroll={{ y: 420 }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={directoryData?.message || '当前目录为空'} /> }} /></div></Modal>
    </>
  )
}

export default PublishSectionPanel
