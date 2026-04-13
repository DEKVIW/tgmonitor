import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import { listPanTransferPublishRecords, publishManualPanTransferMessage } from '@/api/panTransfer'
import type { PanTransferManualPublishRequest, PanTransferPublishRecordItem } from '@/types/panTransfer'

import { PLATFORM_OPTIONS, formatDateTime, getErrorMessage } from './shared'

const { Title, Paragraph, Text } = Typography

type PublishSectionProps = {
  refreshToken: number
}

const PublishSection = ({ refreshToken }: PublishSectionProps) => {
  const [records, setRecords] = useState<PanTransferPublishRecordItem[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10, total: 0 })
  const [manualModalOpen, setManualModalOpen] = useState(false)
  const [manualSaving, setManualSaving] = useState(false)
  const [form] = Form.useForm()

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
    return { manualCount, batchCount }
  }, [records])

  const columns: ColumnsType<PanTransferPublishRecordItem> = [
    {
      title: '发布时间',
      dataIndex: 'published_at',
      key: 'published_at',
      width: 152,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '标题',
      dataIndex: 'published_title',
      key: 'published_title',
      width: 260,
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">{record.published_title}</span>
          <span className="resource-ops-transfer-title-sub">
            {record.published_description || (record.published_tags.length > 0 ? record.published_tags.join(' / ') : '无补充说明')}
          </span>
        </div>
      ),
    },
    {
      title: '来源',
      key: 'source_type',
      width: 164,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <Space wrap size={[6, 6]}>
            <Tag color={record.source_type === 'manual' ? 'default' : 'processing'}>
              {record.source_type === 'manual' ? '手动新建' : '批次快捷发布'}
            </Tag>
            <Tag>{record.platform}</Tag>
          </Space>
          <small>
            {record.source_batch_item_id ? `来自批次项 #${record.source_batch_item_id}` : '直接填写分享链接创建'}
          </small>
        </div>
      ),
    },
    {
      title: '前台消息',
      dataIndex: 'published_message_id',
      key: 'published_message_id',
      width: 120,
      render: (value?: number | null) => (value ? <Tag color="success">#{value}</Tag> : <Text type="secondary">未记录</Text>),
    },
    {
      title: '使用链接',
      dataIndex: 'source_url',
      key: 'source_url',
      width: 320,
      render: (value: string) => (
        <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
          {value}
        </a>
      ),
    },
    {
      title: '操作人',
      dataIndex: 'operator',
      key: 'operator',
      width: 120,
      render: (value?: string | null) => value || <Text type="secondary">-</Text>,
    },
  ]

  const handleManualPublish = async () => {
    try {
      const values = await form.validateFields()
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
      form.resetFields()
      await loadRecords(1, pagination.pageSize)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(getErrorMessage(error, '手动发布失败'))
    } finally {
      setManualSaving(false)
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
                form.resetFields()
                form.setFieldsValue({
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
          scroll={{ x: 1210 }}
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
        <Form form={form} layout="vertical">
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
    </>
  )
}

export default PublishSection
