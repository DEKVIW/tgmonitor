/**
 * 认证相关Hooks
 */

import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { getCurrentUser } from '@/api/auth'

/**
 * 检查认证状态并获取用户信息
 */
export const useAuth = () => {
  const { token, user, setUser, isAuthenticated } = useAuthStore()

  useEffect(() => {
    // 如果有token但没有用户信息，尝试获取用户信息
    if (token && !user) {
      getCurrentUser()
        .then((userInfo) => {
          setUser(userInfo)
        })
        .catch((error) => {
          console.error('获取用户信息失败:', error)
          // Token可能已过期，清除token
          useAuthStore.getState().logout()
        })
    }
  }, [token, user, setUser])

  return {
    token,
    user,
    isAuthenticated: isAuthenticated && !!token,
  }
}

/**
 * 路由守卫Hook
 */
export const useRequireAuth = () => {
  const { isAuthenticated, token } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (!isAuthenticated || !token) {
      navigate('/login', { replace: true })
    }
  }, [isAuthenticated, token, navigate])

  return { isAuthenticated: isAuthenticated && !!token }
}

