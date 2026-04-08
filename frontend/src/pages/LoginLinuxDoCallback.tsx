import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Card, Spin, message } from 'antd'

import { exchangeLinuxDoLogin } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { LOGIN_LINUXDO_CALLBACK_PATH, LOGIN_PATH } from '@/utils/routes'

import './Login.css'

const buildRedirectUri = () => `${window.location.origin}${LOGIN_LINUXDO_CALLBACK_PATH}`

const LoginLinuxDoCallback = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const startedRef = useRef(false)
  const { setToken, setUser } = useAuthStore()

  useEffect(() => {
    if (startedRef.current) {
      return
    }
    startedRef.current = true

    const params = new URLSearchParams(location.search)
    const error = params.get('error')
    const code = params.get('code')
    const state = params.get('state')

    if (error) {
      message.error(`LinuxDo 登录已取消或失败：${error}`)
      navigate(LOGIN_PATH, { replace: true })
      return
    }

    if (!code || !state) {
      message.error('缺少 LinuxDo 登录回调参数')
      navigate(LOGIN_PATH, { replace: true })
      return
    }

    void exchangeLinuxDoLogin({
      code,
      state,
      redirect_uri: buildRedirectUri(),
    })
      .then((response) => {
        setToken(response.access_token)
        setUser(response.user)
        message.success('LinuxDo 登录成功')
        navigate('/dashboard', { replace: true })
      })
      .catch((errorResponse: any) => {
        message.error(errorResponse.response?.data?.detail || 'LinuxDo 登录失败')
        navigate(LOGIN_PATH, { replace: true })
      })
  }, [location.search, navigate, setToken, setUser])

  return (
    <div className="login-shell">
      <div className="login-container">
        <Card className="login-card" title="正在完成 LinuxDo 登录" variant="borderless">
          <div className="login-callback-state">
            <Spin size="large" />
            <p>正在验证授权结果并建立会话，请稍候。</p>
          </div>
        </Card>
      </div>
    </div>
  )
}

export default LoginLinuxDoCallback
