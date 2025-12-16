/**
 * 游客路由组件
 * 根据系统配置决定是否允许游客访问
 * 如果用户已登录，重定向到 /dashboard
 */

import { ReactNode, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import { getPublicConfig } from '@/api/admin'
import { useAuthStore } from '@/store/authStore'
import GuestLayout from './layout/GuestLayout'

interface GuestRouteProps {
  children: ReactNode
}

const GuestRoute = ({ children }: GuestRouteProps) => {
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [publicDashboardEnabled, setPublicDashboardEnabled] = useState(false)

  useEffect(() => {
    const checkConfig = async () => {
      try {
        const config = await getPublicConfig()
        setPublicDashboardEnabled(config.public_dashboard_enabled)
      } catch (error) {
        console.error('获取系统配置失败:', error)
        // 如果获取失败，默认不允许游客访问
        setPublicDashboardEnabled(false)
      } finally {
        setLoading(false)
      }
    }

    checkConfig()
  }, [])

  // 等待 Zustand 状态恢复
  if (!_hasHydrated || loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  // 如果用户已登录，重定向到 /dashboard
  if (isAuthenticated && token) {
    return <Navigate to="/dashboard" replace />
  }

  // 如果游客模式未启用，重定向到登录页
  if (!publicDashboardEnabled) {
    return <Navigate to="/login" replace />
  }

  // 游客模式：未登录且游客模式已启用
  return <GuestLayout>{children}</GuestLayout>
}

export default GuestRoute

