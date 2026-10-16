/**
 * 消息列表页面（主页面）
 */

import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import MessageList from '@/components/messages/MessageList'
import { useAuthStore } from '@/store/authStore'
import { useMessageStore } from '@/store/messageStore'
import { Spin } from 'antd'
import './Dashboard.css'

const Dashboard = () => {
  const { isAuthenticated, _hasHydrated } = useAuthStore()
  const [searchParams] = useSearchParams()
  const setFilters = useMessageStore((state) => state.setFilters)

  useEffect(() => {
    const search = searchParams.get('search')
    if (search !== null) {
      setFilters({ search_query: search })
    }
  }, [searchParams, setFilters])
  
  // 等待 Zustand persist 从 localStorage 恢复状态
  if (!_hasHydrated) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }
  
  // 只有在状态恢复后，才能准确判断是否为游客模式
  const isGuestMode = !isAuthenticated

  return (
    <div className={`dashboard-page ${isGuestMode ? 'guest-mode' : ''}`}>
      <div className="dashboard-content">
        <div className="messages-area">
          <MessageList isGuestMode={isGuestMode} />
        </div>
      </div>
    </div>
  )
}

export default Dashboard

