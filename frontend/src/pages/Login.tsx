import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'

import { login } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { formatBrandTitle, useSiteBranding } from '@/utils/siteBranding'

import './Login.css'

const Login = () => {
  const navigate = useNavigate()
  const { setToken, setUser } = useAuthStore()
  const siteBranding = useSiteBranding()
  const [loading, setLoading] = useState(false)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const response = await login(values)
      setToken(response.access_token)
      setUser(response.user)
      message.success('登录成功')
      navigate('/dashboard', { replace: true })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-shell">
      <div className="login-container">
        <Card className="login-card" title={formatBrandTitle(siteBranding)} variant="borderless">
          <Form name="login" onFinish={onFinish} autoComplete="off" size="large">
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                登录
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    </div>
  )
}

export default Login
