/**
 * 频道管理组件
 */

import { useState, useEffect } from 'react'
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  message,
  Popconfirm,
  Space,
  Tag,
  Alert,
  Spin,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SearchOutlined,
  ExperimentOutlined,
} from '@ant-design/icons'
import {
  getChannels,
  createChannel,
  updateChannel,
  deleteChannel,
  diagnoseChannels,
  testMonitor,
} from '@/api/admin'
import {
  ChannelResponse,
  ChannelCreate,
  ChannelDiagnosisResult,
  MonitorTestResult,
} from '@/types/admin'

const ChannelManager = () => {
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
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()

  // 加载频道列表
  const loadChannels = async () => {
    setLoading(true)
    try {
      const data = await getChannels()
      setChannels(data)
    } catch (error) {
      message.error('加载频道列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadChannels()
  }, [])

  // 添加频道
  const handleAdd = async (values: ChannelCreate) => {
    try {
      await createChannel(values)
      message.success('添加成功')
      setModalVisible(false)
      form.resetFields()
      loadChannels()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '添加失败')
    }
  }

  // 编辑频道
  const handleEdit = (channel: ChannelResponse) => {
    setEditingChannel(channel)
    editForm.setFieldsValue({ username: channel.username })
    setEditModalVisible(true)
  }

  const handleUpdate = async (values: ChannelCreate) => {
    if (!editingChannel) return

    try {
      await updateChannel(editingChannel.id, values)
      message.success('编辑成功')
      setEditModalVisible(false)
      editForm.resetFields()
      setEditingChannel(null)
      loadChannels()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '编辑失败')
    }
  }

  // 删除频道
  const handleDelete = async (id: number) => {
    try {
      await deleteChannel(id)
      message.success('删除成功')
      loadChannels()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败')
    }
  }

  // 诊断频道
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

  // 测试监控
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

  const columns = [
    {
      title: '频道用户名',
      dataIndex: 'username',
      key: 'username',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: ChannelResponse) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个频道吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
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
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModalVisible(true)}
          >
            添加频道
          </Button>
          <Button
            icon={<SearchOutlined />}
            onClick={handleDiagnose}
            loading={diagnosisLoading}
          >
            诊断所有频道
          </Button>
          <Button
            icon={<ExperimentOutlined />}
            onClick={handleTestMonitor}
            loading={testLoading}
          >
            测试监控
          </Button>
        </Space>
      </div>

      {testResult && (
        <Alert
          message={testResult.success ? '测试成功' : '测试失败'}
          description={
            testResult.success
              ? `已测试 ${testResult.channels_tested} 个频道，事件处理器已注册${testResult.message_received ? '，已收到消息' : ''}`
              : testResult.error
          }
          type={testResult.success ? 'success' : 'error'}
          closable
          onClose={() => setTestResult(null)}
          style={{ marginBottom: 16 }}
        />
      )}

      <Table
        columns={columns}
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
        onCancel={() => {
          setModalVisible(false)
          form.resetFields()
        }}
        footer={null}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleAdd}
        >
          <Form.Item
            name="username"
            label="频道用户名（不加@）"
            rules={[{ required: true, message: '请输入频道用户名' }]}
          >
            <Input placeholder="请输入频道用户名" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              确定
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑频道Modal */}
      <Modal
        title="编辑频道"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false)
          editForm.resetFields()
          setEditingChannel(null)
        }}
        footer={null}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleUpdate}
        >
          <Form.Item
            name="username"
            label="频道用户名（不加@）"
            rules={[{ required: true, message: '请输入频道用户名' }]}
          >
            <Input placeholder="请输入频道用户名" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                确定
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

      {/* 诊断结果Modal */}
      <Modal
        title="频道诊断结果"
        open={diagnosisModalVisible}
        onCancel={() => {
          setDiagnosisModalVisible(false)
          setDiagnosisResult(null)
        }}
        footer={null}
        width={800}
      >
        {diagnosisLoading ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}>正在诊断频道...</div>
          </div>
        ) : diagnosisResult ? (
          <div>
            <Alert
              message={`诊断完成：有效 ${diagnosisResult.valid_channels.length} 个，无效 ${diagnosisResult.invalid_channels.length} 个`}
              type="info"
              style={{ marginBottom: 16 }}
            />

            {diagnosisResult.valid_channels.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <h4>✅ 有效频道 ({diagnosisResult.valid_channels.length}个)</h4>
                <Table
                  dataSource={diagnosisResult.valid_channels}
                  rowKey="username"
                  pagination={false}
                  size="small"
                  columns={[
                    {
                      title: '频道名',
                      dataIndex: 'username',
                      key: 'username',
                    },
                    {
                      title: '标题',
                      dataIndex: 'title',
                      key: 'title',
                    },
                    {
                      title: '类型',
                      dataIndex: 'type',
                      key: 'type',
                      render: (type: string) => (
                        <Tag color={type === 'standard' ? 'blue' : 'green'}>
                          {type === 'standard' ? '标准频道' : '邀请链接'}
                        </Tag>
                      ),
                    },
                    {
                      title: 'ID',
                      dataIndex: 'id',
                      key: 'id',
                    },
                    {
                      title: '参与者',
                      dataIndex: 'participants_count',
                      key: 'participants_count',
                      render: (count: number) => count || '未知',
                    },
                  ]}
                />
              </div>
            )}

            {diagnosisResult.invalid_channels.length > 0 && (
              <div>
                <h4>❌ 无效频道 ({diagnosisResult.invalid_channels.length}个)</h4>
                <Table
                  dataSource={diagnosisResult.invalid_channels}
                  rowKey="username"
                  pagination={false}
                  size="small"
                  columns={[
                    {
                      title: '频道名',
                      dataIndex: 'username',
                      key: 'username',
                    },
                    {
                      title: '错误信息',
                      dataIndex: 'error',
                      key: 'error',
                      ellipsis: true,
                    },
                  ]}
                />
              </div>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

export default ChannelManager

