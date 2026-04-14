import { CheckCircleOutlined, CopyOutlined, EditOutlined, EyeOutlined, LinkOutlined, RedoOutlined } from '@ant-design/icons'
import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Dropdown, Empty, Form, Input, Modal, Select, Space, Table, Tag, Tooltip, Typography, message } from 'antd'
import type { MenuProps } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import {
  listPanTransferPublishRecords,
  previewPanTransferLinkDirectory,
  publishManualPanTransferMessage,
  refreshPanTransferPublishRecordShare,
  updatePanTransferPublishRecord,
  validatePanTransferPublishRecord,
} from '@/api/panTransfer'
import type {
  PanTransferLinkDirectoryEntry,
  PanTransferLinkDirectoryPreviewResponse,
  PanTransferManualPublishRequest,
  PanTransferPublishRecordItem,
  PanTransferPublishRecordUpdateRequest,
} from '@/types/panTransfer'

import { PLATFORM_OPTIONS, formatDateTime, getErrorMessage } from './shared'

const { Title, Paragraph, Text } = Typography

const LINK_STATUS_META: Record<string, { tone: string; label: string }> = {
  healthy: { tone: 'success', label: '有效' },
  valid: { tone: 'success', label: '有效' },
  invalid: { tone: 'danger', label: '失效' },
  warning: { tone: 'warning', label: '存疑' },
  unknown: { tone: 'muted', label: '未知' },
  error: { tone: 'danger', label: '异常' },
}

type PublishSectionProps = {
  refreshToken: number
}

type PublishLinkKind = 'original' | 'current_share' | 'published'

type PublishLinkChip = {
  key: PublishLinkKind
  label: string
  url: string
  status?: string | null
}

const getLinkStatusMeta = (value?: string | null) =>
  LINK_STATUS_META[String(value || '').toLowerCase()] || LINK_STATUS_META.unknown

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

const buildLinkItems = (record: PanTransferPublishRecordItem): PublishLinkChip[] => {
  const items: PublishLinkChip[] = []
  if (record.source_original_url) {
    items.push({
      key: 'original',
      label: '原链',
      url: record.source_original_url,
      status: record.original_link_status,
    })
  }
  if (record.current_share_url) {
    items.push({
      key: 'current_share',
      label: '新分享',
      url: record.current_share_url,
      status: record.current_share_status,
    })
  }
  if (record.source_url) {
    items.push({
      key: 'published',
      label: '前台使用',
      url: record.source_url,
      status: record.published_link_status,
    })
  }
  return items
}

const copyText = async (value: string, successText: string) => {
  try {
    await navigator.clipboard.writeText(value)
    message.success(successText)
  } catch {
    message.error('复制失败，请检查浏览器权限')
  }
}

