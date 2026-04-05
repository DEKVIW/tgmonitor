/**
 * 顶部导航栏
 */

import { ReactNode } from 'react'
import { Button } from 'antd'
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import UserAccountMenu from './UserAccountMenu'
import './Header.css'

interface HeaderProps {
  collapsed: boolean
  onToggle: () => void
  toolbar?: ReactNode
}

const Header = ({ collapsed, onToggle, toolbar }: HeaderProps) => {
  const navigate = useNavigate()
  const location = useLocation()

  const handleTitleClick = () => {
    // 如果当前不在 dashboard，则跳转
    if (location.pathname !== '/dashboard') {
      navigate('/dashboard', { replace: false })
    }
  }

  return (
    <div className={`app-header ${toolbar ? 'app-header--with-toolbar' : ''}`}>
      <div className="header-left">
        <Button
          type="text"
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={onToggle}
        />
        <h1 className="header-title clickable" onClick={handleTitleClick}>
          📱 TG频道监控
        </h1>
      </div>
      {toolbar ? <div className="header-toolbar-slot">{toolbar}</div> : null}
      <div className="header-right">
        <UserAccountMenu variant="header" />
      </div>
    </div>
  )
}

export default Header

