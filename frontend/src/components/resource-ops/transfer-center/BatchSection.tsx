import { useEffect, useMemo, useState } from 'react'
import type { Key } from 'react'
import { Alert, Button, Card, Descriptions, Drawer, Empty, Popconfirm, Segmented, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { PanTransferBatchDetailResponse, PanTransferBatchItem, PanTransferBatchSummaryItem } from '@/types/panTransfer'
import { formatServerDateTime } from '@/utils/dateTime'

import {
  BATCH_STATUS_META,
  formatDateTime,
  formatRetryDelay,
  getBatchSummary,
  ITEM_STATUS_META,
  REPLACEMENT_STATUS_META,
  VALIDATION_STATUS_META,
} from './shared'

const { Title, Paragraph, Text } = Typography

const EXECUTION_STAGE_LABELS: Record<string, string> = {
  transfer: '转存',
  share: '分享',
  validate: '校验',
  replace: '回写',
  publish: '发布',
  finish: '完成',
  general: '通用',
}

const formatExecutionStatus = (status: unknown) => {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'valid') return '有效'
  if (normalized === 'warning') return '存疑'
  if (normalized === 'invalid') return '失效'
  if (normalized === 'error') return '异常'
  if (normalized === 'pending') return '待校验'
  return normalized || '未知'
}

type ExecutionTimelineLog = PanTransferBatchItem['execution_logs'][number] & {
  batchItemId?: number
  batchItemTitle?: string
}

type TerminalFilter = 'all' | 'error'

const formatExecutionLogTime = (value?: string | null) =>
  value ? formatServerDateTime(value, 'HH:mm:ss', 'Asia/Shanghai') : '--:--:--'

