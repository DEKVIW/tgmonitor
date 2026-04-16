import { useEffect, useMemo, useState, type Key } from 'react'
import {
  CloseCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  EllipsisOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Collapse, Descriptions, Drawer, Dropdown, Empty, InputNumber, Modal, Segmented, Space, Table, Tag, Tooltip, Typography, message } from 'antd'
import type { MenuProps } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import {
  clearPanTransferFollowTaskCandidate,
  clearPanTransferFollowTaskLogs,
  createPanTransferFollowSyncBatch,
  deletePanTransferFollowTask,
  getPanTransferFollowTaskDetail,
  listPanTransferFollowTasks,
  pausePanTransferFollowTask,
  previewPanTransferLinkDirectory,
  queuePanTransferFollowTaskCheck,
  resumePanTransferFollowTask,
  updatePanTransferFollowTaskSettings,
} from '@/api/panTransfer'
import type {
  PanTransferFollowTaskCandidatePolicy,
  PanTransferFollowTaskDetailResponse,
  PanTransferFollowTaskItem,
  PanTransferFollowTaskLogItem,
  PanTransferFollowTaskSyncSelectionEntry,
  PanTransferLinkDirectoryEntry,
  PanTransferLinkDirectoryPreviewResponse,
} from '@/types/panTransfer'
import { usePageVisibility } from '@/hooks/usePageVisibility'
import { formatServerDateTime } from '@/utils/dateTime'
import AppLogTerminal from '@/components/common/AppLogTerminal'

import { getErrorMessage } from './shared'

const { Title, Paragraph, Link } = Typography

type FollowTasksSectionProps = {
  refreshToken: number
  isActive?: boolean
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

type FollowTaskSettingsDraft = {
  taskId: number
  check_interval_minutes: number
  candidate_policy: PanTransferFollowTaskCandidatePolicy
}

const TASK_STATUS_META: Record<string, { color: string; label: string }> = {
  active: { color: 'processing', label: '启用中' },
  paused: { color: 'default', label: '已暂停' },
}

const TASK_STATE_META: Record<string, { color: string; label: string }> = {
  idle: { color: 'success', label: '正常跟踪' },
  queued: { color: 'processing', label: '等待检查' },
  checking: { color: 'processing', label: '检查中' },
  candidate_found: { color: 'warning', label: '发现候选' },
  sync_queued: { color: 'processing', label: '同步已排队' },
  source_invalid: { color: 'error', label: '原链失效' },
  share_invalid: { color: 'error', label: '分享异常' },
  error: { color: 'error', label: '检查异常' },
}

const FOLLOW_CHANGE_LABELS: Record<string, string> = {
  candidate_found: '检测到更晚的候选原链',
  source_invalid: '当前原链失效',
  share_invalid: '当前对外分享异常',
  no_change: '本次检查未发现变化',
  sync_completed: '已按当前原链完成同步',
  candidate_applied: '已应用候选原链并完成同步',
  sync_failed: '同步失败，等待人工处理',
}

const FOLLOW_TRANSIENT_TASK_STATES = new Set(['queued', 'checking', 'sync_queued'])

const FOLLOW_RULE_TONE: Record<string, { color: string; label: string }> = {
  info: { color: 'processing', label: '推荐' },
  warning: { color: 'warning', label: '人工确认' },
  danger: { color: 'error', label: '高风险' },
}

const DIRECTORY_ROOT_LABELS: Record<FollowSyncSourceKind, string> = {
  current: '当前原链',
  candidate: '候选原链',
}

const DEFAULT_FOLLOW_CHECK_INTERVAL_MINUTES = 180
const DEFAULT_FOLLOW_LOOKBACK_DAYS = 3
const DEFAULT_FOLLOW_MAX_RECALL_CANDIDATES = 12
const DEFAULT_FOLLOW_MAX_JUDGE_CANDIDATES = 6

const LINK_ROOT_LABELS: Record<FollowLinkChip['key'], string> = {
  source: '原链',
  candidate: '候选原链',
  share: '新分享',
}

const formatDateTime = (value?: string | null, format = 'YYYY-MM-DD HH:mm') =>
  value ? formatServerDateTime(value, format, 'Asia/Shanghai') : '-'

const FOLLOW_STAGE_LABELS: Record<string, string> = {
  setup: '建立',
  settings: '设置',
  queue: '排队',
  check: '巡检',
  source: '原链',
  share: '分享',
  identity: '识别',
  candidate: '候选',
  sync: '同步',
  publish: '发布',
  finish: '结束',
  general: '通用',
}

const formatFollowLogStatus = (value: unknown) => {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'valid') return '有效'
  if (normalized === 'warning') return '存疑'
  if (normalized === 'invalid') return '失效'
  if (normalized === 'error') return '异常'
  if (normalized === 'pending') return '待校验'
  return normalized || '未知'
}

const formatFollowSourceKind = (value: unknown) =>
  String(value || '').trim().toLowerCase() === 'candidate' ? '候选原链' : '当前原链'

const formatFollowSyncMode = (value: unknown) => {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'replace_all') return '全量替换'
  if (normalized === 'incremental') return '增量追加'
  return '安全同步'
}

const buildFollowIdentitySummary = (payload: Record<string, unknown>) => {
  const segments: string[] = []
  const coreTitle = String(payload.core_title || '').trim()
  const releaseYear = Number(payload.release_year || 0)
  const season = Number(payload.season || 0)
  const latestEpisode = Number(payload.latest_episode || 0)
  if (coreTitle) segments.push(coreTitle)
  if (releaseYear > 0) segments.push(String(releaseYear))
  if (season > 0) segments.push(`第 ${season} 季`)
  if (latestEpisode > 0) segments.push(`更至 ${latestEpisode} 集`)
  return segments.join(' · ')
}

