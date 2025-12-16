/**
 * 用户管理组件
 */

import { useState, useEffect } from 'react'
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  message,
  Popconfirm,
  Space,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined } from '@ant-design/icons'
import {
  getUsers,
  createUser,
  updateUser,
  deleteUser,
  changeUserPassword,
  changeUserRole,
  getAvailableRoles,
  bulkRandomCreateUsers,
  bulkDeleteUsers,
  bulkResetPasswords,
  exportUsers,
} from '@/api/admin'
import {
  UserResponse,
  UserCreate,
  UserUpdate,
  PasswordChange,
  BulkCreateResponse,
  BulkResetResponse,
} from '@/types/admin'

const UserManager = () => {
  const [users, setUsers] = useState<UserResponse[]>([])
  const [roles, setRoles] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [passwordModalVisible, setPasswordModalVisible] = useState(false)
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null)
  const [bulkCreateVisible, setBulkCreateVisible] = useState(false)
  const [bulkResult, setBulkResult] = useState<BulkCreateResponse | null>(null)
  const [resetResult, setResetResult] = useState<BulkResetResponse | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [form] = Form.useForm()
  const [passwordForm] = Form.useForm()
  const [bulkForm] = Form.useForm()

  useEffect(() => {
    loadUsers()
    loadRoles()
  }, [])

  const loadUsers = async () => {
    setLoading(true)
    try {
      const data = await getUsers()
      setUsers(data)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  const loadRoles = async () => {
    try {
      const data = await getAvailableRoles()
      setRoles(data)
    } catch (error: any) {
      console.error('加载角色列表失败:', error)
    }
  }

  const handleAdd = () => {
    setEditingUser(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (user: UserResponse) => {
    setEditingUser(user)
    form.setFieldsValue({
      name: user.name,
      email: user.email,
      role: user.role,
    })
    setModalVisible(true)
  }

  const handleSave = async (values: UserCreate | UserUpdate) => {
    try {
      if (editingUser) {
        // 更新用户
        await updateUser(editingUser.username, values as UserUpdate)
        message.success('用户信息更新成功')
      } else {
        // 创建用户
        await createUser(values as UserCreate)
        message.success('用户创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      loadUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '操作失败')
    }
  }

  const handleDelete = async (username: string) => {
    try {
      await deleteUser(username)
      message.success('用户删除成功')
      loadUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败')
    }
  }

  const handleChangePassword = (user: UserResponse) => {
    setEditingUser(user)
    passwordForm.resetFields()
    setPasswordModalVisible(true)
  }

  const handleSavePassword = async (values: PasswordChange) => {
    if (!editingUser) return

    try {
      await changeUserPassword(editingUser.username, values)
      message.success('密码修改成功')
      setPasswordModalVisible(false)
      passwordForm.resetFields()
      setEditingUser(null)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '修改密码失败')
    }
  }

  const handleChangeRole = async (username: string, newRole: string) => {
    try {
      await changeUserRole(username, { new_role: newRole })
      message.success('角色修改成功')
      loadUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '修改角色失败')
    }
  }

  const handleBulkCreate = () => {
    bulkForm.setFieldsValue({
      count: 5,
      prefix: 'user',
      start_index: 1,
      role: 'user',
      password_length: 10,
    })
    setBulkResult(null)
    setBulkCreateVisible(true)
  }

  const submitBulkCreate = async (values: any) => {
    try {
      const data = await bulkRandomCreateUsers(values)
      setBulkResult(data)
      message.success(`创建完成：成功 ${data.successes.length}，失败 ${data.failures.length}`)
      loadUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '批量创建失败')
    }
  }

  const handleBulkDelete = async () => {
    if (selectedRowKeys.length === 0) {
      message.info('请先选择要删除的用户')
      return
    }
    Modal.confirm({
      title: '确认批量删除',
      content: '将删除选中的用户（admin 不会被删除），是否继续？',
      okText: '确定',
      cancelText: '取消',
      async onOk() {
        try {
          const res = await bulkDeleteUsers({ usernames: selectedRowKeys as string[] })
          message.success(`删除完成：成功 ${res.successes.length}，失败 ${res.failures.length}`)
          setSelectedRowKeys([])
          loadUsers()
        } catch (error: any) {
          message.error(error.response?.data?.detail || '批量删除失败')
        }
      },
    })
  }

  const handleBulkReset = async () => {
    if (selectedRowKeys.length === 0) {
      message.info('请先选择要重置密码的用户')
      return
    }
    Modal.confirm({
      title: '确认批量重置密码',
      content: '将为选中的用户生成新密码（admin 不会被重置），是否继续？',
      okText: '确定',
      cancelText: '取消',
      async onOk() {
        try {
          const res = await bulkResetPasswords({ usernames: selectedRowKeys as string[] })
          setResetResult(res)
          message.success(`重置完成：成功 ${res.successes.length}，失败 ${res.failures.length}`)
        } catch (error: any) {
          message.error(error.response?.data?.detail || '批量重置密码失败')
        }
      },
    })
  }

  const handleExport = async () => {
    try {
      const data = await exportUsers()
      if (!data || data.length === 0) {
        message.info('暂无可导出的用户')
        return
      }
      const headers = ['username', 'name', 'email', 'role']
      const csv = [
        headers.join(','),
        ...data.map((u) =>
          headers
            .map((h) => {
              const val = (u as any)[h] ?? ''
              const safe = String(val).replace(/"/g, '""')
              return `"${safe}"`
            })
            .join(',')
        ),
      ].join('\n')
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'users.csv'
      link.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '导出失败')
    }
  }

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      ellipsis: true,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      ellipsis: true,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string, record: UserResponse) => (
        <Select
          value={role}
          style={{ width: '100%', minWidth: 120 }}
          onChange={(newRole) => handleChangeRole(record.username, newRole)}
        >
          {Object.entries(roles).map(([key, label]) => (
            <Select.Option key={key} value={key}>
              {label}
            </Select.Option>
          ))}
        </Select>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: UserResponse) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            icon={<KeyOutlined />}
            onClick={() => handleChangePassword(record)}
          >
            改密
          </Button>
          {record.username !== 'admin' && (
            <Popconfirm
              title="确定要删除这个用户吗？"
              onConfirm={() => handleDelete(record.username)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="user-manager">
      <div className="manager-header" style={{ marginBottom: 16, gap: 8, flexWrap: 'wrap' }}>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            添加用户
          </Button>
          <Button onClick={handleBulkCreate}>批量创建</Button>
          <Button onClick={handleBulkReset}>批量重置密码</Button>
          <Button danger onClick={handleBulkDelete}>
            批量删除
          </Button>
          <Button onClick={handleExport}>导出</Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={users}
        rowKey="username"
        loading={loading}
        tableLayout="auto"
        scroll={{ x: 'max-content' }}
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys,
        }}
        pagination={false}
      />

      {/* 添加/编辑用户Modal */}
      <Modal
        title={editingUser ? '编辑用户' : '添加用户'}
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
          onFinish={handleSave}
        >
          {!editingUser && (
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input placeholder="请输入用户名" />
            </Form.Item>
          )}

          {!editingUser && (
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password placeholder="请输入密码" />
            </Form.Item>
          )}

          <Form.Item
            name="name"
            label="姓名"
          >
            <Input placeholder="请输入姓名" />
          </Form.Item>

          <Form.Item
            name="email"
            label="邮箱"
          >
            <Input placeholder="请输入邮箱" />
          </Form.Item>

          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select placeholder="请选择角色">
              {Object.entries(roles).map(([key, label]) => (
                <Select.Option key={key} value={key}>
                  {label}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                确定
              </Button>
              <Button
                onClick={() => {
                  setModalVisible(false)
                  form.resetFields()
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 修改密码Modal */}
      <Modal
        title="修改密码"
        open={passwordModalVisible}
        onCancel={() => {
          setPasswordModalVisible(false)
          passwordForm.resetFields()
          setEditingUser(null)
        }}
        footer={null}
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleSavePassword}
        >
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[{ required: true, message: '请输入新密码' }]}
          >
            <Input.Password placeholder="请输入新密码" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                确定
              </Button>
              <Button
                onClick={() => {
                  setPasswordModalVisible(false)
                  passwordForm.resetFields()
                  setEditingUser(null)
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 批量创建 Modal */}
      <Modal
        title="批量随机创建用户"
        open={bulkCreateVisible}
        onCancel={() => {
          setBulkCreateVisible(false)
        }}
        footer={null}
      >
        <Form form={bulkForm} layout="vertical" onFinish={submitBulkCreate}>
          <Form.Item name="count" label="数量" rules={[{ required: true, message: '请输入数量' }]}>
            <Input type="number" min={1} max={500} />
          </Form.Item>
          <Form.Item name="prefix" label="前缀">
            <Input placeholder="user" />
          </Form.Item>
          <Form.Item name="start_index" label="起始序号">
            <Input type="number" min={1} />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select>
              {Object.entries(roles).map(([key, label]) => (
                <Select.Option key={key} value={key}>
                  {label}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="password_length" label="密码长度">
            <Input type="number" min={6} max={32} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                开始创建
              </Button>
              <Button onClick={() => setBulkCreateVisible(false)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>

        {bulkResult && (
          <div style={{ marginTop: 16 }}>
            <div>成功：{bulkResult.successes.length}，失败：{bulkResult.failures.length}</div>
            {bulkResult.successes.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong>成功列表（仅本次可见）：</strong>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {bulkResult.successes.map((item) => `${item.username}, 密码: ${item.password}`).join('\n')}
                </pre>
              </div>
            )}
            {bulkResult.failures.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong>失败原因：</strong>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {bulkResult.failures.map((item) => `${item.username || ''} ${item.reason}`).join('\n')}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* 批量重置结果 */}
      <Modal
        title="批量重置密码结果"
        open={!!resetResult}
        onCancel={() => setResetResult(null)}
        footer={[
          <Button key="ok" type="primary" onClick={() => setResetResult(null)}>
            确定
          </Button>,
        ]}
      >
        {resetResult && (
          <div>
            <div>成功：{resetResult.successes.length}，失败：{resetResult.failures.length}</div>
            {resetResult.successes.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong>成功列表（仅本次可见）：</strong>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {resetResult.successes.map((item) => `${item.username}, 新密码: ${item.password}`).join('\n')}
                </pre>
              </div>
            )}
            {resetResult.failures.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong>失败原因：</strong>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {resetResult.failures.map((item) => `${item.username || ''} ${item.reason}`).join('\n')}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

export default UserManager

