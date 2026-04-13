import type { Key } from 'react'
import type { Dayjs } from 'dayjs'
import { Alert, Button, Card, DatePicker, Empty, InputNumber, Segmented, Select, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import type { PanTransferManualPreviewResponse, PanTransferPreviewItem } from '@/types/panTransfer'

import { HEALTH_FILTER_OPTIONS, HEALTH_META, PLATFORM_OPTIONS, PreviewDraft } from './shared'

const { Title, Paragraph, Text } = Typography
const { RangePicker } = DatePicker

type PreviewSectionProps = {
  draft: PreviewDraft
  previewData: PanTransferManualPreviewResponse | null
  previewLoading: boolean
  selectedPreviewKeys: Key[]
  onDraftChange: (updater: (current: PreviewDraft) => PreviewDraft) => void
  onPreview: () => void
  onOpenCreateBatch: () => void
  onSelectionChange: (keys: Key[]) => void
  onTableChange: (pagination: TablePaginationConfig) => void
}

const PreviewSection = ({
  draft,
  previewData,
  previewLoading,
  selectedPreviewKeys,
  onDraftChange,
  onPreview,
  onOpenCreateBatch,
  onSelectionChange,
  onTableChange,
}: PreviewSectionProps) => {
  const columns: ColumnsType<PanTransferPreviewItem> = [
    {
      title: '资源标题',
      dataIndex: 'short_title',
      key: 'short_title',
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">{record.short_title}</span>
          <span className="resource-ops-transfer-title-sub">
            {record.latest_message_title || record.work_title || '未补充标题'}
          </span>
        </div>
      ),
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 110,
      render: (value) => <Tag>{value}</Tag>,
    },
    {
      title: '来源健康',
      key: 'latest_link_health',
      width: 140,
      render: (_, record) => {
        const meta = HEALTH_META[record.latest_link_health] || HEALTH_META.unknown
        return (
          <Tooltip title={record.latest_link_health_reason || '暂无补充说明'}>
            <Tag color={meta.color}>{record.latest_link_health_label || meta.label}</Tag>
          </Tooltip>
        )
      },
    },
    {
      title: '影响范围',
      key: 'impact',
      width: 140,
      render: (_, record) => (
        <div className="resource-ops-transfer-number-stack">
          <strong>{record.impact_message_count}</strong>
          <small>{record.source_ref_count} 条链接引用</small>
        </div>
      ),
    },
    {
      title: '推荐账号',
      dataIndex: 'recommended_account_name',
      key: 'recommended_account_name',
      width: 160,
      render: (value) => value || <Text type="secondary">未配置</Text>,
    },
    {
      title: '原链接',
      dataIndex: 'original_url',
      key: 'original_url',
      render: (value: string) => (
        <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
          {value}
        </a>
      ),
    },
  ]

  return (
    <Card className="resource-ops-panel-card">
      <div className="resource-ops-transfer-card-head">
        <div>
          <Title level={4}>手动批量转存</Title>
          <Paragraph className="resource-ops-transfer-copy">
            先从最近消息或时间范围里筛出符合条件的网盘链接，再按唯一原链接去重，勾选后创建真实批次进入 worker 队列执行。
          </Paragraph>
        </div>
        <div className="resource-ops-transfer-head-actions">
          <Button onClick={onPreview} loading={previewLoading}>
            生成预览
          </Button>
          <Button type="primary" disabled={selectedPreviewKeys.length <= 0} onClick={onOpenCreateBatch}>
            创建批次
          </Button>
        </div>
      </div>

      <div className="resource-ops-transfer-toolbar">
        <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
          <label>选择方式</label>
          <Segmented
            block
            value={draft.selectionMode}
            options={[
              { label: '最近消息', value: 'recent_messages' },
              { label: '时间范围', value: 'time_range' },
            ]}
            onChange={(value) =>
              onDraftChange((current) => ({ ...current, selectionMode: value as PreviewDraft['selectionMode'] }))
            }
          />
        </div>
        <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
          <label>遍历方向</label>
          <Select
            value={draft.direction}
            options={[
              { label: '最新优先', value: 'newest_first' },
              { label: '最早优先', value: 'oldest_first' },
            ]}
            onChange={(value) =>
              onDraftChange((current) => ({ ...current, direction: value as PreviewDraft['direction'] }))
            }
          />
        </div>
        {draft.selectionMode === 'recent_messages' ? (
          <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
            <label>最近消息数</label>
            <InputNumber
              min={1}
              max={3000}
              style={{ width: '100%' }}
              value={draft.recentMessageCount}
              onChange={(value) =>
                onDraftChange((current) => ({ ...current, recentMessageCount: Number(value || 1) }))
              }
            />
          </div>
        ) : (
          <div className="resource-ops-transfer-field">
            <label>时间范围</label>
            <RangePicker
              style={{ width: '100%' }}
              value={draft.range}
              onChange={(value) =>
                onDraftChange((current) => ({ ...current, range: (value as [Dayjs, Dayjs] | null) ?? null }))
              }
            />
          </div>
        )}
        <div className="resource-ops-transfer-field">
          <label>平台筛选</label>
          <Select
            mode="multiple"
            allowClear
            placeholder="留空表示所有已支持平台"
            value={draft.platforms}
            options={PLATFORM_OPTIONS}
            onChange={(value) => onDraftChange((current) => ({ ...current, platforms: value }))}
          />
        </div>
        <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
          <label>来源健康筛选</label>
          <Select
            value={draft.healthFilter}
            options={HEALTH_FILTER_OPTIONS}
            onChange={(value) =>
              onDraftChange((current) => ({ ...current, healthFilter: value as PreviewDraft['healthFilter'] }))
            }
          />
        </div>
      </div>

      {previewData ? (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="来源健康状态说明"
            description="这里的“正常 / 失效 / 未知”来自系统里已有的历史链接检测结果，不是本次转存前的实时校验。建议优先使用“排除失效”，避免因为“未知”被全部过滤掉。"
          />

          <div className="resource-ops-transfer-summary">
            <div className="resource-ops-transfer-summary-item">
              <span>命中消息</span>
              <strong>{previewData.effective_message_count}</strong>
              <small>{previewData.selection_mode === 'time_range' ? '时间范围内实际扫到的消息数' : '本次纳入扫描的消息数'}</small>
            </div>
            <div className="resource-ops-transfer-summary-item">
              <span>唯一源链</span>
              <strong>{previewData.unique_link_target_count}</strong>
              <small>按源链接去重后的可处理项目</small>
            </div>
            <div className="resource-ops-transfer-summary-item">
              <span>影响引用</span>
              <strong>{previewData.matched_link_ref_count}</strong>
              <small>这些源链覆盖到的消息链接引用总数</small>
            </div>
            <div className="resource-ops-transfer-summary-item">
              <span>当前勾选</span>
              <strong>{selectedPreviewKeys.length}</strong>
              <small>创建批次时只会处理当前勾选的源链</small>
            </div>
          </div>

          {previewData.truncated ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 16 }}
              message="本次范围过大，预览已自动截断"
              description="为了控制扫描成本，时间范围模式最多扫描 3000 条带链接消息。需要更细时可以缩短范围后再建批。"
            />
          ) : null}

          <Table
            style={{ marginTop: 16 }}
            rowKey="link_target_id"
            loading={previewLoading}
            dataSource={previewData.items}
            columns={columns}
            rowSelection={{
              selectedRowKeys: selectedPreviewKeys,
              preserveSelectedRowKeys: true,
              onChange: (keys) => onSelectionChange(keys),
            }}
            onChange={onTableChange}
            pagination={{
              current: previewData.page,
              pageSize: previewData.page_size,
              total: previewData.total,
              showSizeChanger: true,
            }}
            scroll={{ x: 1250 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无符合条件的源链" /> }}
          />
        </>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先选择范围并生成预览" />
      )}
    </Card>
  )
}

export default PreviewSection
