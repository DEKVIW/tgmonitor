import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  InputNumber,
  Modal,
  Progress,
  Segmented,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  TimePicker,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ClusterOutlined,
  DeleteOutlined,
  EyeOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  SaveOutlined,
  SyncOutlined,
} from '@ant-design/icons'

import {
  applyLinkCheckCleanup,
  deleteLinkCheckHistories,
  deleteLinkCheckHistory,
  getActiveLinkCheckTask,
  getLinkCheckDateRange,
  getLinkCheckHistory,
  getLinkCheckPlan,
  getLinkCheckResult,
  getLinkCheckTaskStatus,
  previewLinkCheckTask,
  startLinkCheckTask,
  stopLinkCheckTask,
  updateLinkCheckPlan,
} from '@/api/admin'
import HintTooltip from '@/components/common/HintTooltip'
import type {
  LinkCheckDateRange,
  LinkCheckHistoryBatchDeleteResult,
  LinkCheckPlanResponse,
  LinkCheckPlanUpdate,
  LinkCheckPreviewRequest,
  LinkCheckPreviewResponse,
  LinkCheckTaskCreate,
  LinkCheckTaskHistory,
  LinkCheckTaskResult,
  LinkCheckTaskStatus,
  LinkCleanupApplyRequest,
} from '@/types/admin'
import LinkMaintenanceTools from '@/components/admin/LinkMaintenanceTools'
import './LinkCheckManagerRuntime.css'

const { RangePicker } = DatePicker
const { Text, Title } = Typography

type DateRangeValue = [Dayjs, Dayjs] | null
type ManualSelectionMode = 'smart_count' | 'time_range'
type TraversalOrder = 'newest_first' | 'oldest_first'
type CleanupMode = 'none' | 'remove_invalid_links' | 'delete_message_if_empty'
type InvalidLinkDetail = LinkCheckTaskResult['details'][number]

type ManualDraft = {
  selection_mode: ManualSelectionMode
  range: DateRangeValue
  target_link_count: number
  direction: TraversalOrder
  max_concurrent: number
}

type PlanDraft = {
  is_enabled: boolean
  schedule_time: Dayjs
  timezone: string
  cycle_days: number
  batch_link_target: number
  max_batches_per_run: number
  max_concurrent: number
  traversal_order: TraversalOrder
  cleanup_mode: CleanupMode
  cleanup_min_consecutive_invalid_runs: number
}

type OverviewTone = 'success' | 'accent' | 'warning' | 'neutral'

type OverviewCard = {
  key: string
  icon: ReactNode
  title: string
  status: string
  live: boolean
  chips: Array<{ label: string; tone?: OverviewTone }>
}

const TASK_POLL_INTERVAL = 2000

const statusLabelMap: Record<string, string> = {
  running: '进行中',
  stopping: '停止中',
  stopped: '已停止',
  completed: '已完成',
  failed: '失败',
  pending: '待执行',
  waiting: '顺延中',
  idle: '已空闲',
}

const statusColorMap: Record<string, string> = {
  running: 'processing',
  stopping: 'warning',
  stopped: 'default',
  completed: 'success',
  failed: 'error',
  pending: 'blue',
  waiting: 'warning',
  idle: 'default',
}

const phaseLabelMap: Record<string, string> = {
  queued: '排队中',
  loading_messages: '读取消息',
  checking_links: '检测链接',
  saving_results: '写入结果',
  completed: '已完成',
  failed: '失败',
  stopped: '已停止',
}

const triggerSourceLabelMap: Record<string, string> = {
  manual: '手动',
  scheduled: '自动',
}

const taskModeLabelMap: Record<string, string> = {
  smart_count: '智能分批',
  time_range: '时间范围',
  scheduled_batch: '自动批次',
}

const cleanupModeLabelMap: Record<CleanupMode, string> = {
  none: '仅检测',
  remove_invalid_links: '移除失效链接',
  delete_message_if_empty: '移除失效链接并清空空消息',
}

const resultStatusLabelMap: Record<string, string> = {
  valid: '有效',
  invalid: '失效',
  uncertain: '不确定',
  rate_limited: '限流',
  requires_code: '需提取码',
  format_error: '格式错误',
  unsupported: '暂不支持',
}

const directionOptions = [
  { value: 'newest_first', label: '最新优先' },
  { value: 'oldest_first', label: '最早优先' },
]

const cleanupOptions = [
  { value: 'none', label: '只检测，不自动清理' },
  { value: 'remove_invalid_links', label: '自动移除失效链接' },
  { value: 'delete_message_if_empty', label: '移除失效链接，空消息则删整条' },
]

const createDefaultManualDraft = (): ManualDraft => ({
  selection_mode: 'smart_count',
  range: null,
  target_link_count: 800,
  direction: 'newest_first',
  max_concurrent: 5,
})

const parseBackendDateTime = (value?: string | null) => {
  const normalized = value?.trim()
  if (!normalized) {
    return null
  }

  const hasTimezoneSuffix = /([zZ]|[+-]\d{2}:\d{2})$/.test(normalized)
  const parsed = dayjs(hasTimezoneSuffix ? normalized : `${normalized}Z`)
  return parsed.isValid() ? parsed : null
}

const formatDateTime = (value?: string | null, format = 'YYYY-MM-DD HH:mm') => {
  const parsed = parseBackendDateTime(value)
  return parsed ? parsed.format(format) : '-'
}

