/**
 * 顶部导航栏
 */

import { useState } from 'react'
import { Button, Dropdown, Space, Modal, Form, Input, message } from 'antd'
import { LogoutOutlined, UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined, KeyOutlined } from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { logout, changePassword } from '@/api/auth'
import { ChangePasswordRequest } from '@/types/auth'
import './Header.css'

interface HeaderProps {
  collapsed: boolean
  onToggle: () => void
}

const Header = ({ collapsed, onToggle }: HeaderProps) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout: logoutStore } = useAuthStore()
  const [passwordModalVisible, setPasswordModalVisible] = useState(false)
  const [passwordForm] = Form.useForm()

  const handleLogout = async () => {
    try {
      await logout()
    } catch (error) {
      console.error('登出失败:', error)
    } finally {
      logoutStore()
      navigate('/login', { replace: true })
    }
  }

  const handleChangePassword = async (values: ChangePasswordRequest) => {
    try {
      await changePassword(values)
      message.success('密码修改成功，请使用新密码登录')
      setPasswordModalVisible(false)
      passwordForm.resetFields()
      // 修改密码后需要重新登录
      setTimeout(() => {
        handleLogout()
      }, 1500)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '密码修改失败')
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

  const handleTitleClick = () => {
    // 如果当前不在 dashboard，则跳转
    if (location.pathname !== '/dashboard') {
      navigate('/dashboard', { replace: false })
    }
  }

  return (
    <div className="app-header">
      <div className="header-left">
        <Button
          type="text"
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={onToggle}
        />
        <h1 className="header-title clickable" onClick={handleTitleClick}>
          📱 TG频道监控
        </h1>
      </div>
      <div className="header-right">
        <Space>
          <Dropdown menu={{ items: menuItems }} placement="bottomRight">
            <Button type="text" icon={<UserOutlined />}>
              <span className="user-name-text">{user?.name || user?.username}</span>
            </Button>
          </Dropdown>
        </Space>
      </div>

      {/* 修改密码 Modal */}
      <Modal
        title="修改密码"
        open={passwordModalVisible}
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
    </div>
  )
}

export default Header

