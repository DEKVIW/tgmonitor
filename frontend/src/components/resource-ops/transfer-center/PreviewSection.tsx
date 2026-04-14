import { useEffect, useMemo, useState } from 'react'
import type { Key } from 'react'
import { Alert, Button, Card, Empty, Input, InputNumber, Modal, Select, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { SearchOutlined } from '@ant-design/icons'

import type { PanTransferManualPreviewResponse, PanTransferPreviewItem } from '@/types/panTransfer'

import {
  HEALTH_FILTER_OPTIONS,
  HEALTH_META,
  PLATFORM_OPTIONS,
  type PreviewDraft,
  type TargetAccountSelectionMap,
} from './shared'

const { Title, Paragraph, Text } = Typography
const { CheckableTag } = Tag

type PreviewSectionProps = {
  draft: PreviewDraft
  previewData: PanTransferManualPreviewResponse | null
  previewLoading: boolean
  selectedPreviewKeys: Key[]
  targetAccountOptionsByPlatform: Record<string, { label: string; value: number }[]>
  selectedTargetAccountIds: TargetAccountSelectionMap
  onDraftChange: (updater: (current: PreviewDraft) => PreviewDraft) => void
  onTargetAccountChange: (platform: string, accountId: number | undefined) => void
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
  targetAccountOptionsByPlatform,
  selectedTargetAccountIds,
  onDraftChange,
  onTargetAccountChange,
  onPreview,
  onOpenCreateBatch,
  onSelectionChange,
  onTableChange,
}: PreviewSectionProps) => {
  const [pickerOpen, setPickerOpen] = useState(false)
  const isGlobalKeywordSearch = draft.searchKeyword.trim().length > 0

  const visibleAccountPlatforms = useMemo(() => {
    const basePlatforms = draft.platforms.length > 0 ? draft.platforms : Object.keys(targetAccountOptionsByPlatform)
    return basePlatforms.filter((platform) => (targetAccountOptionsByPlatform[platform] || []).length > 0)
  }, [draft.platforms, targetAccountOptionsByPlatform])

  const getSelectedAccountLabel = (platform: string, fallback?: string | null) => {
    const options = targetAccountOptionsByPlatform[platform] || []
    const selectedId = selectedTargetAccountIds[platform]
    return options.find((option) => option.value === selectedId)?.label || fallback || ''
  }

  useEffect(() => {
    if (!pickerOpen || previewData || previewLoading) return
    onPreview()
  }, [pickerOpen, previewData, previewLoading, onPreview])

  const filterSummary = useMemo(
    () => ({
      platformLabel: draft.platforms.length > 0 ? draft.platforms.join(' / ') : '全部平台',
      keywordLabel: draft.searchKeyword.trim() || '未限制关键词',
      healthLabel: HEALTH_FILTER_OPTIONS.find((item) => item.value === draft.healthFilter)?.label || '全部',
      accountLabel:
        visibleAccountPlatforms.length > 0
          ? visibleAccountPlatforms
              .map((platform) => `${platform}：${getSelectedAccountLabel(platform, '未指定') || '未指定'}`)
              .join(' / ')
          : '按平台默认账号执行',
    }),
    [draft, visibleAccountPlatforms, selectedTargetAccountIds, targetAccountOptionsByPlatform]
  )

  const columns: ColumnsType<PanTransferPreviewItem> = [
    {
      title: '资源',
      dataIndex: 'short_title',
      key: 'short_title',
      render: (_, record) => {
        const title = record.short_title || record.latest_message_title || record.work_title || '暂无标题'
        return (
          <Tooltip title={title}>
            <div className="resource-ops-transfer-title-cell">
              <span className="resource-ops-transfer-title-main">{title}</span>
            </div>
          </Tooltip>
        )
      },
    },
    {
      title: '网盘',
      dataIndex: 'platform',
      key: 'platform',
      width: 110,
      render: (value) => <Tag>{value}</Tag>,
    },
    {
      title: '原链状态',
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
      title: '影响',
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
      title: '目标账号',
      dataIndex: 'recommended_account_name',
      key: 'recommended_account_name',
      width: 160,
      render: (value, record) => getSelectedAccountLabel(record.platform, value) || <Text type="secondary">未配置</Text>,
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
    <>
      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head">
          <div>
            <Title level={4}>手动批量转存</Title>
            <Paragraph className="resource-ops-transfer-copy">
              先点“选择资源”，在弹窗里按最近消息、关键词、网盘平台和链接状态筛出资源，再勾选真正要进入批次的源链。
            </Paragraph>
          </div>
          <div className="resource-ops-transfer-head-actions">
            <Button
              onClick={() => {
                setPickerOpen(true)
              }}
            >
              选择资源
            </Button>
            <Button type="primary" disabled={selectedPreviewKeys.length <= 0} onClick={onOpenCreateBatch}>
              创建批次
            </Button>
          </div>
        </div>

        <div className="resource-ops-transfer-summary">
          <div className="resource-ops-transfer-summary-item">
            <span>{isGlobalKeywordSearch ? '搜索范围' : '扫描范围'}</span>
            <strong>{isGlobalKeywordSearch ? '全库历史' : `最近 ${draft.recentMessageCount}`}</strong>
            <small>{isGlobalKeywordSearch ? '输入关键词后自动检索全部历史消息' : '按最新消息倒序扫描'}</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>关键词</span>
            <strong>{filterSummary.keywordLabel}</strong>
            <small>匹配资源标题、消息标题、原链接和分享码</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>平台 / 状态</span>
            <strong>{filterSummary.platformLabel}</strong>
            <small>链接状态：{filterSummary.healthLabel}</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>目标账号</span>
            <strong>{visibleAccountPlatforms.length > 0 ? visibleAccountPlatforms.length : '-'}</strong>
            <small>{filterSummary.accountLabel}</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>已选择资源</span>
            <strong>{selectedPreviewKeys.length}</strong>
            <small>{previewData ? `当前候选共 ${previewData.total} 条` : '打开弹窗后开始筛选资源'}</small>
          </div>
        </div>

        {selectedPreviewKeys.length > 0 ? (
          <Alert
            style={{ marginTop: 16 }}
            type="success"
            showIcon
            message={`已选中 ${selectedPreviewKeys.length} 条待转存资源`}
            description="如果想补充或取消某些资源，重新打开“选择资源”即可继续筛选和勾选。"
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="尚未选择转存资源"
            style={{ marginTop: 20, marginBottom: 8 }}
          />
        )}
      </Card>

      <Modal
        open={pickerOpen}
        title="选择转存资源"
        onCancel={() => setPickerOpen(false)}
        onOk={() => setPickerOpen(false)}
        okText={selectedPreviewKeys.length > 0 ? `确认选择（${selectedPreviewKeys.length}）` : '关闭'}
        width={1180}
        destroyOnHidden={false}
      >
        <div className="resource-ops-transfer-picker-stack">
          <div className="resource-ops-transfer-picker-toolbar">
            <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
              <label>最近消息数</label>
              <InputNumber
                min={1}
                max={3000}
                style={{ width: '100%' }}
                value={draft.recentMessageCount}
                onChange={(value) => onDraftChange((current) => ({ ...current, recentMessageCount: Number(value || 1) }))}
              />
            </div>
            <div className="resource-ops-transfer-field">
              <label>关键词搜索</label>
              <Input
                allowClear
                prefix={<SearchOutlined />}
                value={draft.searchKeyword}
                placeholder="支持资源标题、全部历史消息标题、原链接、分享码"
                onChange={(event) => onDraftChange((current) => ({ ...current, searchKeyword: event.target.value }))}
                onPressEnter={() => onPreview()}
              />
            </div>
            <div className="resource-ops-transfer-field resource-ops-transfer-field--compact">
              <label>链接状态</label>
              <Select
                value={draft.healthFilter}
                options={HEALTH_FILTER_OPTIONS}
                onChange={(value) => onDraftChange((current) => ({ ...current, healthFilter: value as PreviewDraft['healthFilter'] }))}
              />
            </div>
            <div className="resource-ops-transfer-head-actions">
              <Button type="primary" loading={previewLoading} onClick={onPreview}>
                搜索资源
              </Button>
            </div>
          </div>

          <div className="resource-ops-transfer-chip-group">
            {PLATFORM_OPTIONS.map((option) => {
              const checked = draft.platforms.includes(option.value)
              return (
                <CheckableTag
                  key={option.value}
                  checked={checked}
                  onChange={(nextChecked) =>
                    onDraftChange((current) => ({
                      ...current,
                      platforms: nextChecked
                        ? [...current.platforms, option.value]
                        : current.platforms.filter((item) => item !== option.value),
                    }))
                  }
                >
                  {option.label}
                </CheckableTag>
              )
            })}
          </div>

          {visibleAccountPlatforms.length > 0 ? (
            <div className="resource-ops-transfer-picker-account-grid">
              {visibleAccountPlatforms.map((platform) => {
                const options = targetAccountOptionsByPlatform[platform] || []
                const selectedAccountId = selectedTargetAccountIds[platform]
                const currentLabel = getSelectedAccountLabel(platform)
                return (
                  <div key={platform} className="resource-ops-transfer-picker-account-item">
                    <label>{platform}账号</label>
                    <Select
                      value={selectedAccountId}
                      options={options}
                      disabled={options.length <= 1}
                      onChange={(value) => onTargetAccountChange(platform, Number(value || 0) || undefined)}
                    />
                    <small>
                      {options.length > 1
                        ? '本批次该平台将按这里选择的账号执行转存'
                        : currentLabel
                          ? `当前仅启用账号：${currentLabel}`
                          : '当前平台暂无启用账号'}
                    </small>
                  </div>
                )
              })}
            </div>
          ) : null}

          {previewData ? (
            <>
              <div className="resource-ops-transfer-summary">
                <div className="resource-ops-transfer-summary-item">
                  <span>命中消息</span>
                  <strong>{previewData.effective_message_count}</strong>
                  <small>本次纳入扫描的消息数</small>
                </div>
                <div className="resource-ops-transfer-summary-item">
                  <span>唯一源链</span>
                  <strong>{previewData.unique_link_target_count}</strong>
                  <small>去重后的可处理资源数</small>
                </div>
                <div className="resource-ops-transfer-summary-item">
                  <span>影响引用</span>
                  <strong>{previewData.matched_link_ref_count}</strong>
                  <small>这些源链覆盖到的消息链接引用总数</small>
                </div>
                <div className="resource-ops-transfer-summary-item">
                  <span>当前勾选</span>
                  <strong>{selectedPreviewKeys.length}</strong>
                  <small>创建批次时只处理勾选项</small>
                </div>
              </div>

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
                scroll={{ x: 1180 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无符合条件的源链" /> }}
              />
            </>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="正在准备资源列表" />
          )}
        </div>
      </Modal>
    </>
  )
}

export default PreviewSection
