/**
 * API凭据管理组件
 */

import { useState, useEffect } from 'react'
import { Table, Button, Modal, Form, Input, message, Popconfirm, Space } from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { getCredentials, createCredential, deleteCredential } from '@/api/admin'
import { CredentialResponse, CredentialCreate } from '@/types/admin'

const CredentialManager = () => {
  const [credentials, setCredentials] = useState<CredentialResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  // 加载凭据列表
  const loadCredentials = async () => {
    setLoading(true)
    try {
      const data = await getCredentials()
      setCredentials(data)
    } catch (error) {
      message.error('加载API凭据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCredentials()
  }, [])

  // 添加凭据
  const handleAdd = async (values: CredentialCreate) => {
    try {
      await createCredential(values)
      message.success('添加成功')
      setModalVisible(false)
      form.resetFields()
      loadCredentials()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '添加失败')
    }
  }

  // 删除凭据
  const handleDelete = async (id: number) => {
    try {
      await deleteCredential(id)
      message.success('删除成功')
      loadCredentials()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败')
    }
  }

  const columns = [
    {
      title: 'API ID',
      dataIndex: 'api_id',
      key: 'api_id',
      ellipsis: true,
    },
    {
      title: 'API Hash',
      dataIndex: 'api_hash',
      key: 'api_hash',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: CredentialResponse) => (
        <Popconfirm
          title="确定要删除这个API凭据吗？"
          onConfirm={() => handleDelete(record.id)}
          okText="确定"
          cancelText="取消"
        >
          <Button type="link" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="credential-manager">
      <div className="manager-header">
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalVisible(true)}
        >
          添加API凭据
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={credentials}
        rowKey="id"
        loading={loading}
        tableLayout="auto"
        scroll={{ x: 'max-content' }}
        pagination={false}
      />

      <Modal
        title="添加API凭据"
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
            name="api_id"
            label="API ID"
            rules={[{ required: true, message: '请输入API ID' }]}
          >
            <Input placeholder="请输入API ID" />
          </Form.Item>

          <Form.Item
            name="api_hash"
            label="API Hash"
            rules={[{ required: true, message: '请输入API Hash' }]}
          >
            <Input placeholder="请输入API Hash" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                确定
              </Button>
              <Button onClick={() => {
                setModalVisible(false)
                form.resetFields()
              }}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default CredentialManager

