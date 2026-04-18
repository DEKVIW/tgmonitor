import { useEffect, useMemo, useState } from 'react'
import type { Key } from 'react'
import { Alert, Form, Input, InputNumber, Modal, Select, Space, Switch, Tabs, Tooltip, message } from 'antd'
import type { TablePaginationConfig } from 'antd/es/table'
import { QuestionCircleOutlined } from '@ant-design/icons'

import {
  cancelPanTransferBatch,
  clearPanTransferBatchLogs,
  createPanTransferFollowTaskFromBatchItem,
  createManualPanTransferBatch,
  createPanTransferAccount,
  deletePanTransferAccount,
  deletePanTransferBatch,
  getPanTransferBatchDetail,
  listPanTransferAccounts,
  listPanTransferBatches,
  publishPanTransferBatchItemMessage,
  previewManualPanTransfer,
  retryPanTransferBatch,
  startPanTransferBatch,
  updatePanTransferAccount,
  validatePanTransferAccount,
} from '@/api/panTransfer'
import { usePageVisibility } from '@/hooks/usePageVisibility'
import type {
  PanTransferAccountCreateRequest,
  PanTransferAccountItem,
  PanTransferAccountUpdateRequest,
  PanTransferBatchCreateRequest,
  PanTransferBatchDetailResponse,
  PanTransferBatchItem,
  PanTransferBatchSummaryItem,
  PanTransferManualPreviewRequest,
  PanTransferManualPreviewResponse,
  PanTransferMessagePublishRequest,
} from '@/types/panTransfer'

import AccountsSection from './AccountsSection'
import BatchSection from './BatchSection'
import FollowTasksSection from './FollowTasksSectionV2'
import PublishSection from './PublishSectionPanel'
import PreviewSection from './PreviewSection'
import {
  BATCH_FOLDER_NAME_OPTIONS,
  type BatchCreateDraft,
  type BatchPagination,
  buildDefaultTargetAccountSelections,
  buildPreviewPayload,
  buildTargetAccountOptionsByPlatform,
  CODED_ITEM_TEMPLATE,
  DEFAULT_BATCH_CREATE_DRAFT,
  DEFAULT_PREVIEW_DRAFT,
  formatRetryDelay,
  getErrorMessage,
  ITEM_FOLDER_TEMPLATE_PRESET_OPTIONS,
  MASKED_MIX_ITEM_TEMPLATE,
  MASKED_CN_ITEM_TEMPLATE,
  PLATFORM_OPTIONS,
  type PreviewDraft,
  RETRY_DELAY_OPTIONS,
  resolveBatchCreateTemplate,
  SHARE_MODE_OPTIONS,
  SHARE_TARGET_MODE_OPTIONS,
  type TargetAccountSelectionMap,
  TRANSFER_LAYOUT_OPTIONS,
} from './shared'
import '../ResourceOpsTransferCenter.css'

const TRANSFER_CENTER_TAB_STORAGE_KEY = 'resource-ops-transfer-center-active-tab'
const TRANSFER_CENTER_TAB_KEYS = new Set(['accounts', 'batches', 'follow', 'publish'])

const getInitialTransferCenterTab = () => {
  if (typeof window === 'undefined') {
    return 'accounts'
  }
  const saved = window.sessionStorage.getItem(TRANSFER_CENTER_TAB_STORAGE_KEY)
  return saved && TRANSFER_CENTER_TAB_KEYS.has(saved) ? saved : 'accounts'
}

const renderBatchCreateLabel = (label: string, tip: string) => (
  <span className="resource-ops-transfer-create-label">
    <span>{label}</span>
    <Tooltip title={tip}>
      <QuestionCircleOutlined className="resource-ops-transfer-create-label-icon" />
    </Tooltip>
  </span>
)

type BatchBulkAction = 'start' | 'cancel' | 'retry' | 'delete'

