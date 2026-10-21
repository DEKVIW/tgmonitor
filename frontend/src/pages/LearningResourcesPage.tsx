import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, DatePicker, Input, InputNumber, List, Modal, Popconfirm, Radio, Select, Space, Switch, Table, Tag, Tooltip, Typography, Upload, message } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, EditOutlined, ExclamationCircleOutlined, FileSearchOutlined, FolderOpenOutlined, MinusCircleOutlined, PauseCircleOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined, SyncOutlined, UploadOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import type { Dayjs } from 'dayjs'
import {
  deleteAllImportedLearningResources,
  deleteLearningAutomationTask,
  deleteLearningResource,
  getLearningAdminItems,
  getLearningAdminOverview,
  clearLearningAutomationLogs,
  getLearningAutomationLogs,
  getLearningAutomationTasks,
  getLearningDirectories,
  getLearningAutomationSupplement,
  getPublicLearningCategories,
  getPublicLearningResources,
  confirmLearningImport,
  previewLearningImport,
  retryLearningResource,
  retryLearningAutomationTask,
  createLearningAutomationTask,
  pauseLearningAutomationSupplement,
  previewLearningAutomationSupplement,
  pauseLearningAutomationTask,
  resumeLearningAutomationTask,
  startLearningAutomationSupplement,
  updateLearningAutomationTask,
  updateLearningResource,
} from '@/api/learningResources'
import type {
  LearningAdminOverview,
  LearningCategory,
  LearningDirectory,
  LearningAutomationTask,
  LearningAutomationTaskTarget,
  LearningAutomationLog,
  LearningAutomationSupplementPreview,
  LearningAutomationSupplementRun,
  LearningImportPreview,
  LearningResource,
} from '@/types/learningResources'
import LearningResourceSheet from '@/components/learning/LearningResourceSheet'
import AppLogTerminal from '@/components/common/AppLogTerminal'
import { cleanLearningSheetText } from '@/utils/learningResources'

import './LearningResourcesPage.css'

const { Text } = Typography
const { RangePicker } = DatePicker

type TaskDraftTarget = LearningAutomationTaskTarget

type LearningTaskDraft = {
  name: string
  is_enabled: boolean
  channel_ids: number[]
  targets: TaskDraftTarget[]
}

type LearningSupplementMode = 'checkpoint' | 'date_range' | 'recent'

const taskStatusLabel: Record<string, string> = {
  running: '处理中',
  waiting: '等待消息',
  degraded: '有失败任务',
  paused: '已暂停',
  invalid: '配置不完整',
}

const taskStatusColor: Record<string, string> = {
  running: 'processing',
  waiting: 'default',
  degraded: 'warning',
  paused: 'default',
  invalid: 'error',
}

const getRequestErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

const learningLogStageLabels: Record<string, string> = {
  config: '配置',
  received: '监听',
  classified: '解析',
  skipped: '跳过',
  replay: '补充更新',
  enqueued: '入队',
  retrying: '重试',
  transferring: '转存',
  sharing: '分享',
  published: '发布',
  failed: '失败',
}

const learningLogLevelLabels: Record<string, string> = {
  info: 'INFO',
  warning: 'WARN',
  error: 'ERROR',
}

const formatLearningLogTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

const formatLearningLogContext = (log: LearningAutomationLog) => {
  const details = log.details || {}
  const context: string[] = []
  const append = (label: string, value: unknown) => {
    if (value !== undefined && value !== null && String(value).trim()) context.push(`${label}=${String(value).trim()}`)
  }
  append('分类', details.category)
  append('频道', details.channel)
  append('账号', details.target_account)
  if (typeof details.monitor_message_id === 'number') {
    append('原始消息', details.monitor_message_id)
  }
  if (typeof details.resource_index === 'number' && typeof details.resource_total === 'number' && !log.message.includes(`资源 ${details.resource_index}/${details.resource_total}`)) {
    append('资源序号', `${details.resource_index}/${details.resource_total}`)
  }
  if (typeof details.job_count === 'number' && details.job_count > 1) append('任务数', details.job_count)
  if (typeof details.link_count === 'number' && details.link_count > 1) append('链接数', details.link_count)
  if (details.share_url_created === true) append('分享', '已生成')
  if (details.share_url_created === false) append('分享', '未生成')
  if (details.retry_waiting === true) append('重试', '等待自动重试')
  append('错误', details.error)
  return context.length > 0 ? ` | ${context.join(' | ')}` : ''
}

const buildLearningLogLine = (log: LearningAutomationLog) => {
  const stage = learningLogStageLabels[log.stage] || log.stage || '未知'
  const level = learningLogLevelLabels[log.level] || String(log.level || 'INFO').toUpperCase()
  return `[${formatLearningLogTime(log.created_at)}] [${stage}] [${level}] ${log.message}${formatLearningLogContext(log)}`
}