const buildFollowLogSummary = (log: PanTransferFollowTaskLogItem) => {
  const messageText = String(log.message || '')
  const payload = log.payload || {}
  const candidateTitle = String(payload.title || payload.candidate_title || '').trim()
  const candidateStatus = formatFollowLogStatus(payload.candidate_status)
  const candidateTime = payload.latest_message_time ? formatDateTime(String(payload.latest_message_time), 'YYYY-MM-DD HH:mm') : ''
  const batchId = Number(payload.batch_id || 0)
  const publishRecordId = Number(payload.publish_record_id || 0)
  const selectedCount = Number(payload.selected_count || 0)
  const nextCheckAt = String(payload.next_check_at || '').trim()
  const newShareUrl = String(payload.new_share_url || payload.source_url || '').trim()
  const identitySummary = buildFollowIdentitySummary(payload)

  if (messageText === 'Follow task created from transfer batch item') {
    return '已从转存批次创建追更任务'
  }
  if (messageText === 'Follow task queued for immediate check') {
    return '已加入立即检查队列'
  }
  if (messageText === 'Updated follow task settings') {
    return '已更新追更设置'
  }
  if (messageText === 'Follow task paused') {
    return '已暂停追更任务'
  }
  if (messageText === 'Follow task resumed and queued') {
    return '已恢复追更任务，并重新加入检查队列'
  }
  if (messageText === 'Cleared the stored candidate source') {
    return '已手动清空候选原链'
  }
  if (messageText === 'Starting follow task check') {
    return '开始执行追更巡检'
  }
  if (messageText.startsWith('Source link validation finished with status:')) {
    return `原链校验完成 -> ${formatFollowLogStatus(messageText.split(':').pop())}`
  }
  if (messageText.startsWith('Current share validation finished with status:')) {
    return `当前分享校验完成 -> ${formatFollowLogStatus(messageText.split(':').pop())}`
  }
  if (messageText === 'Built follow task identity snapshot') {
    return identitySummary ? `已更新作品识别快照 -> ${identitySummary}` : '已更新作品识别快照'
  }
  if (messageText.startsWith('Removed the stored candidate source because link validation finished with status:')) {
    return `已移除旧候选原链 -> ${candidateStatus}`
  }
  if (messageText.startsWith('Discarded a detected candidate source because link validation finished with status:')) {
    return candidateTitle ? `已丢弃本轮候选原链 -> ${candidateTitle} · ${candidateStatus}` : `已丢弃本轮候选原链 -> ${candidateStatus}`
  }
  if (messageText === 'Detected a recent candidate source link for this tracked resource') {
    if (candidateTitle && candidateTime) return `发现新候选原链 -> ${candidateTitle} · ${candidateTime}`
    if (candidateTitle) return `发现新候选原链 -> ${candidateTitle}`
    return '发现新候选原链'
  }
  if (messageText === 'Keeping the stored candidate source because it is still valid') {
    return candidateTitle ? `保留已有候选原链 -> ${candidateTitle}` : '保留已有候选原链'
  }
  if (messageText === 'No new candidate found and the current source link is invalid') {
    return '当前原链已失效，且本轮未发现新候选'
  }
  if (messageText === 'No new candidate found and the current outward share is invalid') {
    return '当前对外分享异常，且本轮未发现新候选'
  }
  if (messageText === 'No recent candidate source link was found for this check') {
    return '本轮未发现新的候选原链'
  }
  if (messageText === 'Created a follow-sync batch targeting the existing resource directory') {
    const details = [
      batchId > 0 ? `批次 #${batchId}` : '',
      formatFollowSourceKind(payload.source_kind),
      formatFollowSyncMode(payload.sync_mode),
      selectedCount > 0 ? `已选 ${selectedCount} 项` : '',
    ].filter(Boolean)
    return details.length > 0 ? `已创建同步批次 -> ${details.join(' · ')}` : '已创建同步批次'
  }
  if (messageText === 'Follow-sync batch completed and the tracked resource directory was refreshed') {
    const details = [
      batchId > 0 ? `批次 #${batchId}` : '',
      formatFollowSourceKind(payload.source_kind),
      newShareUrl ? `新分享 ${newShareUrl}` : '',
    ].filter(Boolean)
    return details.length > 0 ? `同步完成 -> ${details.join(' · ')}` : '同步完成'
  }
  if (messageText === 'Bound frontend publish record was updated to the latest share URL') {
    return publishRecordId > 0 ? `已更新前台发布记录 -> 记录 #${publishRecordId}` : '已更新前台发布记录'
  }
  if (messageText.startsWith('Follow-sync batch failed:')) {
    return `同步失败 -> ${messageText.replace('Follow-sync batch failed:', '').trim() || '未知错误'}`
  }
  if (messageText === 'Follow task check completed') {
    return nextCheckAt ? `巡检完成 -> 下次检查 ${formatDateTime(nextCheckAt)}` : '巡检完成'
  }
  if (messageText.startsWith('Follow task check failed:')) {
    return `巡检失败 -> ${messageText.replace('Follow task check failed:', '').trim() || '未知错误'}`
  }
  return messageText || '日志已更新'
}

const getFollowLogTone = (log: PanTransferFollowTaskLogItem) => {
  const level = String(log.level || '').trim().toLowerCase()
  const messageText = String(log.message || '')
  if (level === 'error' || messageText.startsWith('Follow task check failed:') || messageText.startsWith('Follow-sync batch failed:')) {
    return 'error' as const
  }
  if (
    level === 'warning' ||
    messageText === 'Detected a recent candidate source link for this tracked resource' ||
    messageText.startsWith('Removed the stored candidate source') ||
    messageText.startsWith('Discarded a detected candidate source')
  ) {
    return 'warning' as const
  }
  if (
    messageText.startsWith('Source link validation finished with status: valid') ||
    messageText.startsWith('Current share validation finished with status: valid') ||
    messageText === 'Built follow task identity snapshot' ||
    messageText === 'Created a follow-sync batch targeting the existing resource directory' ||
    messageText === 'Follow-sync batch completed and the tracked resource directory was refreshed' ||
    messageText === 'Bound frontend publish record was updated to the latest share URL' ||
    messageText === 'Follow task check completed'
  ) {
    return 'success' as const
  }
  return 'default' as const
}

const buildFollowTerminalLine = (log: PanTransferFollowTaskLogItem) =>
  `[${formatDateTime(log.created_at, 'HH:mm:ss')}] [${FOLLOW_STAGE_LABELS[log.stage] || log.stage || '通用'}] [${String(log.level || 'info').toUpperCase()}] ${buildFollowLogSummary(log)}`

const clearFollowLogMarker = (markers: Record<number, number>, taskId: number) => {
  const next = { ...markers }
  delete next[taskId]
  return next
}

const getAutomationSummary = (task: PanTransferFollowTaskItem) => {
  const automation = (task.extra_json?.automation as Record<string, unknown> | undefined) || {}
  if (!automation.enabled) {
    return '自动换源与自动前台回写已预埋，当前默认关闭。'
  }
  return '已启用自动模式：候选命中后可进入自动同步链路。'
}

const getLinkChipMeta = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'candidate_pending') return { tone: 'warning', label: '待处理' }
  if (normalized === 'pending_check') return { tone: 'muted', label: '待检查' }
  if (normalized === 'healthy' || normalized === 'valid') return { tone: 'success', label: '有效' }
  if (normalized === 'warning') return { tone: 'warning', label: '存疑' }
  if (normalized === 'invalid' || normalized === 'error') return { tone: 'danger', label: normalized === 'error' ? '异常' : '失效' }
  return { tone: 'muted', label: '未知' }
}

type FollowLinkChip = {
  key: 'source' | 'candidate' | 'share'
  label: string
  url: string
  status?: string | null
  detail?: string | null
}

