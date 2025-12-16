/**
 * 认证状态管理（Zustand）
 */

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { UserInfo } from '@/types/auth'
import { TOKEN_KEY } from '@/utils/constants'

interface AuthState {
  token: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  _hasHydrated: boolean
  setToken: (token: string) => void
  setUser: (user: UserInfo) => void
  logout: () => void
  setHasHydrated: (state: boolean) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      _hasHydrated: false,
      
      setToken: (token: string) => {
        localStorage.setItem(TOKEN_KEY, token)
        set({ token, isAuthenticated: true })
      },
      
      setUser: (user: UserInfo) => {
        set({ user })
      },
      
      logout: () => {
        localStorage.removeItem(TOKEN_KEY)
        set({ token: null, user: null, isAuthenticated: false })
      },
      
      setHasHydrated: (state: boolean) => {
        set({ _hasHydrated: state })
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        // 当状态从 localStorage 恢复后，设置 hydration 完成标志
        // 同时确保 isAuthenticated 与 token 保持一致
        if (state) {
          // 如果 token 存在，确保 isAuthenticated 为 true
          if (state.token && !state.isAuthenticated) {
            state.isAuthenticated = true
          }
          // 如果 token 不存在，确保 isAuthenticated 为 false
          if (!state.token && state.isAuthenticated) {
            state.isAuthenticated = false
          }
          state.setHasHydrated(true)
        }
      },
    }
  )
)

