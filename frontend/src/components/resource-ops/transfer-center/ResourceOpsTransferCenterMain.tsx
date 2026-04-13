import { useEffect, useMemo, useState } from 'react'
import type { Key } from 'react'
import { Alert, Form, Input, InputNumber, Modal, Select, Space, Switch, message } from 'antd'
import type { TablePaginationConfig } from 'antd/es/table'

import {
  cancelPanTransferBatch,
  clearPanTransferBatchLogs,
  createManualPanTransferBatch,
  createPanTransferAccount,
  deletePanTransferAccount,
  deletePanTransferBatch,
  getPanTransferBatchDetail,
  listPanTransferAccounts,
  listPanTransferBatches,
  previewManualPanTransfer,
  retryPanTransferBatch,
  startPanTransferBatch,
  updatePanTransferAccount,
  validatePanTransferAccount,
} from '@/api/panTransfer'
import type {
  PanTransferAccountCreateRequest,
  PanTransferAccountItem,
  PanTransferAccountUpdateRequest,
  PanTransferBatchCreateRequest,
  PanTransferBatchDetailResponse,
  PanTransferBatchSummaryItem,
  PanTransferManualPreviewRequest,
  PanTransferManualPreviewResponse,
} from '@/types/panTransfer'

import AccountsSection from './AccountsSection'
import BatchSection from './BatchSection'
import PreviewSection from './PreviewSection'
import {
  BatchCreateDraft,
  BatchPagination,
  buildPreviewPayload,
  DEFAULT_BATCH_CREATE_DRAFT,
  DEFAULT_PREVIEW_DRAFT,
  formatRetryDelay,
  getErrorMessage,
  PLATFORM_OPTIONS,
  PreviewDraft,
  RETRY_DELAY_OPTIONS,
  SHARE_MODE_OPTIONS,
} from './shared'
import '../ResourceOpsTransferCenter.css'