const openLink = (url: string) => {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

const copyText = async (value: string, successText: string) => {
  try {
    await navigator.clipboard.writeText(value)
    message.success(successText)
  } catch {
    message.error('复制失败，请检查浏览器权限')
  }
}

const getFollowScheduleLine = (record: PanTransferFollowTaskItem) => {
  if (record.task_state === 'checking') {
    return '当前正在执行检查'
  }
  if (record.task_state === 'queued' && record.next_check_at) {
    return `已加入检查队列 ${formatDateTime(record.next_check_at)}`
  }
  if (record.task_state === 'sync_queued') {
    return '同步批次已排队，等待 worker 处理'
  }
  if (record.next_check_at) {
    return `下次自动检查 ${formatDateTime(record.next_check_at)}`
  }
  return '未安排下一次检查'
}

const getFollowStatusSummary = (record: PanTransferFollowTaskItem) => {
  if (record.last_error_message) {
    return '最近一次检查或同步出现异常'
  }
  if (record.task_state === 'sync_queued') {
    return '同步批次已排队，等待 worker 处理'
  }
  if (record.task_state === 'candidate_found') {
    return FOLLOW_CHANGE_LABELS.candidate_found
  }
  if (record.task_state === 'source_invalid') {
    return FOLLOW_CHANGE_LABELS.source_invalid
  }
  if (record.task_state === 'share_invalid') {
    return FOLLOW_CHANGE_LABELS.share_invalid
  }
  if (!record.last_checked_at) {
    if (record.task_state === 'checking') return '首次检查进行中'
    if (record.task_state === 'queued') return '等待首次检查'
    return '尚未完成首次检查'
  }
  return FOLLOW_CHANGE_LABELS[record.last_change_type || ''] || '最近一次检查已完成'
}

const getFollowTaskTitle = (record: PanTransferFollowTaskItem) =>
  record.source_message_title || record.work_title || record.topic_title || record.task_name || `追更任务 #${record.id}`

const buildFollowSettingsDraft = (task: PanTransferFollowTaskItem): FollowTaskSettingsDraft => ({
  taskId: task.id,
  check_interval_minutes: Number(task.check_interval_minutes || DEFAULT_FOLLOW_CHECK_INTERVAL_MINUTES),
  candidate_policy: {
    lookback_days: Number(task.candidate_policy?.lookback_days || DEFAULT_FOLLOW_LOOKBACK_DAYS),
    max_recall_candidates: Number(task.candidate_policy?.max_recall_candidates || DEFAULT_FOLLOW_MAX_RECALL_CANDIDATES),
    max_judge_candidates: Number(task.candidate_policy?.max_judge_candidates || DEFAULT_FOLLOW_MAX_JUDGE_CANDIDATES),
  },
})

const getFollowCandidateAssessmentSummary = (record: PanTransferFollowTaskItem) => {
  const assessment = record.candidate_assessment
  if (assessment.should_promote) {
    return 'AI 判定当前候选可提升为追更来源'
  }
  if (assessment.is_same_work && assessment.is_newer === false) {
    return 'AI 判定是同作品，但没有明显更新'
  }
  if (assessment.is_same_work === false) {
    return 'AI 判定召回结果不是同一作品'
  }
  return assessment.reason || '本次巡检没有形成新的候选命中'
}

const getFollowRuleTone = (record: PanTransferFollowTaskItem) =>
  FOLLOW_RULE_TONE[String(record.rule_assessment?.risk_level || '').toLowerCase()] || FOLLOW_RULE_TONE.info

const getFollowRuleAlertType = (record: PanTransferFollowTaskItem): 'info' | 'warning' | 'error' => {
  const riskLevel = String(record.rule_assessment?.risk_level || '').toLowerCase()
  if (riskLevel === 'danger') return 'error'
  if (riskLevel === 'warning') return 'warning'
  return 'info'
}

const getRuleExecutionHelp = (record: PanTransferFollowTaskItem) => {
  const executionMode = String(record.rule_assessment?.execution_mode || '').toLowerCase()
  if (executionMode === 'manual_modal') {
    return '当前建议先进入人工确认，核对目录或文件后再同步。'
  }
  if (executionMode === 'recheck_only') {
    return '当前更适合先重新检查，确认最新状态后再处理。'
  }
  if (executionMode === 'wait_candidate') {
    return '当前没有可直接执行的同步规则，先等待新候选或重新检查。'
  }
  if (executionMode === 'busy') {
    return '当前已有检查或同步在进行，请先等待本轮完成。'
  }
  return '当前可直接按规则复用现有资源目录继续同步。'
}

const buildFollowLinkItems = (record: PanTransferFollowTaskItem): FollowLinkChip[] => {
  const items: FollowLinkChip[] = []
  if (record.source_url) {
    items.push({
      key: 'source',
      label: '原链',
      url: record.source_url,
      status:
        !record.last_checked_at && String(record.source_link_status || '').toLowerCase() === 'unknown'
          ? 'pending_check'
          : record.source_link_status,
      detail: [
        '当前绑定原链',
        record.last_checked_at ? `最近检查 ${formatDateTime(record.last_checked_at)}` : '等待首次检查',
      ]
        .filter(Boolean)
        .join('\n'),
    })
  }
  if (record.last_candidate_url) {
    items.push({
      key: 'candidate',
      label: '候选',
      url: record.last_candidate_url,
      status: 'candidate_pending',
      detail: [record.last_candidate_title, record.last_candidate_message_time ? `发现于 ${formatDateTime(record.last_candidate_message_time)}` : ''].filter(Boolean).join('\n'),
    })
  }
  if (record.current_share_url) {
    items.push({
      key: 'share',
      label: '新分享',
      url: record.current_share_url,
      status:
        !record.last_checked_at && String(record.current_share_status || '').toLowerCase() === 'unknown'
          ? 'pending_check'
          : record.current_share_status,
      detail: [
        record.publish_record_title ? `已绑定前台：${record.publish_record_title}` : '当前对外分享',
        record.last_checked_at ? `最近检查 ${formatDateTime(record.last_checked_at)}` : '等待首次检查',
      ]
        .filter(Boolean)
        .join('\n'),
    })
  }
  return items
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

const getFollowSyncKey = (taskId: number, sourceKind: FollowSyncSourceKind, syncMode: 'standard' | FollowSyncMode = 'standard') =>
  `${taskId}:${sourceKind}:${syncMode}`

const FollowTasksSectionV2 = ({ refreshToken, isActive = true }: FollowTasksSectionProps) => {
  const isPageVisible = usePageVisibility()
  const [tasks, setTasks] = useState<PanTransferFollowTaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<FollowStatusFilter>('all')
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10, total: 0 })
  const [queueingTaskId, setQueueingTaskId] = useState<number | null>(null)
  const [clearingCandidateTaskId, setClearingCandidateTaskId] = useState<number | null>(null)
  const [syncingTaskKey, setSyncingTaskKey] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<PanTransferFollowTaskDetailResponse | null>(null)
  const [settingsDraft, setSettingsDraft] = useState<FollowTaskSettingsDraft | null>(null)
  const [savingSettingsTaskId, setSavingSettingsTaskId] = useState<number | null>(null)
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
  const [directoryOpen, setDirectoryOpen] = useState(false)
  const [directoryLoading, setDirectoryLoading] = useState(false)
  const [directoryTitle, setDirectoryTitle] = useState('')
  const [directoryData, setDirectoryData] = useState<PanTransferLinkDirectoryPreviewResponse | null>(null)
  const [directoryLink, setDirectoryLink] = useState<FollowLinkChip | null>(null)
  const [directoryTrail, setDirectoryTrail] = useState<DirectoryTrailItem[]>([])
  const [clearedLogMarkerByTaskId, setClearedLogMarkerByTaskId] = useState<Record<number, number>>({})
  const [clearingDetailLogsTaskId, setClearingDetailLogsTaskId] = useState<number | null>(null)

  const loadTasks = async (
    page = pagination.page,
    pageSize = pagination.pageSize,
    filter = statusFilter,
    options?: { silent?: boolean }
  ) => {
    if (!(options?.silent ?? false)) {
      setLoading(true)
    }
    try {
      const response = await listPanTransferFollowTasks(page, pageSize, filter === 'all' ? undefined : filter)
      setTasks(response.items)
      setPagination({ page: response.page, pageSize: response.page_size, total: response.total })
    } catch (error) {
      message.error(getErrorMessage(error, '加载追更任务失败'))
    } finally {
      if (!(options?.silent ?? false)) {
        setLoading(false)
      }
    }
  }

  const loadTaskDetail = async (taskId: number, options?: { open?: boolean; silent?: boolean }) => {
    if (!(options?.silent ?? false)) {
      setDetailLoading(true)
    }
    try {
      const response = await getPanTransferFollowTaskDetail(taskId)
      setDetailData(response)
      setSettingsDraft((current) => (current?.taskId === response.task.id ? current : buildFollowSettingsDraft(response.task)))
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

  const openDirectoryAt = async (item: FollowLinkChip, trail: DirectoryTrailItem[]) => {
    setDirectoryOpen(true)
    setDirectoryLoading(true)
    setDirectoryLink(item)
    setDirectoryTrail(trail)
    setDirectoryTitle(LINK_ROOT_LABELS[item.key])
    try {
      const current = trail[trail.length - 1]
      const response = await previewPanTransferLinkDirectory({
        url: item.url,
        entry_id: current?.entryId || undefined,
        entry_path: current?.entryPath || undefined,
        entry_name: current?.label || undefined,
      })
      setDirectoryData(response)
      setDirectoryTrail(buildDirectoryTrail(LINK_ROOT_LABELS[item.key], trail, response))
    } catch (error) {
      setDirectoryOpen(false)
      message.error(getErrorMessage(error, '目录预览失败'))
    } finally {
      setDirectoryLoading(false)
    }
  }

  const handleLinkMenuClick = async (actionKey: string, item: FollowLinkChip) => {
    if (actionKey === 'open') return openLink(item.url)
    if (actionKey === 'copy') return copyText(item.url, '已复制链接')
    if (actionKey === 'preview') return openDirectoryAt(item, [{ key: 'root', label: LINK_ROOT_LABELS[item.key] }])
  }

  const openManualSyncModal = async (
    task: PanTransferFollowTaskItem,
    initialSourceKind: FollowSyncSourceKind = 'current',
    initialSyncMode: FollowSyncMode = 'incremental'
  ) => {
    const nextSourceKind =
      initialSourceKind === 'candidate' && task.last_candidate_url ? 'candidate' : 'current'
    resetManualSyncState()
    setManualSyncSourceKind(nextSourceKind)
    setManualSyncMode(initialSyncMode)
    setManualSyncOpen(true)
    await loadManualPreview(task, nextSourceKind, [{ key: 'root', label: DIRECTORY_ROOT_LABELS[nextSourceKind] }])
  }

  useEffect(() => {
    void loadTasks(1, pagination.pageSize, statusFilter)
  }, [refreshToken, statusFilter])

  useEffect(() => {
    if (!isActive || !isPageVisible) return

    void loadTasks(pagination.page, pagination.pageSize, statusFilter, { silent: true })

    if (detailOpen && detailData) {
      void loadTaskDetail(detailData.task.id, { open: false, silent: true })
    }
  }, [detailData?.task.id, detailOpen, isActive, isPageVisible, pagination.page, pagination.pageSize, statusFilter])

  useEffect(() => {
    const hasTransientTaskOnPage = tasks.some((item) => FOLLOW_TRANSIENT_TASK_STATES.has(item.task_state))
    const shouldPollList = isActive && hasTransientTaskOnPage
    const shouldPollDetail =
      isActive &&
      detailOpen &&
      detailData !== null &&
      FOLLOW_TRANSIENT_TASK_STATES.has(detailData.task.task_state)

    if (!isPageVisible || (!shouldPollList && !shouldPollDetail)) return

    const timer = window.setInterval(() => {
      if (shouldPollList) {
        void loadTasks(pagination.page, pagination.pageSize, statusFilter, { silent: true })
      }
      if (shouldPollDetail && detailData) {
        void loadTaskDetail(detailData.task.id, { open: false, silent: true })
      }
    }, 4000)
    return () => window.clearInterval(timer)
  }, [detailData, detailOpen, isActive, isPageVisible, pagination.page, pagination.pageSize, statusFilter, tasks])

  useEffect(() => {
    if (!detailOpen) {
      setManualSyncOpen(false)
      resetManualSyncState()
      setSettingsDraft(null)
    }
  }, [detailOpen])

  const summary = useMemo(() => {
    const activeCount = tasks.filter((item) => item.status === 'active').length
    const alertCount = tasks.filter((item) => ['candidate_found', 'source_invalid', 'share_invalid', 'error'].includes(item.task_state)).length
    const pausedCount = tasks.filter((item) => item.status === 'paused').length
    return { activeCount, alertCount, pausedCount }
  }, [tasks])

  const queueTaskCheck = async (taskId: number) => {
    setQueueingTaskId(taskId)
    try {
      const response = await queuePanTransferFollowTaskCheck(taskId)
      setDetailData((current) => (current?.task.id === taskId ? response : current))
      message.success(`追更任务 #${taskId} 已加入立即检查队列`)
      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
      return response
    } catch (error) {
      message.error(getErrorMessage(error, '加入检查队列失败'))
      return null
    } finally {
      setQueueingTaskId(null)
    }
  }

  const triggerFollowSync = async (
    taskId: number,
    sourceKind: FollowSyncSourceKind,
    syncMode: 'standard' | FollowSyncMode = 'standard'
  ) => {
    const syncKey = getFollowSyncKey(taskId, sourceKind, syncMode)
    setSyncingTaskKey(syncKey)
    try {
      const response = await createPanTransferFollowSyncBatch(taskId, {
        source_kind: sourceKind,
        sync_mode: syncMode,
        reuse_existing_share_if_valid: true,
        update_publish_record: true,
      })
      await loadTaskDetail(taskId, { open: false })
      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
      return response
    } catch (error) {
      message.error(getErrorMessage(error, '创建追更同步批次失败'))
      return null
    } finally {
      setSyncingTaskKey(null)
    }
  }

  const toggleTaskStatus = async (record: PanTransferFollowTaskItem) => {
    try {
      const response =
        record.status === 'active'
          ? await pausePanTransferFollowTask(record.id)
          : await resumePanTransferFollowTask(record.id)
      setDetailData((current) => (current?.task.id === record.id ? response : current))
      message.success(record.status === 'active' ? `追更任务 #${record.id} 已暂停` : `追更任务 #${record.id} 已恢复`)
      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
      return response
    } catch (error) {
      message.error(getErrorMessage(error, record.status === 'active' ? '暂停追更任务失败' : '恢复追更任务失败'))
      return null
    }
  }

  const saveTaskSettings = async () => {
    if (!detailTask || !settingsDraft) return
    setSavingSettingsTaskId(detailTask.id)
    try {
      const response = await updatePanTransferFollowTaskSettings(detailTask.id, {
        check_interval_minutes: settingsDraft.check_interval_minutes,
        candidate_policy: settingsDraft.candidate_policy,
      })
      setDetailData(response)
      setSettingsDraft(buildFollowSettingsDraft(response.task))
      message.success(`追更任务 #${detailTask.id} 设置已保存`)
      await loadTasks(pagination.page, pagination.pageSize, statusFilter, { silent: true })
    } catch (error) {
      message.error(getErrorMessage(error, '保存追更设置失败'))
    } finally {
      setSavingSettingsTaskId(null)
    }
  }

  const clearCandidate = async (taskId: number) => {
    setClearingCandidateTaskId(taskId)
    try {
      const response = await clearPanTransferFollowTaskCandidate(taskId)
      setDetailData((current) => (current?.task.id === taskId ? response : current))
      message.success(`已清空追更任务 #${taskId} 的候选原链`)
      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
    } catch (error) {
      message.error(getErrorMessage(error, '清空候选原链失败'))
    } finally {
      setClearingCandidateTaskId(null)
    }
  }

  const clearTaskLogs = async (taskId: number) => {
    setClearingDetailLogsTaskId(taskId)
    try {
      const response = await clearPanTransferFollowTaskLogs(taskId)
      setDetailData((current) => (current?.task.id === taskId ? response : current))
      setClearedLogMarkerByTaskId((current) => clearFollowLogMarker(current, taskId))
      message.success(`已清理追更任务 #${taskId} 的后端日志`)
    } catch (error) {
      message.error(getErrorMessage(error, '清理追更日志失败'))
    } finally {
      setClearingDetailLogsTaskId(null)
    }
  }

  const deleteTask = async (record: PanTransferFollowTaskItem) => {
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
    }
  }

  const runRuleAction = async (
    task: PanTransferFollowTaskItem,
    ruleKey: 'safe_sync' | 'replace_all' | 'candidate_manual'
  ) => {
    if (ruleKey === 'safe_sync') {
      const response = await triggerFollowSync(task.id, 'current', 'standard')
      if (response) {
        message.success(`已创建规则一安全同步批次 #${response.batch_id}`)
      }
      return
    }
    if (ruleKey === 'replace_all') {
      await openManualSyncModal(task, task.last_candidate_url ? 'candidate' : 'current', 'replace_all')
      return
    }
    await openManualSyncModal(task, task.last_candidate_url ? 'candidate' : 'current', 'incremental')
  }

  const runRecommendedAction = async (task: PanTransferFollowTaskItem) => {
    const executionMode = String(task.rule_assessment?.execution_mode || '').toLowerCase()
    if (executionMode === 'manual_modal') {
      await runRuleAction(task, 'candidate_manual')
      return
    }
    if (executionMode === 'recheck_only') {
      if (task.status !== 'active') {
        message.info('任务已暂停，请先恢复追更后再重新检查。')
        return
      }
      await queueTaskCheck(task.id)
      return
    }
    if (executionMode === 'wait_candidate') {
      if (task.status !== 'active') {
        message.info('任务已暂停，当前请先恢复追更后再重新检查。')
        return
      }
      message.info('当前还没有可直接执行的同步规则，请先等待新候选或手动重新检查。')
      return
    }
    if (executionMode === 'busy') {
      message.info('当前已有检查或同步在进行，请先等待本轮完成。')
      return
    }
    const response = await triggerFollowSync(task.id, 'current', 'standard')
    if (response) {
      message.success(`已按推荐规则创建同步批次 #${response.batch_id}`)
    }
  }

  const buildMoreActionsMenu = (record: PanTransferFollowTaskItem): MenuProps => ({
    items: [
      {
        key: 'advanced',
        icon: <FolderOpenOutlined />,
        label: '高级处理',
      },
      {
        key: 'clear_candidate',
        icon: <CloseCircleOutlined />,
        label: '忽略候选',
        disabled: !record.last_candidate_url,
      },
      {
        key: 'toggle',
        icon: record.status === 'active' ? <PauseCircleOutlined /> : <PlayCircleOutlined />,
        label: record.status === 'active' ? '暂停追更' : '恢复追更',
      },
      {
        key: 'delete',
        icon: <DeleteOutlined />,
        label: '删除任务',
        danger: true,
      },
    ],
    onClick: ({ key }) => {
      if (key === 'advanced') {
        void openManualSyncModal(record, record.last_candidate_url ? 'candidate' : 'current')
        return
      }
      if (key === 'clear_candidate') {
        void clearCandidate(record.id)
        return
      }
      if (key === 'toggle') {
        void toggleTaskStatus(record)
        return
      }
      if (key === 'delete') {
        Modal.confirm({
          title: `确认删除追更任务 #${record.id} 吗？`,
          content: '只删除追更跟踪记录和日志，不会删除已转存的数据或前台消息。',
          okButtonProps: { danger: true },
          onOk: async () => {
            await deleteTask(record)
          },
        })
      }
    },
  })

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
      title: '资源',
      key: 'task_name',
      width: 220,
      render: (_, record) => {
        const mainTitle = getFollowTaskTitle(record)
        return (
          <Tooltip
            title={
              <div>
                <div>{mainTitle}</div>
                <div>点击复制标题</div>
              </div>
            }
          >
            <div className="resource-ops-transfer-title-cell">
              <button
                type="button"
                className="resource-ops-transfer-title-button"
                onClick={() => void copyText(mainTitle, '已复制资源标题')}
              >
                <span className="resource-ops-transfer-title-main">{mainTitle}</span>
              </button>
            </div>
          </Tooltip>
        )
      },
    },
    {
      title: '网盘',
      dataIndex: 'platform',
      key: 'platform',
      width: 92,
      render: (value: string) => <Tag>{value || '-'}</Tag>,
    },
    {
      title: '资源目录',
      key: 'target',
      width: 180,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation resource-ops-transfer-validation--publish-meta resource-ops-transfer-target-cell">
          <small>{record.target_account_name || '未指定账号'}</small>
          <small title={record.fixed_save_path}>{record.fixed_save_path || '未记录固定目录'}</small>
        </div>
      ),
    },
    {
      title: '链接',
      key: 'links',
      render: (_, record) => (
        <div className="resource-ops-transfer-link-stack">
          <div className="resource-ops-transfer-link-row">
            {buildFollowLinkItems(record).map((item) => {
              const statusMeta = getLinkChipMeta(item.status)
              const tip = [item.url, item.detail].filter(Boolean).join('\n')
              const menu: MenuProps = {
                items: [
                  { key: 'open', icon: <LinkOutlined />, label: '访问链接' },
                  { key: 'copy', icon: <CopyOutlined />, label: '复制链接' },
                  { key: 'preview', icon: <EyeOutlined />, label: '查看目录' },
                ],
                onClick: ({ key }) => {
                  void handleLinkMenuClick(String(key), item)
                },
              }
              return (
                <Dropdown key={`${item.key}-${item.url}`} menu={menu} trigger={['contextMenu']}>
                  <Tooltip title={tip}>
                    <button
                      type="button"
                      className="resource-ops-transfer-link-chip"
                      onClick={() => openLink(item.url)}
                    >
                      <span className="resource-ops-transfer-link-chip-label">{item.label}</span>
                      <span className={`resource-ops-transfer-link-chip-status is-${statusMeta.tone}`}>{statusMeta.label}</span>
                    </button>
                  </Tooltip>
                </Dropdown>
              )
            })}
          </div>
          <small>左键访问，右键可复制或查看目录</small>
        </div>
      ),
    },
    {
      title: '规则',
      key: 'rule',
      width: 186,
      render: (_, record) => {
        const ruleTone = getFollowRuleTone(record)
        const ruleTip = (
          <div>
            <div>{record.rule_assessment.rule_label}</div>
            <div>{record.rule_assessment.summary}</div>
            {record.last_error_message ? <div>{record.last_error_message}</div> : <div>{getFollowStatusSummary(record)}</div>}
          </div>
        )
        return (
          <Tooltip title={ruleTip}>
            <div className="resource-ops-transfer-validation resource-ops-transfer-validation--rule-compact">
              <Space wrap size={[6, 6]}>
                <Tag color={ruleTone.color}>{record.rule_assessment.rule_label}</Tag>
                <Tag color={(TASK_STATE_META[record.task_state] || { color: 'default' }).color}>
                  {(TASK_STATE_META[record.task_state] || { label: record.task_state }).label}
                </Tag>
                <Tag color={(TASK_STATUS_META[record.status] || { color: 'default' }).color}>
                  {(TASK_STATUS_META[record.status] || { label: record.status }).label}
                </Tag>
                {record.last_error_message ? <Tag color="error">!</Tag> : null}
              </Space>
            </div>
          </Tooltip>
        )
      },
    },
    {
      title: '检查',
      key: 'sync_meta',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation resource-ops-transfer-validation--publish-meta">
          <small>{`上次检查 ${formatDateTime(record.last_checked_at)}`}</small>
          <small>{getFollowScheduleLine(record)}</small>
          {record.last_sync_batch_id ? (
            <small>{`最近同步 #${record.last_sync_batch_id} · ${record.last_sync_source_kind === 'candidate' ? '候选原链' : '当前原链'}`}</small>
          ) : (
            <small>还没有人工同步记录</small>
          )}
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 148,
      fixed: 'right',
      render: (_, record) => {
        const executionMode = String(record.rule_assessment?.execution_mode || '').toLowerCase()
        const primaryActionIcon =
          executionMode === 'manual_modal' ? (
            <FolderOpenOutlined />
          ) : executionMode === 'recheck_only' ? (
            <SearchOutlined />
          ) : (
            <SyncOutlined />
          )
        const primaryActionTitle =
          executionMode === 'manual_modal'
            ? `执行推荐：${record.rule_assessment.rule_label}`
            : executionMode === 'recheck_only'
              ? '执行推荐：先重新检查'
              : executionMode === 'wait_candidate'
                ? '当前先等待候选原链'
                : executionMode === 'busy'
                  ? '当前任务进行中'
                  : `执行推荐：${record.rule_assessment.rule_label}`
        return (
          <div className="resource-ops-transfer-action-grid resource-ops-transfer-action-grid--wide">
            <Tooltip title="查看详情">
              <Button size="small" type="text" icon={<EyeOutlined />} onClick={() => void loadTaskDetail(record.id, { open: true })} />
            </Tooltip>
            <Tooltip title="立即检查">
              <Button
                size="small"
                type="text"
                icon={<SearchOutlined />}
                loading={queueingTaskId === record.id}
                disabled={record.status !== 'active'}
                onClick={() => void queueTaskCheck(record.id)}
              />
            </Tooltip>
            <Tooltip title={primaryActionTitle}>
              <Button
                size="small"
                type="text"
                icon={primaryActionIcon}
                disabled={
                  !record.rule_assessment.can_execute ||
                  ((executionMode === 'recheck_only' || executionMode === 'wait_candidate') && record.status !== 'active')
                }
                loading={
                  syncingTaskKey === getFollowSyncKey(record.id, 'current', 'standard') ||
                  syncingTaskKey === getFollowSyncKey(record.id, 'candidate', 'standard')
                }
                onClick={() => void runRecommendedAction(record)}
              />
            </Tooltip>
            <Dropdown menu={buildMoreActionsMenu(record)} trigger={['click']}>
              <Tooltip title="更多操作">
                <Button size="small" type="text" icon={<EllipsisOutlined />} />
              </Tooltip>
            </Dropdown>
          </div>
        )
      },
    },
  ]

  const detailTask = detailData?.task ?? null
  const activeSettingsDraft =
    detailTask && settingsDraft?.taskId === detailTask.id ? settingsDraft : detailTask ? buildFollowSettingsDraft(detailTask) : null
  const detailLogs = detailData?.logs ?? []
  const detailLogMarker = detailTask ? clearedLogMarkerByTaskId[detailTask.id] || 0 : 0
  const visibleDetailLogs = detailLogs.filter((log) => log.id > detailLogMarker)
  const visibleDetailLogLines = useMemo(
    () =>
      visibleDetailLogs.map((log) => ({
        key: log.id,
        text: buildFollowTerminalLine(log),
        tone: getFollowLogTone(log),
      })),
    [visibleDetailLogs]
  )
  const hasCandidate = Boolean(detailTask?.last_candidate_link_target_id && detailTask?.last_candidate_url)
  const detailLinkItems = detailTask ? buildFollowLinkItems(detailTask) : []
  const detailReferenceTitles = detailTask?.identity_snapshot.reference_titles ?? []
  const detailSearchQueries = detailTask?.identity_snapshot.search_queries ?? []
  const detailRecallQueries = detailTask?.candidate_recall.queries ?? []
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
                  key: entry.entry_id || entry.path || `${entry.name}-${directoryTrail.length}-${entry.is_dir ? 'dir' : 'file'}`,
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
          <Title level={4}>追更同步</Title>
          <Space>
            <Button onClick={() => void loadTasks(pagination.page, pagination.pageSize, statusFilter)}>
              刷新
            </Button>
            <Segmented
              value={statusFilter}
              options={[
                { label: '全部任务', value: 'all' },
                { label: '启用中', value: 'active' },
                { label: '已暂停', value: 'paused' },
              ]}
              onChange={(value) => setStatusFilter(value as FollowStatusFilter)}
            />
          </Space>
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
            <small>会继续由 worker 定时检查</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页待关注</span>
            <strong>{summary.alertCount}</strong>
            <small>候选原链、原链失效、新分享异常都算在内</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页已暂停</span>
            <strong>{summary.pausedCount}</strong>
            <small>暂停后不会继续自动检查，恢复时会重新排队</small>
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
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无追更任务" /> }}
        />
      </Card>

      <Drawer
        width={980}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailTask ? `追更资源 #${detailTask.id}` : '追更任务详情'}
        extra={
          detailTask ? (
            <Space>
              <Button loading={detailLoading} onClick={() => void loadTaskDetail(detailTask.id, { open: false })}>
                刷新详情
              </Button>
              {detailTask.status === 'active' ? (
                <Button
                  loading={queueingTaskId === detailTask.id}
                  onClick={() => void queueTaskCheck(detailTask.id)}
                >
                  立即检查
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
                { key: 'topic', label: '资源主题', children: getFollowTaskTitle(detailTask) },
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
                { key: 'last_checked', label: '上次检查', children: formatDateTime(detailTask.last_checked_at) },
                { key: 'next_check', label: '下次检查', children: formatDateTime(detailTask.next_check_at) },
              ]}
            />

            {activeSettingsDraft ? (
              <Card
                size="small"
                title="追更设置"
                className="resource-ops-follow-sync-card"
                extra={
                  <Button
                    type="primary"
                    loading={savingSettingsTaskId === detailTask.id}
                    onClick={() => void saveTaskSettings()}
                  >
                    保存设置
                  </Button>
                }
              >
                <div className="resource-ops-follow-settings-grid">
                  <div className="resource-ops-follow-settings-field">
                    <label>巡检间隔：</label>
                    <InputNumber
                      min={15}
                      max={10080}
                      step={15}
                      value={activeSettingsDraft.check_interval_minutes}
                      addonAfter="分钟"
                      style={{ width: '100%' }}
                      onChange={(value) =>
                        setSettingsDraft((current) =>
                          current && current.taskId === detailTask.id
                            ? { ...current, check_interval_minutes: Number(value || DEFAULT_FOLLOW_CHECK_INTERVAL_MINUTES) }
                            : buildFollowSettingsDraft({
                                ...detailTask,
                                check_interval_minutes: Number(value || DEFAULT_FOLLOW_CHECK_INTERVAL_MINUTES),
                              })
                        )
                      }
                    />
                  </div>

                  <div className="resource-ops-follow-settings-field">
                    <label>候选时间范围：</label>
                    <InputNumber
                      min={1}
                      max={90}
                      value={activeSettingsDraft.candidate_policy.lookback_days}
                      addonAfter="天"
                      style={{ width: '100%' }}
                      onChange={(value) =>
                        setSettingsDraft((current) =>
                          current && current.taskId === detailTask.id
                            ? {
                                ...current,
                                candidate_policy: {
                                  ...current.candidate_policy,
                                  lookback_days: Number(value || DEFAULT_FOLLOW_LOOKBACK_DAYS),
                                },
                              }
                            : buildFollowSettingsDraft({
                                ...detailTask,
                                candidate_policy: {
                                  ...detailTask.candidate_policy,
                                  lookback_days: Number(value || DEFAULT_FOLLOW_LOOKBACK_DAYS),
                                },
                              })
                        )
                      }
                    />
                  </div>

                  <div className="resource-ops-follow-settings-field">
                    <label>最多召回候选：</label>
                    <InputNumber
                      min={1}
                      max={30}
                      value={activeSettingsDraft.candidate_policy.max_recall_candidates}
                      style={{ width: '100%' }}
                      onChange={(value) =>
                        setSettingsDraft((current) => {
                          const nextValue = Number(value || DEFAULT_FOLLOW_MAX_RECALL_CANDIDATES)
                          if (current && current.taskId === detailTask.id) {
                            return {
                              ...current,
                              candidate_policy: {
                                ...current.candidate_policy,
                                max_recall_candidates: nextValue,
                                max_judge_candidates: Math.min(current.candidate_policy.max_judge_candidates, nextValue),
                              },
                            }
                          }
                          const nextDraft = buildFollowSettingsDraft(detailTask)
                          return {
                            ...nextDraft,
                            candidate_policy: {
                              ...nextDraft.candidate_policy,
                              max_recall_candidates: nextValue,
                              max_judge_candidates: Math.min(nextDraft.candidate_policy.max_judge_candidates, nextValue),
                            },
                          }
                        })
                      }
                    />
                  </div>

                  <div className="resource-ops-follow-settings-field">
                    <label>最多 AI 判定：</label>
                    <InputNumber
                      min={1}
                      max={Math.max(1, activeSettingsDraft.candidate_policy.max_recall_candidates)}
                      value={activeSettingsDraft.candidate_policy.max_judge_candidates}
                      style={{ width: '100%' }}
                      onChange={(value) =>
                        setSettingsDraft((current) =>
                          current && current.taskId === detailTask.id
                            ? {
                                ...current,
                                candidate_policy: {
                                  ...current.candidate_policy,
                                  max_judge_candidates: Math.min(
                                    Number(value || current.candidate_policy.max_judge_candidates || DEFAULT_FOLLOW_MAX_JUDGE_CANDIDATES),
                                    current.candidate_policy.max_recall_candidates
                                  ),
                                },
                              }
                            : buildFollowSettingsDraft(detailTask)
                        )
                      }
                    />
                  </div>
                </div>
              </Card>
            ) : null}

            <Card size="small" title="AI 识别身份" className="resource-ops-follow-sync-card">
              <div className="resource-ops-follow-sync-meta resource-ops-follow-identity-card">
                <span>{detailTask.identity_snapshot.core_title || getFollowTaskTitle(detailTask)}</span>
                <small>{`当前资源标题：${detailTask.identity_snapshot.resource_title || getFollowTaskTitle(detailTask)}`}</small>
                <small>
                  {[
                    detailTask.identity_snapshot.release_year ? `年份 ${detailTask.identity_snapshot.release_year}` : null,
                    detailTask.identity_snapshot.season ? `季 ${detailTask.identity_snapshot.season}` : null,
                    detailTask.identity_snapshot.latest_episode ? `当前集数 ${detailTask.identity_snapshot.latest_episode}` : null,
                    detailTask.identity_snapshot.content_type || null,
                  ]
                    .filter(Boolean)
                    .join(' · ') || '当前还没有更多结构化身份信息'}
                </small>
                <small>
                  {[
                    detailTask.identity_snapshot.source ? `来源 ${detailTask.identity_snapshot.source}` : null,
                    detailTask.identity_snapshot.used_model ? `模型 ${detailTask.identity_snapshot.used_model}` : null,
                    detailTask.identity_snapshot.updated_at ? `更新时间 ${formatDateTime(detailTask.identity_snapshot.updated_at)}` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ') || '尚未记录 AI 执行元数据'}
                </small>
                {detailTask.identity_snapshot.identity_error ? (
                  <small>{`回退原因：${detailTask.identity_snapshot.identity_error}`}</small>
                ) : null}
              </div>
            </Card>

            <Card size="small" title="候选判定" className="resource-ops-follow-sync-card">
              <div className="resource-ops-follow-sync-meta resource-ops-follow-candidate-card">
                <span>{getFollowCandidateAssessmentSummary(detailTask)}</span>
                <small>
                  {`召回 ${detailTask.candidate_recall.recall_count || 0} 条 · 最多评估 ${detailTask.candidate_recall.judge_limit || 0} 条`}
                </small>
                <small>
                  {[
                    detailTask.candidate_assessment.is_same_work === undefined || detailTask.candidate_assessment.is_same_work === null
                      ? null
                      : `同作品 ${detailTask.candidate_assessment.is_same_work ? '是' : '否'}`,
                    detailTask.candidate_assessment.is_newer === undefined || detailTask.candidate_assessment.is_newer === null
                      ? null
                      : `更晚更新 ${detailTask.candidate_assessment.is_newer ? '是' : '否'}`,
                    detailTask.candidate_assessment.confidence !== undefined && detailTask.candidate_assessment.confidence !== null
                      ? `置信度 ${Number(detailTask.candidate_assessment.confidence).toFixed(2)}`
                      : null,
                  ]
                    .filter(Boolean)
                    .join(' · ') || '本次没有可展示的判定结论'}
                </small>
                {(detailTask.candidate_assessment.current_episode || detailTask.candidate_assessment.candidate_episode) ? (
                  <small>
                    {[
                      detailTask.candidate_assessment.current_episode ? `当前集数 ${detailTask.candidate_assessment.current_episode}` : null,
                      detailTask.candidate_assessment.candidate_episode ? `候选集数 ${detailTask.candidate_assessment.candidate_episode}` : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </small>
                ) : null}
                {detailTask.candidate_assessment.reason ? (
                  <small>{`判定说明：${detailTask.candidate_assessment.reason}`}</small>
                ) : null}
                {(detailReferenceTitles.length > 0 || detailSearchQueries.length > 0 || detailRecallQueries.length > 0) ? (
                  <Collapse
                    ghost
                    className="resource-ops-follow-advanced-collapse"
                    items={[
                      {
                        key: 'recall',
                        label: '识别与召回详情',
                        children: (
                          <div className="resource-ops-follow-sync-meta resource-ops-follow-advanced-meta">
                            {detailReferenceTitles.length > 0 ? (
                              <div className="resource-ops-follow-reference-list">
                                {detailReferenceTitles.map((title, index) => (
                                  <div key={`${title}-${index}`} className="resource-ops-follow-reference-item">
                                    {title}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                            {detailSearchQueries.length > 0 ? (
                              <div className="resource-ops-follow-chip-row">
                                {detailSearchQueries.map((query) => (
                                  <Tag key={query} className="resource-ops-follow-query-tag">
                                    {query}
                                  </Tag>
                                ))}
                              </div>
                            ) : null}
                            {detailRecallQueries.length > 0 ? (
                              <div className="resource-ops-follow-chip-row">
                                {detailRecallQueries.map((query) => (
                                  <Tag key={query} className="resource-ops-follow-query-tag">
                                    {query}
                                  </Tag>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        ),
                      },
                    ]}
                  />
                ) : null}
              </div>
            </Card>

            <Card size="small" title="链接状态" className="resource-ops-follow-sync-card">
              <div className="resource-ops-transfer-link-stack">
                <div className="resource-ops-transfer-link-row">
                  {detailLinkItems.map((item) => {
                    const statusMeta = getLinkChipMeta(item.status)
                    const tip = [item.url, item.detail].filter(Boolean).join('\n')
                    const menu: MenuProps = {
                      items: [
                        { key: 'open', icon: <LinkOutlined />, label: '访问链接' },
                        { key: 'copy', icon: <CopyOutlined />, label: '复制链接' },
                        { key: 'preview', icon: <EyeOutlined />, label: '查看目录' },
                      ],
                      onClick: ({ key }) => {
                        void handleLinkMenuClick(String(key), item)
                      },
                    }
                    return (
                      <Dropdown key={`${item.key}-${item.url}`} menu={menu} trigger={['contextMenu']}>
                        <Tooltip title={tip}>
                          <button
                            type="button"
                            className="resource-ops-transfer-link-chip"
                            onClick={() => openLink(item.url)}
                          >
                            <span className="resource-ops-transfer-link-chip-label">{item.label}</span>
                            <span className={`resource-ops-transfer-link-chip-status is-${statusMeta.tone}`}>{statusMeta.label}</span>
                          </button>
                        </Tooltip>
                      </Dropdown>
                    )
                  })}
                </div>
                <small>左键访问，右键可复制或查看目录。</small>
              </div>
            </Card>

            <Card size="small" title="系统建议" className="resource-ops-follow-sync-card">
              <Alert
                type={getFollowRuleAlertType(detailTask)}
                showIcon
                message={detailTask.rule_assessment.rule_label}
                description={
                  <div className="resource-ops-follow-sync-meta">
                    <small>{detailTask.rule_assessment.summary}</small>
                    <small>{getRuleExecutionHelp(detailTask)}</small>
                    {detailTask.last_sync_batch_id ? (
                      <small>
                        {`最近同步批次 #${detailTask.last_sync_batch_id} · 来源 ${detailTask.last_sync_source_kind === 'candidate' ? '候选原链' : '当前原链'} · 发起时间 ${formatDateTime(detailTask.last_sync_started_at)}`}
                      </small>
                    ) : (
                      <small>{getAutomationSummary(detailTask)}</small>
                    )}
                  </div>
                }
                action={
                  String(detailTask.rule_assessment.execution_mode || '').toLowerCase() === 'recheck_only' ? (
                    <Button size="small" disabled={detailTask.status !== 'active'} onClick={() => void queueTaskCheck(detailTask.id)}>
                      先重新检查
                    </Button>
                  ) : String(detailTask.rule_assessment.execution_mode || '').toLowerCase() === 'busy' ? (
                    <Button size="small" disabled>
                      当前处理中
                    </Button>
                  ) : String(detailTask.rule_assessment.execution_mode || '').toLowerCase() === 'wait_candidate' ? (
                    <Button size="small" disabled={detailTask.status !== 'active'} onClick={() => void queueTaskCheck(detailTask.id)}>
                      重新检查
                    </Button>
                  ) : null
                }
              />
            </Card>

            <Card size="small" title="规则处理" className="resource-ops-follow-sync-card">
              <div className="resource-ops-follow-rule-grid">
                <div className={`resource-ops-follow-rule-card${detailTask.rule_assessment.rule_key === 'safe_sync_current' ? ' is-recommended' : ''}`}>
                  <div className="resource-ops-follow-rule-card-head">
                    <span>规则一：安全同步</span>
                    <Tag color="processing">默认</Tag>
                  </div>
                  <small>适合当前原链仍可用，或只是想刷新对外分享。复用现有资源目录，不主动删除旧内容。</small>
                  <Button
                    type={detailTask.rule_assessment.rule_key === 'safe_sync_current' ? 'primary' : 'default'}
                    loading={syncingTaskKey === getFollowSyncKey(detailTask.id, 'current', 'standard')}
                    onClick={() => void runRuleAction(detailTask, 'safe_sync')}
                  >
                    执行规则一
                  </Button>
                </div>

                <div className="resource-ops-follow-rule-card is-danger">
                  <div className="resource-ops-follow-rule-card-head">
                    <span>规则二：全量替换</span>
                    <Tag color="error">高风险</Tag>
                  </div>
                  <small>先清空当前资源目录，再导入你手动确认的目录或文件。不会默认执行，必须显式确认。</small>
                  <Button danger onClick={() => void runRuleAction(detailTask, 'replace_all')}>
                    进入高风险处理
                  </Button>
                </div>

                <div className={`resource-ops-follow-rule-card${detailTask.rule_assessment.rule_key === 'candidate_manual_review' ? ' is-recommended' : ''}`}>
                  <div className="resource-ops-follow-rule-card-head">
                    <span>规则三：候选人工确认</span>
                    <Tag color={hasCandidate ? 'warning' : 'default'}>{hasCandidate ? '有候选' : '无候选'}</Tag>
                  </div>
                  <small>适合候选原链命中后先人工核对目录结构，再决定增量同步还是其它处理，避免误写入。</small>
                  <Button
                    disabled={!hasCandidate}
                    type={detailTask.rule_assessment.rule_key === 'candidate_manual_review' ? 'primary' : 'default'}
                    onClick={() => void runRuleAction(detailTask, 'candidate_manual')}
                  >
                    进入人工确认
                  </Button>
                </div>
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
                  <div className="resource-ops-follow-sync-actions">
                    <Button size="small" onClick={() => void openManualSyncModal(detailTask, 'candidate', 'incremental')}>
                      进入人工确认
                    </Button>
                    <Button
                      size="small"
                      icon={<CloseCircleOutlined />}
                      loading={clearingCandidateTaskId === detailTask.id}
                      onClick={() => void clearCandidate(detailTask.id)}
                    >
                      清空候选
                    </Button>
                  </div>
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有候选原链" />
              )}
            </Card>

            <Card size="small" title="执行终端" className="resource-ops-transfer-log-card">
              <AppLogTerminal
                description="按真实执行顺序输出检查与同步日志，便于确认候选发现、同步排队和前台回写过程。"
                items={visibleDetailLogLines}
                emptyText="暂无追更检查日志"
                isCleared={detailLogMarker > 0}
                onClearDisplay={() => {
                  if (!detailTask || detailLogs.length <= 0) return
                  setClearedLogMarkerByTaskId((current) => ({
                    ...current,
                    [detailTask.id]: detailLogs[detailLogs.length - 1]?.id || 0,
                  }))
                }}
                onShowAll={() => {
                  if (!detailTask) return
                  setClearedLogMarkerByTaskId((current) => clearFollowLogMarker(current, detailTask.id))
                }}
                canShowAll={detailLogMarker > 0}
                copyPayload={visibleDetailLogLines.map((item) => item.text)}
                copyEmptyText="当前没有可复制的日志"
                copySuccessText="已复制当前日志"
                onClearBackend={detailTask ? () => clearTaskLogs(detailTask.id) : null}
                clearBackendLoading={detailTask ? clearingDetailLogsTaskId === detailTask.id : false}
                clearBackendDisabled={!detailTask || detailLogs.length <= 0}
                clearBackendConfirmTitle="确认清理这条追更任务的后端日志？"
                clearBackendConfirmDescription="这会删除追更检查与同步日志，但不会删除追更任务本身。"
              />
            </Card>
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无追更任务详情" />
        )}
      </Drawer>

      <Modal
        open={manualSyncOpen}
        title="高级处理：同步到现有资源目录"
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
              这里用于高级人工处理。先进入源目录，再勾选当前层级里需要同步的文件或子目录。想选更深层内容时，先点进子目录，再在该层级提交。
            </Paragraph>

            <div className="resource-ops-follow-sync-manual-grid">
              <Card size="small" title="处理配置" className="resource-ops-follow-sync-card">
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

      <Modal
        open={directoryOpen}
        title={directoryTitle ? `${directoryTitle}目录预览` : '目录预览'}
        onCancel={() => {
          setDirectoryOpen(false)
          setDirectoryData(null)
          setDirectoryLink(null)
          setDirectoryTrail([])
        }}
        footer={null}
        width={820}
        destroyOnHidden
      >
        <div className="resource-ops-transfer-modal-stack">
          <Paragraph className="resource-ops-transfer-copy">
            支持继续点进子目录查看结构，不会改动当前追更任务、原链或新分享。
          </Paragraph>
          <div className="resource-ops-transfer-directory-meta">
            {directoryData ? (
              <>
                <Tag>{directoryData.platform}</Tag>
                <Tag color="processing">共 {directoryData.item_count} 项</Tag>
                {directoryData.truncated ? <Tag color="warning">仅显示前 {directoryData.items.length} 项</Tag> : null}
              </>
            ) : null}
          </div>
          <div className="resource-ops-transfer-directory-breadcrumbs">
            {directoryTrail.map((item, index) => (
              <button
                key={item.key}
                type="button"
                className="resource-ops-transfer-directory-crumb"
                onClick={() => {
                  if (!directoryLink) return
                  void openDirectoryAt(directoryLink, directoryTrail.slice(0, index + 1))
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <Table
            size="small"
            rowKey={(entry) => entry.entry_id || entry.path || `${entry.name}-${entry.is_dir ? 'dir' : 'file'}`}
            loading={directoryLoading}
            columns={directoryColumns}
            dataSource={directoryData?.items || []}
            pagination={false}
            scroll={{ y: 420 }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={directoryData?.message || '当前目录为空'}
                />
              ),
            }}
          />
        </div>
      </Modal>
    </>
  )
}

export default FollowTasksSectionV2
