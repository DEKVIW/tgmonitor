/**
 * 用户账户菜单
 */

import { useState } from 'react'
import { Button, Dropdown, Form, Input, Modal, Space, message } from 'antd'
import { EditOutlined, KeyOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { changePassword, changeUsername, logout } from '@/api/auth'
import { ChangePasswordRequest, ChangeUsernameRequest } from '@/types/auth'
import { LOGIN_PATH } from '@/utils/routes'

interface UserAccountMenuProps {
  variant?: 'header' | 'sidebar'
  collapsed?: boolean
}

const UserAccountMenu = ({
  variant = 'header',
  collapsed = false,
}: UserAccountMenuProps) => {
  const navigate = useNavigate()
  const { user, logout: logoutStore, setUser } = useAuthStore()
  const [usernameModalVisible, setUsernameModalVisible] = useState(false)
  const [passwordModalVisible, setPasswordModalVisible] = useState(false)
  const [usernameForm] = Form.useForm()
  const [passwordForm] = Form.useForm()

  const handleLogout = async () => {
    try {
      await logout()
    } catch (error) {
      console.error('登出失败:', error)
    } finally {
      logoutStore()
      navigate(LOGIN_PATH, { replace: true })
    }
  }

  const handleChangePassword = async (values: ChangePasswordRequest) => {
    try {
      await changePassword(values)
      message.success('密码修改成功，请使用新密码登录')
      setPasswordModalVisible(false)
      passwordForm.resetFields()
      window.setTimeout(() => {
        handleLogout()
      }, 1500)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '密码修改失败')
    }
  }

  const handleChangeUsername = async (values: ChangeUsernameRequest) => {
    try {
      await changeUsername(values)
      setUser({
        username: values.new_username,
        name: user?.name || values.new_username,
        email: user?.email,
        role: user?.role || 'user',
      })
      message.success('用户名修改成功')
      setUsernameModalVisible(false)
      usernameForm.resetFields()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '用户名修改失败')
    }
  }

  const menuItems: MenuProps['items'] = [
    {
      key: 'user',
      label: (
        <div className="user-info">
          <div className="user-name">{user?.name || user?.username}</div>
          <div className="user-email">{user?.email || ''}</div>
        </div>
      ),
      disabled: true,
    },
    {
      type: 'divider',
    },
    {
      key: 'change-username',
      label: '修改用户名',
      icon: <EditOutlined />,
      onClick: () => {
        usernameForm.setFieldsValue({ new_username: user?.username || '' })
        setUsernameModalVisible(true)
      },
    },
    {
      type: 'divider',
    },
    {
      key: 'change-password',
      label: '修改密码',
      icon: <KeyOutlined />,
      onClick: () => setPasswordModalVisible(true),
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      label: '登出',
      icon: <LogoutOutlined />,
      danger: true,
      onClick: handleLogout,
    },
  ]

  const buttonClassName =
    variant === 'sidebar'
      ? `sidebar-account-button ${collapsed ? 'is-collapsed' : 'is-expanded'}`
      : 'header-account-button'

  return (
    <>
      <Dropdown
        menu={{ items: menuItems }}
        placement={variant === 'sidebar' ? 'topRight' : 'bottomRight'}
      >
        <Button
          type="text"
          className={buttonClassName}
          icon={<UserOutlined />}
        >
          {variant === 'header' ? (
            <span className="user-name-text">{user?.name || user?.username}</span>
          ) : !collapsed ? (
            <span className="sidebar-account-text">{user?.name || user?.username}</span>
          ) : null}
        </Button>
      </Dropdown>

      <Modal
        title="修改用户名"
        open={usernameModalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setUsernameModalVisible(false)
          usernameForm.resetFields()
        }}
        footer={null}
      >
        <Form
          form={usernameForm}
          layout="vertical"
          onFinish={handleChangeUsername}
        >
          <Form.Item
            name="new_username"
            label="新用户名"
            rules={[
              { required: true, message: '请输入新用户名' },
              { pattern: /^\S+$/, message: '用户名不能包含空格' },
            ]}
          >
            <Input placeholder="请输入新用户名" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                确定
              </Button>
              <Button
                onClick={() => {
                  setUsernameModalVisible(false)
                  usernameForm.resetFields()
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="修改密码"
        open={passwordModalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setPasswordModalVisible(false)
          passwordForm.resetFields()
        }}
        footer={null}
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleChangePassword}
        >
          <Form.Item
            name="old_password"
            label="旧密码"
            rules={[{ required: true, message: '请输入旧密码' }]}
          >
            <Input.Password placeholder="请输入旧密码" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码长度至少6位' },
            ]}
          >
            <Input.Password placeholder="请输入新密码" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请确认新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password placeholder="请再次输入新密码" />
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
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default UserAccountMenu
