/**
 * 顶部导航栏
 */

import { Button, Tooltip } from 'antd'
import { MenuFoldOutlined, MenuUnfoldOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import GlobalSearch from './GlobalSearch'
import SiteBrand from './SiteBrand'
import UserAccountMenu from './UserAccountMenu'
import { useAuthStore } from '@/store/authStore'
import { LOGIN_PATH } from '@/utils/routes'
import './Header.css'

interface HeaderProps {
  collapsed: boolean
  onToggle: () => void
}

const Header = ({ collapsed, onToggle }: HeaderProps) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated, token } = useAuthStore()
  const isGuest = !isAuthenticated || !token
  const handleTitleClick = () => {
    const homePath = isGuest ? '/' : '/dashboard'
    if (location.pathname !== homePath) {
      navigate(homePath, { replace: false })
    }
  }

  return (
    <div className="app-header">
      <div className="header-left">
        <Button
          type="text"
          className="header-toggle-button"
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          aria-expanded={!collapsed}
          onClick={onToggle}
        />
        <SiteBrand className="header-site-brand" onClick={handleTitleClick} />
      </div>
      <div className="header-right">
        <GlobalSearch />
        {isGuest ? (
          <Tooltip title="登录" placement="bottomRight">
            <Button
              type="text"
              icon={<UserOutlined />}
              className="guest-login-button"
              aria-label="登录"
              onClick={() => navigate(LOGIN_PATH)}
            />
          </Tooltip>
        ) : (
          <UserAccountMenu variant="header" />
        )}
      </div>
    </div>
  )
}

export default Header

