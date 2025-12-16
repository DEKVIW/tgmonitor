/**
 * 消息列表页面（主页面）
 */

import MessageFilters from '@/components/messages/MessageFilters'
import MessageList from '@/components/messages/MessageList'
import { useAuthStore } from '@/store/authStore'
import { Spin } from 'antd'
import './Dashboard.css'

const Dashboard = () => {
  const { isAuthenticated, _hasHydrated } = useAuthStore()
  
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
        {!isGuestMode && (
          <div className="filters-bar">
            <MessageFilters disabled={false} />
          </div>
        )}
        <div className="messages-area">
          <MessageList isGuestMode={isGuestMode} />
        </div>
      </div>
    </div>
  )
}

export default Dashboard

