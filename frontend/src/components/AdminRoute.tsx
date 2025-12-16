/**
 * 管理员路由守卫组件
 * 只有 admin 角色才能访问
 */

import { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '@/store/authStore'

interface AdminRouteProps {
  children: ReactNode
}

export const AdminRoute = ({ children }: AdminRouteProps) => {
  const { isAuthenticated, token, user, _hasHydrated } = useAuthStore()

  // 等待 Zustand persist 从 localStorage 恢复状态
  if (!_hasHydrated) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  // 未登录，跳转到登录页
  if (!isAuthenticated || !token) {
    return <Navigate to="/login" replace />
  }

  // 已登录但不是 admin，跳转到首页
  if (user?.role !== 'admin') {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}

export default AdminRoute