const LearningResourcesPage = () => {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin'
  const [categories, setCategories] = useState<LearningCategory[]>([])
  const [resources, setResources] = useState<LearningResource[]>([])
  const [resourceTotal, setResourceTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 100
  const [overview, setOverview] = useState<LearningAdminOverview | null>(null)
  const [activeCategory, setActiveCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [automationTasks, setAutomationTasks] = useState<LearningAutomationTask[]>([])
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [editingTaskId, setEditingTaskId] = useState<number | null>(null)
  const [taskDraft, setTaskDraft] = useState<LearningTaskDraft>({ name: '', is_enabled: false, channel_ids: [], targets: [] })
  const [savingTask, setSavingTask] = useState(false)
  const [taskBusyId, setTaskBusyId] = useState<number | null>(null)
  const [taskLogs, setTaskLogs] = useState<LearningAutomationLog[]>([])
  const [taskLogsTask, setTaskLogsTask] = useState<LearningAutomationTask | null>(null)
  const [taskLogsOpen, setTaskLogsOpen] = useState(false)
  const [taskLogsLoading, setTaskLogsLoading] = useState(false)
  const [taskLogsClearing, setTaskLogsClearing] = useState(false)
  const [supplementTask, setSupplementTask] = useState<LearningAutomationTask | null>(null)
  const [supplementOpen, setSupplementOpen] = useState(false)
  const [supplementMode, setSupplementMode] = useState<LearningSupplementMode>('checkpoint')
  const [supplementRange, setSupplementRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [supplementLimit, setSupplementLimit] = useState(10)
  const [supplementPreview, setSupplementPreview] = useState<LearningAutomationSupplementPreview | null>(null)
  const [supplementRun, setSupplementRun] = useState<LearningAutomationSupplementRun | null>(null)
  const [supplementLoading, setSupplementLoading] = useState(false)
  const [supplementPausing, setSupplementPausing] = useState(false)
  const [maintenanceBusyId, setMaintenanceBusyId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState({ display_title: '', category: '', tags: '', share_url: '' })
  const [deletingAll, setDeletingAll] = useState(false)
  const [importPreview, setImportPreview] = useState<LearningImportPreview | null>(null)
  const [importMode, setImportMode] = useState<'direct' | 'transfer' | 'collect'>('direct')
  const [importAccountId, setImportAccountId] = useState<number | undefined>(undefined)
  const [importRoot, setImportRoot] = useState('')
  const [importConfirming, setImportConfirming] = useState(false)
  const [directoryModalOpen, setDirectoryModalOpen] = useState(false)
  const [directoryTarget, setDirectoryTarget] = useState<'task' | 'import'>('task')
  const [directoryTargetIndex, setDirectoryTargetIndex] = useState<number | null>(null)
  const [directoryAccountId, setDirectoryAccountId] = useState<number | undefined>(undefined)
  const [directoryLoading, setDirectoryLoading] = useState(false)
  const [directoryItems, setDirectoryItems] = useState<LearningDirectory[]>([])
  const [directoryStack, setDirectoryStack] = useState<Array<{ id: string; name: string; path: string }>>([])
  const requestSequenceRef = useRef(0)
  const loadMoreRequestedRef = useRef(false)

  const supplementRunId = supplementRun?.id
  const supplementRunStatus = supplementRun?.status

  useEffect(() => {
    if (!supplementRunId || !['queued', 'running', 'pause_requested'].includes(supplementRunStatus || '')) return undefined
    const timer = window.setInterval(() => {
      void getLearningAutomationSupplement(supplementRunId)
        .then((nextRun) => setSupplementRun(nextRun))
        .catch(() => undefined)
    }, 1500)
    return () => window.clearInterval(timer)
  }, [supplementRunId, supplementRunStatus])

  const load = useCallback(async (targetPage: number) => {
    const requestId = requestSequenceRef.current + 1
    requestSequenceRef.current = requestId
    if (targetPage === 1) loadMoreRequestedRef.current = false
    setLoading(true)
    setError('')
    try {
      if (isAdmin) {
        const adminDataRequest = getLearningAdminItems({
          category: activeCategory === 'all' ? undefined : activeCategory,
          search: search.trim() || undefined,
          page: targetPage,
          page_size: pageSize,
        })
        if (targetPage === 1) {
          const [overviewData, adminData, taskData] = await Promise.all([getLearningAdminOverview(), adminDataRequest, getLearningAutomationTasks()])
          if (requestId !== requestSequenceRef.current) return
          setOverview(overviewData)
          setAutomationTasks(taskData.items)
          setCategories(overviewData.categories.map((category) => ({
            id: category.id,
            name: category.name,
            slug: category.slug,
            sort_order: category.sort_order,
            resource_count: category.resource_count,
          })))
          const items = adminData.items.map((item) => ({ ...item, share_url: item.share_url || '', platform: item.platform || '' }))
          setResources(items)
          setResourceTotal(adminData.total)
        } else {
          const adminData = await adminDataRequest
          if (requestId !== requestSequenceRef.current) return
          const items = adminData.items.map((item) => ({ ...item, share_url: item.share_url || '', platform: item.platform || '' }))
          setResources((current) => {
            const existingIds = new Set(current.map((item) => item.id))
            return [...current, ...items.filter((item) => !existingIds.has(item.id))]
          })
          setResourceTotal(adminData.total)
        }
      } else {
        const resourceDataRequest = getPublicLearningResources({
          category: activeCategory === 'all' ? undefined : activeCategory,
          search: search.trim() || undefined,
          page: targetPage,
          page_size: pageSize,
        })
        if (targetPage === 1) {
          const [categoryData, resourceData] = await Promise.all([getPublicLearningCategories(), resourceDataRequest])
          if (requestId !== requestSequenceRef.current) return
          setCategories(categoryData)
          setResources(resourceData.items)
          setResourceTotal(resourceData.total)
        } else {
          const resourceData = await resourceDataRequest
          if (requestId !== requestSequenceRef.current) return
          setResources((current) => {
            const existingIds = new Set(current.map((item) => item.id))
            return [...current, ...resourceData.items.filter((item) => !existingIds.has(item.id))]
          })
          setResourceTotal(resourceData.total)
        }
      }
    } catch (loadError: unknown) {
      if (requestId === requestSequenceRef.current) {
        setError(getRequestErrorMessage(loadError, '学习资料加载失败，请稍后重试'))
      }
    } finally {
      if (requestId === requestSequenceRef.current) {
        loadMoreRequestedRef.current = false
        setLoading(false)
      }
    }
  }, [activeCategory, isAdmin, search])

  useEffect(() => {
    void load(page)
  }, [load, page])

  const refreshFirstPage = useCallback(async () => {
    if (page === 1) {
      await load(1)
      return
    }
    loadMoreRequestedRef.current = false
    setPage(1)
  }, [load, page])

  const handleLoadMore = useCallback(() => {
    if (loading || loadMoreRequestedRef.current || resources.length >= resourceTotal) return
    loadMoreRequestedRef.current = true
    setPage((current) => current + 1)
  }, [loading, resources.length, resourceTotal])

  const buildTaskDraft = (task?: LearningAutomationTask): LearningTaskDraft => ({
    name: task?.name || '',
    is_enabled: Boolean(task?.is_enabled),
    channel_ids: task?.channels.filter((channel) => channel.is_enabled).map((channel) => channel.channel_id) || [],
    targets: task?.targets.map((target) => ({ ...target })) || [],
  })

  const openCreateTask = () => {
    const firstAccount = overview?.accounts.find((account) => account.is_enabled)
    setEditingTaskId(null)
    setTaskDraft({
      name: '',
      is_enabled: false,
      channel_ids: [],
      targets: firstAccount ? [{ target_account_id: firstAccount.id, save_root_id: '0', save_root_name: firstAccount.default_save_root, auto_create_category_dirs: true, is_enabled: true }] : [],
    })
    setTaskModalOpen(true)
  }

  const openEditTask = (task: LearningAutomationTask) => {
    setEditingTaskId(task.id)
    setTaskDraft(buildTaskDraft(task))
    setTaskModalOpen(true)
  }

  const handleSaveTask = async () => {
    if (!taskDraft.name.trim() || taskDraft.channel_ids.length === 0 || taskDraft.targets.length === 0) {
      message.warning('请填写任务名称，并至少选择一个频道和一个转存目标')
      return
    }
    setSavingTask(true)
    try {
      const payload = {
        name: taskDraft.name.trim(),
        is_enabled: taskDraft.is_enabled,
        backfill_policy: 'new_messages_only',
        channels: taskDraft.channel_ids.map((channelId) => ({ channel_id: channelId, is_enabled: true })),
        targets: taskDraft.targets.map((target) => ({
          id: target.id || undefined,
          target_account_id: target.target_account_id,
          save_root_id: target.save_root_id || '0',
          save_root_name: target.save_root_name || '',
          auto_create_category_dirs: target.auto_create_category_dirs,
          is_enabled: target.is_enabled,
        })),
      }
      if (editingTaskId) {
        await updateLearningAutomationTask(editingTaskId, payload)
      } else {
        await createLearningAutomationTask(payload)
      }
      message.success(taskDraft.is_enabled ? '自动监听与转存已开启' : '任务配置已保存，当前未启动')
      setTaskModalOpen(false)
      await refreshFirstPage()
    } catch (saveError: unknown) {
      message.error(getRequestErrorMessage(saveError, '保存自动转存任务失败'))
    } finally {
      setSavingTask(false)
    }
  }

  const handleTaskToggle = async (task: LearningAutomationTask) => {
    setTaskBusyId(task.id)
    try {
      if (task.is_enabled) {
        await pauseLearningAutomationTask(task.id)
        message.success('自动监听已暂停，已入队任务继续处理')
      } else {
        await resumeLearningAutomationTask(task.id)
        message.success('自动监听已恢复')
      }
      await refreshFirstPage()
    } catch (taskError: unknown) {
      message.error(getRequestErrorMessage(taskError, '更新自动任务状态失败'))
    } finally {
      setTaskBusyId(null)
    }
  }

  const openSupplement = (task: LearningAutomationTask) => {
    setSupplementTask(task)
    setSupplementMode('checkpoint')
    setSupplementRange(null)
    setSupplementLimit(10)
    setSupplementPreview(null)
    setSupplementRun(null)
    setSupplementOpen(true)
  }

  const closeSupplement = () => {
    setSupplementOpen(false)
    setSupplementTask(null)
    setSupplementPreview(null)
    setSupplementRun(null)
  }

  const buildSupplementPayload = () => {
    if (supplementMode === 'date_range') {
      return {
        mode: supplementMode,
        from_at: supplementRange?.[0]?.startOf('day').toISOString(),
        to_at: supplementRange?.[1]?.endOf('day').toISOString(),
      }
    }
    if (supplementMode === 'recent') {
      return { mode: supplementMode, recent_limit: Math.max(1, Math.min(5000, Number(supplementLimit) || 10)) }
    }
    return { mode: supplementMode }
  }

  const handlePreviewSupplement = async () => {
    if (!supplementTask) return
    if (supplementMode === 'date_range' && (!supplementRange?.[0] || !supplementRange?.[1])) {
      message.warning('请选择完整的补充更新时间范围')
      return
    }
    setSupplementLoading(true)
    try {
      setSupplementPreview(await previewLearningAutomationSupplement(supplementTask.id, buildSupplementPayload()))
    } catch (previewError: unknown) {
      message.error(getRequestErrorMessage(previewError, '预览补充更新失败'))
      setSupplementPreview(null)
    } finally {
      setSupplementLoading(false)
    }
  }

  const handleStartSupplement = async () => {
    if (!supplementTask || !supplementPreview) {
      message.warning('请先预览待处理内容')
      return
    }
    setSupplementLoading(true)
    try {
      const run = await startLearningAutomationSupplement(supplementTask.id, buildSupplementPayload())
      setSupplementRun(run)
      message.success('补充更新已开始，实时监听不受影响')
      await refreshFirstPage()
    } catch (startError: unknown) {
      message.error(getRequestErrorMessage(startError, '开始补充更新失败'))
    } finally {
      setSupplementLoading(false)
    }
  }

  const handlePauseSupplement = async () => {
    if (!supplementRun) return
    setSupplementPausing(true)
    try {
      setSupplementRun(await pauseLearningAutomationSupplement(supplementRun.id))
      message.success('已请求暂停补充更新，当前批次完成后停止')
    } catch (pauseError: unknown) {
      message.error(getRequestErrorMessage(pauseError, '暂停补充更新失败'))
    } finally {
      setSupplementPausing(false)
    }
  }

  const handleDeleteTask = async (task: LearningAutomationTask) => {
    setTaskBusyId(task.id)
    try {
      await deleteLearningAutomationTask(task.id)
      message.success(`自动任务“${task.name}”已删除`)
      await refreshFirstPage()
    } catch (taskError: unknown) {
      message.error(getRequestErrorMessage(taskError, '删除自动任务失败'))
    } finally {
      setTaskBusyId(null)
    }
  }

  const handleRetryTask = async (task: LearningAutomationTask) => {
    setTaskBusyId(task.id)
    try {
      const result = await retryLearningAutomationTask(task.id)
      message.success(`已重新加入 ${result.retried_count} 个失败任务`)
      await refreshFirstPage()
    } catch (taskError: unknown) {
      message.error(getRequestErrorMessage(taskError, '重试失败任务失败'))
    } finally {
      setTaskBusyId(null)
    }
  }

  const handleViewTaskLogs = async (task: LearningAutomationTask) => {
    setTaskLogsTask(task)
    setTaskLogsOpen(true)
    setTaskLogsLoading(true)
    try {
      const result = await getLearningAutomationLogs(task.id, 300)
      setTaskLogs([...result.items].reverse())
    } catch (logError: unknown) {
      message.error(getRequestErrorMessage(logError, '读取任务日志失败'))
      setTaskLogs([])
    } finally {
      setTaskLogsLoading(false)
    }
  }

  const handleClearTaskLogs = async () => {
    if (!taskLogsTask) return
    setTaskLogsClearing(true)
    try {
      const result = await clearLearningAutomationLogs(taskLogsTask.id)
      setTaskLogs([])
      message.success(`已清理 ${result.deleted_count} 条自动任务日志`)
    } catch (logError: unknown) {
      message.error(getRequestErrorMessage(logError, '清理任务日志失败'))
    } finally {
      setTaskLogsClearing(false)
    }
  }

  const loadDirectories = async (accountId: number, parentId: string) => {
    setDirectoryLoading(true)
    try {
      setDirectoryItems(await getLearningDirectories(accountId, parentId))
    } catch (directoryError: unknown) {
      message.error(getRequestErrorMessage(directoryError, '读取网盘目录失败'))
      setDirectoryItems([])
    } finally {
      setDirectoryLoading(false)
    }
  }

  const openDirectoryPicker = async (target: 'task' | 'import', targetIndex?: number) => {
    const accountId = target === 'task'
      ? (targetIndex === undefined ? undefined : taskDraft.targets[targetIndex]?.target_account_id)
      : importAccountId
    if (!accountId) {
      message.warning('请先选择已配置的夸克账号')
      return
    }
    setDirectoryTarget(target)
    setDirectoryTargetIndex(targetIndex ?? null)
    setDirectoryAccountId(accountId)
    setDirectoryStack([{ id: '0', name: '网盘根目录', path: '' }])
    setDirectoryModalOpen(true)
    await loadDirectories(accountId, '0')
  }

  const enterDirectory = async (directory: LearningDirectory) => {
    if (!directoryAccountId) return
    const currentPath = directoryStack[directoryStack.length - 1]?.path || ''
    const path = [currentPath, directory.name].filter(Boolean).join('/')
    setDirectoryStack((current) => [...current, { id: directory.id, name: directory.name, path }])
    await loadDirectories(directoryAccountId, directory.id)
  }

  const handleDirectoryBack = async () => {
    if (!directoryAccountId || directoryStack.length <= 1) return
    const nextStack = directoryStack.slice(0, -1)
    setDirectoryStack(nextStack)
    await loadDirectories(directoryAccountId, nextStack[nextStack.length - 1].id)
  }

  const handleDirectorySelect = () => {
    const currentPath = directoryStack[directoryStack.length - 1]?.path || ''
    const currentId = directoryStack[directoryStack.length - 1]?.id || '0'
    if (directoryTarget === 'task' && directoryTargetIndex !== null) {
      setTaskDraft((draft) => ({
        ...draft,
        targets: draft.targets.map((target, index) => index === directoryTargetIndex
          ? { ...target, save_root_id: currentId, save_root_name: currentPath }
          : target),
      }))
    } else {
      setImportRoot(currentPath)
    }
    setDirectoryModalOpen(false)
  }

  const handlePreviewImport = async (file: File) => {
    try {
      setImportPreview(await previewLearningImport(file))
      setImportMode('direct')
    } catch (importError: unknown) {
      message.error(getRequestErrorMessage(importError, '解析学习资料文件失败'))
    }
  }

  const handleConfirmImport = async () => {
    if (!importPreview) return
    if (importMode === 'transfer' && (!importAccountId || !importRoot.trim())) {
      message.warning('提交转存前请选择夸克账号和资料根目录')
      return
    }
    setImportConfirming(true)
    try {
      const result = await confirmLearningImport(importPreview.id, {
        mode: importMode,
        target_account_id: importMode === 'transfer' ? importAccountId : undefined,
        save_root: importMode === 'transfer' ? importRoot.trim() : undefined,
      })
      message.success(result.queued_count > 0 ? `已导入并排队 ${result.queued_count} 个转存任务` : '学习资料已导入')
      setImportPreview(null)
      await refreshFirstPage()
    } catch (importError: unknown) {
      message.error(getRequestErrorMessage(importError, '确认学习资料导入失败'))
    } finally {
      setImportConfirming(false)
    }
  }

  const startEditing = (item: LearningResource) => {
    setEditingId(item.id)
    setEditDraft({
      display_title: cleanLearningSheetText(item.display_title),
      category: cleanLearningSheetText(item.category?.name || '待分类'),
      tags: item.tags.map(cleanLearningSheetText).filter(Boolean).join('、'),
      share_url: cleanLearningSheetText(item.share_url || ''),
    })
  }

  const cancelEditing = () => {
    setEditingId(null)
    setEditDraft({ display_title: '', category: '', tags: '', share_url: '' })
  }

  const handleSaveEditing = async (item: LearningResource) => {
    setMaintenanceBusyId(item.id)
    try {
      await updateLearningResource(item.id, {
        display_title: editDraft.display_title.trim(),
        category: editDraft.category.trim() || '待分类',
        tags: editDraft.tags.split(/[、,，|]/).map((tag) => tag.trim()).filter(Boolean),
        share_url: editDraft.share_url.trim(),
      })
      message.success('资源已保存')
      cancelEditing()
      await refreshFirstPage()
    } catch (editError: unknown) {
      message.error(getRequestErrorMessage(editError, '保存资源失败'))
    } finally {
      setMaintenanceBusyId(null)
    }
  }

  const handleDeleteRow = async (item: LearningResource) => {
    setMaintenanceBusyId(item.id)
    try {
      await deleteLearningResource(item.id)
      message.success('资源及其学习资料记录已删除')
      await refreshFirstPage()
    } catch (deleteError: unknown) {
      message.error(getRequestErrorMessage(deleteError, '删除资源失败'))
    } finally {
      setMaintenanceBusyId(null)
    }
  }

  const handleDeleteAllImported = async () => {
    setDeletingAll(true)
    try {
      const result = await deleteAllImportedLearningResources()
      message.success(`已删除 ${result.deleted_resources} 条手动导入资料及其关联记录`)
      cancelEditing()
      await refreshFirstPage()
    } catch (deleteError: unknown) {
      message.error(getRequestErrorMessage(deleteError, '删除手动导入资料失败'))
    } finally {
      setDeletingAll(false)
    }
  }

  const handleRetry = async (item: LearningResource) => {
    setMaintenanceBusyId(item.id)
    try {
      await retryLearningResource(item.id)
      message.success('已重新加入转存队列')
      await refreshFirstPage()
    } catch (retryError: unknown) {
      message.error(getRequestErrorMessage(retryError, '重试转存失败'))
    } finally {
      setMaintenanceBusyId(null)
    }
  }

  const tabs = [
    { key: 'all', label: '全部 ' + resourceTotal },
    ...categories.map((category) => ({
      key: category.slug,
      label: category.name + ' ' + category.resource_count,
    })),
  ]

  return (
    <div className="learning-resources-page">
      {isAdmin && overview ? (
        <section className="learning-config-panel learning-automation-panel">
          <div className="learning-config-heading">
            <div>
              <Text strong>自动监听与转存</Text>
              <Text type="secondary">只有已启动的任务才会处理所选频道的新消息；已发布资料不会因暂停任务被删除。</Text>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateTask}>新建自动任务</Button>
          </div>
          {automationTasks.length === 0 ? (
            <div className="learning-task-empty">还没有自动任务。先选择监听频道和夸克账号，保存后再启动。</div>
          ) : (
            <div className="learning-task-list">
              {automationTasks.map((task) => (
                <article className="learning-task-row" key={task.id}>
                  <div className="learning-task-main">
                    <div className="learning-task-title-line">
                      <Text strong>{task.name}</Text>
                      <Tag color={taskStatusColor[task.status] || 'default'}>{taskStatusLabel[task.status] || task.status}</Tag>
                      {task.is_enabled ? <Tag color="green">自动监听已开启</Tag> : null}
                    </div>
                    <div className="learning-task-meta">
                      <span>频道：{task.channels.filter((channel) => channel.is_enabled).map((channel) => channel.channel_key || channel.channel_title).join('、') || '未配置'}</span>
                      <span>目标：{task.targets.filter((target) => target.is_enabled).map((target) => target.account_name || `账号 ${target.target_account_id}`).join('、') || '未配置'}</span>
                      <span>待处理 {task.pending_count}</span>
                      {task.failed_count > 0 ? <span className="learning-task-error-text">失败 {task.failed_count}</span> : null}
                    </div>
                    {task.last_error_message ? <div className="learning-task-error"><ExclamationCircleOutlined /> {task.last_error_message}</div> : null}
                  </div>
                  <Space className="learning-task-actions" wrap>
                    <Tooltip title="编辑任务"><Button type="text" icon={<EditOutlined />} aria-label="编辑任务" onClick={() => openEditTask(task)} /></Tooltip>
                    <Tooltip title={task.is_enabled ? '暂停自动监听' : '启动自动监听'}>
                      <Button type="text" icon={task.is_enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />} loading={taskBusyId === task.id} aria-label={task.is_enabled ? '暂停自动监听' : '启动自动监听'} onClick={() => void handleTaskToggle(task)} />
                    </Tooltip>
                    <Tooltip title="补充更新"><Button type="text" icon={<SyncOutlined />} loading={supplementTask?.id === task.id && supplementLoading} aria-label="补充更新" onClick={() => openSupplement(task)} disabled={task.status === 'invalid'} /></Tooltip>
                    <Tooltip title="重试失败任务"><Button type="text" icon={<ReloadOutlined />} loading={taskBusyId === task.id} aria-label="重试失败任务" onClick={() => void handleRetryTask(task)} disabled={task.failed_count === 0} /></Tooltip>
                    <Tooltip title="查看处理日志"><Button type="text" icon={<FileSearchOutlined />} aria-label="查看处理日志" onClick={() => void handleViewTaskLogs(task)} /></Tooltip>
                    <Popconfirm
                      title="删除这个自动任务？"
                      description="仅删除任务配置和任务日志，不删除已发布资料或夸克网盘文件。存在未完成转存项时需要先处理完成。"
                      okText="删除任务"
                      cancelText="取消"
                      onConfirm={() => void handleDeleteTask(task)}
                    >
                      <Tooltip title="删除自动任务"><Button type="text" danger icon={<DeleteOutlined />} loading={taskBusyId === task.id} aria-label="删除自动任务" /></Tooltip>
                    </Popconfirm>
                  </Space>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}

      <Modal
        open={supplementOpen}
        title={supplementTask ? `补充更新 · ${supplementTask.name}` : '补充更新'}
        width={980}
        onCancel={closeSupplement}
        footer={supplementRun ? (
          <Space>
            <Button onClick={closeSupplement}>关闭</Button>
            {['queued', 'running', 'pause_requested'].includes(supplementRun.status) ? (
              <Button icon={<PauseCircleOutlined />} loading={supplementPausing} onClick={() => void handlePauseSupplement()}>
                暂停补充更新
              </Button>
            ) : null}
          </Space>
        ) : (
          <Space>
            <Button onClick={closeSupplement}>取消</Button>
            <Button loading={supplementLoading} onClick={() => void handlePreviewSupplement()}>预览待处理内容</Button>
            <Button type="primary" loading={supplementLoading} disabled={!supplementPreview} onClick={() => void handleStartSupplement()}>
              开始补充更新
            </Button>
          </Space>
        )}
      >
        {!supplementRun ? (
          <div className="learning-supplement-panel">
            <Alert
              type="info"
              showIcon
              message="补处理监听期间遗漏的资源消息，不影响实时监听；已处理内容会自动跳过。"
            />
            <div className="learning-supplement-form">
              <Text strong>补充方式</Text>
              <Radio.Group
                value={supplementMode}
                onChange={(event) => {
                  setSupplementMode(event.target.value)
                  setSupplementPreview(null)
                }}
                optionType="button"
                buttonStyle="solid"
                options={[
                  { label: '继续上次补充', value: 'checkpoint' },
                  { label: '按日期范围', value: 'date_range' },
                  { label: '处理最近 N 条', value: 'recent' },
                ]}
              />
              <Text type="secondary">
                {supplementMode === 'checkpoint'
                  ? '从每个频道上次扫描到的原始消息位置继续。'
                  : supplementMode === 'date_range'
                    ? '扫描指定时间范围内的原始消息。'
                    : '按原始 Telegram 消息数量计算，不按拆分后的资源数量计算。'}
              </Text>
              {supplementMode === 'date_range' ? (
                <RangePicker
                  picker="date"
                  format="YYYY-MM-DD"
                  allowClear
                  inputReadOnly
                  placeholder={['开始日期', '结束日期']}
                  style={{ width: '100%' }}
                  value={supplementRange}
                  onChange={(value) => {
                    setSupplementRange(value && value[0] && value[1] ? [value[0], value[1]] : null)
                    setSupplementPreview(null)
                  }}
                />
              ) : null}
              {supplementMode === 'recent' ? (
                <InputNumber min={1} max={5000} value={supplementLimit} onChange={(value) => { setSupplementLimit(Number(value) || 10); setSupplementPreview(null) }} addonAfter="条有效资源消息" style={{ width: 240 }} />
              ) : null}
            </div>
            {supplementPreview ? (
              <div className="learning-supplement-preview">
                <div className="learning-supplement-summary">
                  <span>扫描原始消息：<strong>{supplementPreview.scanned_messages}</strong></span>
                  <span>有效资源消息：<strong>{supplementPreview.valid_messages}</strong></span>
                  <span>跳过无链接：<strong>{supplementPreview.skipped_messages}</strong></span>
                  <span>资源记录：<strong>{supplementPreview.resources}</strong></span>
                  <span>网盘链接：<strong>{supplementPreview.links}</strong></span>
                </div>
                <Text strong>原始消息预览</Text>
                <List
                  size="small"
                  bordered
                  dataSource={supplementPreview.message_previews}
                  locale={{ emptyText: '没有找到待补充内容' }}
                  renderItem={(preview) => (
                    <List.Item>
                      <div className="learning-supplement-message-preview">
                        <div className="learning-supplement-message-heading">
                          <Text strong>{preview.channel || '未知频道'}{preview.monitor_message_id ? ` · 原始消息 ${preview.monitor_message_id}` : ''}</Text>
                          <Tag color={preview.valid ? 'green' : 'default'}>{preview.valid ? '含有效链接' : '跳过'}</Tag>
                          <Text type="secondary">资源 {preview.resource_count} 条 · 链接 {preview.link_count} 个</Text>
                        </div>
                        <div className="learning-supplement-message-titles">{preview.resource_titles.join(' ｜ ') || '无可识别资源标题'}</div>
                        {preview.raw_text ? <pre>{preview.raw_text}</pre> : <Text type="secondary">历史记录未保存原始正文，仅展示解析结果。</Text>}
                      </div>
                    </List.Item>
                  )}
                />
                {supplementPreview.message_previews.length >= 50 ? <Text type="secondary">仅展示前 50 条原始消息，实际处理范围以统计结果为准。</Text> : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="learning-supplement-run-panel">
            <Alert
              type={supplementRun.status === 'failed' ? 'error' : supplementRun.status === 'completed' ? 'success' : 'info'}
              showIcon
              message={`补充更新${supplementRun.status === 'completed' ? '已完成' : supplementRun.status === 'failed' ? '失败' : supplementRun.status === 'paused' ? '已暂停' : '处理中'}`}
              description={supplementRun.last_error_message || '实时监听不受影响，已经创建的转存任务会继续按队列执行。'}
            />
            <div className="learning-supplement-summary">
              <span>扫描原始消息：<strong>{supplementRun.scanned_messages}</strong></span>
              <span>有效资源消息：<strong>{supplementRun.valid_messages}</strong></span>
              <span>资源记录：<strong>{supplementRun.resources}</strong></span>
              <span>新增转存任务：<strong>{supplementRun.jobs}</strong></span>
              <span>跳过已存在：<strong>{supplementRun.skipped_existing}</strong></span>
              <span>失败：<strong>{supplementRun.failed}</strong></span>
            </div>
          </div>
        )}
      </Modal>

      {isAdmin && overview ? (
        <section className="learning-import-panel">
          <div className="learning-admin-heading">
            <div>
              <Text strong>批量导入学习资料</Text>
              <Text type="secondary">支持 TXT / XLSX；先预览，确认后再入库或排队转存。</Text>
            </div>
            <Upload
              accept=".txt,.xlsx,.xlsm"
              showUploadList={false}
              beforeUpload={(file) => {
                void handlePreviewImport(file)
                return false
              }}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </div>
          {importPreview ? (
            <div className="learning-import-preview">
              <Alert
                type="info"
                showIcon
                message={`已解析 ${importPreview.total_records} 个资源、${importPreview.total_links} 个链接，${importPreview.invalid_count} 行异常`}
              />
              <Space wrap className="learning-import-controls">
                <Select
                  value={importMode}
                  options={[
                    { value: 'direct', label: '直接入库（已有自有分享）' },
                    { value: 'transfer', label: '提交夸克转存' },
                    { value: 'collect', label: '仅收集，暂不公开' },
                  ]}
                  onChange={setImportMode}
                  style={{ minWidth: 220 }}
                />
                {importMode === 'transfer' ? (
                  <>
                    <Select
                      value={importAccountId}
                      placeholder="选择夸克账号"
                      options={overview.accounts.filter((account) => account.is_enabled).map((account) => ({ value: account.id, label: account.account_name }))}
                      onChange={(value) => setImportAccountId(value)}
                      style={{ minWidth: 180 }}
                    />
                    <Input value={importRoot} placeholder="选择资料根目录" readOnly style={{ width: 220 }} />
                    <Button icon={<FolderOpenOutlined />} onClick={() => void openDirectoryPicker('import')} disabled={!importAccountId}>
                      选择目录
                    </Button>
                  </>
                ) : null}
                <Button type="primary" loading={importConfirming} onClick={() => void handleConfirmImport()}>确认导入</Button>
                <Button onClick={() => setImportPreview(null)}>取消</Button>
              </Space>
              <Table
                rowKey={(record) => `${record.display_title}-${record.category}`}
                size="small"
                pagination={{ pageSize: 8 }}
                dataSource={importPreview.records}
                columns={[
                  { title: '资源标题', dataIndex: 'display_title' },
                  { title: '分类', dataIndex: 'category', width: 120 },
                  { title: '标签', dataIndex: 'tags', render: (tags: string[]) => tags.join('、') || '-' },
                  { title: '链接数', dataIndex: 'links', render: (links: unknown[]) => links.length, width: 80 },
                ]}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      {error ? <Alert className="learning-alert" type="error" showIcon message={error} action={<Button onClick={() => void refreshFirstPage()}>重试</Button>} /> : null}

      <section className="learning-sheet">
        <div className="learning-sheet-toolbar">
          <div className="learning-sheet-tabs">
            {tabs.map((tab) => (
              <button key={tab.key} type="button" className={activeCategory === tab.key ? 'active' : ''} onClick={() => { setActiveCategory(tab.key); setPage(1) }}>
                {tab.label}
              </button>
            ))}
          </div>
          <Space>
            <Input.Search value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="搜索资源标题" allowClear style={{ width: 250 }} />
            <Tooltip title="刷新资料">
              <Button
                type="text"
                icon={<ReloadOutlined />}
                loading={loading}
                aria-label="刷新资料"
                onClick={() => void refreshFirstPage()}
              />
            </Tooltip>
            {isAdmin ? (
              <Popconfirm
                title="删除全部手动导入资料？"
                description="将永久删除项目中的手动导入记录、链接、转存任务和导入记录，不删除 Telegram 原消息或网盘远端文件。"
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={() => void handleDeleteAllImported()}
              >
                <Button danger loading={deletingAll} icon={<DeleteOutlined />}>删除全部导入</Button>
              </Popconfirm>
            ) : null}
          </Space>
        </div>
        <LearningResourceSheet
          resources={resources}
          total={resourceTotal}
          hasMore={resources.length < resourceTotal}
          isAdmin={isAdmin}
          loading={loading}
          editingId={editingId}
          editDraft={editDraft}
          maintenanceBusyId={maintenanceBusyId}
          onLoadMore={handleLoadMore}
          onStartEditing={startEditing}
          onCancelEditing={cancelEditing}
          onEditDraftChange={(field, value) => setEditDraft((draft) => ({ ...draft, [field]: value }))}
          onSaveEditing={(resource) => void handleSaveEditing(resource)}
          onDeleteRow={(resource) => void handleDeleteRow(resource)}
          onRetry={(resource) => void handleRetry(resource)}
        />
      </section>

      {isAdmin && overview ? (
        <Modal
          open={taskModalOpen}
          title={editingTaskId ? '编辑自动监听任务' : '新建自动监听任务'}
          width={780}
          okText="保存任务"
          cancelText="取消"
          confirmLoading={savingTask}
          onOk={() => void handleSaveTask()}
          onCancel={() => setTaskModalOpen(false)}
        >
          <div className="learning-task-form">
            <div className="learning-task-form-row">
              <Text strong>任务名称</Text>
              <Input value={taskDraft.name} placeholder="例如：考公资料自动归档" onChange={(event) => setTaskDraft((draft) => ({ ...draft, name: event.target.value }))} />
            </div>
            <div className="learning-task-form-row">
              <Text strong>监听频道</Text>
              <Select
                mode="multiple"
                value={taskDraft.channel_ids}
                placeholder="选择一个或多个频道"
                options={overview.channels.map((channel) => ({ value: channel.channel_id, label: `${channel.channel_key} · ${channel.channel_title}` }))}
                onChange={(values: number[]) => setTaskDraft((draft) => ({ ...draft, channel_ids: values }))}
                style={{ width: '100%' }}
                optionFilterProp="label"
              />
            </div>
            <div className="learning-task-form-section">
              <div className="learning-task-form-section-heading">
                <div>
                  <Text strong>转存目标</Text>
                  <Text type="secondary">同一个任务可以把每条消息转存到多个夸克账号；每个目标可使用不同根目录。</Text>
                </div>
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => {
                    const account = overview.accounts.find((item) => item.is_enabled)
                    setTaskDraft((draft) => ({
                      ...draft,
                      targets: [...draft.targets, {
                        target_account_id: account?.id || 0,
                        save_root_id: '0',
                        save_root_name: account?.default_save_root || '',
                        auto_create_category_dirs: true,
                        is_enabled: true,
                      }],
                    }))
                  }}
                >
                  添加目标
                </Button>
              </div>
              <div className="learning-task-target-list">
                {taskDraft.targets.map((target, index) => (
                  <div className="learning-task-target-row" key={`${target.id || 'new'}-${index}`}>
                    <Select
                      value={target.target_account_id || undefined}
                      placeholder="选择夸克账号"
                      options={overview.accounts.filter((account) => account.is_enabled).map((account) => ({ value: account.id, label: account.account_name }))}
                      onChange={(value: number) => {
                        const account = overview.accounts.find((item) => item.id === value)
                        setTaskDraft((draft) => ({
                          ...draft,
                          targets: draft.targets.map((item, itemIndex) => itemIndex === index
                            ? { ...item, target_account_id: value, save_root_id: '0', save_root_name: account?.default_save_root || '' }
                            : item),
                        }))
                      }}
                      style={{ minWidth: 180, flex: '0 0 180px' }}
                    />
                    <Input
                      value={target.save_root_name}
                      placeholder="账号默认目录"
                      readOnly
                      style={{ flex: 1 }}
                    />
                    <Button
                      icon={<FolderOpenOutlined />}
                      onClick={() => void openDirectoryPicker('task', index)}
                      disabled={!target.target_account_id}
                    >
                      选择目录
                    </Button>
                    <Tooltip title="移除此目标">
                      <Button
                        type="text"
                        danger
                        icon={<MinusCircleOutlined />}
                        aria-label="移除转存目标"
                        disabled={taskDraft.targets.length <= 1}
                        onClick={() => setTaskDraft((draft) => ({ ...draft, targets: draft.targets.filter((_, itemIndex) => itemIndex !== index) }))}
                      />
                    </Tooltip>
                  </div>
                ))}
              </div>
            </div>
            <div className="learning-task-form-footer">
              <Space>
                <Switch checked={taskDraft.is_enabled} onChange={(checked) => setTaskDraft((draft) => ({ ...draft, is_enabled: checked }))} />
                <Text>保存后立即启动自动监听与转存</Text>
              </Space>
              <Text type="secondary">默认只处理任务启动后的新消息；监听中断后可用“补充更新”补入。</Text>
            </div>
          </div>
        </Modal>
      ) : null}

      <Modal
        open={directoryModalOpen}
        title="选择网盘资料根目录"
        onCancel={() => setDirectoryModalOpen(false)}
        onOk={handleDirectorySelect}
        okText="选择当前目录"
        cancelText="取消"
      >
        <div className="learning-directory-path">当前路径：{directoryStack[directoryStack.length - 1]?.path || '网盘根目录'}</div>
        <Space style={{ marginBottom: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => void handleDirectoryBack()} disabled={directoryStack.length <= 1}>
            返回上级
          </Button>
        </Space>
        <List
          loading={directoryLoading}
          bordered
          dataSource={directoryItems}
          locale={{ emptyText: '当前目录没有子目录' }}
          renderItem={(directory) => (
            <List.Item
              actions={[<Button key={directory.id} type="link" onClick={() => void enterDirectory(directory)}>打开</Button>]}
            >
              <Space><FolderOpenOutlined />{directory.name}</Space>
            </List.Item>
          )}
        />
      </Modal>

      <Modal
        open={taskLogsOpen}
        title={taskLogsTask ? `自动任务处理终端 · ${taskLogsTask.name}` : '自动任务处理终端'}
        width={980}
        footer={null}
        onCancel={() => {
          setTaskLogsOpen(false)
          setTaskLogsTask(null)
        }}
      >
        <AppLogTerminal
          description="按实际发生顺序展示处理日志：原始消息 → 解析 → 入队 → 转存 → 分享 → 发布。每条日志保留原始消息、分类、账号和失败原因等关键上下文。清理只删除日志记录。"
          controls={
            <Button size="small" icon={<ReloadOutlined />} loading={taskLogsLoading} onClick={() => taskLogsTask && void handleViewTaskLogs(taskLogsTask)}>
              刷新
            </Button>
          }
          items={taskLogs.map((log) => ({
            key: log.id,
            text: buildLearningLogLine(log),
            tone: log.level === 'error' ? 'error' : log.level === 'warning' ? 'warning' : log.stage === 'published' ? 'success' : 'default',
          }))}
          emptyText={taskLogsLoading ? '正在读取任务日志……' : '暂无处理日志'}
          copyPayload={taskLogs.map(buildLearningLogLine)}
          copyEmptyText="当前没有可复制的日志"
          copySuccessText="已复制任务日志"
          copyButtonLabel="复制日志"
          onClearBackend={() => void handleClearTaskLogs()}
          clearBackendLoading={taskLogsClearing}
          clearBackendDisabled={taskLogs.length <= 0}
          clearBackendLabel="清理后端日志"
          clearBackendConfirmTitle="确认清理该自动任务日志？"
          clearBackendConfirmDescription="只删除这个任务的处理日志，不会删除学习资料、转存任务或网盘文件。"
        />
      </Modal>
    </div>
  )
}

export default LearningResourcesPage
