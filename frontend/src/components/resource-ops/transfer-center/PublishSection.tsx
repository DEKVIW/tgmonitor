import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import {
  listPanTransferPublishRecords,
  publishManualPanTransferMessage,
  refreshPanTransferPublishRecordShare,
  updatePanTransferPublishRecord,
  validatePanTransferPublishRecord,
} from '@/api/panTransfer'
import type {
  PanTransferManualPublishRequest,
  PanTransferPublishRecordItem,
  PanTransferPublishRecordUpdateRequest,
} from '@/types/panTransfer'

import { PLATFORM_OPTIONS, formatDateTime, getErrorMessage } from './shared'

const { Title, Paragraph, Text } = Typography

const LINK_STATUS_META: Record<string, { color: string; label: string }> = {
  healthy: { color: 'success', label: '有效' },
  valid: { color: 'success', label: '有效' },
  invalid: { color: 'error', label: '失效' },
  warning: { color: 'warning', label: '存疑' },
  unknown: { color: 'default', label: '未知' },
  error: { color: 'error', label: '异常' },
}

const renderStatusTag = (value?: string | null) => {
  const meta = LINK_STATUS_META[String(value || '').toLowerCase()] || LINK_STATUS_META.unknown
  return <Tag color={meta.color}>{meta.label}</Tag>
}

type PublishSectionProps = {
  refreshToken: number
}

const PublishSection = ({ refreshToken }: PublishSectionProps) => {
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

  const columns: ColumnsType<PanTransferPublishRecordItem> = [
    {
      title: '发布内容',
      dataIndex: 'published_title',
      key: 'published_title',
      width: 280,
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">{record.published_title}</span>
          <span className="resource-ops-transfer-title-sub">
            {record.published_description || (record.published_tags.length > 0 ? record.published_tags.join(' / ') : '无补充说明')}
          </span>
          <span className="resource-ops-transfer-title-sub">
            {formatDateTime(record.published_at)}
            {record.published_message_id ? ` · 前台消息 #${record.published_message_id}` : ''}
          </span>
        </div>
      ),
    },
    {
      title: '链接矩阵',
      key: 'links',
      width: 420,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>原链</small>
          {record.source_original_url ? (
            <a href={record.source_original_url} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={record.source_original_url}>
              {record.source_original_url}
            </a>
          ) : (
            <Text type="secondary">无</Text>
          )}
          <small>当前新分享</small>
          {record.current_share_url ? (
            <a href={record.current_share_url} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={record.current_share_url}>
              {record.current_share_url}
            </a>
          ) : (
            <Text type="secondary">无</Text>
          )}
          <small>前台正在使用</small>
          <a href={record.source_url} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={record.source_url}>
            {record.source_url}
          </a>
        </div>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 240,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <div className="resource-ops-transfer-tag-stack">
            <span>原链 {renderStatusTag(record.original_link_status)}</span>
            <span>新分享 {renderStatusTag(record.current_share_status)}</span>
            <span>前台链接 {renderStatusTag(record.published_link_status)}</span>
          </div>
          <small>{record.published_link_detail_message || '可手动触发校验获取最新结果'}</small>
          <small>{record.published_link_checked_at ? `最近校验：${formatDateTime(record.published_link_checked_at)}` : '最近校验：暂无'}</small>
        </div>
      ),
    },
    {
      title: '来源',
      key: 'source_type',
      width: 160,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <Space wrap size={[6, 6]}>
            <Tag color={record.source_type === 'manual' ? 'default' : 'processing'}>
              {record.source_type === 'manual' ? '手动新建' : '批次发布'}
            </Tag>
            <Tag>{record.platform}</Tag>
          </Space>
          <small>{record.source_batch_item_id ? `批次项 #${record.source_batch_item_id}` : '独立运营发布记录'}</small>
          <small>操作人：{record.operator || '-'}</small>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <Space size={8} wrap>
          <Button
            size="small"
            disabled={!record.can_edit}
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
          >
            编辑
          </Button>
          <Button
            size="small"
            loading={validatingRecordId === record.id}
            onClick={() => void (async () => {
              setValidatingRecordId(record.id)
              try {
                await validatePanTransferPublishRecord(record.id)
                message.success('已完成前台链接校验')
                await loadRecords(pagination.page, pagination.pageSize)
              } catch (error) {
                message.error(getErrorMessage(error, '校验发布记录失败'))
              } finally {
                setValidatingRecordId(null)
              }
            })()}
          >
            校验链接
          </Button>
          {record.can_refresh_share ? (
            <Button
              size="small"
              loading={refreshingRecordId === record.id}
              onClick={() => void (async () => {
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
              })()}
            >
              重建分享
            </Button>
          ) : null}
        </Space>
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
              这里统一汇总管理员发布到前台的记录。既包含批次详情里的一键发布，也支持直接填写标题和分享链接进行手动发布。
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
          message="批次内的一键发布仍然保留"
          description="批次详情里的“发布到前台”继续保留为快捷入口；这里负责集中查看所有发布结果，并补上纯手动运营发布能力。"
        />

        <div className="resource-ops-transfer-summary">
          <div className="resource-ops-transfer-summary-item">
            <span>发布总数</span>
            <strong>{pagination.total}</strong>
            <small>按发布时间倒序展示，历史不会因为删除批次而丢失</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页快捷发布</span>
            <strong>{summary.batchCount}</strong>
            <small>来自转存批次项的一键发布</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页手动发布</span>
            <strong>{summary.manualCount}</strong>
            <small>运营人员直接填写链接与标题创建</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>可重建分享</span>
            <strong>{summary.refreshableCount}</strong>
            <small>这些记录来自转存批次，支持重建分享并直接回填前台</small>
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
          scroll={{ x: 1380 }}
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
            <Input placeholder="这里改的是前台当前要展示给用户的链接" />
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
    </>
  )
}

export default PublishSection
