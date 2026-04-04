import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  createChannel,
  deleteChannel,
  diagnoseChannels,
  getChannelSamples,
  getChannels,
  testMonitor,
  updateChannel,
} from '@/api/admin'
import type {
  ChannelCreate,
  ChannelDiagnosisResult,
  ChannelMessageSample,
  ChannelResponse,
  ChannelSampleResponse,
  MonitorTestResult,
  ParsedMessageRecord,
} from '@/types/admin'

const { Paragraph, Text } = Typography
const TITLE_MAX_CHARS = 20

const truncateText = (value: string | null | undefined, maxChars: number) => {
  const text = (value || '').trim()
  if (!text) {
    return ''
  }
  if (text.length <= maxChars) {
    return text
  }
  return `${text.slice(0, maxChars)}...`
}

const formatTimestamp = (value: string) => {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

const getRecordLinkCount = (record: ParsedMessageRecord) =>
  Object.values(record.links || {}).reduce((total, items) => total + items.length, 0)

const SampleRecordCard = ({ record, index }: { record: ParsedMessageRecord; index: number }) => {
  const linkEntries = Object.entries(record.links || {})
  const recordTitle = record.title?.trim() || `记录 ${index + 1}`

  return (
    <div className="sample-record-card">
      <div className="sample-record-header">
        <Text strong>{recordTitle}</Text>
        <Tag color={linkEntries.length > 0 ? 'blue' : 'default'}>{getRecordLinkCount(record)} 个链接</Tag>
      </div>

      {record.description ? (
        <Paragraph className="sample-pretty-text">{record.description}</Paragraph>
      ) : (
        <Text type="secondary">无额外描述</Text>
      )}

      {(record.tags || []).length > 0 && (
        <div className="sample-tag-row">
          {record.tags.map((tag) => (
            <Tag key={`${recordTitle}-${tag}`}>{tag}</Tag>
          ))}
        </div>
      )}

      {linkEntries.length > 0 && (
        <div className="sample-link-list">
          {linkEntries.map(([netdiskName, items]) => (
            <div key={`${recordTitle}-${netdiskName}`} className="sample-link-group">
              <Text strong>{netdiskName}</Text>
              <div className="sample-tag-row">
                {items.map((item, itemIndex) => (
                  <Tag key={`${netdiskName}-${item.url}-${itemIndex}`} color="processing">
                    {item.label || '链接'}
                  </Tag>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const SamplePanelBody = ({ sample }: { sample: ChannelMessageSample }) => (
  <div className="channel-sample-body">
    <Descriptions size="small" column={2} bordered>
      <Descriptions.Item label="消息 ID">{sample.message_id}</Descriptions.Item>
      <Descriptions.Item label="原始链接数">{sample.raw_urls.length}</Descriptions.Item>
      <Descriptions.Item label="解析记录数">{sample.parsed_records.length}</Descriptions.Item>
      <Descriptions.Item label="提取链接数">{sample.extracted_link_count}</Descriptions.Item>
      <Descriptions.Item label="文本长度">{sample.text_length}</Descriptions.Item>
      <Descriptions.Item label="包含媒体">{sample.has_media ? '是' : '否'}</Descriptions.Item>
      <Descriptions.Item label="网页预览" span={2}>
        {sample.webpage_url || '-'}
      </Descriptions.Item>
    </Descriptions>

    <div className="sample-section">
      <Text strong>原始文本</Text>
      <Paragraph className="sample-pre-block" copyable={{ text: sample.text || '' }}>
        {sample.text || '(空文本)'}
      </Paragraph>
    </div>

    {sample.raw_urls.length > 0 && (
      <div className="sample-section">
        <Text strong>原始 URL</Text>
        <div className="sample-tag-row">
          {sample.raw_urls.map((url) => (
            <Tag key={url} color="blue">
              {truncateText(url, 48)}
            </Tag>
          ))}
        </div>
      </div>
    )}

    {sample.entity_urls.length > 0 && (
      <div className="sample-section">
        <Text strong>Entity URL</Text>
        <div className="sample-entity-list">
          {sample.entity_urls.map((entity, index) => (
            <div key={`${entity.url}-${index}`} className="sample-entity-item">
              <Tag>{entity.type}</Tag>
              <Text>{entity.url}</Text>
            </div>
          ))}
        </div>
      </div>
    )}

    {sample.button_urls.length > 0 && (
      <div className="sample-section">
        <Text strong>按钮 URL</Text>
        <div className="sample-entity-list">
          {sample.button_urls.map((url, index) => (
            <div key={`${url}-${index}`} className="sample-entity-item">
              <Text>{url}</Text>
            </div>
          ))}
        </div>
      </div>
    )}

    <div className="sample-section">
      <Text strong>解析结果</Text>
      {sample.parsed_records.length > 0 ? (
        <div className="sample-record-list">
          {sample.parsed_records.map((record, index) => (
            <SampleRecordCard key={`${sample.message_id}-${index}`} record={record} index={index} />
          ))}
        </div>
      ) : (
        <Empty description="没有可展示的解析记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </div>

    <div className="sample-section">
      <Text strong>解析诊断</Text>
      <pre className="sample-json-block">{JSON.stringify(sample.diagnostics, null, 2)}</pre>
    </div>
  </div>
)

const ChannelManagerEnhanced = () => {
  const [channels, setChannels] = useState<ChannelResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [diagnosisModalVisible, setDiagnosisModalVisible] = useState(false)
  const [diagnosisResult, setDiagnosisResult] = useState<ChannelDiagnosisResult | null>(null)
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState<MonitorTestResult | null>(null)
  const [editingChannel, setEditingChannel] = useState<ChannelResponse | null>(null)
  const [sampleModalVisible, setSampleModalVisible] = useState(false)
  const [sampleLoading, setSampleLoading] = useState(false)
  const [sampleChannel, setSampleChannel] = useState<ChannelResponse | null>(null)
  const [sampleData, setSampleData] = useState<ChannelSampleResponse | null>(null)
  const [samplePage, setSamplePage] = useState(1)
  const [samplePageSize, setSamplePageSize] = useState(10)
  const [sampleOnlyWithLinks, setSampleOnlyWithLinks] = useState(true)
  const [form] = Form.useForm<ChannelCreate>()
  const [editForm] = Form.useForm<ChannelCreate>()

  const loadChannels = async () => {
    setLoading(true)
    try {
      const data = await getChannels()
      setChannels(data)
    } catch {
      message.error('加载频道列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadChannels()
  }, [])

  const handleAdd = async (values: ChannelCreate) => {
    try {
      await createChannel(values)
      message.success('添加成功')
      setModalVisible(false)
      form.resetFields()
      await loadChannels()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '添加失败')
    }
  }

  const handleEdit = (channel: ChannelResponse) => {
    setEditingChannel(channel)
    editForm.setFieldsValue({ username: channel.username })
    setEditModalVisible(true)
  }

  const handleUpdate = async (values: ChannelCreate) => {
    if (!editingChannel) {
      return
    }

    try {
      await updateChannel(editingChannel.id, values)
      message.success('编辑成功')
      setEditModalVisible(false)
      editForm.resetFields()
      setEditingChannel(null)
      await loadChannels()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '编辑失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteChannel(id)
      message.success('删除成功')
      await loadChannels()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败')
    }
  }

  const handleDiagnose = async () => {
    setDiagnosisLoading(true)
    setDiagnosisResult(null)
    setDiagnosisModalVisible(true)

    try {
      const result = await diagnoseChannels()
      setDiagnosisResult(result)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '诊断失败')
      setDiagnosisModalVisible(false)
    } finally {
      setDiagnosisLoading(false)
    }
  }

  const handleTestMonitor = async () => {
    setTestLoading(true)
    setTestResult(null)

    try {
      const result = await testMonitor()
      setTestResult(result)
      if (result.success) {
        message.success('测试完成')
      } else {
        message.error(result.error || '测试失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '测试失败')
    } finally {
      setTestLoading(false)
    }
  }

  const loadSamples = async (
    channel: ChannelResponse,
    nextPage: number = samplePage,
    nextPageSize: number = samplePageSize,
    nextOnlyWithLinks: boolean = sampleOnlyWithLinks
  ) => {
    setSampleLoading(true)
    try {
      const data = await getChannelSamples(channel.id, {
        page: nextPage,
        page_size: nextPageSize,
        limit: nextPageSize,
        only_with_links: nextOnlyWithLinks,
      })
      setSampleData(data)
      setSamplePage(nextPage)
      setSamplePageSize(nextPageSize)
      setSampleOnlyWithLinks(nextOnlyWithLinks)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '获取频道样本失败')
    } finally {
      setSampleLoading(false)
    }
  }

  const handleOpenSamples = async (channel: ChannelResponse) => {
    setSampleChannel(channel)
    setSampleData(null)
    setSamplePage(1)
    setSamplePageSize(10)
    setSampleOnlyWithLinks(true)
    setSampleModalVisible(true)
    await loadSamples(channel, 1, 10, true)
  }

  const handleExportSamples = () => {
    if (!sampleData) {
      return
    }

    const blob = new Blob([JSON.stringify(sampleData, null, 2)], {
      type: 'application/json;charset=utf-8',
    })
    const objectUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = `channel-samples-${sampleData.username}-page-${sampleData.page}.json`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(objectUrl)
  }

  const channelColumns: TableProps<ChannelResponse>['columns'] = [
    {
      title: '频道用户名',
      dataIndex: 'username',
      key: 'username',
      ellipsis: true,
    },
    {
      title: '频道标题',
      dataIndex: 'title',
      key: 'title',
      width: 260,
      render: (value: string | null | undefined) =>
        value ? (
          <Tooltip title={value}>
            <span className="channel-title-text">{truncateText(value, TITLE_MAX_CHARS)}</span>
          </Tooltip>
        ) : (
          <span style={{ color: '#999' }}>未解析</span>
        ),
    },
    {
      title: 'Telegram ID',
      dataIndex: 'telegram_id',
      key: 'telegram_id',
      width: 160,
      render: (value: number | null | undefined) => value ?? <span style={{ color: '#999' }}>-</span>,
    },
    {
      title: '类型',
      dataIndex: 'channel_type',
      key: 'channel_type',
      width: 130,
      render: (value: string | null | undefined) => {
        if (!value) {
          return <Tag>未知</Tag>
        }
        return <Tag color={value === 'invite_link' ? 'green' : 'blue'}>{value === 'invite_link' ? '邀请链接' : '标准频道'}</Tag>
      },
    },
    {
      title: '解析状态',
      dataIndex: 'resolution_status',
      key: 'resolution_status',
      width: 160,
      render: (value: string | null | undefined, record: ChannelResponse) => {
        if (value === 'ok') {
          return <Tag color="success">正常</Tag>
        }
        if (value === 'error') {
          return <Tag color="error">{record.resolution_error || '解析失败'}</Tag>
        }
        return <Tag>未解析</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 320,
      render: (_: unknown, record: ChannelResponse) => (
        <Space wrap>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button type="link" onClick={() => void handleOpenSamples(record)}>
            样本抓取
          </Button>
          <Popconfirm
            title="确认删除这个频道？"
            onConfirm={() => void handleDelete(record.id)}
            okText="确认"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="channel-manager">
      <div className="manager-header" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
            添加频道
          </Button>
          <Button icon={<SearchOutlined />} onClick={() => void handleDiagnose()} loading={diagnosisLoading}>
            诊断所有频道
          </Button>
          <Button icon={<ExperimentOutlined />} onClick={() => void handleTestMonitor()} loading={testLoading}>
            测试监听
          </Button>
        </Space>
      </div>

      {testResult && (
        <Alert
          message={testResult.success ? '测试成功' : '测试失败'}
          description={
            testResult.success
              ? `已测试 ${testResult.channels_tested} 个频道${testResult.message_received ? '，并检测到消息事件' : '，暂未等到新消息' }`
              : testResult.error
          }
          type={testResult.success ? 'success' : 'error'}
          closable
          onClose={() => setTestResult(null)}
          style={{ marginBottom: 16 }}
        />
      )}

      <Table
        columns={channelColumns}
        dataSource={channels}
        rowKey="id"
        loading={loading}
        tableLayout="auto"
        scroll={{ x: 'max-content' }}
        pagination={false}
      />

      <Modal
        title="添加频道"
        open={modalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setModalVisible(false)
          form.resetFields()
        }}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={(values) => void handleAdd(values)}>
          <Form.Item
            name="username"
            label="频道用户名或邀请链接"
            rules={[{ required: true, message: '请输入频道用户名或邀请链接' }]}
          >
            <Input placeholder="例如：shareAliyun 或 https://t.me/+xxxx" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              确认
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑频道"
        open={editModalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setEditModalVisible(false)
          editForm.resetFields()
          setEditingChannel(null)
        }}
        footer={null}
      >
        <Form form={editForm} layout="vertical" onFinish={(values) => void handleUpdate(values)}>
          <Form.Item
            name="username"
            label="频道用户名或邀请链接"
            rules={[{ required: true, message: '请输入频道用户名或邀请链接' }]}
          >
            <Input placeholder="例如：shareAliyun 或 https://t.me/+xxxx" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                确认
              </Button>
              <Button
                onClick={() => {
                  setEditModalVisible(false)
                  editForm.resetFields()
                  setEditingChannel(null)
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="频道诊断结果"
        open={diagnosisModalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setDiagnosisModalVisible(false)
          setDiagnosisResult(null)
        }}
        footer={null}
        width={900}
      >
        {diagnosisLoading ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}>正在诊断频道...</div>
          </div>
        ) : diagnosisResult ? (
          <div>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message={`诊断完成：有效 ${diagnosisResult.valid_channels.length} 个，无效 ${diagnosisResult.invalid_channels.length} 个`}
            />

            {diagnosisResult.valid_channels.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <Text strong>有效频道</Text>
                <Table
                  style={{ marginTop: 12 }}
                  dataSource={diagnosisResult.valid_channels}
                  rowKey="username"
                  pagination={false}
                  size="small"
                  scroll={{ x: 'max-content' }}
                  columns={[
                    { title: '频道', dataIndex: 'username', key: 'username' },
                    { title: '标题', dataIndex: 'title', key: 'title' },
                    { title: 'Telegram ID', dataIndex: 'id', key: 'id' },
                  ]}
                />
              </div>
            )}

            {diagnosisResult.invalid_channels.length > 0 && (
              <div>
                <Text strong>无效频道</Text>
                <Table
                  style={{ marginTop: 12 }}
                  dataSource={diagnosisResult.invalid_channels}
                  rowKey="username"
                  pagination={false}
                  size="small"
                  scroll={{ x: 'max-content' }}
                  columns={[
                    { title: '频道', dataIndex: 'username', key: 'username' },
                    { title: '错误', dataIndex: 'error', key: 'error' },
                  ]}
                />
              </div>
            )}
          </div>
        ) : null}
      </Modal>

      <Modal
        title={sampleChannel ? `频道样本：${sampleChannel.username}` : '频道样本'}
        open={sampleModalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setSampleModalVisible(false)
          setSampleChannel(null)
          setSampleData(null)
        }}
        footer={null}
        width={1100}
      >
        <div className="channel-sample-toolbar">
          <div className="channel-sample-toolbar-group">
            <Text strong>每页条数</Text>
            <Select
              value={samplePageSize}
              options={[10, 20, 50, 100].map((value) => ({ value, label: `${value} 条` }))}
              onChange={(value) => {
                if (sampleChannel) {
                  void loadSamples(sampleChannel, 1, value, sampleOnlyWithLinks)
                }
              }}
            />
          </div>

          <div className="channel-sample-toolbar-group">
            <Text strong>只看含链接</Text>
            <Switch
              checked={sampleOnlyWithLinks}
              onChange={(checked) => {
                if (sampleChannel) {
                  void loadSamples(sampleChannel, 1, samplePageSize, checked)
                }
              }}
            />
          </div>

          <Space wrap>
            <Button
              type="primary"
              loading={sampleLoading}
              disabled={!sampleChannel}
              onClick={() => {
                if (sampleChannel) {
                  void loadSamples(sampleChannel, samplePage, samplePageSize, sampleOnlyWithLinks)
                }
              }}
            >
              刷新样本
            </Button>
            <Button disabled={!sampleData || samplePage <= 1} onClick={() => sampleChannel && void loadSamples(sampleChannel, samplePage - 1)}>
              上一页
            </Button>
            <Button
              disabled={!sampleData?.has_more}
              onClick={() => sampleChannel && void loadSamples(sampleChannel, samplePage + 1)}
            >
              下一页
            </Button>
            <Button disabled={!sampleData} onClick={handleExportSamples}>
              导出 JSON
            </Button>
          </Space>
        </div>

        {sampleChannel && (
          <Descriptions size="small" bordered column={2} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="频道用户名">{sampleChannel.username}</Descriptions.Item>
            <Descriptions.Item label="频道标题">{sampleData?.title || sampleChannel.title || '-'}</Descriptions.Item>
            <Descriptions.Item label="Telegram ID">{sampleData?.telegram_id ?? sampleChannel.telegram_id ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="当前页">
              第 {samplePage} 页 / 每页 {samplePageSize} 条
            </Descriptions.Item>
            <Descriptions.Item label="本页样本数">{sampleData?.sample_count ?? 0}</Descriptions.Item>
            <Descriptions.Item label="本次扫描消息数">{sampleData?.inspected_count ?? 0}</Descriptions.Item>
          </Descriptions>
        )}

        {sampleLoading ? (
          <div style={{ textAlign: 'center', padding: '48px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}>正在抓取频道样本...</div>
          </div>
        ) : sampleData ? (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message={`已返回第 ${sampleData.page} 页，共 ${sampleData.sample_count} 条样本`}
              description={`本次共扫描 ${sampleData.inspected_count} 条 Telegram 消息${sampleData.has_more ? '，后面还有更多样本可继续翻页' : ''}`}
            />

            {sampleData.samples.length > 0 ? (
              <Collapse
                className="channel-sample-collapse"
                items={sampleData.samples.map((sample) => ({
                  key: String(sample.message_id),
                  label: (
                    <div className="channel-sample-summary">
                      <span>{formatTimestamp(sample.timestamp)}</span>
                      <Tag color="blue">原始 {sample.raw_urls.length}</Tag>
                      <Tag color="processing">解析 {sample.extracted_link_count}</Tag>
                      <span className="channel-sample-summary-text">{truncateText(sample.text || '(空文本)', 48)}</span>
                    </div>
                  ),
                  children: <SamplePanelBody sample={sample} />,
                }))}
              />
            ) : (
              <Empty description="没有符合条件的样本" />
            )}
          </>
        ) : (
          <Empty description="点击刷新样本开始抓取" />
        )}
      </Modal>
    </div>
  )
}

export default ChannelManagerEnhanced