const ResourceOpsTransferCenterMain = () => {
  const [activeTab, setActiveTab] = useState(getInitialTransferCenterTab)
  const isPageVisible = usePageVisibility()
  const [accounts, setAccounts] = useState<PanTransferAccountItem[]>([])
  const [accountsLoading, setAccountsLoading] = useState(false)
  const [accountModalOpen, setAccountModalOpen] = useState(false)
  const [accountSaving, setAccountSaving] = useState(false)
  const [validatingAccountId, setValidatingAccountId] = useState<number | null>(null)
  const [deletingAccountId, setDeletingAccountId] = useState<number | null>(null)
  const [editingAccount, setEditingAccount] = useState<PanTransferAccountItem | null>(null)

  const [previewDraft, setPreviewDraft] = useState<PreviewDraft>(DEFAULT_PREVIEW_DRAFT)
  const [previewData, setPreviewData] = useState<PanTransferManualPreviewResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [lastPreviewPayload, setLastPreviewPayload] = useState<PanTransferManualPreviewRequest | null>(null)
  const [selectedPreviewKeys, setSelectedPreviewKeys] = useState<Key[]>([])
  const [targetAccountIdsByPlatform, setTargetAccountIdsByPlatform] = useState<TargetAccountSelectionMap>({})

  const [batchCreateModalOpen, setBatchCreateModalOpen] = useState(false)
  const [batchCreateDraft, setBatchCreateDraft] = useState<BatchCreateDraft>(DEFAULT_BATCH_CREATE_DRAFT)
  const [batchCreating, setBatchCreating] = useState(false)

  const [batches, setBatches] = useState<PanTransferBatchSummaryItem[]>([])
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchPagination, setBatchPagination] = useState<BatchPagination>({ page: 1, pageSize: 10, total: 0 })
  const [startingBatchId, setStartingBatchId] = useState<number | null>(null)
  const [cancellingBatchId, setCancellingBatchId] = useState<number | null>(null)
  const [retryingBatchId, setRetryingBatchId] = useState<number | null>(null)
  const [deletingBatchId, setDeletingBatchId] = useState<number | null>(null)
  const [clearingLogsBatchId, setClearingLogsBatchId] = useState<number | null>(null)

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<PanTransferBatchDetailResponse | null>(null)
  const [selectedBatchKeys, setSelectedBatchKeys] = useState<Key[]>([])
  const [selectedDetailItemKeys, setSelectedDetailItemKeys] = useState<Key[]>([])
  const [publishModalOpen, setPublishModalOpen] = useState(false)
  const [publishingItem, setPublishingItem] = useState<PanTransferBatchItem | null>(null)
  const [publishingItemId, setPublishingItemId] = useState<number | null>(null)
  const [bulkPublishing, setBulkPublishing] = useState(false)
  const [creatingFollowItemId, setCreatingFollowItemId] = useState<number | null>(null)
  const [bulkCreatingFollow, setBulkCreatingFollow] = useState(false)
  const [batchBulkAction, setBatchBulkAction] = useState<BatchBulkAction | null>(null)
  const [followRefreshToken, setFollowRefreshToken] = useState(0)
  const [publishRefreshToken, setPublishRefreshToken] = useState(0)

  const [accountForm] = Form.useForm()
  const [publishForm] = Form.useForm()

  const loadAccounts = async () => {
    setAccountsLoading(true)
    try {
      const response = await listPanTransferAccounts()
      setAccounts(response.items)
    } catch (error) {
      message.error(getErrorMessage(error, '加载转存账号失败'))
    } finally {
      setAccountsLoading(false)
    }
  }

  const loadBatches = async (
    page = batchPagination.page,
    pageSize = batchPagination.pageSize,
    options?: { silent?: boolean }
  ) => {
    if (!(options?.silent ?? false)) {
      setBatchLoading(true)
    }
    try {
      const response = await listPanTransferBatches(page, pageSize)
      setBatches(response.items)
      setSelectedBatchKeys((current) => {
        const availableIds = new Set(response.items.map((item) => item.id))
        return current.filter((item) => availableIds.has(Number(item)))
      })
      setBatchPagination({ page: response.page, pageSize: response.page_size, total: response.total })
    } catch (error) {
      message.error(getErrorMessage(error, '加载转存批次失败'))
    } finally {
      if (!(options?.silent ?? false)) {
        setBatchLoading(false)
      }
    }
  }

  const applyBatchDetail = (response: PanTransferBatchDetailResponse) => {
    setDetailData(response)
    setSelectedDetailItemKeys((current) => {
      const available = new Set(response.items.map((item) => item.id))
      return current.filter((itemId) => available.has(Number(itemId)))
    })
  }

  const loadBatchDetail = async (batchId: number, options?: { open?: boolean; silent?: boolean }) => {
    if (!(options?.silent ?? false)) {
      setDetailLoading(true)
    }
    try {
      const response = await getPanTransferBatchDetail(batchId)
      applyBatchDetail(response)
      if (options?.open ?? true) {
        setDetailOpen(true)
      }
    } catch (error) {
      message.error(getErrorMessage(error, '加载批次明细失败'))
    } finally {
      if (!(options?.silent ?? false)) {
        setDetailLoading(false)
      }
    }
  }

  useEffect(() => {
    void Promise.all([loadAccounts(), loadBatches(1, batchPagination.pageSize)])
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined' || !TRANSFER_CENTER_TAB_KEYS.has(activeTab)) {
      return
    }
    window.sessionStorage.setItem(TRANSFER_CENTER_TAB_STORAGE_KEY, activeTab)
  }, [activeTab])

  useEffect(() => {
    const shouldPollBatchList = activeTab === 'batches' && batches.some((item) => item.status === 'running')
    const shouldPollBatchDetail = detailOpen && detailData?.batch.status === 'running'

    if (!isPageVisible || (!shouldPollBatchList && !shouldPollBatchDetail)) {
      return
    }

    const timer = window.setInterval(() => {
      if (shouldPollBatchList) {
        void loadBatches(batchPagination.page, batchPagination.pageSize, { silent: true })
      }
      if (shouldPollBatchDetail && detailData) {
        void loadBatchDetail(detailData.batch.id, { open: false, silent: true })
      }
    }, 4000)

    return () => window.clearInterval(timer)
  }, [
    activeTab,
    batchPagination.page,
    batchPagination.pageSize,
    batches,
    detailData,
    detailOpen,
    isPageVisible,
  ])

  const missingPlatforms = useMemo(() => {
    const enabledPlatforms = new Set(accounts.filter((item) => item.is_enabled).map((item) => item.platform))
    return PLATFORM_OPTIONS.filter((item) => !enabledPlatforms.has(item.value))
  }, [accounts])

  const targetAccountOptionsByPlatform = useMemo(
    () => buildTargetAccountOptionsByPlatform(accounts),
    [accounts]
  )

  useEffect(() => {
    const defaults = buildDefaultTargetAccountSelections(accounts)
    setTargetAccountIdsByPlatform((current) => {
      const next: TargetAccountSelectionMap = {}
      const platforms = new Set([
        ...Object.keys(current),
        ...Object.keys(defaults),
        ...Object.keys(targetAccountOptionsByPlatform),
      ])
      platforms.forEach((platform) => {
        const options = targetAccountOptionsByPlatform[platform] || []
        if (options.length <= 0) {
          return
        }
        const currentValue = current[platform]
        if (currentValue && options.some((option) => option.value === currentValue)) {
          next[platform] = currentValue
          return
        }
        next[platform] = defaults[platform] || options[0]?.value
      })
      return next
    })
  }, [accounts, targetAccountOptionsByPlatform])

  const batchPathPreview = useMemo(() => {
    const itemFolderName =
      batchCreateDraft.itemFolderPreset === 'masked_mix'
        ? '<强混淆乱码标题>'
        : batchCreateDraft.itemFolderPreset === 'masked_cn'
          ? '<中文混淆标题>'
          : batchCreateDraft.itemFolderPreset === 'coded'
              ? 'tg-transfer-<批次>-<项目>-<标题slug>'
              : resolveBatchCreateTemplate(batchCreateDraft).trim() || MASKED_MIX_ITEM_TEMPLATE
    const folderParts = ['<账号根目录>']
    if (batchCreateDraft.transferLayout === 'batch_archive') {
      folderParts.push(batchCreateDraft.batchFolderName.trim() || '剧集')
    }
    folderParts.push(itemFolderName)
    const resourceDirPath = folderParts.join('/')
    const transferPath = `${resourceDirPath}/<原分享目录或文件>`
    const sharePath =
      batchCreateDraft.shareTargetMode === 'content_root'
        ? `${resourceDirPath}/<原分享目录或文件>`
        : resourceDirPath
    const shareTip =
      batchCreateDraft.shareTargetMode === 'content_root'
        ? '默认优先分享转存后的原分享目录；如果该层不唯一，系统会自动回退为资源目录。'
        : '默认分享资源目录，原分享目录或文件会保留在该目录下一层。'
    return {
      itemFolderName,
      transferPath,
      sharePath,
      shareTip,
    }
  }, [batchCreateDraft])

  const currentTemplatePresetMeta = useMemo(
    () =>
      ITEM_FOLDER_TEMPLATE_PRESET_OPTIONS.find((item) => item.value === batchCreateDraft.itemFolderPreset) ||
      ITEM_FOLDER_TEMPLATE_PRESET_OPTIONS[0],
    [batchCreateDraft.itemFolderPreset]
  )

  const selectedTargetAccountSummary = useMemo(() => {
    const platforms = previewDraft.platforms.length > 0 ? previewDraft.platforms : Object.keys(targetAccountOptionsByPlatform)
    const parts = platforms
      .map((platform) => {
        const options = targetAccountOptionsByPlatform[platform] || []
        const selectedAccountId = targetAccountIdsByPlatform[platform]
        const label = options.find((option) => option.value === selectedAccountId)?.label
        return label ? `${platform}：${label}` : ''
      })
      .filter(Boolean)
    return parts.length > 0 ? parts.join(' / ') : '按各平台默认账号执行'
  }, [previewDraft.platforms, targetAccountIdsByPlatform, targetAccountOptionsByPlatform])

  const publishSourceHint = useMemo(() => {
    if (!publishingItem) return null
    if (publishingItem.new_link_target_url) {
      return { label: '已回写新链接', url: publishingItem.new_link_target_url }
    }
    if (publishingItem.new_share_url) {
      return { label: '新分享链接', url: publishingItem.new_share_url }
    }
    if (publishingItem.original_url) {
      return { label: '原始链接', url: publishingItem.original_url }
    }
    return null
  }, [publishingItem])

  const getBatchItemPublishDefaults = (item: PanTransferBatchItem) => {
    const snapshot = (item.extra_json?.source_message_snapshot as Record<string, unknown> | undefined) || {}
    const snapshotDescription = typeof snapshot.description === 'string' ? snapshot.description.trim() : ''
    const snapshotTags = Array.isArray(snapshot.tags)
      ? snapshot.tags.filter((tag): tag is string => typeof tag === 'string').map((tag) => tag.trim()).filter(Boolean)
      : []
    return {
      title: item.short_title || (typeof snapshot.title === 'string' ? snapshot.title : '') || '',
      description: item.source_message_description || snapshotDescription || '',
      tags: Array.isArray(item.source_message_tags) && item.source_message_tags.length > 0 ? item.source_message_tags : snapshotTags,
    }
  }

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

  const openPublishModal = (item: PanTransferBatchItem) => {
    setPublishingItem(item)
    publishForm.resetFields()
    const defaults = getBatchItemPublishDefaults(item)
    publishForm.setFieldsValue({
      title: defaults.title,
      description: defaults.description,
      tags: defaults.tags,
    })
    setPublishModalOpen(true)
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
        message.success('账号已更新')
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
        message.success('账号已创建')
      }
      setAccountModalOpen(false)
      setEditingAccount(null)
      accountForm.resetFields()
      await loadAccounts()
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '保存账号失败'))
    } finally {
      setAccountSaving(false)
    }
  }

  const refreshPreviewPage = async (pagination: TablePaginationConfig) => {
    if (!lastPreviewPayload) return
    setPreviewLoading(true)
    try {
      const payload = {
        ...lastPreviewPayload,
        page: pagination.current || 1,
        page_size: pagination.pageSize || lastPreviewPayload.page_size || 10,
      }
      const response = await previewManualPanTransfer(payload)
      setPreviewData(response)
      setLastPreviewPayload(payload)
    } catch (error) {
      message.error(getErrorMessage(error, '刷新预览失败'))
    } finally {
      setPreviewLoading(false)
    }
  }

  const runBatchRetry = async (batchId: number, itemIds?: number[]) => {
    setRetryingBatchId(batchId)
    try {
      const response = await retryPanTransferBatch(batchId, itemIds && itemIds.length > 0 ? { item_ids: itemIds } : {})
      message.success(itemIds && itemIds.length > 0 ? '已提交所选失败项重试' : '已提交批次失败项重试')
      applyBatchDetail(response)
      setDetailOpen(true)
      await loadBatches(batchPagination.page, batchPagination.pageSize)
    } catch (error) {
      message.error(getErrorMessage(error, '重试批次失败'))
    } finally {
      setRetryingBatchId(null)
    }
  }

  const runBatchCancel = async (batchId: number) => {
    setCancellingBatchId(batchId)
    try {
      const response = await cancelPanTransferBatch(batchId)
      message.success(`批次 #${batchId} 已停止，当前处理中的任务会在本次尝试结束后退出`)
      applyBatchDetail(response)
      setDetailOpen(true)
      await loadBatches(batchPagination.page, batchPagination.pageSize)
    } catch (error) {
      message.error(getErrorMessage(error, '停止批次失败'))
    } finally {
      setCancellingBatchId(null)
    }
  }

  const runBatchClearLogs = async (batchId: number) => {
    setClearingLogsBatchId(batchId)
    try {
      const response = await clearPanTransferBatchLogs(batchId)
      message.success(`批次 #${batchId} 的执行日志已清理`)
      applyBatchDetail(response)
      setDetailOpen(true)
      await loadBatches(batchPagination.page, batchPagination.pageSize)
    } catch (error) {
      message.error(getErrorMessage(error, '清理批次日志失败'))
    } finally {
      setClearingLogsBatchId(null)
    }
  }

  const handlePublishMessage = async () => {
    if (!publishingItem) return
    try {
      const values = await publishForm.validateFields()
      setPublishingItemId(publishingItem.id)
      const payload: PanTransferMessagePublishRequest = {
        title: values.title,
        description: values.description || null,
        tags: Array.isArray(values.tags) ? values.tags : [],
      }
      const response = await publishPanTransferBatchItemMessage(
        publishingItem.batch_id,
        publishingItem.id,
        payload
      )
      message.success(`已发布到前台，消息 #${response.message_id}`)
      setPublishModalOpen(false)
      setPublishingItem(null)
      publishForm.resetFields()
      setPublishRefreshToken((current) => current + 1)
      await loadBatchDetail(publishingItem.batch_id, { open: false })
      await loadBatches(batchPagination.page, batchPagination.pageSize)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '发布消息失败'))
    } finally {
      setPublishingItemId(null)
    }
  }

  const handleCreateFollowTask = async (item: PanTransferBatchItem) => {
    setCreatingFollowItemId(item.id)
    try {
      const response = await createPanTransferFollowTaskFromBatchItem(item.batch_id, item.id, {})
      message.success(`已创建追更任务 #${response.task.id}`)
      setActiveTab('follow')
      setFollowRefreshToken((current) => current + 1)
    } catch (error) {
      message.error(getErrorMessage(error, '创建追更任务失败'))
    } finally {
      setCreatingFollowItemId(null)
    }
  }

  const handlePreview = async () => {
    setPreviewLoading(true)
    try {
      const payload = buildPreviewPayload(previewDraft)
      const response = await previewManualPanTransfer(payload)
      setPreviewData(response)
      setLastPreviewPayload(payload)
      setSelectedPreviewKeys([])
    } catch (error) {
      message.error(getErrorMessage(error, '查询转存资源失败'))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleBulkPublishSelected = async () => {
    if (!detailData) return
    const selectedSet = new Set(selectedDetailItemKeys.map((item) => Number(item)))
    const selectedRows = detailData.items.filter((item) => selectedSet.has(item.id))
    if (selectedRows.length <= 0) {
      message.warning('请先选择要发布的资源')
      return
    }
    setBulkPublishing(true)
    let successCount = 0
    let failureCount = 0
    for (const item of selectedRows) {
      try {
        const defaults = getBatchItemPublishDefaults(item)
        await publishPanTransferBatchItemMessage(item.batch_id, item.id, {
          title: defaults.title,
          description: defaults.description || null,
          tags: defaults.tags,
        })
        successCount += 1
      } catch {
        failureCount += 1
      }
    }
    setBulkPublishing(false)
    if (successCount > 0) {
      setPublishRefreshToken((current) => current + 1)
      await loadBatchDetail(detailData.batch.id, { open: false })
      await loadBatches(batchPagination.page, batchPagination.pageSize)
    }
    if (failureCount > 0) {
      message.warning(`批量发布完成，成功 ${successCount} 条，失败 ${failureCount} 条`)
    } else {
      message.success(`已批量发布 ${successCount} 条资源到前台`)
    }
  }

  const handleBulkCreateFollowSelected = async () => {
    if (!detailData) return
    const selectedSet = new Set(selectedDetailItemKeys.map((item) => Number(item)))
    const selectedRows = detailData.items.filter((item) => selectedSet.has(item.id))
    if (selectedRows.length <= 0) {
      message.warning('请先选择要转为追更的资源')
      return
    }
    setBulkCreatingFollow(true)
    let successCount = 0
    let failureCount = 0
    for (const item of selectedRows) {
      try {
        await createPanTransferFollowTaskFromBatchItem(item.batch_id, item.id, {})
        successCount += 1
      } catch {
        failureCount += 1
      }
    }
    setBulkCreatingFollow(false)
    if (successCount > 0) {
      setFollowRefreshToken((current) => current + 1)
    }
    if (failureCount > 0) {
      message.warning(`批量创建追更完成，成功 ${successCount} 条，失败 ${failureCount} 条`)
    } else {
      message.success(`已批量创建 ${successCount} 条追更任务`)
    }
  }

  const getSelectedBatchRows = () => {
    const selectedSet = new Set(selectedBatchKeys.map((item) => Number(item)))
    return batches.filter((item) => selectedSet.has(item.id))
  }

  const handleBulkStartBatches = async () => {
    const selectedRows = getSelectedBatchRows()
    if (selectedRows.length <= 0) {
      message.warning('请先选择要启动的批次')
      return
    }

    const eligibleRows = selectedRows.filter((item) => item.status === 'draft')
    if (eligibleRows.length <= 0) {
      message.warning('所选批次里没有可启动的草稿批次')
      return
    }

    setBatchBulkAction('start')
    let successCount = 0
    let failureCount = 0
    const skippedCount = selectedRows.length - eligibleRows.length

    try {
      for (const batch of eligibleRows) {
        try {
          const response = await startPanTransferBatch(batch.id)
          if (detailData?.batch.id === batch.id) {
            applyBatchDetail(response)
            setDetailOpen(true)
          }
          successCount += 1
        } catch {
          failureCount += 1
        }
      }

      await loadBatches(batchPagination.page, batchPagination.pageSize)
      if (failureCount > 0 || skippedCount > 0) {
        message.warning(`批量启动完成，成功 ${successCount} 个，失败 ${failureCount} 个，跳过 ${skippedCount} 个`)
      } else {
        message.success(`已批量启动 ${successCount} 个批次`)
      }
    } finally {
      setBatchBulkAction(null)
    }
  }

  const handleBulkCancelBatches = async () => {
    const selectedRows = getSelectedBatchRows()
    if (selectedRows.length <= 0) {
      message.warning('请先选择要停止的批次')
      return
    }

    const eligibleRows = selectedRows.filter((item) => item.can_cancel)
    if (eligibleRows.length <= 0) {
      message.warning('所选批次里没有可停止的运行中批次')
      return
    }

    setBatchBulkAction('cancel')
    let successCount = 0
    let failureCount = 0
    const skippedCount = selectedRows.length - eligibleRows.length

    try {
      for (const batch of eligibleRows) {
        try {
          const response = await cancelPanTransferBatch(batch.id)
          if (detailData?.batch.id === batch.id) {
            applyBatchDetail(response)
            setDetailOpen(true)
          }
          successCount += 1
        } catch {
          failureCount += 1
        }
      }

      await loadBatches(batchPagination.page, batchPagination.pageSize)
      if (failureCount > 0 || skippedCount > 0) {
        message.warning(`批量停止完成，成功 ${successCount} 个，失败 ${failureCount} 个，跳过 ${skippedCount} 个`)
      } else {
        message.success(`已批量停止 ${successCount} 个批次`)
      }
    } finally {
      setBatchBulkAction(null)
    }
  }

  const handleBulkRetryBatches = async () => {
    const selectedRows = getSelectedBatchRows()
    if (selectedRows.length <= 0) {
      message.warning('请先选择要重试的批次')
      return
    }

    const eligibleRows = selectedRows.filter((item) => item.can_retry)
    if (eligibleRows.length <= 0) {
      message.warning('所选批次里没有可重试的批次')
      return
    }

    setBatchBulkAction('retry')
    let successCount = 0
    let failureCount = 0
    const skippedCount = selectedRows.length - eligibleRows.length

    try {
      for (const batch of eligibleRows) {
        try {
          const response = await retryPanTransferBatch(batch.id, {})
          if (detailData?.batch.id === batch.id) {
            applyBatchDetail(response)
            setDetailOpen(true)
          }
          successCount += 1
        } catch {
          failureCount += 1
        }
      }

      await loadBatches(batchPagination.page, batchPagination.pageSize)
      if (failureCount > 0 || skippedCount > 0) {
        message.warning(`批量重试完成，成功 ${successCount} 个，失败 ${failureCount} 个，跳过 ${skippedCount} 个`)
      } else {
        message.success(`已批量提交 ${successCount} 个批次的失败项重试`)
      }
    } finally {
      setBatchBulkAction(null)
    }
  }

  const handleBulkDeleteBatches = async () => {
    const selectedRows = getSelectedBatchRows()
    if (selectedRows.length <= 0) {
      message.warning('请先选择要删除的批次')
      return
    }

    const eligibleRows = selectedRows.filter((item) => item.can_delete)
    if (eligibleRows.length <= 0) {
      message.warning('所选批次里没有可删除的批次')
      return
    }

    setBatchBulkAction('delete')
    let successCount = 0
    let failureCount = 0
    const skippedCount = selectedRows.length - eligibleRows.length
    const deletedBatchIds = new Set<number>()

    try {
      for (const batch of eligibleRows) {
        try {
          await deletePanTransferBatch(batch.id)
          deletedBatchIds.add(batch.id)
          successCount += 1
        } catch {
          failureCount += 1
        }
      }

      if (detailData?.batch.id && deletedBatchIds.has(detailData.batch.id)) {
        setDetailOpen(false)
        setDetailData(null)
        setSelectedDetailItemKeys([])
      }
      setSelectedBatchKeys((current) => current.filter((item) => !deletedBatchIds.has(Number(item))))

      const nextPage =
        batchPagination.page > 1 && successCount > 0 && successCount === batches.length
          ? batchPagination.page - 1
          : batchPagination.page
      await loadBatches(nextPage, batchPagination.pageSize)

      if (failureCount > 0 || skippedCount > 0) {
        message.warning(`批量删除完成，成功 ${successCount} 个，失败 ${failureCount} 个，跳过 ${skippedCount} 个`)
      } else {
        message.success(`已批量删除 ${successCount} 个批次`)
      }
    } finally {
      setBatchBulkAction(null)
    }
  }

  return (
    <div className="resource-ops-transfer-stack">
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        className="resource-ops-transfer-tabs"
        items={[
          {
            key: 'accounts',
            label: '网盘账号',
            children: (
              <AccountsSection
                accounts={accounts}
                accountsLoading={accountsLoading}
                validatingAccountId={validatingAccountId}
                deletingAccountId={deletingAccountId}
                missingPlatforms={missingPlatforms}
                onRefresh={() => void loadAccounts()}
                onCreate={openCreateModal}
                onEdit={openEditModal}
                onValidate={(account) => void (async () => {
                  setValidatingAccountId(account.id)
                  try {
                    await validatePanTransferAccount(account.id)
                    message.success(`${account.account_name} 校验完成`)
                    await loadAccounts()
                  } catch (error) {
                    message.error(getErrorMessage(error, '账号校验失败'))
                  } finally {
                    setValidatingAccountId(null)
                  }
                })()}
                onDelete={(account) => void (async () => {
                  setDeletingAccountId(account.id)
                  try {
                    await deletePanTransferAccount(account.id)
                    message.success('账号已删除')
                    await loadAccounts()
                  } catch (error) {
                    message.error(getErrorMessage(error, '删除账号失败'))
                  } finally {
                    setDeletingAccountId(null)
                  }
                })()}
              />
            ),
          },
          {
            key: 'batches',
            label: '批量转存',
            children: (
              <div className="resource-ops-transfer-tab-stack">
                <PreviewSection
                  draft={previewDraft}
                  previewData={previewData}
                  previewLoading={previewLoading}
                  selectedPreviewKeys={selectedPreviewKeys}
                  targetAccountOptionsByPlatform={targetAccountOptionsByPlatform}
                  selectedTargetAccountIds={targetAccountIdsByPlatform}
                  onDraftChange={(updater) => setPreviewDraft((current) => updater(current))}
                  onTargetAccountChange={(platform, accountId) =>
                    setTargetAccountIdsByPlatform((current) => ({
                      ...current,
                      [platform]: accountId,
                    }))
                  }
                  onPreview={() => void handlePreview()}
                  onOpenCreateBatch={() => {
                    if (selectedPreviewKeys.length <= 0) {
                      message.warning('请先勾选要转存的链接')
                      return
                    }
                    setBatchCreateDraft(DEFAULT_BATCH_CREATE_DRAFT)
                    setBatchCreateModalOpen(true)
                  }}
                  onSelectionChange={setSelectedPreviewKeys}
                  onTableChange={(pagination) => void refreshPreviewPage(pagination)}
                />

                <BatchSection
                  batches={batches}
                  batchLoading={batchLoading}
                  batchPagination={batchPagination}
                  startingBatchId={startingBatchId}
                  cancellingBatchId={cancellingBatchId}
                  retryingBatchId={retryingBatchId}
                  publishingItemId={publishingItemId}
                  creatingFollowItemId={creatingFollowItemId}
                  deletingBatchId={deletingBatchId}
                  clearingLogsBatchId={clearingLogsBatchId}
                  detailOpen={detailOpen}
                  detailLoading={detailLoading}
                  detailData={detailData}
                  selectedBatchKeys={selectedBatchKeys}
                  selectedItemKeys={selectedDetailItemKeys}
                  batchBulkAction={batchBulkAction}
                  bulkPublishing={bulkPublishing}
                  bulkCreatingFollow={bulkCreatingFollow}
                  onRefresh={() => void loadBatches()}
                  onTableChange={(pagination) =>
                    void loadBatches(pagination.current || 1, pagination.pageSize || batchPagination.pageSize)
                  }
                  onOpenDetail={(batchId) => void loadBatchDetail(batchId, { open: true })}
                  onStart={(batchId) => void (async () => {
                    setStartingBatchId(batchId)
                    try {
                      const response = await startPanTransferBatch(batchId)
                      message.success(`批次 #${batchId} 已启动`)
                      applyBatchDetail(response)
                      setDetailOpen(true)
                      await loadBatches(batchPagination.page, batchPagination.pageSize)
                    } catch (error) {
                      message.error(getErrorMessage(error, '启动批次失败'))
                    } finally {
                      setStartingBatchId(null)
                    }
                  })()}
                  onCancel={(batchId) => void runBatchCancel(batchId)}
                  onRetry={(batchId, itemIds) => void runBatchRetry(batchId, itemIds)}
                  onDelete={(batchId) => void (async () => {
                    setDeletingBatchId(batchId)
                    try {
                      await deletePanTransferBatch(batchId)
                      message.success(`批次 #${batchId} 已删除`)
                      if (detailData?.batch.id === batchId) {
                        setDetailOpen(false)
                        setDetailData(null)
                        setSelectedDetailItemKeys([])
                      }
                      const nextPage =
                        batchPagination.page > 1 && batches.length === 1 ? batchPagination.page - 1 : batchPagination.page
                      await loadBatches(nextPage, batchPagination.pageSize)
                    } catch (error) {
                      message.error(getErrorMessage(error, '删除批次失败'))
                    } finally {
                      setDeletingBatchId(null)
                    }
                  })()}
                  onCloseDetail={() => {
                    setDetailOpen(false)
                    setSelectedDetailItemKeys([])
                  }}
                  onSelectBatchKeys={setSelectedBatchKeys}
                  onRefreshDetail={(batchId) => void loadBatchDetail(batchId, { open: false })}
                  onSelectItemKeys={setSelectedDetailItemKeys}
                  onClearLogs={(batchId) => void runBatchClearLogs(batchId)}
                  onPublish={(item) => openPublishModal(item)}
                  onCreateFollow={(item) => void handleCreateFollowTask(item)}
                  onBulkStart={() => void handleBulkStartBatches()}
                  onBulkCancel={() => void handleBulkCancelBatches()}
                  onBulkRetry={() => void handleBulkRetryBatches()}
                  onBulkDelete={() => void handleBulkDeleteBatches()}
                  onBulkPublish={() => void handleBulkPublishSelected()}
                  onBulkCreateFollow={() => void handleBulkCreateFollowSelected()}
                />
              </div>
            ),
          },
          {
            key: 'follow',
            label: '追更同步',
            children: <FollowTasksSection refreshToken={followRefreshToken} isActive={activeTab === 'follow'} />,
          },
          {
            key: 'publish',
            label: '运营发布',
            children: <PublishSection refreshToken={publishRefreshToken} />,
          },
        ]}
      />

      <Modal
        open={accountModalOpen}
        title={editingAccount ? '编辑转存账号' : '新增转存账号'}
        onCancel={() => setAccountModalOpen(false)}
        onOk={() => void handleSaveAccount()}
        confirmLoading={accountSaving}
        destroyOnHidden
      >
        <Form form={accountForm} layout="vertical">
          <Form.Item label="平台" name="platform" rules={[{ required: true, message: '请选择平台' }]}><Select options={PLATFORM_OPTIONS} /></Form.Item>
          <Form.Item label="账号名称" name="account_name" rules={[{ required: true, message: '请输入账号名称' }]}><Input placeholder="例如：百度主账号 A" /></Form.Item>
          <Form.Item label="认证方式" name="auth_type" rules={[{ required: true, message: '请输入认证方式' }]}><Input disabled /></Form.Item>
          <Form.Item label={editingAccount ? 'Cookie（留空表示保持不变）' : 'Cookie'} name="credential_value" rules={editingAccount ? [] : [{ required: true, message: '请输入 Cookie' }]}><Input.TextArea rows={4} placeholder="粘贴完整 Cookie 文本" /></Form.Item>
          <div className="resource-ops-transfer-form-tip">Cookie 只做加密存储，列表页不会回显明文。</div>
          <Form.Item label="默认保存目录" name="default_save_root"><Input placeholder="例如：TG镜像/影视" /></Form.Item>
          <Form.Item label="默认分享方式" name="default_share_mode"><Select options={SHARE_MODE_OPTIONS} /></Form.Item>
          <Form.Item label="默认提取码" name="default_share_passcode"><Input placeholder="可留空" /></Form.Item>
          <Form.Item label="默认有效天数" name="default_share_expire_days"><InputNumber min={1} max={3650} style={{ width: '100%' }} placeholder="可留空" /></Form.Item>
          <Form.Item label="状态" style={{ marginBottom: 0 }}>
            <Space>
              <Form.Item name="is_enabled" valuePropName="checked" noStyle><Switch /></Form.Item>
              <span>启用账号</span>
              <Form.Item name="is_default" valuePropName="checked" noStyle><Switch /></Form.Item>
              <span>设为默认</span>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={batchCreateModalOpen}
        title="创建转存批次"
        onCancel={() => setBatchCreateModalOpen(false)}
        onOk={() => void (async () => {
          if (!lastPreviewPayload || selectedPreviewKeys.length <= 0) return
          setBatchCreating(true)
          try {
            const { page: _page, page_size: _pageSize, ...selectionPayload } = lastPreviewPayload
            const payload: PanTransferBatchCreateRequest = {
              ...selectionPayload,
              selected_link_target_ids: selectedPreviewKeys.map((item) => Number(item)),
              start_immediately: batchCreateDraft.startImmediately,
              max_attempts: batchCreateDraft.maxAttempts,
              retry_delay_seconds: batchCreateDraft.retryDelaySeconds,
              target_account_ids_by_platform: Object.entries(targetAccountIdsByPlatform).reduce<Record<string, number>>(
                (accumulator, [platform, accountId]) => {
                  if (Number(accountId || 0) > 0) {
                    accumulator[platform] = Number(accountId)
                  }
                  return accumulator
                },
                {}
              ),
              transfer_layout: batchCreateDraft.transferLayout,
              batch_folder_name:
                batchCreateDraft.transferLayout === 'batch_archive'
                  ? batchCreateDraft.batchFolderName || null
                  : null,
              item_folder_mode: 'custom',
              item_folder_template: resolveBatchCreateTemplate(batchCreateDraft) || null,
              share_target_mode: batchCreateDraft.shareTargetMode,
            }
            const response = await createManualPanTransferBatch(payload)
            message.success(batchCreateDraft.startImmediately ? `已创建并启动批次 #${response.batch.id}` : `已创建草稿批次 #${response.batch.id}`)
            setBatchCreateModalOpen(false)
            setSelectedPreviewKeys([])
            applyBatchDetail(response)
            setDetailOpen(true)
            await loadBatches(1, batchPagination.pageSize)
          } catch (error) {
            if (!(error as { response?: unknown })?.response) {
              message.error(getErrorMessage(error, '创建批次失败'))
            }
          } finally {
            setBatchCreating(false)
          }
        })()}
        confirmLoading={batchCreating}
        okText="确认创建"
        destroyOnHidden
        width={1080}
      >
        <div className="resource-ops-transfer-create-shell">
          <section className="resource-ops-transfer-create-panel">
            <div className="resource-ops-transfer-create-panel-head resource-ops-transfer-create-panel-head--compact">
              <h4>{renderBatchCreateLabel('执行策略', '控制队列启动方式和失败重试规则。')}</h4>
            </div>
            <div className="resource-ops-transfer-create-strategy-grid">
              <div className="resource-ops-transfer-create-field-card resource-ops-transfer-create-field-card--compact">
                <label>{renderBatchCreateLabel('创建后立即入列', '打开后，批次创建成功会直接进入 worker 队列；关闭则先保存为草稿，稍后手动启动。')}</label>
                <div className="resource-ops-transfer-create-control-row">
                  <span className="resource-ops-transfer-create-control-value">
                    {batchCreateDraft.startImmediately ? '立即入列' : '草稿保存'}
                  </span>
                  <Switch
                    checked={batchCreateDraft.startImmediately}
                    onChange={(checked) =>
                      setBatchCreateDraft((current) => ({ ...current, startImmediately: checked }))
                    }
                  />
                </div>
                <small>创建完成后仍走现有 worker 队列，不会绕开当前执行链路。</small>
              </div>

              <div className="resource-ops-transfer-create-field-card resource-ops-transfer-create-field-card--compact">
                <label>{renderBatchCreateLabel('最大尝试次数', '单条任务最多执行多少次，超过后会停止自动重试。')}</label>
                <div className="resource-ops-transfer-create-control-row">
                  <InputNumber
                    min={1}
                    max={10}
                    style={{ width: 96 }}
                    value={batchCreateDraft.maxAttempts}
                    onChange={(value) =>
                      setBatchCreateDraft((current) => ({ ...current, maxAttempts: Number(value || 1) }))
                    }
                  />
                  <span className="resource-ops-transfer-create-control-suffix">次</span>
                </div>
                <small>达到上限后会停留在失败状态，支持后续手动立即重试。</small>
              </div>

              <div className="resource-ops-transfer-create-field-card resource-ops-transfer-create-field-card--compact">
                <label>{renderBatchCreateLabel('自动重试间隔', '失败项进入 retry_wait 后，按这个间隔自动再次尝试。')}</label>
                <div className="resource-ops-transfer-create-control-row">
                  <Select
                    className="resource-ops-transfer-create-select"
                    options={RETRY_DELAY_OPTIONS}
                    value={batchCreateDraft.retryDelaySeconds}
                    onChange={(value) =>
                      setBatchCreateDraft((current) => ({ ...current, retryDelaySeconds: Number(value || 0) }))
                    }
                  />
                </div>
                <small>适合临时风控、目录延迟或分享接口波动的场景。</small>
              </div>

              <div className="resource-ops-transfer-create-field-card resource-ops-transfer-create-field-card--preview">
                <label>执行策略预览</label>
                <div className="resource-ops-transfer-create-meta-list">
                  <div className="resource-ops-transfer-create-meta-row">
                    <span>本次处理</span>
                    <strong>{selectedPreviewKeys.length} 个唯一源链</strong>
                  </div>
                  <div className="resource-ops-transfer-create-meta-row">
                    <span>创建方式</span>
                    <strong>{batchCreateDraft.startImmediately ? '立即入列' : '草稿保存'}</strong>
                  </div>
                  <div className="resource-ops-transfer-create-meta-row">
                    <span>自动重试</span>
                    <strong>{formatRetryDelay(batchCreateDraft.retryDelaySeconds)}</strong>
                  </div>
                  <div className="resource-ops-transfer-create-meta-row">
                    <span>目标账号</span>
                    <strong title={selectedTargetAccountSummary}>{selectedTargetAccountSummary}</strong>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="resource-ops-transfer-create-panel">
            <div className="resource-ops-transfer-create-panel-head resource-ops-transfer-create-panel-head--compact">
              <h4>{renderBatchCreateLabel('目录与分享', '控制落目录方式，以及最终对外分享的是哪一层。')}</h4>
            </div>
            <div className="resource-ops-transfer-create-field-row">
              <div className="resource-ops-transfer-create-field-card">
                <label>{renderBatchCreateLabel('目录布局', '独立目录：每条源链直接落在账号根目录下。批次归档：先进入一个批次目录，再进入每条资源目录。')}</label>
                <Select
                  options={TRANSFER_LAYOUT_OPTIONS}
                  value={batchCreateDraft.transferLayout}
                  onChange={(value) =>
                    setBatchCreateDraft((current) => ({
                      ...current,
                      transferLayout: value as BatchCreateDraft['transferLayout'],
                    }))
                  }
                />
                <small>默认使用批次归档，先分入分类目录，再进入资源目录。</small>
              </div>

              <div className="resource-ops-transfer-create-field-card">
                <label>{renderBatchCreateLabel('批次目录名', '内置常用分类目录；切到独立目录时保留当前值但不会生效。')}</label>
                <Select
                  disabled={batchCreateDraft.transferLayout !== 'batch_archive'}
                  options={BATCH_FOLDER_NAME_OPTIONS}
                  value={batchCreateDraft.batchFolderName}
                  onChange={(value) =>
                    setBatchCreateDraft((current) => ({
                      ...current,
                      batchFolderName: String(value || ''),
                    }))
                  }
                />
                <small>{batchCreateDraft.transferLayout === 'batch_archive' ? '默认先进入这个分类目录，再落到资源目录。' : '当前为独立目录模式，这个值暂不参与路径生成。'}</small>
              </div>

              <div className="resource-ops-transfer-create-field-card">
                <label>{renderBatchCreateLabel('资源目录模板', '默认用强混淆乱码模板。支持变量：{title}、{title_masked_mix}、{title_masked_cn}、{title_slug}、{platform}、{batch_id}、{item_id}、{share_key}、{date}。')}</label>
                <div className="resource-ops-transfer-create-field-stack">
                  <Select
                    options={ITEM_FOLDER_TEMPLATE_PRESET_OPTIONS.map((item) => ({
                      label: item.label,
                      value: item.value,
                    }))}
                    value={batchCreateDraft.itemFolderPreset}
                    onChange={(value) =>
                      setBatchCreateDraft((current) => ({
                        ...current,
                        itemFolderPreset: value as BatchCreateDraft['itemFolderPreset'],
                        itemFolderTemplate:
                          value === 'masked_mix'
                            ? MASKED_MIX_ITEM_TEMPLATE
                            : value === 'masked_cn'
                              ? MASKED_CN_ITEM_TEMPLATE
                              : value === 'coded'
                                ? CODED_ITEM_TEMPLATE
                                : current.itemFolderTemplate || MASKED_MIX_ITEM_TEMPLATE,
                      }))
                    }
                  />
                  <Input
                    value={batchCreateDraft.itemFolderTemplate}
                    disabled={batchCreateDraft.itemFolderPreset !== 'custom'}
                    placeholder={MASKED_MIX_ITEM_TEMPLATE}
                    onChange={(event) =>
                      setBatchCreateDraft((current) => ({
                        ...current,
                        itemFolderTemplate: event.target.value,
                      }))
                    }
                  />
                </div>
                <small>{currentTemplatePresetMeta.description}</small>
              </div>

              <div className="resource-ops-transfer-create-field-card">
                <label>{renderBatchCreateLabel('分享层级', '原分享目录：若资源目录下只有一个顶层目录或文件，则直接分享该层，否则自动回退为资源目录。')}</label>
                <Select
                  options={SHARE_TARGET_MODE_OPTIONS}
                  value={batchCreateDraft.shareTargetMode}
                  onChange={(value) =>
                    setBatchCreateDraft((current) => ({
                      ...current,
                      shareTargetMode: value as BatchCreateDraft['shareTargetMode'],
                    }))
                  }
                />
                <small>{batchCreateDraft.shareTargetMode === 'content_root' ? '默认更接近原链接打开后的目录效果。' : '始终分享系统生成的资源目录，结构更稳定。'}</small>
              </div>
            </div>
          </section>

          <section className="resource-ops-transfer-create-panel">
            <div className="resource-ops-transfer-create-panel-head resource-ops-transfer-create-panel-head--compact">
              <h4>路径预览</h4>
            </div>
            <div className="resource-ops-transfer-create-preview">
              <div className="resource-ops-transfer-create-preview-row">
                <span>转存路径</span>
                <code>{batchPathPreview.transferPath}</code>
              </div>
              <div className="resource-ops-transfer-create-preview-row">
                <span>创建分享</span>
                <code>{batchPathPreview.sharePath}</code>
              </div>
              <div className="resource-ops-transfer-create-preview-note">{batchPathPreview.shareTip}</div>
            </div>
          </section>
        </div>
      </Modal>

      <Modal
        open={publishModalOpen}
        title={publishingItem ? `发布到前台：${publishingItem.short_title}` : '发布到前台'}
        onCancel={() => {
          setPublishModalOpen(false)
          setPublishingItem(null)
          publishForm.resetFields()
        }}
        onOk={() => void handlePublishMessage()}
        confirmLoading={publishingItemId !== null}
        okText="确认发布"
        destroyOnHidden
      >
        <Form form={publishForm} layout="vertical">
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="发布后会作为一条新消息进入前台列表"
            description={
              <div className="resource-ops-transfer-validation">
                <small>优先复用转存回写后的链接；如果该条任务还没有新链接，则回退使用当前可用的原链接。</small>
                {publishSourceHint ? <small>当前预计使用：{publishSourceHint.label} {'->'} {publishSourceHint.url}</small> : null}
              </div>
            }
          />
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="请输入前台展示标题" maxLength={255} />
          </Form.Item>
          <Form.Item label="简介" name="description">
            <Input.TextArea rows={4} placeholder="可选，补充前台展示说明" maxLength={1000} />
          </Form.Item>
          <Form.Item label="标签" name="tags">
            <Select
              mode="tags"
              tokenSeparators={[',', '，']}
              placeholder="可选，输入后回车"
              open={false}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default ResourceOpsTransferCenterMain
