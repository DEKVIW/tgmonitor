import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'

import { login } from '@/api/auth'
import SiteFooter from '@/components/layout/SiteFooter'
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
      message.success('\u767b\u5f55\u6210\u529f')
      navigate('/dashboard', { replace: true })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u7528\u6237\u540d\u548c\u5bc6\u7801')
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
              rules={[{ required: true, message: '\u8bf7\u8f93\u5165\u7528\u6237\u540d' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="\u7528\u6237\u540d" />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '\u8bf7\u8f93\u5165\u5bc6\u7801' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="\u5bc6\u7801" />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                {'\u767b\u5f55'}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
      <SiteFooter />
    </div>
  )
}

export default Login