const normalizeTitleText = (value?: string | null) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s\u3000]+/g, '')
    .replace(/[()（）\[\]【】\-_.,:;!?'"]/g, '')

const shouldHideSubtitle = (mainTitle?: string | null, subtitle?: string | null) => {
  const normalizedMain = normalizeTitleText(mainTitle)
  const normalizedSubtitle = normalizeTitleText(subtitle)
  if (!normalizedMain || !normalizedSubtitle) {
    return false
  }
  if (normalizedMain === normalizedSubtitle) {
    return true
  }
  const shorter = normalizedMain.length <= normalizedSubtitle.length ? normalizedMain : normalizedSubtitle
  const longer = normalizedMain.length > normalizedSubtitle.length ? normalizedMain : normalizedSubtitle
  return shorter.length >= 10 && longer.includes(shorter) && longer.length - shorter.length <= 8
}

const getExecutionLineStatus = (log: ExecutionTimelineLog) => {
  const messageText = String(log.message || '').toLowerCase()
  if (log.level === 'error' || messageText.includes(' failed')) return 'ERR'
  if (log.level === 'warning') return 'WARN'
  if (
    messageText.includes(' completed') ||
    messageText.includes('completed successfully') ||
    messageText.includes('finished with status: valid')
  ) {
    return 'OK'
  }
  return 'INFO'
}

const buildExecutionLogSummary = (log: ExecutionTimelineLog) => {
  const message = String(log.message || '')
  const payload = log.payload || {}
  const folderName = String(payload.staging_folder_name || '')
  const stagingRoot = String(payload.staging_root || '')
  const fullPath = [stagingRoot, folderName].filter(Boolean).join('/')
  const shareUrl = String(payload.new_share_url || '')
  const accountName = String(payload.account_name || '')
  const shareMode = String(payload.share_mode || '')
  const stagingFolderId = String(payload.staging_folder_id || '')
  const errorMessage = String(payload.error_message || '').trim()
  const affectedMessageCount = Number(payload.affected_message_count || 0)
  const affectedRefCount = Number(payload.affected_ref_count || 0)
  const retryDelaySeconds = Number(payload.retry_delay_seconds || 0)
  const retryableText =
    payload.retryable === true
      ? retryDelaySeconds > 0
        ? `${formatRetryDelay(retryDelaySeconds)}后自动重试`
        : '可手动重试'
      : payload.retryable === false
        ? '不自动重试'
        : ''

  if (message.startsWith('Starting transfer to staging directory')) {
    const pathText = fullPath || '未命名暂存目录'
    return accountName ? `开始转存 -> ${pathText} (账号: ${accountName})` : `开始转存 -> ${pathText}`
  }
  if (message.startsWith('Transfer to staging completed')) {
    if (stagingFolderId) return `转存成功 -> folder_id=${stagingFolderId}`
    return fullPath ? `转存成功 -> ${fullPath}` : '转存成功'
  }
  if (message.startsWith('Transfer to staging failed:')) {
    return `转存失败 -> ${message.replace('Transfer to staging failed:', '').trim() || errorMessage || '未知错误'}`
  }
  if (message.startsWith('Skipping transfer and reusing existing staging snapshot')) {
    return fullPath ? `跳过转存，复用暂存目录 -> ${fullPath}` : '跳过转存，复用已有暂存目录'
  }
  if (message.startsWith('Starting share creation for staging directory')) {
    const shareModeText = shareMode === 'private' ? 'private' : shareMode === 'public' ? 'public' : shareMode || 'unknown'
    return `开始创建分享 -> mode=${shareModeText}`
  }
  if (message.startsWith('Share creation completed')) {
    return shareUrl ? `分享创建成功 -> ${shareUrl}` : '分享创建成功'
  }
  if (message.startsWith('Share creation failed:')) {
    return `分享创建失败 -> ${message.replace('Share creation failed:', '').trim() || errorMessage || '未知错误'}`
  }
  if (message.startsWith('Validating newly created share URL')) {
    return shareUrl ? `开始校验新分享 -> ${shareUrl}` : '开始校验新分享'
  }
  if (message.startsWith('Share URL validation finished with status:')) {
    return `校验完成 -> ${formatExecutionStatus(message.split(':').pop())}`
  }
  if (message.startsWith('Share URL validation failed:')) {
    return `校验失败 -> ${message.replace('Share URL validation failed:', '').trim() || errorMessage || '未知错误'}`
  }
  if (message.startsWith('Replacing old links with the new shared URL')) {
    return shareUrl ? `开始回写 -> ${shareUrl}` : '开始回写'
  }
  if (message.startsWith('Link replacement completed')) {
    const impactText =
      affectedMessageCount > 0 || affectedRefCount > 0
        ? `影响消息=${affectedMessageCount} 引用=${affectedRefCount}`
        : ''
    return impactText ? `回写成功 -> ${impactText}` : '回写成功'
  }
  if (message.startsWith('Link replacement failed:')) {
    return `回写失败 -> ${message.replace('Link replacement failed:', '').trim() || errorMessage || '未知错误'}`
  }
  if (message.startsWith('Admin message published to feed')) {
    const publishedMessageId = Number(payload.published_message_id || 0)
    return publishedMessageId > 0 ? `已发布到前台 -> 消息 #${publishedMessageId}` : '已发布到前台'
  }
  if (message.startsWith('Pan transfer item completed successfully')) {
    return '任务完成'
  }
  if (message.startsWith('Pan transfer item failed:')) {
    const detail = message.replace('Pan transfer item failed:', '').trim() || errorMessage || '未知错误'
    return retryableText ? `任务失败 -> ${detail} (${retryableText})` : `任务失败 -> ${detail}`
  }
  if (message.startsWith('Batch cancelled')) {
    return '批次已停止'
  }
  return message || errorMessage || '任务状态已更新'
}

const buildExecutionTerminalLine = (log: ExecutionTimelineLog) => {
  const stageLabel = EXECUTION_STAGE_LABELS[log.stage] || log.stage || '通用'
  const statusLabel = getExecutionLineStatus(log)
  const timeLabel = formatExecutionLogTime(log.created_at)
  const scopeLabel = log.batchItemId ? `批次#${log.batch_id}/项#${log.batchItemId}` : `批次#${log.batch_id}`
  return `[${timeLabel}] [${scopeLabel}] [${stageLabel}] [${statusLabel}] ${buildExecutionLogSummary(log)}`
}

const getTerminalLineClassName = (log: ExecutionTimelineLog) => {
  const statusLabel = getExecutionLineStatus(log)
  if (statusLabel === 'ERR') return 'resource-ops-transfer-terminal-line is-error'
  if (statusLabel === 'WARN') return 'resource-ops-transfer-terminal-line is-warning'
  if (statusLabel === 'OK') return 'resource-ops-transfer-terminal-line is-success'
  return 'resource-ops-transfer-terminal-line'
}

type BatchSectionProps = {
  batches: PanTransferBatchSummaryItem[]
  batchLoading: boolean
  batchPagination: { page: number; pageSize: number; total: number }
  startingBatchId: number | null
  cancellingBatchId: number | null
  retryingBatchId: number | null
  publishingItemId: number | null
  creatingFollowItemId: number | null
  deletingBatchId: number | null
  clearingLogsBatchId: number | null
  detailOpen: boolean
  detailLoading: boolean
  detailData: PanTransferBatchDetailResponse | null
  selectedFailedItemKeys: Key[]
  onRefresh: () => void
  onTableChange: (pagination: TablePaginationConfig) => void
  onOpenDetail: (batchId: number) => void
  onStart: (batchId: number) => void
  onCancel: (batchId: number) => void
  onRetry: (batchId: number, itemIds?: number[]) => void
  onDelete: (batchId: number) => void
  onCloseDetail: () => void
  onRefreshDetail: (batchId: number) => void
  onSelectFailedKeys: (keys: Key[]) => void
  onClearLogs: (batchId: number) => void
  onPublish: (item: PanTransferBatchItem) => void
  onCreateFollow: (item: PanTransferBatchItem) => void
}

const BatchSection = ({
  batches,
  batchLoading,
  batchPagination,
  startingBatchId,
  cancellingBatchId,
  retryingBatchId,
  publishingItemId,
  creatingFollowItemId,
  deletingBatchId,
  clearingLogsBatchId,
  detailOpen,
  detailLoading,
  detailData,
  selectedFailedItemKeys,
  onRefresh,
  onTableChange,
  onOpenDetail,
  onStart,
  onCancel,
  onRetry,
  onDelete,
  onCloseDetail,
  onRefreshDetail,
  onSelectFailedKeys,
  onClearLogs,
  onPublish,
  onCreateFollow,
}: BatchSectionProps) => {
  const [terminalFilter, setTerminalFilter] = useState<TerminalFilter>('all')
  const [terminalItemFilter, setTerminalItemFilter] = useState<number | 'all'>('all')
  const [terminalCleared, setTerminalCleared] = useState(false)

  const batchExecutionLogs = useMemo<ExecutionTimelineLog[]>(
    () =>
      detailData
        ? detailData.items
            .flatMap((item) =>
              item.execution_logs.map((log) => ({
                ...log,
                batchItemId: item.id,
                batchItemTitle: item.short_title,
              }))
            )
            .sort((left, right) => {
              const leftTime = new Date(left.created_at).getTime()
              const rightTime = new Date(right.created_at).getTime()
              return leftTime - rightTime || left.id - right.id
            })
        : [],
    [detailData]
  )

  useEffect(() => {
    setTerminalFilter('all')
    setTerminalItemFilter('all')
    setTerminalCleared(false)
  }, [detailData?.batch.id, batchExecutionLogs.length])

  const filteredBatchExecutionLogs = useMemo(
    () =>
      batchExecutionLogs.filter((log) => {
        if (terminalFilter === 'error' && getExecutionLineStatus(log) !== 'ERR') {
          return false
        }
        if (terminalItemFilter !== 'all' && log.batchItemId !== terminalItemFilter) {
          return false
        }
        return true
      }),
    [batchExecutionLogs, terminalFilter, terminalItemFilter]
  )

  const terminalLines = useMemo(
    () => filteredBatchExecutionLogs.map((log) => buildExecutionTerminalLine(log)),
    [filteredBatchExecutionLogs]
  )

  const handleCopyTerminal = async () => {
    if (terminalLines.length <= 0) {
      message.info('当前没有可复制的日志')
      return
    }
    try {
      await navigator.clipboard.writeText(terminalLines.join('\n'))
      message.success('已复制当前日志')
    } catch {
      message.error('复制日志失败，请检查浏览器权限')
    }
  }

  const batchColumns: ColumnsType<PanTransferBatchSummaryItem> = [
    {
      title: '批次',
      dataIndex: 'id',
      key: 'id',
      width: 120,
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">#{record.id}</span>
          <span className="resource-ops-transfer-title-sub">{record.created_by || 'system'}</span>
        </div>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 200,
      render: (_, record) => {
        const meta = BATCH_STATUS_META[record.status] || { color: 'default', label: record.status }
        const summary = getBatchSummary(record)
        return (
          <div className="resource-ops-transfer-validation">
            <Space wrap size={[6, 6]}>
              <Tag color={meta.color}>{meta.label}</Tag>
              {summary.processing > 0 ? <Tag color="processing">处理中 {summary.processing}</Tag> : null}
              {summary.retryWait > 0 ? <Tag color="warning">待重试 {summary.retryWait}</Tag> : null}
            </Space>
            <small>
              成功 {record.success_item_count} / 失败 {record.failed_item_count} / 总计 {record.total_link_target_count}
            </small>
            <small>自动重试 {formatRetryDelay(record.retry_delay_seconds)}</small>
          </div>
        )
      },
    },
    {
      title: '来源范围',
      key: 'scope',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>{record.batch_type === 'manual' ? '手动批量转存' : record.batch_type}</small>
          <small>覆盖消息 {record.total_message_count} 条</small>
        </div>
      ),
    },
    {
      title: '时间',
      key: 'time',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>创建 {formatDateTime(record.created_at)}</small>
          <small>结束 {formatDateTime(record.finished_at)}</small>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_, record) => (
        <Space wrap>
          <Button size="small" onClick={() => onOpenDetail(record.id)}>
            明细
          </Button>
          {record.status === 'draft' ? (
            <Button
              size="small"
              type="primary"
              loading={startingBatchId === record.id}
              onClick={() => onStart(record.id)}
            >
              启动
            </Button>
          ) : null}
          {record.can_cancel ? (
            <Button size="small" loading={cancellingBatchId === record.id} onClick={() => onCancel(record.id)}>
              停止
            </Button>
          ) : null}
          {record.can_retry ? (
            <Button size="small" loading={retryingBatchId === record.id} onClick={() => onRetry(record.id)}>
              重试失败项
            </Button>
          ) : null}
          {record.can_delete ? (
            <Popconfirm
              title={`确认删除批次 #${record.id} 吗？`}
              description="只删除批次、任务和回写日志，不会删原始消息。"
              onConfirm={() => onDelete(record.id)}
            >
              <Button size="small" danger loading={deletingBatchId === record.id}>
                删除
              </Button>
            </Popconfirm>
          ) : null}
        </Space>
      ),
    },
  ]

  const detailColumns: ColumnsType<PanTransferBatchItem> = [
    {
      title: '资源',
      dataIndex: 'short_title',
      key: 'short_title',
      width: 260,
      render: (_, record) => {
        const subtitle = shouldHideSubtitle(record.short_title, record.latest_message_title)
          ? ''
          : record.latest_message_title || `${record.source_message_count} 条消息受影响`

        return (
          <div className="resource-ops-transfer-title-cell">
            <span className="resource-ops-transfer-title-main">{record.short_title}</span>
            {subtitle ? <span className="resource-ops-transfer-title-sub">{subtitle}</span> : null}
          </div>
        )
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 260,
      render: (_, record) => {
        const transferMeta = ITEM_STATUS_META[record.transfer_status] || { color: 'default', label: record.transfer_status }
        const validationMeta = VALIDATION_STATUS_META[record.validation_status] || { color: 'default', label: record.validation_status }
        const replacementMeta = REPLACEMENT_STATUS_META[record.replacement_status] || { color: 'default', label: record.replacement_status }
        return (
          <div className="resource-ops-transfer-validation">
            <Space wrap size={[6, 6]}>
              <Tag color={transferMeta.color}>{transferMeta.label}</Tag>
              <Tag color={validationMeta.color}>{validationMeta.label}</Tag>
              <Tag color={replacementMeta.color}>{replacementMeta.label}</Tag>
            </Space>
            <small>
              尝试 {record.attempt_count}/{record.max_attempts}
              {record.next_retry_at ? `，下次 ${formatDateTime(record.next_retry_at)}` : ''}
            </small>
          </div>
        )
      },
    },
    {
      title: '目标账号',
      key: 'target_account_name',
      width: 180,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>{record.target_account_name || '未指定账号'}</small>
          <small>{record.platform}</small>
        </div>
      ),
    },
    {
      title: '原链接',
      dataIndex: 'original_url',
      key: 'original_url',
      width: 280,
      render: (value: string) => (
        <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
          {value}
        </a>
      ),
    },
    {
      title: '新分享链接',
      dataIndex: 'new_share_url',
      key: 'new_share_url',
      width: 280,
      render: (value?: string | null) =>
        value ? (
          <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
            {value}
          </a>
        ) : (
          <Text type="secondary">尚未生成</Text>
        ),
    },
    {
      title: '当前生效链接',
      dataIndex: 'new_link_target_url',
      key: 'new_link_target_url',
      width: 280,
      render: (value: string | null | undefined, record) =>
        value ? (
          <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
            {value}
          </a>
        ) : record.replacement_status === 'replaced' ? (
          <Text type="secondary">已替换，但未读取到新目标 URL</Text>
        ) : (
          <Text type="secondary">尚未回写</Text>
        ),
    },
    {
      title: '操作',
      key: 'item_actions',
      width: 220,
      fixed: 'right',
      render: (_, record) => {
        const canPublish = Boolean(record.new_link_target_url) || Boolean(record.new_share_url) || Boolean(record.original_url)
        const canCreateFollow = Boolean(record.original_url)
        const canRetry = record.transfer_status === 'failed' && detailData
        if (!canPublish && !canRetry && !canCreateFollow) {
          return <Text type="secondary">-</Text>
        }
        return (
          <Space size={8} wrap>
            {canRetry && detailData ? (
              <Button
                size="small"
                loading={retryingBatchId === detailData.batch.id}
                onClick={() => onRetry(detailData.batch.id, [record.id])}
              >
                立即重试
              </Button>
            ) : null}
            {canPublish ? (
              <Button size="small" loading={publishingItemId === record.id} onClick={() => onPublish(record)}>
                发布到前台
              </Button>
            ) : null}
            {canCreateFollow ? (
              <Button size="small" loading={creatingFollowItemId === record.id} onClick={() => onCreateFollow(record)}>
                转为追更任务
              </Button>
            ) : null}
          </Space>
        )
      },
    },
  ]

  return (
    <>
      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head">
          <div>
            <Title level={4}>批次历史</Title>
            <Paragraph className="resource-ops-transfer-copy">
              这里能看到队列执行、失败重试、新分享链接和回写状态。确认无用后可以删除批次，避免历史记录持续累积。
            </Paragraph>
          </div>
          <Button loading={batchLoading} onClick={onRefresh}>
            刷新
          </Button>
        </div>

        <Table
          rowKey="id"
          loading={batchLoading}
          dataSource={batches}
          columns={batchColumns}
          onChange={onTableChange}
          pagination={{
            current: batchPagination.page,
            pageSize: batchPagination.pageSize,
            total: batchPagination.total,
            showSizeChanger: true,
          }}
          scroll={{ x: 1100 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无转存批次" /> }}
        />
      </Card>

      <Drawer
        width={1120}
        open={detailOpen}
        onClose={onCloseDetail}
        title={detailData ? `转存批次 #${detailData.batch.id}` : '转存批次明细'}
        extra={
          detailData ? (
            <Space>
              <Button loading={detailLoading} onClick={() => onRefreshDetail(detailData.batch.id)}>
                刷新明细
              </Button>
              <Button
                loading={clearingLogsBatchId === detailData.batch.id}
                disabled={batchExecutionLogs.length <= 0}
                onClick={() => onClearLogs(detailData.batch.id)}
              >
                清理日志
              </Button>
              {detailData.batch.can_cancel ? (
                <Button loading={cancellingBatchId === detailData.batch.id} onClick={() => onCancel(detailData.batch.id)}>
                  停止批次
                </Button>
              ) : null}
              {detailData.batch.can_retry ? (
                <Button
                  loading={retryingBatchId === detailData.batch.id}
                  onClick={() =>
                    onRetry(
                      detailData.batch.id,
                      selectedFailedItemKeys.length > 0 ? selectedFailedItemKeys.map((item) => Number(item)) : undefined
                    )
                  }
                >
                  {selectedFailedItemKeys.length > 0 ? `重试所选失败项 (${selectedFailedItemKeys.length})` : '重试全部失败项'}
                </Button>
              ) : null}
            </Space>
          ) : null
        }
      >
        {detailData ? (
          <div className="resource-ops-transfer-drawer-stack">
            <Descriptions
              size="small"
              column={2}
              bordered
              items={[
                {
                  key: 'status',
                  label: '批次状态',
                  children: (
                    <Tag color={(BATCH_STATUS_META[detailData.batch.status] || { color: 'default' }).color}>
                      {(BATCH_STATUS_META[detailData.batch.status] || { label: detailData.batch.status }).label}
                    </Tag>
                  ),
                },
                { key: 'created_by', label: '创建人', children: detailData.batch.created_by || 'system' },
                { key: 'count', label: '链接数量', children: detailData.batch.total_link_target_count },
                { key: 'message_count', label: '覆盖消息数', children: detailData.batch.total_message_count },
                { key: 'retry_delay', label: '自动重试间隔', children: formatRetryDelay(detailData.batch.retry_delay_seconds) },
                { key: 'created_at', label: '创建时间', children: formatDateTime(detailData.batch.created_at) },
                { key: 'finished_at', label: '结束时间', children: formatDateTime(detailData.batch.finished_at) },
              ]}
            />

            <div className="resource-ops-transfer-summary">
              <div className="resource-ops-transfer-summary-item">
                <span>成功</span>
                <strong>{detailData.batch.success_item_count}</strong>
                <small>已完成转存并通过回写</small>
              </div>
              <div className="resource-ops-transfer-summary-item">
                <span>失败</span>
                <strong>{detailData.batch.failed_item_count}</strong>
                <small>可在这里重试失败项</small>
              </div>
              <div className="resource-ops-transfer-summary-item">
                <span>排队 / 处理中</span>
                <strong>
                  {getBatchSummary(detailData.batch).queued} / {getBatchSummary(detailData.batch).processing}
                </strong>
                <small>共用现有 worker 队列执行</small>
              </div>
              <div className="resource-ops-transfer-summary-item">
                <span>待重试 / 间隔</span>
                <strong>
                  {getBatchSummary(detailData.batch).retryWait} / {formatRetryDelay(detailData.batch.retry_delay_seconds)}
                </strong>
                <small>{detailData.batch.retry_delay_seconds > 0 ? '失败项会按该间隔自动再试' : '关闭自动重试，仅支持手动立即重试'}</small>
              </div>
            </div>

            <Alert
              type="info"
              showIcon
              message="当前生效链接"
              description="“新分享链接”表示转存平台刚生成的新链接，“当前生效链接”表示已经写回系统后的链接目标。管理员可在这里直接核对是否替换成功。"
            />

            <Card size="small" title="执行终端" className="resource-ops-transfer-log-card">
              <Paragraph className="resource-ops-transfer-copy">
                按真实执行顺序输出关键日志行。推荐先看这里定位“卡在哪一步”“失败原因是什么”，再决定是否立即重试或清理日志。
              </Paragraph>
              <div className="resource-ops-transfer-terminal-toolbar">
                <Segmented
                  size="small"
                  value={terminalFilter}
                  options={[
                    { label: '全部日志', value: 'all' },
                    { label: '仅错误', value: 'error' },
                  ]}
                  onChange={(value) => setTerminalFilter(value as TerminalFilter)}
                />
                <Select
                  size="small"
                  className="resource-ops-transfer-terminal-select"
                  value={terminalItemFilter}
                  options={[
                    { label: '全部任务项', value: 'all' },
                    ...detailData.items.map((item) => ({
                      label: `项 #${item.id} ${item.short_title}`,
                      value: item.id,
                    })),
                  ]}
                  onChange={(value) => setTerminalItemFilter(value as number | 'all')}
                />
                <Space size={8}>
                  <Button size="small" onClick={() => setTerminalCleared(true)}>
                    清空显示
                  </Button>
                  <Button size="small" onClick={() => void handleCopyTerminal()}>
                    复制日志
                  </Button>
                </Space>
              </div>
              <div className="resource-ops-terminal resource-ops-transfer-terminal">
                {terminalCleared ? (
                  <div className="resource-ops-terminal-empty">已清空当前显示，刷新明细或切换批次可重新载入日志。</div>
                ) : filteredBatchExecutionLogs.length > 0 ? (
                  filteredBatchExecutionLogs.map((log) => (
                    <div key={log.id} className={getTerminalLineClassName(log)}>
                      {buildExecutionTerminalLine(log)}
                    </div>
                  ))
                ) : (
                  <div className="resource-ops-terminal-empty">当前筛选条件下暂无执行日志。</div>
                )}
              </div>
            </Card>

            <Table
              rowKey="id"
              loading={detailLoading}
              dataSource={detailData.items}
              columns={detailColumns}
              rowSelection={{
                selectedRowKeys: selectedFailedItemKeys,
                onChange: (keys) => onSelectFailedKeys(keys),
                getCheckboxProps: (record) => ({
                  disabled: record.transfer_status !== 'failed',
                }),
              }}
              expandable={{
                expandedRowRender: (record) => (
                  <div className="resource-ops-transfer-expanded">
                    {record.error_message ? (
                      <Alert
                        type="error"
                        showIcon
                        message="最近错误"
                        description={record.error_message}
                        style={{ marginBottom: 12 }}
                      />
                    ) : null}
                    <Descriptions
                      size="small"
                      column={1}
                      bordered
                      items={[
                        { key: 'validated', label: '最近校验时间', children: formatDateTime(record.last_validated_at) },
                        { key: 'started', label: '开始时间', children: formatDateTime(record.started_at) },
                        { key: 'finished', label: '结束时间', children: formatDateTime(record.finished_at) },
                        {
                          key: 'execution_log',
                          label: '执行日志',
                          children:
                            record.execution_logs.length > 0 ? (
                              <div className="resource-ops-terminal resource-ops-transfer-terminal resource-ops-transfer-terminal--compact">
                                {record.execution_logs.map((log) => {
                                  const terminalLog: ExecutionTimelineLog = {
                                    ...log,
                                    batchItemId: record.id,
                                    batchItemTitle: record.short_title,
                                  }
                                  return (
                                    <div key={log.id} className={getTerminalLineClassName(terminalLog)}>
                                      {buildExecutionTerminalLine(terminalLog)}
                                    </div>
                                  )
                                })}
                              </div>
                            ) : (
                              <Text type="secondary">暂无执行日志</Text>
                            ),
                        },
                      ]}
                    />
                  </div>
                ),
              }}
              pagination={false}
              scroll={{ x: 1550 }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="批次下暂无任务" /> }}
            />
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无批次明细" />
        )}
      </Drawer>
    </>
  )
}

export default BatchSection