const openLink = (url: string) => {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

const PublishSectionCompact = ({ refreshToken }: PublishSectionProps) => {
  const [records, setRecords] = useState<PanTransferPublishRecordItem[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10, total: 0 })
  const [manualModalOpen, setManualModalOpen] = useState(false)
  const [manualSaving, setManualSaving] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<PanTransferPublishRecordItem | null>(null)
  const [editSaving, setEditSaving] = useState(false)
  const [validatingRecordId, setValidatingRecordId] = useState<number | null>(null)
  const [refreshingRecordId, setRefreshingRecordId] = useState<number | null>(null)
  const [directoryPreviewOpen, setDirectoryPreviewOpen] = useState(false)
  const [directoryPreviewLoading, setDirectoryPreviewLoading] = useState(false)
  const [directoryPreviewTitle, setDirectoryPreviewTitle] = useState('')
  const [directoryPreviewData, setDirectoryPreviewData] = useState<PanTransferLinkDirectoryPreviewResponse | null>(null)
  const [manualForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const loadRecords = async (page = pagination.page, pageSize = pagination.pageSize) => {
    setLoading(true)
    try {
      const response = await listPanTransferPublishRecords(page, pageSize)
      setRecords(response.items)
      setPagination({ page: response.page, pageSize: response.page_size, total: response.total })
    } catch (error) {
      message.error(getErrorMessage(error, '加载运营发布记录失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRecords(1, pagination.pageSize)
  }, [refreshToken])

  const summary = useMemo(() => {
    const manualCount = records.filter((item) => item.source_type === 'manual').length
    const batchCount = records.filter((item) => item.source_type === 'batch_item').length
    const refreshableCount = records.filter((item) => item.can_refresh_share).length
    return { manualCount, batchCount, refreshableCount }
  }, [records])

  const handlePreviewDirectory = async (item: PublishLinkChip) => {
    setDirectoryPreviewTitle(item.label)
    setDirectoryPreviewOpen(true)
    setDirectoryPreviewLoading(true)
    setDirectoryPreviewData(null)
    try {
      const response = await previewPanTransferLinkDirectory({ url: item.url })
      setDirectoryPreviewData(response)
    } catch (error) {
      setDirectoryPreviewOpen(false)
      message.error(getErrorMessage(error, '目录预览失败'))
    } finally {
      setDirectoryPreviewLoading(false)
    }
  }

  const handleLinkMenuClick = async (actionKey: string, item: PublishLinkChip) => {
    if (actionKey === 'open') {
      openLink(item.url)
      return
    }
    if (actionKey === 'copy') {
      await copyText(item.url, '已复制链接')
      return
    }
    if (actionKey === 'preview') {
      await handlePreviewDirectory(item)
    }
  }

  const renderLinkChip = (item: PublishLinkChip) => {
    const statusMeta = getLinkStatusMeta(item.status)
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
        <Tooltip title={`${item.label}: ${item.url}`}>
          <button type="button" className="resource-ops-transfer-link-chip" onClick={() => openLink(item.url)}>
            <span className="resource-ops-transfer-link-chip-label">{item.label}</span>
            <span className={`resource-ops-transfer-link-chip-status is-${statusMeta.tone}`}>{statusMeta.label}</span>
          </button>
        </Tooltip>
      </Dropdown>
    )
  }

  const directoryColumns: ColumnsType<PanTransferLinkDirectoryEntry> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (_, entry) => (
        <div className="resource-ops-transfer-title-cell">
          <span className={`resource-ops-transfer-directory-name${entry.is_dir ? ' is-dir' : ''}`}>{entry.name}</span>
        </div>
      ),
    },
    {
      title: '类型',
      dataIndex: 'is_dir',
      key: 'is_dir',
      width: 90,
      render: (value: boolean) => <Tag color={value ? 'processing' : 'default'}>{value ? '文件夹' : '文件'}</Tag>,
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

  const columns: ColumnsType<PanTransferPublishRecordItem> = [
    {
      title: '发布内容',
      dataIndex: 'published_title',
      key: 'published_title',
      width: 300,
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <Tooltip title="点击复制标题">
            <button
              type="button"
              className="resource-ops-transfer-title-copy"
              onClick={() => void copyText(record.published_title, '已复制标题')}
            >
              {record.published_title}
            </button>
          </Tooltip>
          <span className="resource-ops-transfer-title-sub">
            {formatDateTime(record.published_at)}
            {record.published_message_id ? ` · 前台消息 #${record.published_message_id}` : ''}
          </span>
        </div>
      ),
    },
    {
      title: '链接',
      key: 'links',
      width: 420,
      render: (_, record) => {
        const linkItems = buildLinkItems(record)
        return (
          <div className="resource-ops-transfer-link-stack">
            {linkItems.length > 0 ? (
              <Space size={[6, 6]} wrap>
                {linkItems.map((item) => renderLinkChip(item))}
              </Space>
            ) : (
              <Text type="secondary">暂无可用链接</Text>
            )}
            <small>
              {record.published_link_checked_at
                ? `最近校验：${formatDateTime(record.published_link_checked_at)}`
                : '左键访问，右键可复制或查看目录'}
              {record.published_link_detail_message ? ` · ${record.published_link_detail_message}` : ''}
            </small>
          </div>
        )
      },
    },
    {
      title: '点击',
      dataIndex: 'published_clicks_total',
      key: 'published_clicks_total',
      width: 92,
      align: 'right',
      render: (value: number) => (
        <div className="resource-ops-transfer-number-stack resource-ops-transfer-number-stack--compact">
          <strong>{value || 0}</strong>
          <small>新链点击</small>
        </div>
      ),
    },
    {
      title: '网盘 / 操作人',
      key: 'source_type',
      width: 180,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <Space wrap size={[6, 6]}>
            <Tag>{record.platform}</Tag>
            <Tag color={record.source_type === 'manual' ? 'default' : 'processing'}>
              {record.source_type === 'manual' ? '手动发布' : '批次发布'}
            </Tag>
          </Space>
          <small>{record.source_batch_item_id ? `批次项 #${record.source_batch_item_id}` : '独立运营发布'}</small>
          <small>操作人：{record.operator || '-'}</small>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <div className="resource-ops-transfer-action-grid">
          <Tooltip title="编辑">
            <Button
              size="small"
              type="text"
              disabled={!record.can_edit}
              icon={<EditOutlined />}
              onClick={() => {
                setEditingRecord(record)
                editForm.resetFields()
                editForm.setFieldsValue({
                  source_url: record.source_url,
                  title: record.published_title,
                  description: record.published_description || '',
                  tags: record.published_tags,
                })
                setEditModalOpen(true)
              }}
            />
          </Tooltip>
          <Tooltip title="校验链接">
            <Button
              size="small"
              type="text"
              loading={validatingRecordId === record.id}
              icon={<CheckCircleOutlined />}
              onClick={() =>
                void (async () => {
                  setValidatingRecordId(record.id)
                  try {
                    await validatePanTransferPublishRecord(record.id)
                    message.success('已完成链接校验')
                    await loadRecords(pagination.page, pagination.pageSize)
                  } catch (error) {
                    message.error(getErrorMessage(error, '校验发布记录失败'))
                  } finally {
                    setValidatingRecordId(null)
                  }
                })()
              }
            />
          </Tooltip>
          <Tooltip title={record.can_refresh_share ? '重建分享' : '当前记录不支持重建分享'}>
            <Button
              size="small"
              type="text"
              disabled={!record.can_refresh_share}
              loading={refreshingRecordId === record.id}
              icon={<RedoOutlined />}
              onClick={() =>
                void (async () => {
                  setRefreshingRecordId(record.id)
                  try {
                    await refreshPanTransferPublishRecordShare(record.id)
                    message.success('已重建分享并回填到前台消息')
                    await loadRecords(pagination.page, pagination.pageSize)
                  } catch (error) {
                    message.error(getErrorMessage(error, '重建分享失败'))
                  } finally {
                    setRefreshingRecordId(null)
                  }
                })()
              }
            />
          </Tooltip>
        </div>
      ),
    },
  ]

  const handleManualPublish = async () => {
    try {
      const values = await manualForm.validateFields()
      setManualSaving(true)
      const payload: PanTransferManualPublishRequest = {
        platform: values.platform,
        source_url: values.source_url,
        title: values.title,
        description: values.description || null,
        tags: Array.isArray(values.tags) ? values.tags : [],
      }
      const response = await publishManualPanTransferMessage(payload)
      message.success(`已发布到前台，消息 #${response.message_id}`)
      setManualModalOpen(false)
      manualForm.resetFields()
      await loadRecords(1, pagination.pageSize)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '手动发布失败'))
    } finally {
      setManualSaving(false)
    }
  }

  const handleEditPublish = async () => {
    if (!editingRecord) return
    try {
      const values = await editForm.validateFields()
      setEditSaving(true)
      const payload: PanTransferPublishRecordUpdateRequest = {
        source_url: values.source_url,
        title: values.title,
        description: values.description || null,
        tags: Array.isArray(values.tags) ? values.tags : [],
      }
      await updatePanTransferPublishRecord(editingRecord.id, payload)
      message.success('发布记录已更新')
      setEditModalOpen(false)
      setEditingRecord(null)
      editForm.resetFields()
      await loadRecords(pagination.page, pagination.pageSize)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '更新发布记录失败'))
    } finally {
      setEditSaving(false)
    }
  }

  return (
    <>
      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head">
          <div>
            <Title level={4}>运营发布</Title>
            <Paragraph className="resource-ops-transfer-copy">
              这里集中管理管理员推到前台的资源。链接标签左键直接访问，右键可复制链接或查看目录，表格也会展示当前前台使用新链的累计点击量。
            </Paragraph>
          </div>
          <Space>
            <Button onClick={() => void loadRecords()}>刷新</Button>
            <Button
              type="primary"
              onClick={() => {
                manualForm.resetFields()
                manualForm.setFieldsValue({
                  platform: PLATFORM_OPTIONS[0]?.value,
                  source_url: '',
                  title: '',
                  description: '',
                  tags: [],
                })
                setManualModalOpen(true)
              }}
            >
              手动新建发布
            </Button>
          </Space>
        </div>

        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="批次内一键发布仍然保留"
          description="批次明细里的“发布到前台”继续作为快捷入口；这里负责集中查看发布结果、校验当前链接、重建新分享，以及直接手动发布。"
        />

        <div className="resource-ops-transfer-summary">
          <div className="resource-ops-transfer-summary-item">
            <span>发布总数</span>
            <strong>{pagination.total}</strong>
            <small>按发布时间倒序展示，批次删除不会影响这里的发布台账</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页批次发布</span>
            <strong>{summary.batchCount}</strong>
            <small>来自转存批次项的一键发布</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页手动发布</span>
            <strong>{summary.manualCount}</strong>
            <small>管理员手动填写标题与链接创建的发布记录</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>可重建分享</span>
            <strong>{summary.refreshableCount}</strong>
            <small>这些记录仍可从暂存目录重建新分享，并同步回前台</small>
          </div>
        </div>

        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          loading={loading}
          dataSource={records}
          columns={columns}
          onChange={(tablePagination: TablePaginationConfig) =>
            void loadRecords(tablePagination.current || 1, tablePagination.pageSize || pagination.pageSize)
          }
          pagination={{
            current: pagination.page,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
          }}
          scroll={{ x: 1180 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运营发布记录" /> }}
        />
      </Card>

      <Modal
        open={manualModalOpen}
        title="手动新建发布"
        onCancel={() => setManualModalOpen(false)}
        onOk={() => void handleManualPublish()}
        confirmLoading={manualSaving}
        okText="确认发布"
        destroyOnHidden
      >
        <Form form={manualForm} layout="vertical">
          <Form.Item label="平台" name="platform" rules={[{ required: true, message: '请选择平台' }]}>
            <Select options={PLATFORM_OPTIONS} />
          </Form.Item>
          <Form.Item label="分享链接" name="source_url" rules={[{ required: true, message: '请输入分享链接' }]}>
            <Input placeholder="请输入最终要展示给前台的分享链接" />
          </Form.Item>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="请输入前台展示标题" maxLength={255} />
          </Form.Item>
          <Form.Item label="简介" name="description">
            <Input.TextArea rows={4} placeholder="可选，补充发布说明" maxLength={1000} />
          </Form.Item>
          <Form.Item label="标签" name="tags">
            <Select mode="tags" tokenSeparators={[',', '，']} open={false} placeholder="可选，输入后回车" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={editModalOpen}
        title={editingRecord ? `编辑发布：${editingRecord.published_title}` : '编辑发布'}
        onCancel={() => {
          setEditModalOpen(false)
          setEditingRecord(null)
          editForm.resetFields()
        }}
        onOk={() => void handleEditPublish()}
        confirmLoading={editSaving}
        okText="保存修改"
        destroyOnHidden
      >
        <Form form={editForm} layout="vertical">
          <Form.Item label="前台链接" name="source_url" rules={[{ required: true, message: '请输入前台链接' }]}>
            <Input placeholder="这里修改的是前台当前对外展示给用户的链接" />
          </Form.Item>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={255} />
          </Form.Item>
          <Form.Item label="简介" name="description">
            <Input.TextArea rows={4} maxLength={1000} />
          </Form.Item>
          <Form.Item label="标签" name="tags">
            <Select mode="tags" tokenSeparators={[',', '，']} open={false} placeholder="输入后回车" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={directoryPreviewOpen}
        title={directoryPreviewTitle ? `${directoryPreviewTitle}目录预览` : '目录预览'}
        onCancel={() => {
          setDirectoryPreviewOpen(false)
          setDirectoryPreviewData(null)
        }}
        footer={null}
        width={760}
        destroyOnHidden
      >
        <div className="resource-ops-transfer-modal-stack">
          <Paragraph className="resource-ops-transfer-copy">
            当前展示的是分享链接的顶层目录内容。这里只做目录核对，不会改动任何现有链接、分享或发布记录。
          </Paragraph>

          {directoryPreviewData ? (
            <div className="resource-ops-transfer-directory-meta">
              <Tag>{directoryPreviewData.platform}</Tag>
              <Tag color="processing">共 {directoryPreviewData.item_count} 项</Tag>
              {directoryPreviewData.truncated ? <Tag color="warning">已截取前 {directoryPreviewData.items.length} 项</Tag> : null}
            </div>
          ) : null}

          <Table
            size="small"
            rowKey={(entry) => entry.entry_id || `${entry.name}-${entry.is_dir ? 'dir' : 'file'}`}
            loading={directoryPreviewLoading}
            columns={directoryColumns}
            dataSource={directoryPreviewData?.items || []}
            pagination={false}
            scroll={{ y: 360 }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={directoryPreviewData?.message || '当前目录为空'}
                />
              ),
            }}
          />
        </div>
      </Modal>
    </>
  )
}

export default PublishSectionCompact