const formatDuration = (seconds?: number | null) => {
  if (seconds === undefined || seconds === null) {
    return '-'
  }
  if (seconds < 60) {
    return `${seconds.toFixed(1)} 秒`
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`
  }
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`
}

const formatCount = (value?: number | null) => (typeof value === 'number' ? value.toLocaleString('zh-CN') : '-')

const getTriggerSourceLabel = (value?: string | null) => triggerSourceLabelMap[value || ''] || '手动'
const getTaskModeLabel = (value?: string | null) => taskModeLabelMap[value || ''] || '时间范围'
const getStatusLabel = (value?: string | null) => statusLabelMap[value || ''] || value || '-'
const getPhaseLabel = (value?: string | null) => phaseLabelMap[value || ''] || value || '-'
const getResultStatusLabel = (value?: string | null) => resultStatusLabelMap[value || ''] || value || '-'

const toPlanTimeValue = (hour: number, minute: number) =>
  dayjs().hour(hour).minute(minute).second(0).millisecond(0)

const buildPlanDraftFromResponse = (plan: LinkCheckPlanResponse): PlanDraft => ({
  is_enabled: plan.is_enabled,
  schedule_time: toPlanTimeValue(plan.schedule_hour, plan.schedule_minute),
  timezone: plan.timezone,
  cycle_days: plan.cycle_days,
  batch_link_target: plan.batch_link_target,
  max_batches_per_run: plan.max_batches_per_run,
  max_concurrent: plan.max_concurrent,
  traversal_order: plan.traversal_order,
  cleanup_mode: plan.cleanup_mode,
  cleanup_min_consecutive_invalid_runs: plan.cleanup_min_consecutive_invalid_runs,
})

const buildPlanPayload = (planName: string, draft: PlanDraft): LinkCheckPlanUpdate => ({
  name: planName,
  is_enabled: draft.is_enabled,
  schedule_hour: draft.schedule_time.hour(),
  schedule_minute: draft.schedule_time.minute(),
  timezone: draft.timezone,
  cycle_days: draft.cycle_days,
  batch_link_target: draft.batch_link_target,
  max_batches_per_run: draft.max_batches_per_run,
  max_concurrent: draft.max_concurrent,
  traversal_order: draft.traversal_order,
  cleanup_mode: draft.cleanup_mode,
  cleanup_min_consecutive_invalid_runs: draft.cleanup_min_consecutive_invalid_runs,
})

const buildDefaultRange = (bounds?: LinkCheckDateRange | null): DateRangeValue => {
  if (!bounds?.max_date) {
    return null
  }

  const maxDate = dayjs(bounds.latest_message_date || bounds.max_date)
  const minDate = bounds.min_date ? dayjs(bounds.min_date) : maxDate
  const startDate = maxDate.isBefore(minDate) ? minDate : maxDate
  return [startDate, maxDate]
}

const clampRangeToBounds = (range: DateRangeValue, bounds?: LinkCheckDateRange | null): DateRangeValue => {
  const fallbackRange = buildDefaultRange(bounds)
  if (!range || !bounds?.max_date) {
    return fallbackRange
  }

  const minDate = bounds.min_date ? dayjs(bounds.min_date) : null
  const maxDate = dayjs(bounds.max_date)
  let [startDate, endDate] = range

  if (minDate && startDate.isBefore(minDate)) {
    startDate = minDate
  }
  if (minDate && endDate.isBefore(minDate)) {
    endDate = minDate
  }
  if (startDate.isAfter(maxDate)) {
    startDate = maxDate
  }
  if (endDate.isAfter(maxDate)) {
    endDate = maxDate
  }
  if (startDate.isAfter(endDate)) {
    startDate = endDate
  }

  return [startDate, endDate]
}

const buildPreviewRequestFromDraft = (draft: ManualDraft): LinkCheckPreviewRequest | null => {
  if (draft.selection_mode === 'time_range') {
    if (!draft.range) {
      return null
    }
    return {
      selection_mode: 'time_range',
      range_start: draft.range[0].format('YYYY-MM-DD'),
      range_end: draft.range[1].format('YYYY-MM-DD'),
      direction: draft.direction,
    }
  }

  if (!draft.target_link_count || draft.target_link_count <= 0) {
    return null
  }
  return {
    selection_mode: 'smart_count',
    target_link_count: draft.target_link_count,
    direction: draft.direction,
  }
}

const buildTaskPayloadFromDraft = (draft: ManualDraft): LinkCheckTaskCreate | null => {
  if (draft.selection_mode === 'time_range') {
    if (!draft.range) {
      return null
    }
    return {
      selection_mode: 'time_range',
      range_start: draft.range[0].format('YYYY-MM-DD'),
      range_end: draft.range[1].format('YYYY-MM-DD'),
      direction: draft.direction,
      max_concurrent: draft.max_concurrent,
    }
  }

  if (!draft.target_link_count || draft.target_link_count <= 0) {
    return null
  }
  return {
    selection_mode: 'smart_count',
    target_link_count: draft.target_link_count,
    direction: draft.direction,
    max_concurrent: draft.max_concurrent,
  }
}

const createFieldLabel = (title: string, hint: string) => (
  <div className="link-check-runtime-field-label">
    <Text strong>{title}</Text>
    <HintTooltip content={hint} />
  </div>
)

const LinkCheckManagerRuntime = () => {
  const [dateBounds, setDateBounds] = useState<LinkCheckDateRange | null>(null)
  const [dateBoundsLoading, setDateBoundsLoading] = useState(false)
  const [manualDraft, setManualDraft] = useState<ManualDraft>(createDefaultManualDraft)
  const [manualPreview, setManualPreview] = useState<LinkCheckPreviewResponse | null>(null)
  const [manualPreviewLoading, setManualPreviewLoading] = useState(false)
  const [manualPreviewError, setManualPreviewError] = useState<string | null>(null)
  const [planData, setPlanData] = useState<LinkCheckPlanResponse | null>(null)
  const [planDraft, setPlanDraft] = useState<PlanDraft | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [planSaving, setPlanSaving] = useState(false)
  const [taskStarting, setTaskStarting] = useState(false)
  const [taskStopping, setTaskStopping] = useState(false)
  const [currentTask, setCurrentTask] = useState<LinkCheckTaskStatus | null>(null)
  const [history, setHistory] = useState<LinkCheckTaskHistory[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [selectedHistoryIds, setSelectedHistoryIds] = useState<number[]>([])
  const [resultModalVisible, setResultModalVisible] = useState(false)
  const [selectedResult, setSelectedResult] = useState<LinkCheckTaskResult | null>(null)
  const [resultLoading, setResultLoading] = useState(false)
  const [cleanupMode, setCleanupMode] = useState<LinkCleanupApplyRequest['mode']>('remove_invalid_links')
  const [cleanupLoading, setCleanupLoading] = useState(false)
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logConsoleRef = useRef<HTMLDivElement | null>(null)
  const previewRequestRef = useRef(0)

  const minDate = dateBounds?.min_date ? dayjs(dateBounds.min_date) : null
  const maxDate = dayjs(dateBounds?.max_date || dayjs().format('YYYY-MM-DD'))
  const currentTaskRunning = currentTask?.status === 'running' || currentTask?.status === 'stopping'
  const selectedHistoryRows = history.filter((item) => selectedHistoryIds.includes(item.id))
  const selectedHistoryCheckTimes = selectedHistoryRows.map((item) => item.check_time)
  const latestHistory = history[0] || null
  const planOverview = planData?.overview
  const taskLinkLimit = planOverview?.task_link_limit ?? manualPreview?.task_link_limit ?? 5000
  const taskConcurrencyLimit = planOverview?.task_concurrency_limit ?? 10
  const manualPreviewRequest = buildPreviewRequestFromDraft(manualDraft)

  const planBaseline = useMemo(() => {
    if (!planData) {
      return ''
    }
    return JSON.stringify(buildPlanPayload(planData.name, buildPlanDraftFromResponse(planData)))
  }, [planData])

  const planCurrent = useMemo(() => {
    if (!planData || !planDraft) {
      return ''
    }
    return JSON.stringify(buildPlanPayload(planData.name, planDraft))
  }, [planData, planDraft])

  const planDirty = Boolean(planData && planDraft && planBaseline !== planCurrent)
  const invalidDetails = selectedResult?.details.filter((detail) => !detail.is_valid) || []

  useEffect(() => {
    void loadInitialData()

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (logConsoleRef.current) {
      logConsoleRef.current.scrollTop = logConsoleRef.current.scrollHeight
    }
  }, [currentTask?.logs?.length])

  useEffect(() => {
    setSelectedHistoryIds((current) => current.filter((id) => history.some((item) => item.id === id)))
  }, [history])

  useEffect(() => {
    if (!dateBounds) {
      return
    }
    setManualDraft((current) => ({
      ...current,
      range: clampRangeToBounds(current.range, dateBounds),
    }))
  }, [dateBounds?.min_date, dateBounds?.max_date, dateBounds?.latest_message_date])

  useEffect(() => {
    if (!planOverview) {
      return
    }

    setManualDraft((current) => ({
      ...current,
      target_link_count: Math.min(current.target_link_count, planOverview.task_link_limit || current.target_link_count),
      max_concurrent: Math.min(current.max_concurrent, planOverview.task_concurrency_limit || current.max_concurrent),
    }))
  }, [planOverview?.task_link_limit, planOverview?.task_concurrency_limit])

  useEffect(() => {
    if (!manualPreviewRequest) {
      previewRequestRef.current += 1
      setManualPreview(null)
      setManualPreviewError(null)
      setManualPreviewLoading(false)
      return
    }

    const timer = setTimeout(() => {
      void loadManualPreview(manualPreviewRequest, false)
    }, 260)

    return () => clearTimeout(timer)
  }, [
    manualDraft.selection_mode,
    manualDraft.range?.[0]?.format('YYYY-MM-DD'),
    manualDraft.range?.[1]?.format('YYYY-MM-DD'),
    manualDraft.target_link_count,
    manualDraft.direction,
  ])

  useEffect(() => {
    if (!planOverview?.refreshing || planSaving || planDirty) {
      return
    }

    const timer = window.setTimeout(() => {
      void loadPlan({ surfaceError: false })
    }, 2500)

    return () => window.clearTimeout(timer)
  }, [planOverview?.refreshing, planOverview?.generated_at, planSaving, planDirty])

  const loadInitialData = async () => {
    await Promise.all([loadDateBounds(), loadPlan(), loadHistory(), restoreActiveTask()])
  }

  const loadDateBounds = async () => {
    setDateBoundsLoading(true)
    try {
      const result = await getLinkCheckDateRange()
      setDateBounds(result)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载链接检测数据范围失败')
    } finally {
      setDateBoundsLoading(false)
    }
  }

  const loadPlan = async (options?: { surfaceError?: boolean }) => {
    const surfaceError = options?.surfaceError ?? true
    setPlanLoading(true)
    try {
      const result = await getLinkCheckPlan()
      setPlanData(result)
      setPlanDraft(buildPlanDraftFromResponse(result))
    } catch (error: any) {
      if (surfaceError) {
        message.error(error.response?.data?.detail || '加载自动巡检计划失败')
      }
    } finally {
      setPlanLoading(false)
    }
  }

  const loadHistory = async () => {
    setHistoryLoading(true)
    try {
      const result = await getLinkCheckHistory(30)
      setHistory(result)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载链接检测历史失败')
    } finally {
      setHistoryLoading(false)
    }
  }

  const restoreActiveTask = async () => {
    try {
      const task = await getActiveLinkCheckTask()
      setCurrentTask(task)
      startPolling(task.task_id)
    } catch (error: any) {
      if (error?.response?.status !== 404) {
        console.error('restoreActiveTask failed', error)
      }
    }
  }

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }

  const startPolling = (taskId: string) => {
    stopPolling()

    pollingIntervalRef.current = setInterval(async () => {
      try {
        const status = await getLinkCheckTaskStatus(taskId)
        setCurrentTask(status)

        if (status.status === 'completed' || status.status === 'failed' || status.status === 'stopped') {
          stopPolling()
          await Promise.all([loadHistory(), loadPlan()])
        }
      } catch (error: any) {
        if (error?.response?.status !== 404) {
          console.error('getLinkCheckTaskStatus failed', error)
        }
      }
    }, TASK_POLL_INTERVAL)
  }

  const loadManualPreview = async (payload: LinkCheckPreviewRequest, surfaceError: boolean) => {
    const requestId = previewRequestRef.current + 1
    previewRequestRef.current = requestId
    setManualPreviewLoading(true)

    try {
      const result = await previewLinkCheckTask(payload)
      if (previewRequestRef.current !== requestId) {
        return
      }

      setManualPreview(result)
      setManualPreviewError(null)
    } catch (error: any) {
      if (previewRequestRef.current !== requestId) {
        return
      }

      const detail = error.response?.data?.detail || '加载本次预估失败'
      setManualPreview(null)
      setManualPreviewError(detail)
      if (surfaceError) {
        message.error(detail)
      }
    } finally {
      if (previewRequestRef.current === requestId) {
        setManualPreviewLoading(false)
      }
    }
  }

  const handleRefreshPreview = () => {
    const payload = buildPreviewRequestFromDraft(manualDraft)
    if (!payload) {
      message.warning('请先补全手动检测条件')
      return
    }
    void loadManualPreview(payload, true)
  }

  const handleManualModeChange = (value: string | number) => {
    const nextMode = value as ManualSelectionMode
    setManualDraft((current) => ({
      ...current,
      selection_mode: nextMode,
      range: nextMode === 'time_range' ? current.range || buildDefaultRange(dateBounds) : current.range,
    }))
  }

  const handleSavePlan = async () => {
    if (!planData || !planDraft) {
      return
    }

    setPlanSaving(true)
    try {
      const updated = await updateLinkCheckPlan(buildPlanPayload(planData.name, planDraft))
      setPlanData(updated)
      setPlanDraft(buildPlanDraftFromResponse(updated))
      message.success(updated.overview?.refreshing ? '自动巡检计划已保存，概览正在后台刷新' : '自动巡检计划已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存自动巡检计划失败')
    } finally {
      setPlanSaving(false)
    }
  }

  const handleStartTask = async () => {
    const payload = buildTaskPayloadFromDraft(manualDraft)
    if (!payload) {
      message.warning('请先补全手动检测条件')
      return
    }

    setTaskStarting(true)
    try {
      const task = await startLinkCheckTask(payload)
      setCurrentTask(task)
      startPolling(task.task_id)

      if (task.reused_existing) {
        message.info('已有检测任务正在运行，已恢复到当前任务')
      } else {
        message.success('链接检测任务已启动')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '启动链接检测任务失败')
    } finally {
      setTaskStarting(false)
    }
  }

  const handleStopTask = () => {
    if (!currentTask?.task_id || !currentTaskRunning) {
      return
    }

    Modal.confirm({
      title: '停止当前检测任务？',
      content: '会等待当前批次安全收尾，不会强制中断数据库写入。',
      okText: '停止任务',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setTaskStopping(true)
        try {
          const nextTask = await stopLinkCheckTask(currentTask.task_id)
          setCurrentTask(nextTask)
          message.success('已发送停止请求')
        } catch (error: any) {
          message.error(error.response?.data?.detail || '停止任务失败')
        } finally {
          setTaskStopping(false)
        }
      },
    })
  }

  const handleViewResult = async (checkTime: string) => {
    setResultModalVisible(true)
    setResultLoading(true)
    setSelectedResult(null)

    try {
      const result = await getLinkCheckResult(checkTime)
      setSelectedResult(result)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载检测结果失败')
      setResultModalVisible(false)
    } finally {
      setResultLoading(false)
    }
  }

  const handleDeleteHistory = (checkTime: string) => {
    Modal.confirm({
      title: '删除这次检测历史？',
      content: '只删除检测记录，不会回滚已经执行过的死链清理。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteLinkCheckHistory(checkTime)
          setSelectedHistoryIds((current) =>
            current.filter((id) => !history.some((item) => item.id === id && item.check_time === checkTime))
          )
          if (selectedResult?.stats.check_time === checkTime) {
            setResultModalVisible(false)
            setSelectedResult(null)
          }
          await loadHistory()
          message.success('检测历史已删除')
        } catch (error: any) {
          message.error(error.response?.data?.detail || '删除检测历史失败')
        }
      },
    })
  }

  const handleBatchDeleteHistory = () => {
    if (selectedHistoryCheckTimes.length === 0) {
      message.warning('请先勾选要删除的检测历史')
      return
    }

    Modal.confirm({
      title: `删除已选中的 ${selectedHistoryCheckTimes.length} 条检测历史？`,
      content: '只删除检测记录，不会回滚已经执行过的死链清理。',
      okText: '批量删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const result: LinkCheckHistoryBatchDeleteResult = await deleteLinkCheckHistories({
            check_times: selectedHistoryCheckTimes,
          })

          if (
            selectedResult?.stats.check_time &&
            selectedHistoryCheckTimes.includes(selectedResult.stats.check_time)
          ) {
            setResultModalVisible(false)
            setSelectedResult(null)
          }

          setSelectedHistoryIds([])
          await loadHistory()

          const missingText =
            result.missing_check_times.length > 0
              ? `，另有 ${result.missing_check_times.length} 条记录已经不存在`
              : ''
          message.success(`已删除 ${result.deleted_runs} 条检测历史${missingText}`)
        } catch (error: any) {
          message.error(error.response?.data?.detail || '批量删除检测历史失败')
        }
      },
    })
  }

  const handleApplyCleanup = () => {
    if (!selectedResult?.stats?.check_time) {
      return
    }

    const actionText =
      cleanupMode === 'delete_message_if_empty'
        ? '会移除本次检测确认失效的网盘链接，如果消息里没有任何有效网盘链接，则会删除整条消息。'
        : '只会移除本次检测确认失效的网盘链接，保留消息正文和仍然有效的其他链接。'

    Modal.confirm({
      title: '确认应用死链清理',
      content: actionText,
      okText: '开始清理',
      cancelText: '取消',
      okButtonProps: { danger: cleanupMode === 'delete_message_if_empty' },
      onOk: async () => {
        setCleanupLoading(true)
        try {
          const result = await applyLinkCheckCleanup(selectedResult.stats.check_time, {
            mode: cleanupMode,
            dry_run: false,
          })
          message.success(
            `清理完成：移除 ${result.removed_links} 个失效链接，更新 ${result.updated_messages} 条消息，删除 ${result.deleted_messages} 条消息`
          )
          const refreshed = await getLinkCheckResult(selectedResult.stats.check_time)
          setSelectedResult(refreshed)
          await Promise.all([loadHistory(), loadPlan({ surfaceError: false })])
        } catch (error: any) {
          message.error(error.response?.data?.detail || '应用死链清理失败')
        } finally {
          setCleanupLoading(false)
        }
      },
    })
  }

  const toggleHistorySelection = (record: LinkCheckTaskHistory) => {
    setSelectedHistoryIds((current) =>
      current.includes(record.id) ? current.filter((id) => id !== record.id) : [...current, record.id]
    )
  }

  const disabledRangeDate = (current: Dayjs) => {
    if (current.isAfter(maxDate.endOf('day'))) {
      return true
    }
    if (minDate && current.isBefore(minDate.startOf('day'))) {
      return true
    }
    return false
  }

  const buildRangePreset = (days: number) => {
    const endDate = dayjs(dateBounds?.latest_message_date || dateBounds?.max_date || dayjs().format('YYYY-MM-DD'))
    const minLimit = dateBounds?.min_date ? dayjs(dateBounds.min_date) : endDate
    const startDate = endDate.subtract(days - 1, 'day')
    return [startDate.isBefore(minLimit) ? minLimit : startDate, endDate] as [Dayjs, Dayjs]
  }

  const historyColumns: TableProps<LinkCheckTaskHistory>['columns'] = [
    {
      title: '检测时间',
      dataIndex: 'check_time',
      key: 'check_time',
      sorter: (a, b) =>
        (parseBackendDateTime(a.check_time)?.valueOf() || 0) - (parseBackendDateTime(b.check_time)?.valueOf() || 0),
      defaultSortOrder: 'descend',
      render: (value: string) => <span title={formatDateTime(value, 'YYYY-MM-DD HH:mm:ss')}>{formatDateTime(value)}</span>,
    },
    {
      title: '来源',
      dataIndex: 'trigger_source',
      key: 'trigger_source',
      filters: [
        { text: '手动', value: 'manual' },
        { text: '自动', value: 'scheduled' },
      ],
      onFilter: (value, record) => (record.trigger_source || 'manual') === value,
      render: (value?: string) => (
        <Tag color={value === 'scheduled' ? 'blue' : 'default'}>{getTriggerSourceLabel(value)}</Tag>
      ),
    },
    {
      title: '模式',
      dataIndex: 'task_mode',
      key: 'task_mode',
      filters: [
        { text: '智能分批', value: 'smart_count' },
        { text: '时间范围', value: 'time_range' },
        { text: '自动批次', value: 'scheduled_batch' },
      ],
      onFilter: (value, record) => (record.task_mode || 'time_range') === value,
      render: (value?: string) => <Tag>{getTaskModeLabel(value)}</Tag>,
    },
    {
      title: '范围',
      dataIndex: 'scope_label',
      key: 'scope_label',
      ellipsis: true,
      render: (value?: string) => (
        <span className="link-check-runtime-history-scope" title={value || '-'}>
          {value || '-'}
        </span>
      ),
    },
    {
      title: '链接',
      dataIndex: 'total_links',
      key: 'total_links',
      align: 'right',
      sorter: (a, b) => a.total_links - b.total_links,
      render: (value: number) => formatCount(value),
    },
    {
      title: '失效',
      dataIndex: 'invalid_links',
      key: 'invalid_links',
      align: 'right',
      sorter: (a, b) => a.invalid_links - b.invalid_links,
      render: (value: number) => <Tag color="error">{value}</Tag>,
    },
    {
      title: '用时',
      dataIndex: 'duration',
      key: 'duration',
      sorter: (a, b) => (a.duration || 0) - (b.duration || 0),
      render: (value?: number) => formatDuration(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => <Tag color={statusColorMap[value] || 'default'}>{getStatusLabel(value)}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: LinkCheckTaskHistory) => (
        <Space size="small" wrap={false}>
          <Button
            size="small"
            type="link"
            icon={<EyeOutlined />}
            onClick={(event) => {
              event.stopPropagation()
              void handleViewResult(record.check_time)
            }}
          >
            查看
          </Button>
          <Button
            size="small"
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={(event) => {
              event.stopPropagation()
              handleDeleteHistory(record.check_time)
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const overviewCards: OverviewCard[] = [
    {
      key: 'dataset',
      icon: <CalendarOutlined />,
      title: '数据范围',
      status: planOverview?.total_links ? `${formatCount(planOverview.total_links)} 链接` : '等待数据',
      live: Boolean(planOverview?.total_links),
      chips: [
        { label: dateBounds?.min_date ? `起始 ${dateBounds.min_date}` : '暂无起始时间', tone: 'neutral' },
        {
          label: dateBounds?.latest_message_date ? `最新 ${dateBounds.latest_message_date}` : '暂无最新消息',
          tone: 'accent',
        },
        { label: `${formatCount(planOverview?.total_messages_with_links || 0)} 条消息`, tone: 'success' },
      ],
    },
    {
      key: 'preview',
      icon: <ClusterOutlined />,
      title: '本次预估',
      status: manualPreviewLoading
        ? '正在估算'
        : manualPreview
          ? manualPreview.can_start
            ? '可以启动'
            : '需要调整'
          : '等待输入',
      live: Boolean(manualPreview?.can_start),
      chips: [
        { label: manualDraft.selection_mode === 'smart_count' ? '智能分批' : '时间范围', tone: 'accent' },
        {
          label:
            manualPreview && !manualPreviewLoading
              ? `${formatCount(manualPreview.estimated_links)} 链接`
              : '未生成预估',
          tone: manualPreview?.can_start ? 'success' : 'neutral',
        },
        {
          label:
            manualPreview && manualPreview.recommended_batch_count > 1
              ? `建议 ${manualPreview.recommended_batch_count} 批`
              : '单批可执行',
          tone: manualPreview && manualPreview.recommended_batch_count > 1 ? 'warning' : 'neutral',
        },
      ],
    },
    {
      key: 'plan',
      icon: <RadarChartOutlined />,
      title: '自动巡检',
      status: planDraft?.is_enabled ? '已启用' : '已暂停',
      live: Boolean(planDraft?.is_enabled),
      chips: [
        { label: planDraft ? `每日 ${planDraft.schedule_time.format('HH:mm')}` : '等待加载', tone: 'accent' },
        {
          label: planOverview?.estimated_days_to_complete_cycle
            ? `约 ${planOverview.estimated_days_to_complete_cycle} 天一轮`
            : '尚无覆盖估算',
          tone: planOverview?.can_finish_within_cycle ? 'success' : 'warning',
        },
        {
          label: planData?.next_run_at ? `下次 ${formatDateTime(planData.next_run_at, 'MM-DD HH:mm')}` : '未安排下次执行',
          tone: 'neutral',
        },
      ],
    },
    {
      key: 'task',
      icon: <ClockCircleOutlined />,
      title: '当前任务',
      status: currentTask ? getStatusLabel(currentTask.status) : latestHistory ? `最近 ${getStatusLabel(latestHistory.status)}` : '空闲',
      live: Boolean(currentTaskRunning),
      chips: currentTask
        ? [
            { label: getTriggerSourceLabel(currentTask.trigger_source), tone: 'accent' },
            { label: getTaskModeLabel(currentTask.task_mode), tone: 'neutral' },
            { label: `${formatCount(currentTask.checked_links || 0)} / ${formatCount(currentTask.total_links || 0)}`, tone: 'success' },
          ]
        : latestHistory
          ? [
              { label: latestHistory.check_time ? formatDateTime(latestHistory.check_time, 'MM-DD HH:mm') : '暂无时间', tone: 'neutral' },
              { label: `${formatCount(latestHistory.total_links)} 链接`, tone: 'accent' },
              { label: `${latestHistory.invalid_links} 失效`, tone: 'warning' },
            ]
          : [
              { label: '暂无运行任务', tone: 'neutral' },
              { label: '可以手动启动', tone: 'accent' },
            ],
    },
  ]

  return (
    <div className="link-check-runtime">
      <div className="link-check-runtime-overview-grid">
        {overviewCards.map((card) => (
          <div key={card.key} className="link-check-runtime-overview-card">
            <div className="link-check-runtime-overview-icon-shell">
              <span className="link-check-runtime-overview-icon">{card.icon}</span>
            </div>
            <div className="link-check-runtime-overview-content">
              <div className="link-check-runtime-overview-title-row">
                <span className={`link-check-runtime-overview-dot ${card.live ? 'is-live' : 'is-idle'}`} />
                <span className="link-check-runtime-overview-title">{card.title}</span>
              </div>
              <div className="link-check-runtime-overview-status">{card.status}</div>
              <div className="link-check-runtime-overview-meta-row">
                {card.chips.map((chip) => (
                  <span
                    key={`${card.key}-${chip.label}`}
                    className={`link-check-runtime-overview-meta is-${chip.tone || 'neutral'}`}
                  >
                    {chip.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="link-check-runtime-main-grid">
        <Card
          className="link-check-runtime-card"
          loading={dateBoundsLoading && !dateBounds}
          title={
            <div className="link-check-runtime-card-heading">
              <div className="link-check-runtime-card-heading-main">
                <span className="link-check-runtime-card-title">手动检测</span>
                <Text type="secondary">按链接数切片或按日期范围抽查</Text>
              </div>
            </div>
          }
          extra={
            <Button icon={<SyncOutlined />} onClick={handleRefreshPreview} disabled={!manualPreviewRequest}>
              刷新预估
            </Button>
          }
        >
          <div className="link-check-runtime-section">
            <div className="link-check-runtime-segmented-row">
              <div className="link-check-runtime-field-label">
                <Text strong>检测方式</Text>
                <HintTooltip content="推荐优先用智能分批，它按链接数量切片，能稳定控制每次任务规模。" />
              </div>
              <Segmented
                value={manualDraft.selection_mode}
                onChange={handleManualModeChange}
                options={[
                  { label: '智能分批', value: 'smart_count' },
                  { label: '时间范围', value: 'time_range' },
                ]}
              />
            </div>

            <div className="link-check-runtime-field-grid">
              {manualDraft.selection_mode === 'smart_count' ? (
                <>
                  <div className="link-check-runtime-field">
                    {createFieldLabel('目标链接数', '每次尽量凑到多少条链接再启动任务，适合把总量切成稳定批次。')}
                    <InputNumber
                      className="link-check-runtime-compact-control"
                      min={1}
                      max={taskLinkLimit}
                      value={manualDraft.target_link_count}
                      onChange={(value) =>
                        setManualDraft((current) => ({
                          ...current,
                          target_link_count: Math.max(1, Number(value || 1)),
                        }))
                      }
                    />
                  </div>
                  <div className="link-check-runtime-field">
                    {createFieldLabel('遍历方向', '最新优先适合巡查新内容，最早优先适合补扫旧库存。')}
                    <Select
                      className="link-check-runtime-compact-control"
                      value={manualDraft.direction}
                      options={directionOptions}
                      onChange={(value) =>
                        setManualDraft((current) => ({
                          ...current,
                          direction: value as TraversalOrder,
                        }))
                      }
                    />
                  </div>
                </>
              ) : (
                <div className="link-check-runtime-field is-wide">
                  {createFieldLabel('日期范围', '适合复查某一段时间内的消息。如果链接总量超出单任务上限，预估区会给出拆分建议。')}
                  <RangePicker
                    className="link-check-runtime-range-control"
                    allowClear={false}
                    inputReadOnly
                    value={manualDraft.range}
                    format="YYYY-MM-DD"
                    disabledDate={disabledRangeDate}
                    presets={[
                      { label: '最近 1 天', value: buildRangePreset(1) },
                      { label: '最近 7 天', value: buildRangePreset(7) },
                      { label: '最近 30 天', value: buildRangePreset(30) },
                    ]}
                    onChange={(value) =>
                      setManualDraft((current) => ({
                        ...current,
                        range: value && value[0] && value[1] ? [value[0], value[1]] : null,
                      }))
                    }
                  />
                  <Text type="secondary" className="link-check-runtime-helper-text">
                    {dateBoundsLoading
                      ? '正在加载可选日期范围...'
                      : `最早 ${dateBounds?.min_date || '暂无'}，最新 ${dateBounds?.latest_message_date || '暂无'}，最晚可选到 ${dateBounds?.max_date || dayjs().format('YYYY-MM-DD')}`}
                  </Text>
                </div>
              )}

              <div className="link-check-runtime-field">
                {createFieldLabel('并发数', '控制同一批任务里同时检测多少条链接，建议保持在安全上限以内。')}
                <InputNumber
                  className="link-check-runtime-compact-control"
                  min={1}
                  max={taskConcurrencyLimit}
                  value={manualDraft.max_concurrent}
                  onChange={(value) =>
                    setManualDraft((current) => ({
                      ...current,
                      max_concurrent: Math.max(1, Number(value || 1)),
                    }))
                  }
                />
              </div>
            </div>

            <div className="link-check-runtime-preview-panel">
              <div className="link-check-runtime-panel-heading">
                <div>
                  <span className="link-check-runtime-panel-title">本次预估</span>
                  <Text type="secondary">先确认命中的规模，再启动任务</Text>
                </div>
                {manualPreviewLoading ? <Spin size="small" /> : null}
              </div>

              {manualPreviewError ? (
                <Alert type="error" showIcon message={manualPreviewError} />
              ) : manualPreview ? (
                <>
                  <div className="link-check-runtime-preview-scope">
                    <Text strong>{manualPreview.scope_label}</Text>
                    <Tag color={manualPreview.can_start ? 'success' : 'warning'}>
                      {manualPreview.can_start ? '可以启动' : '需要调整'}
                    </Tag>
                  </div>
                  <div className="link-check-runtime-metric-grid">
                    <div className="link-check-runtime-metric-card">
                      <span className="link-check-runtime-metric-label">命中消息</span>
                      <span className="link-check-runtime-metric-value">{formatCount(manualPreview.estimated_messages)}</span>
                    </div>
                    <div className="link-check-runtime-metric-card">
                      <span className="link-check-runtime-metric-label">命中链接</span>
                      <span className="link-check-runtime-metric-value">{formatCount(manualPreview.estimated_links)}</span>
                    </div>
                    <div className="link-check-runtime-metric-card">
                      <span className="link-check-runtime-metric-label">单任务上限</span>
                      <span className="link-check-runtime-metric-value">{formatCount(manualPreview.task_link_limit)}</span>
                    </div>
                    <div className="link-check-runtime-metric-card">
                      <span className="link-check-runtime-metric-label">建议拆分</span>
                      <span className="link-check-runtime-metric-value">
                        {manualPreview.recommended_batch_count > 1 ? `${manualPreview.recommended_batch_count} 批` : '单批'}
                      </span>
                    </div>
                  </div>
                  {manualPreview.warnings.length > 0 ? (
                    <Alert type="warning" showIcon message={manualPreview.warnings.join('；')} />
                  ) : null}
                </>
              ) : (
                <Alert type="info" showIcon message="补全条件后会自动生成预估" />
              )}
            </div>

            <div className="link-check-runtime-actions">
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={taskStarting}
                disabled={!manualPreviewRequest || manualPreviewLoading || currentTaskRunning}
                onClick={() => void handleStartTask()}
              >
                开始检测
              </Button>
            </div>
          </div>
        </Card>

        <Card
          className="link-check-runtime-card"
          loading={planLoading && !planData}
          title={
            <div className="link-check-runtime-card-heading">
              <div className="link-check-runtime-card-heading-main">
                <span className="link-check-runtime-card-title">自动巡检</span>
                <Text type="secondary">夜间按计划慢慢跑完整体库存</Text>
              </div>
            </div>
          }
          extra={
            <div className="link-check-runtime-inline-actions">
              {planOverview?.refreshing ? <Tag color="processing">概览刷新中</Tag> : null}
              <div className="link-check-runtime-inline-switch">
                <Text>启用</Text>
                <Switch
                  checked={Boolean(planDraft?.is_enabled)}
                  onChange={(checked) =>
                    setPlanDraft((current) => (current ? { ...current, is_enabled: checked } : current))
                  }
                />
              </div>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={planSaving}
                disabled={!planDirty || !planDraft}
                onClick={() => void handleSavePlan()}
              >
                保存计划
              </Button>
            </div>
          }
        >
          {planDraft ? (
            <div className="link-check-runtime-section">
              <div className="link-check-runtime-field-grid">
                <div className="link-check-runtime-field">
                  {createFieldLabel('执行时间', '每天在这个时间点启动计划任务。')}
                  <TimePicker
                    className="link-check-runtime-compact-control"
                    value={planDraft.schedule_time}
                    format="HH:mm"
                    allowClear={false}
                    minuteStep={5}
                    onChange={(value) =>
                      setPlanDraft((current) => (current && value ? { ...current, schedule_time: value } : current))
                    }
                  />
                </div>
                <div className="link-check-runtime-field">
                  {createFieldLabel('全量周期', '希望多少天内把当前全量链接至少扫完一轮。')}
                  <InputNumber
                    className="link-check-runtime-compact-control"
                    min={1}
                    max={90}
                    value={planDraft.cycle_days}
                    onChange={(value) =>
                      setPlanDraft((current) =>
                        current ? { ...current, cycle_days: Math.max(1, Number(value || 1)) } : current
                      )
                    }
                  />
                </div>
                <div className="link-check-runtime-field">
                  {createFieldLabel('每批链接数', '每个自动批次尽量覆盖多少条链接。')}
                  <InputNumber
                    className="link-check-runtime-compact-control"
                    min={100}
                    max={taskLinkLimit}
                    value={planDraft.batch_link_target}
                    onChange={(value) =>
                      setPlanDraft((current) =>
                        current ? { ...current, batch_link_target: Math.max(100, Number(value || 100)) } : current
                      )
                    }
                  />
                </div>
                <div className="link-check-runtime-field">
                  {createFieldLabel('单次批次数', '每次计划触发时，最多连续跑多少个批次。')}
                  <InputNumber
                    className="link-check-runtime-compact-control"
                    min={1}
                    max={12}
                    value={planDraft.max_batches_per_run}
                    onChange={(value) =>
                      setPlanDraft((current) =>
                        current ? { ...current, max_batches_per_run: Math.max(1, Number(value || 1)) } : current
                      )
                    }
                  />
                </div>
                <div className="link-check-runtime-field">
                  {createFieldLabel('计划并发', '自动批次执行时的并发数量。')}
                  <InputNumber
                    className="link-check-runtime-compact-control"
                    min={1}
                    max={taskConcurrencyLimit}
                    value={planDraft.max_concurrent}
                    onChange={(value) =>
                      setPlanDraft((current) =>
                        current ? { ...current, max_concurrent: Math.max(1, Number(value || 1)) } : current
                      )
                    }
                  />
                </div>
                <div className="link-check-runtime-field">
                  {createFieldLabel('遍历方向', '最新优先更适合追新，最早优先适合逐步补扫旧资源。')}
                  <Select
                    className="link-check-runtime-compact-control"
                    value={planDraft.traversal_order}
                    options={directionOptions}
                    onChange={(value) =>
                      setPlanDraft((current) =>
                        current ? { ...current, traversal_order: value as TraversalOrder } : current
                      )
                    }
                  />
                </div>
                <div className="link-check-runtime-field is-wide">
                  {createFieldLabel('自动清理', '巡检完成后是否直接清理失效链接。建议先从只检测开始。')}
                  <div className="link-check-runtime-inline-grid">
                    <Select
                      className="link-check-runtime-compact-control"
                      value={planDraft.cleanup_mode}
                      options={cleanupOptions}
                      onChange={(value) =>
                        setPlanDraft((current) => (current ? { ...current, cleanup_mode: value as CleanupMode } : current))
                      }
                    />
                    {planDraft.cleanup_mode !== 'none' ? (
                      <>
                        <InputNumber
                          className="link-check-runtime-compact-control"
                          min={1}
                          max={10}
                          value={planDraft.cleanup_min_consecutive_invalid_runs}
                          onChange={(value) =>
                            setPlanDraft((current) =>
                              current
                                ? {
                                    ...current,
                                    cleanup_min_consecutive_invalid_runs: Math.max(1, Number(value || 1)),
                                  }
                                : current
                            )
                          }
                        />
                        <Text type="secondary">连续 {planDraft.cleanup_min_consecutive_invalid_runs} 次失效后才执行</Text>
                      </>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="link-check-runtime-preview-panel">
                <div className="link-check-runtime-panel-heading">
                  <div>
                    <span className="link-check-runtime-panel-title">计划概览</span>
                    <Text type="secondary">保存前先确认覆盖速度和风险提示</Text>
                  </div>
                  <Space size={[8, 8]} wrap>
                    <Tag>{planDraft.timezone}</Tag>
                    {planOverview?.generated_at ? (
                      <Tag>统计于 {formatDateTime(planOverview.generated_at, 'MM-DD HH:mm:ss')}</Tag>
                    ) : null}
                    <Tag color={planOverview?.can_finish_within_cycle ? 'success' : 'warning'}>
                      {planOverview?.can_finish_within_cycle ? '周期可覆盖' : '周期偏紧'}
                    </Tag>
                  </Space>
                </div>

                <div className="link-check-runtime-summary-grid">
                  <div className="link-check-runtime-summary-card">
                    <span className="link-check-runtime-summary-label">执行节奏</span>
                    <span className="link-check-runtime-summary-value">每日 {planDraft.schedule_time.format('HH:mm')}</span>
                    <span className="link-check-runtime-summary-meta">
                      每晚最多 {planDraft.max_batches_per_run} 批，每批约 {formatCount(planDraft.batch_link_target)} 链接
                    </span>
                  </div>
                  <div className="link-check-runtime-summary-card">
                    <span className="link-check-runtime-summary-label">覆盖预估</span>
                    <span className="link-check-runtime-summary-value">
                      {planOverview?.estimated_days_to_complete_cycle ? `${planOverview.estimated_days_to_complete_cycle} 天 / 轮` : '暂无'}
                    </span>
                    <span className="link-check-runtime-summary-meta">目标 {planDraft.cycle_days} 天内完成一轮</span>
                  </div>
                  <div className="link-check-runtime-summary-card">
                    <span className="link-check-runtime-summary-label">自动清理</span>
                    <span className="link-check-runtime-summary-value">{cleanupModeLabelMap[planDraft.cleanup_mode]}</span>
                    <span className="link-check-runtime-summary-meta">
                      {planDraft.cleanup_mode === 'none'
                        ? '只做巡检，不自动改动消息'
                        : `连续 ${planDraft.cleanup_min_consecutive_invalid_runs} 次失效后执行`}
                    </span>
                  </div>
                </div>

                <Alert
                  type={planOverview?.can_finish_within_cycle ? 'success' : 'warning'}
                  showIcon
                  message={planOverview?.summary || '等待系统计算计划概览'}
                />

                {planOverview?.refreshing ? (
                  <Alert
                    type="info"
                    showIcon
                    message={planOverview?.stale ? '概览正在后台刷新，当前先展示最近一次缓存统计。' : '概览正在后台刷新，稍后会自动更新。'}
                  />
                ) : null}

                {planOverview?.warnings.length ? (
                  <Alert type="warning" showIcon message={planOverview.warnings.join('；')} />
                ) : null}

                {planData?.last_error_message ? (
                  <Alert
                    type={planData.last_status === 'failed' ? 'error' : 'info'}
                    showIcon
                    message={planData.last_error_message}
                  />
                ) : null}
              </div>
            </div>
          ) : null}
        </Card>
      </div>

      <Card
        className="link-check-runtime-card"
        title={
          <div className="link-check-runtime-card-heading">
            <div className="link-check-runtime-card-heading-main">
              <span className="link-check-runtime-card-title">当前任务</span>
              <Text type="secondary">实时进度、日志和运行结果</Text>
            </div>
          </div>
        }
        extra={
          currentTask ? (
            <div className="link-check-runtime-inline-actions">
              <Button icon={<ReloadOutlined />} onClick={() => currentTask.task_id && startPolling(currentTask.task_id)}>
                刷新
              </Button>
              <Button
                icon={<PauseCircleOutlined />}
                danger
                loading={taskStopping}
                disabled={!currentTaskRunning}
                onClick={handleStopTask}
              >
                停止任务
              </Button>
            </div>
          ) : null
        }
      >
        {currentTask ? (
          <div className="link-check-runtime-section">
            <div className="link-check-runtime-task-header">
              <div className="link-check-runtime-task-summary">
                <div className="link-check-runtime-task-title-row">
                  <Title level={5} style={{ margin: 0 }}>
                    {currentTask.scope_label || currentTask.period_desc || '当前任务'}
                  </Title>
                  <Tag color={statusColorMap[currentTask.status] || 'default'}>{getStatusLabel(currentTask.status)}</Tag>
                </div>
                <div className="link-check-runtime-task-meta-row">
                  <span className="link-check-runtime-task-meta">{getTriggerSourceLabel(currentTask.trigger_source)}</span>
                  <span className="link-check-runtime-task-meta">{getTaskModeLabel(currentTask.task_mode)}</span>
                  <span className="link-check-runtime-task-meta">{getPhaseLabel(currentTask.current_phase)}</span>
                  <span className="link-check-runtime-task-meta">启动于 {formatDateTime(currentTask.started_at)}</span>
                </div>
              </div>
              <div className="link-check-runtime-task-metrics">
                <div className="link-check-runtime-task-metric">
                  <span className="link-check-runtime-task-metric-label">链接进度</span>
                  <span className="link-check-runtime-task-metric-value">
                    {formatCount(currentTask.checked_links || 0)} / {formatCount(currentTask.total_links || 0)}
                  </span>
                </div>
                <div className="link-check-runtime-task-metric">
                  <span className="link-check-runtime-task-metric-label">有效 / 失效</span>
                  <span className="link-check-runtime-task-metric-value">
                    {formatCount(currentTask.valid_links || 0)} / {formatCount(currentTask.invalid_links || 0)}
                  </span>
                </div>
              </div>
            </div>

            <div className="link-check-runtime-progress-block">
              <Progress
                percent={currentTask.progress || 0}
                status={
                  currentTask.status === 'failed'
                    ? 'exception'
                    : currentTask.status === 'completed'
                      ? 'success'
                      : 'active'
                }
              />
              <div className="link-check-runtime-task-meta-row">
                <span className="link-check-runtime-task-meta">当前平台 {currentTask.current_platform || '-'}</span>
                {Object.entries(currentTask.status_counts || {}).map(([key, value]) => (
                  <span key={key} className="link-check-runtime-task-meta">
                    {getResultStatusLabel(key)} {value}
                  </span>
                ))}
              </div>
            </div>

            <div className="link-check-runtime-log-console">
              <div className="link-check-runtime-log-console-header">
                <Text strong>运行日志</Text>
                <Text type="secondary">最多保留最近 800 行</Text>
              </div>
              {currentTask.logs && currentTask.logs.length > 0 ? (
                <div ref={logConsoleRef} className="link-check-runtime-log-lines">
                  {currentTask.logs.map((log, index) => (
                    <div key={`${index}-${log}`} className="link-check-runtime-log-line">
                      {log}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="link-check-runtime-empty-state">
                  <Text type="secondary">暂无日志输出</Text>
                </div>
              )}
            </div>

            {currentTask.error ? <Alert type={currentTask.status === 'failed' ? 'error' : 'info'} showIcon message={currentTask.error} /> : null}
          </div>
        ) : (
          <div className="link-check-runtime-empty-state">
            <CheckCircleOutlined className="link-check-runtime-empty-icon" />
            <Text type="secondary">当前没有运行中的链接检测任务。</Text>
          </div>
        )}
      </Card>

      <Card
        className="link-check-runtime-card"
        title={
          <div className="link-check-runtime-card-heading">
            <div className="link-check-runtime-card-heading-main">
              <span className="link-check-runtime-card-title">检测历史</span>
              <Text type="secondary">支持按来源、模式筛选，也可以批量删除</Text>
            </div>
          </div>
        }
        extra={
          <div className="link-check-runtime-inline-actions">
            <Text type="secondary">已选 {selectedHistoryIds.length} 条</Text>
            <Button icon={<ReloadOutlined />} loading={historyLoading} onClick={() => void loadHistory()}>
              刷新
            </Button>
            <Button danger icon={<DeleteOutlined />} disabled={selectedHistoryIds.length === 0} onClick={handleBatchDeleteHistory}>
              批量删除
            </Button>
          </div>
        }
      >
        <Table
          className="link-check-runtime-history-table"
          columns={historyColumns}
          dataSource={history}
          rowKey="id"
          loading={historyLoading}
          rowSelection={{
            selectedRowKeys: selectedHistoryIds,
            onChange: (keys) => setSelectedHistoryIds(keys.map((key) => Number(key))),
          }}
          pagination={false}
          tableLayout="auto"
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: '暂无检测历史' }}
          onRow={(record) => ({
            onClick: (event) => {
              const target = event.target as HTMLElement
              if (target.closest('button,a,.ant-checkbox-wrapper,.ant-checkbox-input,.ant-btn')) {
                return
              }
              toggleHistorySelection(record)
            },
          })}
        />
      </Card>

      <LinkMaintenanceTools />

      <Modal
        title="检测结果详情"
        open={resultModalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setResultModalVisible(false)
          setSelectedResult(null)
        }}
        footer={null}
        width={1080}
      >
        {resultLoading ? (
          <div className="link-check-runtime-modal-loading">
            <Spin size="large" />
          </div>
        ) : selectedResult ? (
          <div className="link-check-runtime-result-view">
            <div className="link-check-runtime-result-grid">
              <div className="link-check-runtime-result-card">
                <span className="link-check-runtime-result-label">检测时间</span>
                <span className="link-check-runtime-result-value">{formatDateTime(selectedResult.stats.check_time)}</span>
              </div>
              <div className="link-check-runtime-result-card">
                <span className="link-check-runtime-result-label">来源 / 模式</span>
                <span className="link-check-runtime-result-value">
                  {getTriggerSourceLabel(selectedResult.stats.trigger_source)} / {getTaskModeLabel(selectedResult.stats.task_mode)}
                </span>
              </div>
              <div className="link-check-runtime-result-card">
                <span className="link-check-runtime-result-label">范围</span>
                <span className="link-check-runtime-result-value">{selectedResult.stats.scope_label || '-'}</span>
              </div>
              <div className="link-check-runtime-result-card">
                <span className="link-check-runtime-result-label">链接结果</span>
                <span className="link-check-runtime-result-value">
                  {selectedResult.stats.valid_links} 有效 / {selectedResult.stats.invalid_links} 失效
                </span>
              </div>
              <div className="link-check-runtime-result-card">
                <span className="link-check-runtime-result-label">消息变更</span>
                <span className="link-check-runtime-result-value">
                  更新 {selectedResult.stats.updated_messages ?? 0} / 删除 {selectedResult.stats.deleted_messages ?? 0}
                </span>
              </div>
              <div className="link-check-runtime-result-card">
                <span className="link-check-runtime-result-label">耗时</span>
                <span className="link-check-runtime-result-value">{formatDuration(selectedResult.stats.duration)}</span>
              </div>
            </div>

            {invalidDetails.length > 0 ? (
              <Card size="small" className="link-check-runtime-cleanup-card">
                <div className="link-check-runtime-panel-heading">
                  <div>
                    <span className="link-check-runtime-panel-title">死链清理</span>
                    <Text type="secondary">仅会改动当前这次检测确认失效的链接</Text>
                  </div>
                </div>
                <div className="link-check-runtime-inline-grid">
                  <Select
                    className="link-check-runtime-compact-control"
                    value={cleanupMode}
                    onChange={(value) => setCleanupMode(value as LinkCleanupApplyRequest['mode'])}
                    options={[
                      { value: 'remove_invalid_links', label: '仅移除失效链接' },
                      { value: 'delete_message_if_empty', label: '失效链接移除后为空则删整条' },
                    ]}
                  />
                  <Button
                    type="primary"
                    danger={cleanupMode === 'delete_message_if_empty'}
                    loading={cleanupLoading}
                    onClick={handleApplyCleanup}
                  >
                    应用清理
                  </Button>
                </div>
              </Card>
            ) : null}

            <div>
              <div className="link-check-runtime-panel-heading">
                <div>
                  <span className="link-check-runtime-panel-title">失效链接详情</span>
                  <Text type="secondary">最多展示 1000 条失效记录</Text>
                </div>
              </div>
              <Table<InvalidLinkDetail>
                dataSource={invalidDetails}
                rowKey={(record, index) => `${record.url}-${index}`}
                pagination={{ pageSize: 20 }}
                size="small"
                columns={[
                  { title: '链接', dataIndex: 'url', key: 'url', ellipsis: true },
                  { title: '网盘类型', dataIndex: 'netdisk_type', key: 'netdisk_type' },
                  {
                    title: '响应时间',
                    dataIndex: 'response_time',
                    key: 'response_time',
                    render: (value?: number) => (value ? `${value.toFixed(2)} 秒` : '-'),
                  },
                  { title: '错误原因', dataIndex: 'error_reason', key: 'error_reason', ellipsis: true },
                ]}
                tableLayout="auto"
                scroll={{ x: 'max-content' }}
              />
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

export default LinkCheckManagerRuntime
