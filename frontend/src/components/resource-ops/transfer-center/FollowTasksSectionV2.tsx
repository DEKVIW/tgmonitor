import { useEffect, useMemo, useState, type Key } from 'react'
import { Alert, Button, Card, Checkbox, Descriptions, Drawer, Empty, Modal, Popconfirm, Segmented, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import {
  createPanTransferFollowSyncBatch,
  deletePanTransferFollowTask,
  getPanTransferFollowTaskDetail,
  listPanTransferFollowTasks,
  pausePanTransferFollowTask,
  previewPanTransferLinkDirectory,
  queuePanTransferFollowTaskCheck,
  resumePanTransferFollowTask,
} from '@/api/panTransfer'
import type {
  PanTransferFollowTaskDetailResponse,
  PanTransferFollowTaskItem,
  PanTransferFollowTaskSyncSelectionEntry,
  PanTransferLinkDirectoryEntry,
  PanTransferLinkDirectoryPreviewResponse,
} from '@/types/panTransfer'
import { formatServerDateTime } from '@/utils/dateTime'

import { getErrorMessage } from './shared'

const { Title, Paragraph, Text, Link } = Typography

type FollowTasksSectionProps = {
  refreshToken: number
}

type FollowStatusFilter = 'all' | 'active' | 'paused'
type FollowSyncSourceKind = 'current' | 'candidate'
type FollowSyncMode = 'incremental' | 'replace_all'
type DirectoryTrailItem = {
  key: string
  label: string
  entryId?: string | null
  entryPath?: string | null
}

const TASK_STATUS_META: Record<string, { color: string; label: string }> = {
  active: { color: 'processing', label: '启用中' },
  paused: { color: 'default', label: '已暂停' },
}

const TASK_STATE_META: Record<string, { color: string; label: string }> = {
  idle: { color: 'success', label: '正常跟踪' },
  queued: { color: 'processing', label: '等待巡检' },
  checking: { color: 'processing', label: '巡检中' },
  candidate_found: { color: 'warning', label: '发现候选' },
  sync_queued: { color: 'processing', label: '同步已排队' },
  source_invalid: { color: 'error', label: '原链失效' },
  share_invalid: { color: 'error', label: '分享异常' },
  error: { color: 'error', label: '巡检异常' },
}

const LINK_STATUS_META: Record<string, { color: string; label: string }> = {
  valid: { color: 'success', label: '有效' },
  healthy: { color: 'success', label: '有效' },
  warning: { color: 'warning', label: '存疑' },
  invalid: { color: 'error', label: '失效' },
  error: { color: 'error', label: '异常' },
  unknown: { color: 'default', label: '未知' },
}

const FOLLOW_CHANGE_LABELS: Record<string, string> = {
  candidate_found: '检测到更晚的候选原链',
  source_invalid: '当前原链失效',
  share_invalid: '当前对外分享异常',
  no_change: '本次巡检未发现变化',
  sync_completed: '已按当前原链完成同步',
  candidate_applied: '已应用候选原链并完成同步',
  sync_failed: '同步失败，等待人工处理',
}

const DIRECTORY_ROOT_LABELS: Record<FollowSyncSourceKind, string> = {
  current: '当前原链',
  candidate: '候选原链',
}

const formatDateTime = (value?: string | null, format = 'YYYY-MM-DD HH:mm') =>
  value ? formatServerDateTime(value, format, 'Asia/Shanghai') : '-'

const formatTerminalLine = (level: string, stage: string, createdAt?: string | null, messageText?: string | null) =>
  `[${formatDateTime(createdAt, 'HH:mm:ss')}] [${stage || 'general'}] [${String(level || 'info').toUpperCase()}] ${messageText || ''}`

const getTerminalLineClassName = (level: string) => {
  const normalized = String(level || '').toLowerCase()
  if (normalized === 'error') return 'resource-ops-transfer-terminal-line is-error'
  if (normalized === 'warning') return 'resource-ops-transfer-terminal-line is-warning'
  return 'resource-ops-transfer-terminal-line'
}

const getAutomationSummary = (task: PanTransferFollowTaskItem) => {
  const automation = (task.extra_json?.automation as Record<string, unknown> | undefined) || {}
  if (!automation.enabled) {
    return '自动换源与自动前台回写已预埋，当前默认关闭。'
  }
  return '已启用自动模式：候选命中后可进入自动同步链路。'
}

const renderLinkStatus = (value?: string | null) => {
  const meta = LINK_STATUS_META[String(value || '').toLowerCase()] || {
    color: 'default',
    label: value || '未知',
  }
  return <Tag color={meta.color}>{meta.label}</Tag>
}

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

const FollowTasksSectionV2 = ({ refreshToken }: FollowTasksSectionProps) => {
  const [tasks, setTasks] = useState<PanTransferFollowTaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<FollowStatusFilter>('all')
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10, total: 0 })
  const [queueingTaskId, setQueueingTaskId] = useState<number | null>(null)
  const [togglingTaskId, setTogglingTaskId] = useState<number | null>(null)
  const [deletingTaskId, setDeletingTaskId] = useState<number | null>(null)
  const [syncingTaskKey, setSyncingTaskKey] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<PanTransferFollowTaskDetailResponse | null>(null)
  const [manualSyncOpen, setManualSyncOpen] = useState(false)
  const [manualSyncSubmitting, setManualSyncSubmitting] = useState(false)
  const [manualPreviewLoading, setManualPreviewLoading] = useState(false)
  const [manualSyncSourceKind, setManualSyncSourceKind] = useState<FollowSyncSourceKind>('current')
  const [manualSyncMode, setManualSyncMode] = useState<FollowSyncMode>('incremental')
  const [manualReplaceConfirmed, setManualReplaceConfirmed] = useState(false)
  const [manualPreviewData, setManualPreviewData] = useState<PanTransferLinkDirectoryPreviewResponse | null>(null)
  const [manualPreviewTrail, setManualPreviewTrail] = useState<DirectoryTrailItem[]>([])
  const [manualSelectedRowKeys, setManualSelectedRowKeys] = useState<Key[]>([])
  const [manualSelectedEntries, setManualSelectedEntries] = useState<PanTransferLinkDirectoryEntry[]>([])

  const loadTasks = async (page = pagination.page, pageSize = pagination.pageSize, filter = statusFilter) => {
    setLoading(true)
    try {
      const response = await listPanTransferFollowTasks(page, pageSize, filter === 'all' ? undefined : filter)
      setTasks(response.items)
      setPagination({ page: response.page, pageSize: response.page_size, total: response.total })
    } catch (error) {
      message.error(getErrorMessage(error, '加载追更任务失败'))
    } finally {
      setLoading(false)
    }
  }

  const loadTaskDetail = async (taskId: number, options?: { open?: boolean; silent?: boolean }) => {
    if (!(options?.silent ?? false)) {
      setDetailLoading(true)
    }
    try {
      const response = await getPanTransferFollowTaskDetail(taskId)
      setDetailData(response)
      if (options?.open ?? true) {
        setDetailOpen(true)
      }
    } catch (error) {
      message.error(getErrorMessage(error, '加载追更任务详情失败'))
    } finally {
      if (!(options?.silent ?? false)) {
        setDetailLoading(false)
      }
    }
  }

  const resetManualSyncState = () => {
    setManualSyncMode('incremental')
    setManualReplaceConfirmed(false)
    setManualPreviewData(null)
    setManualPreviewTrail([])
    setManualSelectedRowKeys([])
    setManualSelectedEntries([])
  }

  const resolveSourceUrl = (task: PanTransferFollowTaskItem, sourceKind: FollowSyncSourceKind) =>
    sourceKind === 'candidate' ? task.last_candidate_url || '' : task.source_url || ''

  const loadManualPreview = async (
    task: PanTransferFollowTaskItem,
    sourceKind: FollowSyncSourceKind,
    trail: DirectoryTrailItem[]
  ) => {
    const sourceUrl = resolveSourceUrl(task, sourceKind)
    if (!sourceUrl) {
      message.error(sourceKind === 'candidate' ? '当前没有可用的候选原链' : '当前原链为空')
      return
    }
    setManualPreviewLoading(true)
    try {
      const current = trail[trail.length - 1]
      const response = await previewPanTransferLinkDirectory({
        url: sourceUrl,
        entry_id: current?.entryId || undefined,
        entry_path: current?.entryPath || undefined,
        entry_name: current?.label || undefined,
      })
      setManualPreviewData(response)
      setManualPreviewTrail(buildDirectoryTrail(DIRECTORY_ROOT_LABELS[sourceKind], trail, response))
      setManualSelectedRowKeys([])
      setManualSelectedEntries([])
    } catch (error) {
      message.error(getErrorMessage(error, '加载源目录失败'))
    } finally {
      setManualPreviewLoading(false)
    }
  }

  const openManualSyncModal = async (
    task: PanTransferFollowTaskItem,
    initialSourceKind: FollowSyncSourceKind = 'current'
  ) => {
    const nextSourceKind =
      initialSourceKind === 'candidate' && task.last_candidate_url ? 'candidate' : 'current'
    resetManualSyncState()
    setManualSyncSourceKind(nextSourceKind)
    setManualSyncOpen(true)
    await loadManualPreview(task, nextSourceKind, [{ key: 'root', label: DIRECTORY_ROOT_LABELS[nextSourceKind] }])
  }

  useEffect(() => {
    void loadTasks(1, pagination.pageSize, statusFilter)
  }, [refreshToken, statusFilter])

  useEffect(() => {
    if (!detailOpen || !detailData) return
    if (!['queued', 'checking', 'sync_queued'].includes(detailData.task.task_state)) return

    const taskId = detailData.task.id
    const timer = window.setInterval(() => {
      void loadTaskDetail(taskId, { open: false, silent: true })
      void loadTasks(pagination.page, pagination.pageSize, statusFilter)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [detailOpen, detailData?.task.id, detailData?.task.task_state, pagination.page, pagination.pageSize, statusFilter])

  useEffect(() => {
    if (!detailOpen) {
      setManualSyncOpen(false)
      resetManualSyncState()
    }
  }, [detailOpen])

  const summary = useMemo(() => {
    const activeCount = tasks.filter((item) => item.status === 'active').length
    const alertCount = tasks.filter((item) => ['candidate_found', 'source_invalid', 'share_invalid', 'error'].includes(item.task_state)).length
    const pausedCount = tasks.filter((item) => item.status === 'paused').length
    return { activeCount, alertCount, pausedCount }
  }, [tasks])

  const triggerFollowSync = async (taskId: number, sourceKind: FollowSyncSourceKind) => {
    const syncKey = `${taskId}:${sourceKind}`
    setSyncingTaskKey(syncKey)
    try {
      const response = await createPanTransferFollowSyncBatch(taskId, {
        source_kind: sourceKind,
        reuse_existing_share_if_valid: true,
        update_publish_record: true,
      })
      message.success(
        sourceKind === 'candidate'
          ? `已创建候选原链同步批次 #${response.batch_id}`
          : `已创建当前原链同步批次 #${response.batch_id}`
      )
      await loadTaskDetail(taskId, { open: false })
      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
    } catch (error) {
      message.error(getErrorMessage(error, '创建追更同步批次失败'))
    } finally {
      setSyncingTaskKey(null)
    }
  }

  const manualSelectionEntries = useMemo<PanTransferFollowTaskSyncSelectionEntry[]>(
    () =>
      manualSelectedEntries.map((entry) => ({
        name: entry.name,
        is_dir: entry.is_dir,
        entry_id: entry.entry_id || undefined,
        path: entry.path || undefined,
      })),
    [manualSelectedEntries]
  )

  const submitManualSync = async () => {
    if (!detailTask) return
    if (manualSelectionEntries.length <= 0) {
      message.warning('请先选择要同步的文件或目录')
      return
    }
    if (manualSyncMode === 'replace_all' && !manualReplaceConfirmed) {
      message.warning('请先确认全量替换风险')
      return
    }
    setManualSyncSubmitting(true)
    try {
      const response = await createPanTransferFollowSyncBatch(detailTask.id, {
        source_kind: manualSyncSourceKind,
        sync_mode: manualSyncMode,
        selected_entries: manualSelectionEntries,
        selection_parent_entry_id: manualPreviewData?.current_entry_id || null,
        selection_parent_path: manualPreviewData?.current_path || null,
        selection_parent_name:
          manualPreviewData?.current_name || manualPreviewTrail[manualPreviewTrail.length - 1]?.label || null,
        confirm_full_replace: manualSyncMode === 'replace_all',
        reuse_existing_share_if_valid: true,
        update_publish_record: true,
      })
      message.success(
        manualSyncMode === 'replace_all'
          ? `已创建全量替换同步批次 #${response.batch_id}`
          : `已创建增量同步批次 #${response.batch_id}`
      )
      setManualSyncOpen(false)
      resetManualSyncState()
      await loadTaskDetail(detailTask.id, { open: false })
      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
    } catch (error) {
      message.error(getErrorMessage(error, '创建手动同步批次失败'))
    } finally {
      setManualSyncSubmitting(false)
    }
  }

  const columns: ColumnsType<PanTransferFollowTaskItem> = [
    {
      title: '任务',
      dataIndex: 'task_name',
      key: 'task_name',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">{record.task_name}</span>
          <span className="resource-ops-transfer-title-sub">
            {record.work_title || record.topic_title || `任务 #${record.id}`}
          </span>
        </div>
      ),
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 96,
      render: (value) => <Tag>{value}</Tag>,
    },
    {
      title: '原链',
      dataIndex: 'source_url',
      key: 'source_url',
      width: 240,
      render: (value: string) => (
        <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
          {value}
        </a>
      ),
    },
    {
      title: '目标账号 / 目录',
      key: 'target',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>{record.target_account_name || '未指定账号'}</small>
          <small title={record.fixed_save_path}>{record.fixed_save_path || '未记录固定目录'}</small>
        </div>
      ),
    },
    {
      title: '当前对外分享',
      dataIndex: 'current_share_url',
      key: 'current_share_url',
      width: 240,
      render: (value?: string | null) =>
        value ? (
          <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
            {value}
          </a>
        ) : (
          <Text type="secondary">尚未记录</Text>
        ),
    },
    {
      title: '原链状态',
      dataIndex: 'source_link_status',
      key: 'source_link_status',
      width: 110,
      render: (value) => renderLinkStatus(value),
    },
    {
      title: '新分享状态',
      dataIndex: 'current_share_status',
      key: 'current_share_status',
      width: 110,
      render: (value) => renderLinkStatus(value),
    },
    {
      title: '最近变化',
      key: 'last_change_type',
      width: 240,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <Space wrap size={[6, 6]}>
            <Tag color={(TASK_STATUS_META[record.status] || { color: 'default' }).color}>
              {(TASK_STATUS_META[record.status] || { label: record.status }).label}
            </Tag>
            <Tag color={(TASK_STATE_META[record.task_state] || { color: 'default' }).color}>
              {(TASK_STATE_META[record.task_state] || { label: record.task_state }).label}
            </Tag>
          </Space>
          <small>{FOLLOW_CHANGE_LABELS[record.last_change_type || ''] || '等待首次巡检'}</small>
          {record.last_candidate_title ? <small>{record.last_candidate_title}</small> : null}
          {record.last_sync_batch_id ? <small>{`最近同步批次 #${record.last_sync_batch_id}`}</small> : null}
        </div>
      ),
    },
    {
      title: '巡检时间',
      key: 'sync_time',
      width: 180,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>上次巡检 {formatDateTime(record.last_checked_at)}</small>
          <small>下次巡检 {formatDateTime(record.next_check_at)}</small>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 230,
      fixed: 'right',
      render: (_, record) => (
        <Space wrap size={[6, 6]}>
          <Button size="small" onClick={() => void loadTaskDetail(record.id, { open: true })}>
            详情
          </Button>
          <Button
            size="small"
            loading={queueingTaskId === record.id}
            disabled={record.status !== 'active'}
            onClick={() => void (async () => {
              setQueueingTaskId(record.id)
              try {
                const response = await queuePanTransferFollowTaskCheck(record.id)
                setDetailData((current) => (current?.task.id === record.id ? response : current))
                message.success(`追更任务 #${record.id} 已加入立即巡检队列`)
                await loadTasks(pagination.page, pagination.pageSize, statusFilter)
              } catch (error) {
                message.error(getErrorMessage(error, '加入巡检队列失败'))
              } finally {
                setQueueingTaskId(null)
              }
            })()}
          >
            立即巡检
          </Button>
          {record.status === 'active' ? (
            <Button
              size="small"
              loading={togglingTaskId === record.id}
              onClick={() => void (async () => {
                setTogglingTaskId(record.id)
                try {
                  const response = await pausePanTransferFollowTask(record.id)
                  setDetailData((current) => (current?.task.id === record.id ? response : current))
                  message.success(`追更任务 #${record.id} 已暂停`)
                  await loadTasks(pagination.page, pagination.pageSize, statusFilter)
                } catch (error) {
                  message.error(getErrorMessage(error, '暂停追更任务失败'))
                } finally {
                  setTogglingTaskId(null)
                }
              })()}
            >
              暂停
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              loading={togglingTaskId === record.id}
              onClick={() => void (async () => {
                setTogglingTaskId(record.id)
                try {
                  const response = await resumePanTransferFollowTask(record.id)
                  setDetailData((current) => (current?.task.id === record.id ? response : current))
                  message.success(`追更任务 #${record.id} 已恢复`)
                  await loadTasks(pagination.page, pagination.pageSize, statusFilter)
                } catch (error) {
                  message.error(getErrorMessage(error, '恢复追更任务失败'))
                } finally {
                  setTogglingTaskId(null)
                }
              })()}
            >
              恢复
            </Button>
          )}
          <Popconfirm
            title={`确认删除追更任务 #${record.id} 吗？`}
            description="只删除追更跟踪记录和日志，不会删除已转存的数据或前台消息。"
            onConfirm={() => void (async () => {
              setDeletingTaskId(record.id)
              try {
                await deletePanTransferFollowTask(record.id)
                if (detailData?.task.id === record.id) {
                  setDetailOpen(false)
                  setDetailData(null)
                }
                message.success(`追更任务 #${record.id} 已删除`)
                const nextPage = pagination.page > 1 && tasks.length === 1 ? pagination.page - 1 : pagination.page
                await loadTasks(nextPage, pagination.pageSize, statusFilter)
              } catch (error) {
                message.error(getErrorMessage(error, '删除追更任务失败'))
              } finally {
                setDeletingTaskId(null)
              }
            })()}
          >
            <Button size="small" danger loading={deletingTaskId === record.id}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const detailTask = detailData?.task ?? null
  const detailLogs = detailData?.logs ?? []
  const hasCandidate = Boolean(detailTask?.last_candidate_link_target_id && detailTask?.last_candidate_url)
  const manualPreviewColumns: ColumnsType<PanTransferLinkDirectoryEntry> = [
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
              if (!detailTask) return
              void loadManualPreview(detailTask, manualSyncSourceKind, [
                ...manualPreviewTrail,
                {
                  key:
                    entry.entry_id ||
                    entry.path ||
                    `${entry.name}-${manualPreviewTrail.length}-${entry.is_dir ? 'dir' : 'file'}`,
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
    {
      title: '类型',
      dataIndex: 'is_dir',
      key: 'is_dir',
      width: 88,
      render: (value: boolean) => <Tag color={value ? 'processing' : 'default'}>{value ? '目录' : '文件'}</Tag>,
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      key: 'size_bytes',
      width: 120,
      align: 'right',
      render: (value?: number | null) => formatSize(value),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (value?: string | null) => formatDateTime(value),
    },
  ]

  return (
    <>
      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head">
          <div>
            <Title level={4}>追更同步</Title>
            <Paragraph className="resource-ops-transfer-copy">
              跟踪已经完成转存的资源，持续巡检原链、当前对外分享以及最新候选原链。当前版本先把“绑定前台记录、同步当前原链、应用候选原链并同步、同步后自动回写前台链接”这条主链路打通。
            </Paragraph>
          </div>
          <Segmented
            value={statusFilter}
            options={[
              { label: '全部任务', value: 'all' },
              { label: '启用中', value: 'active' },
              { label: '已暂停', value: 'paused' },
            ]}
            onChange={(value) => setStatusFilter(value as FollowStatusFilter)}
          />
        </div>

        <div className="resource-ops-transfer-summary">
          <div className="resource-ops-transfer-summary-item">
            <span>任务总数</span>
            <strong>{pagination.total}</strong>
            <small>当前筛选条件下的追更任务数量</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页启用中</span>
            <strong>{summary.activeCount}</strong>
            <small>会继续由 worker 定时巡检</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页待关注</span>
            <strong>{summary.alertCount}</strong>
            <small>候选原链、原链失效、新分享异常都算在内</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页已暂停</span>
            <strong>{summary.pausedCount}</strong>
            <small>暂停后不会继续自动巡检，恢复时会重新排队</small>
          </div>
        </div>

        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          loading={loading}
          dataSource={tasks}
          columns={columns}
          onChange={(tablePagination: TablePaginationConfig) =>
            void loadTasks(tablePagination.current || 1, tablePagination.pageSize || pagination.pageSize, statusFilter)
          }
          pagination={{
            current: pagination.page,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
          }}
          scroll={{ x: 1860 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无追更任务" /> }}
        />
      </Card>

      <Drawer
        width={980}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailTask ? `追更任务 #${detailTask.id}` : '追更任务详情'}
        extra={
          detailTask ? (
            <Space>
              <Button loading={detailLoading} onClick={() => void loadTaskDetail(detailTask.id, { open: false })}>
                刷新详情
              </Button>
              {detailTask.status === 'active' ? (
                <Button
                  loading={queueingTaskId === detailTask.id}
                  onClick={() => void (async () => {
                    setQueueingTaskId(detailTask.id)
                    try {
                      const response = await queuePanTransferFollowTaskCheck(detailTask.id)
                      setDetailData(response)
                      message.success(`追更任务 #${detailTask.id} 已加入立即巡检队列`)
                      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
                    } catch (error) {
                      message.error(getErrorMessage(error, '加入巡检队列失败'))
                    } finally {
                      setQueueingTaskId(null)
                    }
                  })()}
                >
                  立即巡检
                </Button>
              ) : null}
            </Space>
          ) : null
        }
      >
        {detailTask ? (
          <div className="resource-ops-transfer-drawer-stack">
            <Descriptions
              size="small"
              column={2}
              bordered
              items={[
                {
                  key: 'status',
                  label: '任务状态',
                  children: (
                    <Space wrap size={[6, 6]}>
                      <Tag color={(TASK_STATUS_META[detailTask.status] || { color: 'default' }).color}>
                        {(TASK_STATUS_META[detailTask.status] || { label: detailTask.status }).label}
                      </Tag>
                      <Tag color={(TASK_STATE_META[detailTask.task_state] || { color: 'default' }).color}>
                        {(TASK_STATE_META[detailTask.task_state] || { label: detailTask.task_state }).label}
                      </Tag>
                    </Space>
                  ),
                },
                { key: 'topic', label: '资源主题', children: detailTask.work_title || detailTask.topic_title },
                { key: 'account', label: '目标账号', children: detailTask.target_account_name || '-' },
                { key: 'path', label: '固定资源目录', children: detailTask.fixed_save_path || '-' },
                {
                  key: 'publish',
                  label: '绑定前台记录',
                  children: detailTask.publish_record_id ? (
                    <div className="resource-ops-follow-sync-meta">
                      <span>{detailTask.publish_record_title || `发布记录 #${detailTask.publish_record_id}`}</span>
                      <small>{`记录 #${detailTask.publish_record_id} · 最近发布 ${formatDateTime(detailTask.publish_record_published_at)}`}</small>
                    </div>
                  ) : (
                    '尚未绑定'
                  ),
                },
                {
                  key: 'source_url',
                  label: '当前原链',
                  children: detailTask.source_url ? (
                    <Link href={detailTask.source_url} target="_blank" title={detailTask.source_url}>
                      {detailTask.source_url}
                    </Link>
                  ) : (
                    '-'
                  ),
                },
                {
                  key: 'share_url',
                  label: '当前对外分享',
                  children: detailTask.current_share_url ? (
                    <Link href={detailTask.current_share_url} target="_blank" title={detailTask.current_share_url}>
                      {detailTask.current_share_url}
                    </Link>
                  ) : (
                    '-'
                  ),
                },
                { key: 'source', label: '原链状态', children: renderLinkStatus(detailTask.source_link_status) },
                { key: 'share', label: '新分享状态', children: renderLinkStatus(detailTask.current_share_status) },
                { key: 'last_checked', label: '上次巡检', children: formatDateTime(detailTask.last_checked_at) },
                { key: 'next_check', label: '下次巡检', children: formatDateTime(detailTask.next_check_at) },
              ]}
            />

            <Card size="small" title="同步工作台" className="resource-ops-follow-sync-card">
              <Paragraph className="resource-ops-transfer-copy">
                这里既保留原来的整包同步，也支持先预览源目录、再手动选择文件或子目录做“增量追加”或“全量替换”。
                全量替换不会默认执行，必须在弹窗里显式确认，避免误清空现有资源目录。
              </Paragraph>
              <div className="resource-ops-follow-sync-actions">
                <Button
                  type="primary"
                  loading={syncingTaskKey === `${detailTask.id}:current`}
                  onClick={() => void triggerFollowSync(detailTask.id, 'current')}
                >
                  同步当前原链
                </Button>
                <Button
                  loading={syncingTaskKey === `${detailTask.id}:candidate`}
                  disabled={!hasCandidate}
                  onClick={() => void triggerFollowSync(detailTask.id, 'candidate')}
                >
                  应用候选并同步
                </Button>
                <Button onClick={() => void openManualSyncModal(detailTask)}>
                  手动选择同步
                </Button>
                {detailTask.current_share_url ? (
                  <Button href={detailTask.current_share_url} target="_blank">
                    打开当前分享
                  </Button>
                ) : null}
              </div>
              <div className="resource-ops-follow-sync-meta">
                <span>{getAutomationSummary(detailTask)}</span>
                {detailTask.last_sync_batch_id ? (
                  <small>
                    {`最近同步批次 #${detailTask.last_sync_batch_id} · 来源 ${detailTask.last_sync_source_kind === 'candidate' ? '候选原链' : '当前原链'} · 发起时间 ${formatDateTime(detailTask.last_sync_started_at)}`}
                  </small>
                ) : null}
              </div>
            </Card>

            <Card size="small" title="候选来源" className="resource-ops-follow-sync-card">
              {hasCandidate ? (
                <div className="resource-ops-follow-sync-meta">
                  <span>{detailTask.last_candidate_title || '候选原链'}</span>
                  <small>{`候选出现时间 ${formatDateTime(detailTask.last_candidate_message_time)}`}</small>
                  <Link href={detailTask.last_candidate_url || undefined} target="_blank" title={detailTask.last_candidate_url || undefined}>
                    {detailTask.last_candidate_url}
                  </Link>
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有候选原链" />
              )}
            </Card>

            <Card size="small" title="执行终端" className="resource-ops-transfer-log-card">
              <Paragraph className="resource-ops-transfer-copy">
                这里按真实执行顺序输出追更巡检和同步日志，优先用来定位“是否发现候选”“同步批次有没有排队”“同步完成后有没有回写前台”。
              </Paragraph>
              <div className="resource-ops-terminal resource-ops-transfer-terminal">
                {detailLogs.length > 0 ? (
                  detailLogs.map((log) => (
                    <div key={log.id} className={getTerminalLineClassName(log.level)}>
                      {formatTerminalLine(log.level, log.stage, log.created_at, log.message)}
                    </div>
                  ))
                ) : (
                  <div className="resource-ops-terminal-empty">暂无追更巡检日志</div>
                )}
              </div>
            </Card>
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无追更任务详情" />
        )}
      </Drawer>

      <Modal
        open={manualSyncOpen}
        title="手动同步到现有资源目录"
        width={1080}
        destroyOnHidden
        onCancel={() => {
          setManualSyncOpen(false)
          resetManualSyncState()
        }}
        onOk={() => void submitManualSync()}
        okText={manualSyncMode === 'replace_all' ? '创建全量替换批次' : '创建增量同步批次'}
        okButtonProps={{
          danger: manualSyncMode === 'replace_all',
          disabled:
            manualPreviewLoading ||
            manualSyncSubmitting ||
            manualSelectionEntries.length <= 0 ||
            (manualSyncMode === 'replace_all' && !manualReplaceConfirmed),
        }}
        confirmLoading={manualSyncSubmitting}
      >
        {detailTask ? (
          <div className="resource-ops-transfer-modal-stack resource-ops-follow-sync-manual-modal">
            <Paragraph className="resource-ops-transfer-copy">
              先进入源目录，再勾选当前层级里需要同步的文件或子目录。想选更深层内容时，先点进子目录，再在该层级提交。
            </Paragraph>

            <div className="resource-ops-follow-sync-manual-grid">
              <Card size="small" title="同步配置" className="resource-ops-follow-sync-card">
                <div className="resource-ops-follow-sync-meta">
                  <span>来源选择</span>
                  <Segmented
                    block
                    value={manualSyncSourceKind}
                    options={[
                      { label: '当前原链', value: 'current' },
                      { label: '候选原链', value: 'candidate', disabled: !hasCandidate },
                    ]}
                    onChange={(value) => {
                      const nextSourceKind = value as FollowSyncSourceKind
                      setManualSyncSourceKind(nextSourceKind)
                      if (!detailTask) return
                      void loadManualPreview(detailTask, nextSourceKind, [
                        { key: 'root', label: DIRECTORY_ROOT_LABELS[nextSourceKind] },
                      ])
                    }}
                  />
                  <small>{manualSyncSourceKind === 'candidate' ? '会从最新候选原链导入选中的内容。' : '会从当前已绑定原链导入选中的内容。'}</small>
                </div>

                <div className="resource-ops-follow-sync-meta">
                  <span>同步模式</span>
                  <Segmented
                    block
                    value={manualSyncMode}
                    options={[
                      { label: '增量追加', value: 'incremental' },
                      { label: '全量替换', value: 'replace_all' },
                    ]}
                    onChange={(value) => {
                      setManualSyncMode(value as FollowSyncMode)
                      setManualReplaceConfirmed(false)
                    }}
                  />
                  <small>
                    {manualSyncMode === 'replace_all'
                      ? '先清空资源目录当前内容，再导入所选目录/文件。'
                      : '把所选目录/文件追加导入到现有资源目录，不会主动删除旧内容。'}
                  </small>
                </div>

                <div className="resource-ops-follow-sync-meta">
                  <span>目标资源目录</span>
                  <small title={detailTask.fixed_save_path}>{detailTask.fixed_save_path || '-'}</small>
                  <small>{`分享层级：${detailTask.share_target_mode === 'content_root' ? '原内容目录/文件' : '资源目录'}`}</small>
                </div>

                <div className="resource-ops-follow-sync-meta">
                  <span>当前来源链接</span>
                  {resolveSourceUrl(detailTask, manualSyncSourceKind) ? (
                    <Link
                      href={resolveSourceUrl(detailTask, manualSyncSourceKind)}
                      target="_blank"
                      title={resolveSourceUrl(detailTask, manualSyncSourceKind)}
                    >
                      {resolveSourceUrl(detailTask, manualSyncSourceKind)}
                    </Link>
                  ) : (
                    <small>当前没有可用来源</small>
                  )}
                </div>

                {manualSyncMode === 'replace_all' ? (
                  <>
                    <Alert
                      type="error"
                      showIcon
                      message="全量替换是高风险操作"
                      description="会先清空当前资源目录，再导入所选内容。如果导入失败，现有目录可能暂时为空，所以这个模式不会默认启用。"
                    />
                    <Checkbox
                      checked={manualReplaceConfirmed}
                      onChange={(event) => setManualReplaceConfirmed(event.target.checked)}
                    >
                      我确认先清空当前资源目录，再执行这次全量替换
                    </Checkbox>
                  </>
                ) : (
                  <Alert
                    type="info"
                    showIcon
                    message="增量追加更安全"
                    description="系统只会导入你勾选的内容，原目录中的其他文件和分享链接保持原样。"
                  />
                )}
              </Card>

              <Card size="small" title="本次选择" className="resource-ops-follow-sync-card">
                <div className="resource-ops-follow-sync-meta">
                  <span>{`已选 ${manualSelectionEntries.length} 项`}</span>
                  <small>
                    {manualSelectionEntries.length > 0
                      ? manualSelectionEntries
                          .slice(0, 6)
                          .map((entry) => entry.name)
                          .join(' / ')
                      : '还没有选择任何文件或目录'}
                  </small>
                  {manualSelectionEntries.length > 6 ? (
                    <small>{`其余 ${manualSelectionEntries.length - 6} 项会一并同步`}</small>
                  ) : null}
                </div>

                <div className="resource-ops-follow-sync-meta">
                  <span>当前目录</span>
                  <small>{manualPreviewData?.current_name || manualPreviewTrail[manualPreviewTrail.length - 1]?.label || DIRECTORY_ROOT_LABELS[manualSyncSourceKind]}</small>
                  <small>{manualPreviewData?.current_path || manualPreviewData?.current_entry_id || '根目录'}</small>
                </div>

                <div className="resource-ops-follow-sync-actions">
                  <Button
                    size="small"
                    loading={manualPreviewLoading}
                    onClick={() => {
                      if (!detailTask) return
                      void loadManualPreview(detailTask, manualSyncSourceKind, manualPreviewTrail.length > 0 ? manualPreviewTrail : [
                        { key: 'root', label: DIRECTORY_ROOT_LABELS[manualSyncSourceKind] },
                      ])
                    }}
                  >
                    刷新目录
                  </Button>
                  <Button
                    size="small"
                    disabled={!manualPreviewData?.items?.length}
                    onClick={() => {
                      const nextItems = manualPreviewData?.items || []
                      setManualSelectedEntries(nextItems)
                      setManualSelectedRowKeys(
                        nextItems.map(
                          (entry) =>
                            entry.entry_id || entry.path || `${entry.name}-${entry.is_dir ? 'dir' : 'file'}`
                        )
                      )
                    }}
                  >
                    全选当前目录
                  </Button>
                  <Button
                    size="small"
                    disabled={manualSelectedRowKeys.length <= 0}
                    onClick={() => {
                      setManualSelectedEntries([])
                      setManualSelectedRowKeys([])
                    }}
                  >
                    清空选择
                  </Button>
                </div>
              </Card>
            </div>

            <Card size="small" title="源目录内容" className="resource-ops-follow-sync-card">
              <div className="resource-ops-transfer-directory-breadcrumbs">
                {manualPreviewTrail.map((item, index) => (
                  <button
                    key={item.key}
                    type="button"
                    className="resource-ops-transfer-directory-crumb"
                    onClick={() => {
                      if (!detailTask) return
                      void loadManualPreview(detailTask, manualSyncSourceKind, manualPreviewTrail.slice(0, index + 1))
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="resource-ops-transfer-directory-meta">
                {manualPreviewData ? (
                  <>
                    <Tag>{manualPreviewData.platform}</Tag>
                    <Tag color="processing">{`共 ${manualPreviewData.item_count} 项`}</Tag>
                    {manualPreviewData.truncated ? (
                      <Tag color="warning">{`当前仅显示前 ${manualPreviewData.items.length} 项`}</Tag>
                    ) : null}
                  </>
                ) : null}
              </div>
              <Table
                size="small"
                rowKey={(entry) => entry.entry_id || entry.path || `${entry.name}-${entry.is_dir ? 'dir' : 'file'}`}
                loading={manualPreviewLoading}
                columns={manualPreviewColumns}
                dataSource={manualPreviewData?.items || []}
                pagination={false}
                rowSelection={{
                  selectedRowKeys: manualSelectedRowKeys,
                  onChange: (selectedKeys, selectedRows) => {
                    setManualSelectedRowKeys(selectedKeys)
                    setManualSelectedEntries(selectedRows)
                  },
                }}
                scroll={{ y: 360 }}
                locale={{
                  emptyText: (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={manualPreviewData?.message || '当前目录为空'}
                    />
                  ),
                }}
              />
            </Card>
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有可操作的追更任务" />
        )}
      </Modal>
    </>
  )
}

export default FollowTasksSectionV2
