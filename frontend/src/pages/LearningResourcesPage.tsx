import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Input, List, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Tooltip, Typography, Upload, message } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, EditOutlined, ExclamationCircleOutlined, FileSearchOutlined, FolderOpenOutlined, MinusCircleOutlined, PauseCircleOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined, SyncOutlined, UploadOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import {
  deleteAllImportedLearningResources,
  deleteLearningResource,
  getLearningAdminItems,
  getLearningAdminOverview,
  getLearningAutomationLogs,
  getLearningAutomationTasks,
  getLearningDirectories,
  getPublicLearningCategories,
  getPublicLearningResources,
  confirmLearningImport,
  previewLearningImport,
  retryLearningResource,
  retryLearningAutomationTask,
  createLearningAutomationTask,
  processLearningAutomationTaskNow,
  pauseLearningAutomationTask,
  resumeLearningAutomationTask,
  updateLearningAutomationTask,
  updateLearningResource,
} from '@/api/learningResources'
import type {
  LearningAdminOverview,
  LearningCategory,
  LearningDirectory,
  LearningAutomationTask,
  LearningAutomationTaskTarget,
  LearningImportPreview,
  LearningResource,
} from '@/types/learningResources'
import LearningResourceSheet from '@/components/learning/LearningResourceSheet'
import { cleanLearningSheetText } from '@/utils/learningResources'

import './LearningResourcesPage.css'

const { Text } = Typography

type TaskDraftTarget = LearningAutomationTaskTarget

type LearningTaskDraft = {
  name: string
  is_enabled: boolean
  channel_ids: number[]
  targets: TaskDraftTarget[]
}

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
  const [taskLogs, setTaskLogs] = useState<Array<{ id: number; stage: string; level: string; message: string; created_at?: string | null }>>([])
  const [taskLogsOpen, setTaskLogsOpen] = useState(false)
  const [taskLogsLoading, setTaskLogsLoading] = useState(false)
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
        message.success('自动任务已暂停')
      } else {
        await resumeLearningAutomationTask(task.id)
        message.success('自动任务已恢复')
      }
      await refreshFirstPage()
    } catch (taskError: unknown) {
      message.error(getRequestErrorMessage(taskError, '更新自动任务状态失败'))
    } finally {
      setTaskBusyId(null)
    }
  }

  const handleProcessTask = async (task: LearningAutomationTask) => {
    setTaskBusyId(task.id)
    try {
      const result = await processLearningAutomationTaskNow(task.id)
      message.success(`已检查 ${result.selected_messages} 条消息，新增 ${result.jobs || 0} 个转存任务`)
      await refreshFirstPage()
    } catch (taskError: unknown) {
      message.error(getRequestErrorMessage(taskError, '立即处理失败'))
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
    setTaskLogsOpen(true)
    setTaskLogsLoading(true)
    try {
      const result = await getLearningAutomationLogs(task.id)
      setTaskLogs(result.items)
    } catch (logError: unknown) {
      message.error(getRequestErrorMessage(logError, '读取任务日志失败'))
      setTaskLogs([])
    } finally {
      setTaskLogsLoading(false)
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
                    <Tooltip title={task.is_enabled ? '暂停自动流程' : '启动自动流程'}>
                      <Button type="text" icon={task.is_enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />} loading={taskBusyId === task.id} aria-label={task.is_enabled ? '暂停自动流程' : '启动自动流程'} onClick={() => void handleTaskToggle(task)} />
                    </Tooltip>
                    <Tooltip title="立即处理最近消息"><Button type="text" icon={<SyncOutlined />} loading={taskBusyId === task.id} aria-label="立即处理最近消息" onClick={() => void handleProcessTask(task)} disabled={!task.is_enabled} /></Tooltip>
                    <Tooltip title="重试失败任务"><Button type="text" icon={<ReloadOutlined />} loading={taskBusyId === task.id} aria-label="重试失败任务" onClick={() => void handleRetryTask(task)} disabled={task.failed_count === 0} /></Tooltip>
                    <Tooltip title="查看处理日志"><Button type="text" icon={<FileSearchOutlined />} aria-label="查看处理日志" onClick={() => void handleViewTaskLogs(task)} /></Tooltip>
                  </Space>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}

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
              <Text type="secondary">默认只处理任务启动后的新消息；历史消息可用“立即处理”补入。</Text>
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
        title="自动任务处理日志"
        width={820}
        footer={null}
        onCancel={() => setTaskLogsOpen(false)}
      >
        <Table
          rowKey="id"
          size="small"
          loading={taskLogsLoading}
          pagination={{ pageSize: 12 }}
          dataSource={taskLogs}
          locale={{ emptyText: '暂无处理日志' }}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 170, render: (value: string | null | undefined) => value ? new Date(value).toLocaleString() : '-' },
            { title: '阶段', dataIndex: 'stage', width: 90 },
            { title: '级别', dataIndex: 'level', width: 75, render: (value: string) => <Tag color={value === 'error' ? 'error' : value === 'warning' ? 'warning' : 'default'}>{value}</Tag> },
            { title: '处理信息', dataIndex: 'message', render: (value: string) => <span className="learning-log-message">{value}</span> },
          ]}
        />
      </Modal>
    </div>
  )
}

export default LearningResourcesPage
