import type { Key } from 'react'
import { Alert, Button, Card, Descriptions, Drawer, Empty, Popconfirm, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { PanTransferBatchDetailResponse, PanTransferBatchItem, PanTransferBatchSummaryItem } from '@/types/panTransfer'

import {
  BATCH_STATUS_META,
  formatDateTime,
  getBatchSummary,
  ITEM_STATUS_META,
  REPLACEMENT_STATUS_META,
  VALIDATION_STATUS_META,
} from './shared'

const { Title, Paragraph, Text } = Typography

type BatchSectionProps = {
  batches: PanTransferBatchSummaryItem[]
  batchLoading: boolean
  batchPagination: { page: number; pageSize: number; total: number }
  startingBatchId: number | null
  retryingBatchId: number | null
  deletingBatchId: number | null
  detailOpen: boolean
  detailLoading: boolean
  detailData: PanTransferBatchDetailResponse | null
  selectedFailedItemKeys: Key[]
  onRefresh: () => void
  onTableChange: (pagination: TablePaginationConfig) => void
  onOpenDetail: (batchId: number) => void
  onStart: (batchId: number) => void
  onRetry: (batchId: number, itemIds?: number[]) => void
  onDelete: (batchId: number) => void
  onCloseDetail: () => void
  onRefreshDetail: (batchId: number) => void
  onSelectFailedKeys: (keys: Key[]) => void
}

const BatchSection = ({
  batches,
  batchLoading,
  batchPagination,
  startingBatchId,
  retryingBatchId,
  deletingBatchId,
  detailOpen,
  detailLoading,
  detailData,
  selectedFailedItemKeys,
  onRefresh,
  onTableChange,
  onOpenDetail,
  onStart,
  onRetry,
  onDelete,
  onCloseDetail,
  onRefreshDetail,
  onSelectFailedKeys,
}: BatchSectionProps) => {
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
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">{record.short_title}</span>
          <span className="resource-ops-transfer-title-sub">
            {record.latest_message_title || `${record.source_message_count} 条消息受影响`}
          </span>
        </div>
      ),
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
                <span>待重试</span>
                <strong>{getBatchSummary(detailData.batch).retryWait}</strong>
                <small>到达 next_retry_at 后会自动再试</small>
              </div>
            </div>

            <Alert
              type="info"
              showIcon
              message="当前生效链接"
              description="“新分享链接”表示转存平台刚生成的新链接，“当前生效链接”表示已经写回系统后的链接目标。管理员可在这里直接核对是否替换成功。"
            />

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
                          key: 'replacement_log',
                          label: '回写日志',
                          children:
                            record.replacement_logs.length > 0 ? (
                              <div className="resource-ops-transfer-log-list">
                                {record.replacement_logs.map((log) => (
                                  <div key={log.id} className="resource-ops-transfer-log-item">
                                    <Tag color={log.status === 'replaced' ? 'success' : log.status === 'skipped' ? 'default' : 'error'}>
                                      {log.status}
                                    </Tag>
                                    <span>{formatDateTime(log.created_at)}</span>
                                    <span>影响消息 {log.affected_message_count}</span>
                                    {log.new_url ? (
                                      <a href={log.new_url} target="_blank" rel="noreferrer">
                                        查看新链接
                                      </a>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <Text type="secondary">暂无回写日志</Text>
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
