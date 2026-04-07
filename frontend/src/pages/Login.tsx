import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Form, Input, message } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'

import { login } from '@/api/auth'
import TurnstileWidget from '@/components/security/TurnstileWidget'
import { useAuthStore } from '@/store/authStore'
import { formatBrandTitle, hasCachedSiteBranding, useSiteBranding } from '@/utils/siteBranding'
import { usePublicSecurityConfig } from '@/utils/securityConfig'

import './Login.css'

const Login = () => {
  const navigate = useNavigate()
  const { setToken, setUser } = useAuthStore()
  const siteBranding = useSiteBranding()
  const securityConfig = usePublicSecurityConfig()
  const [loading, setLoading] = useState(false)
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileResetKey, setTurnstileResetKey] = useState(0)
  const loginChallengeEnabled =
    securityConfig.loaded && securityConfig.turnstile_ready && securityConfig.login_challenge_enabled
  const submitDisabled = !securityConfig.loaded || (loginChallengeEnabled && !turnstileToken)
  const hasBrandingSnapshot = hasCachedSiteBranding() || siteBranding.site_name !== 'TG频道监控'

  const onFinish = async (values: { username: string; password: string }) => {
    if (loginChallengeEnabled && !turnstileToken) {
      message.error('请先完成人机验证')
      return
    }

    setLoading(true)
    try {
      const response = await login({
        ...values,
        turnstile_token: turnstileToken || undefined,
      })
      setToken(response.access_token)
      setUser(response.user)
      message.success('登录成功')
      navigate('/dashboard', { replace: true })
    } catch (error: any) {
      setTurnstileToken('')
      setTurnstileResetKey((current) => current + 1)
      message.error(error.response?.data?.detail || '登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-shell">
      <div className="login-container">
        <Card
          className="login-card"
          title={
            hasBrandingSnapshot ? (
              formatBrandTitle(siteBranding)
            ) : (
              <span className="login-card-title-placeholder" aria-hidden="true" />
            )
          }
          variant="borderless"
        >
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

            {loginChallengeEnabled ? (
              <div className="login-turnstile-slot">
                <TurnstileWidget
                  key={turnstileResetKey}
                  siteKey={securityConfig.turnstile_site_key}
                  action="login"
                  onVerify={(token) => setTurnstileToken(token)}
                  onExpire={() => setTurnstileToken('')}
                  onError={() => setTurnstileToken('')}
                />
              </div>
            ) : null}

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block disabled={submitDisabled}>
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
