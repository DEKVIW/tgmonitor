/**
 * 顶部导航栏
 */

import { Button } from 'antd'
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import GlobalSearch from './GlobalSearch'
import PublicNavigation from './PublicNavigation'
import UserAccountMenu from './UserAccountMenu'
import { formatBrandTitle, useSiteBranding } from '@/utils/siteBranding'
import './Header.css'

interface HeaderProps {
  collapsed: boolean
  onToggle: () => void
}

const Header = ({ collapsed, onToggle }: HeaderProps) => {
  const navigate = useNavigate()
  const location = useLocation()
  const siteBranding = useSiteBranding()

  const handleTitleClick = () => {
    // 如果当前不在 dashboard，则跳转
    if (location.pathname !== '/dashboard') {
      navigate('/dashboard', { replace: false })
    }
  }

  return (
    <div className="app-header">
      <div className="header-left">
        <Button
          type="text"
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={onToggle}
        />
        <h1 className="header-title clickable" onClick={handleTitleClick}>
          {formatBrandTitle(siteBranding)}
        </h1>
      </div>
      <PublicNavigation messagePath="/dashboard" />
      <div className="header-right">
        <GlobalSearch />
        <UserAccountMenu variant="header" />
      </div>
    </div>
  )
}

export default Header

