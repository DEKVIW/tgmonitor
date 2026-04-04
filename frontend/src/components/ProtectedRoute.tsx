/**
 * 受保护的路由组件
 */

import { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '@/store/authStore'
import { LOGIN_PATH } from '@/utils/routes'

interface ProtectedRouteProps {
  children: ReactNode
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()

  // 等待 Zustand persist 从 localStorage 恢复状态
  if (!_hasHydrated) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!isAuthenticated || !token) {
    return <Navigate to={LOGIN_PATH} replace />
  }

  return <>{children}</>
}

export default ProtectedRoute