const ResourceOpsTransferCenterMain = () => {
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
  const [selectedFailedItemKeys, setSelectedFailedItemKeys] = useState<Key[]>([])

  const [accountForm] = Form.useForm()

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

  const loadBatches = async (page = batchPagination.page, pageSize = batchPagination.pageSize) => {
    setBatchLoading(true)
    try {
      const response = await listPanTransferBatches(page, pageSize)
      setBatches(response.items)
      setBatchPagination({ page: response.page, pageSize: response.page_size, total: response.total })
    } catch (error) {
      message.error(getErrorMessage(error, '加载转存批次失败'))
    } finally {
      setBatchLoading(false)
    }
  }

  const applyBatchDetail = (response: PanTransferBatchDetailResponse) => {
    setDetailData(response)
    setSelectedFailedItemKeys((current) => {
      const available = new Set(response.items.filter((item) => item.transfer_status === 'failed').map((item) => item.id))
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
    if (!detailOpen || !detailData || detailData.batch.status !== 'running') {
      return
    }

    const batchId = detailData.batch.id
    const timer = window.setInterval(() => {
      void loadBatchDetail(batchId, { open: false, silent: true })
    }, 4000)

    return () => window.clearInterval(timer)
  }, [detailOpen, detailData?.batch.id, detailData?.batch.status])

  const missingPlatforms = useMemo(() => {
    const enabledPlatforms = new Set(accounts.filter((item) => item.is_enabled).map((item) => item.platform))
    return PLATFORM_OPTIONS.filter((item) => !enabledPlatforms.has(item.value))
  }, [accounts])

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
        page_size: pagination.pageSize || lastPreviewPayload.page_size || 50,
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

  return (
    <div className="resource-ops-transfer-stack">
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

      <PreviewSection
        draft={previewDraft}
        previewData={previewData}
        previewLoading={previewLoading}
        selectedPreviewKeys={selectedPreviewKeys}
        onDraftChange={(updater) => setPreviewDraft((current) => updater(current))}
        onPreview={() => void (async () => {
          if (previewDraft.selectionMode === 'time_range' && !previewDraft.range) {
            message.warning('请选择时间范围')
            return
          }
          setPreviewLoading(true)
          try {
            const payload = buildPreviewPayload(previewDraft)
            const response = await previewManualPanTransfer(payload)
            setPreviewData(response)
            setLastPreviewPayload(payload)
            setSelectedPreviewKeys([])
          } catch (error) {
            message.error(getErrorMessage(error, '生成转存预览失败'))
          } finally {
            setPreviewLoading(false)
          }
        })()}
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
        deletingBatchId={deletingBatchId}
        clearingLogsBatchId={clearingLogsBatchId}
        detailOpen={detailOpen}
        detailLoading={detailLoading}
        detailData={detailData}
        selectedFailedItemKeys={selectedFailedItemKeys}
        onRefresh={() => void loadBatches()}
        onTableChange={(pagination) => void loadBatches(pagination.current || 1, pagination.pageSize || batchPagination.pageSize)}
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
              setSelectedFailedItemKeys([])
            }
            const nextPage = batchPagination.page > 1 && batches.length === 1 ? batchPagination.page - 1 : batchPagination.page
            await loadBatches(nextPage, batchPagination.pageSize)
          } catch (error) {
            message.error(getErrorMessage(error, '删除批次失败'))
          } finally {
            setDeletingBatchId(null)
          }
        })()}
        onCloseDetail={() => {
          setDetailOpen(false)
          setSelectedFailedItemKeys([])
        }}
        onRefreshDetail={(batchId) => void loadBatchDetail(batchId, { open: false })}
        onSelectFailedKeys={setSelectedFailedItemKeys}
        onClearLogs={(batchId) => void runBatchClearLogs(batchId)}
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
            const payload: PanTransferBatchCreateRequest = {
              ...lastPreviewPayload,
              selected_link_target_ids: selectedPreviewKeys.map((item) => Number(item)),
              start_immediately: batchCreateDraft.startImmediately,
              max_attempts: batchCreateDraft.maxAttempts,
              retry_delay_seconds: batchCreateDraft.retryDelaySeconds,
            }
            const response = await createManualPanTransferBatch(payload)
            message.success(batchCreateDraft.startImmediately ? `已创建并启动批次 #${response.batch.id}` : `已创建草稿批次 #${response.batch.id}`)
            setBatchCreateModalOpen(false)
            setSelectedPreviewKeys([])
            applyBatchDetail(response)
            setDetailOpen(true)
            await loadBatches(1, batchPagination.pageSize)
          } catch (error) {
            message.error(getErrorMessage(error, '创建批次失败'))
          } finally {
            setBatchCreating(false)
          }
        })()}
        confirmLoading={batchCreating}
        okText="确认创建"
        destroyOnHidden
      >
        <div className="resource-ops-transfer-modal-stack">
          <Alert type="info" showIcon message={`本次将处理 ${selectedPreviewKeys.length} 个唯一源链`} description="创建后会进入现有 worker 队列执行，不会启用自动定时任务。" />
          <div className="resource-ops-transfer-field">
            <label>创建后立即启动</label>
            <div className="resource-ops-transfer-inline-switch">
              <Switch checked={batchCreateDraft.startImmediately} onChange={(checked) => setBatchCreateDraft((current) => ({ ...current, startImmediately: checked }))} />
              <span>{batchCreateDraft.startImmediately ? '立即进入队列' : '先保存为草稿'}</span>
            </div>
          </div>
          <div className="resource-ops-transfer-field">
            <label>最大尝试次数</label>
            <InputNumber min={1} max={10} style={{ width: '100%' }} value={batchCreateDraft.maxAttempts} onChange={(value) => setBatchCreateDraft((current) => ({ ...current, maxAttempts: Number(value || 1) }))} />
          </div>
          <div className="resource-ops-transfer-field">
            <label>自动重试间隔</label>
            <Select
              options={RETRY_DELAY_OPTIONS}
              value={batchCreateDraft.retryDelaySeconds}
              onChange={(value) => setBatchCreateDraft((current) => ({ ...current, retryDelaySeconds: Number(value || 0) }))}
            />
            <div className="resource-ops-transfer-form-tip">
              当前设置：{formatRetryDelay(batchCreateDraft.retryDelaySeconds)}。失败项仍然可以在批次详情里手动立即重试。
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}

export default ResourceOpsTransferCenterMain
