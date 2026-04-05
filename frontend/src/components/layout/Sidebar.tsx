/**
 * 侧边栏组件
 */

import type { ReactNode } from 'react'
import { Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useNavigate, useLocation } from 'react-router-dom'
import { DashboardOutlined, BarChartOutlined, SettingOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import UserAccountMenu from './UserAccountMenu'
import './Sidebar.css'

interface SidebarProps {
  collapsed: boolean
  onNavigate?: () => void
  showAccountEntry?: boolean
}

const renderMenuIcon = (icon: ReactNode) => <span className="sidebar-icon-shell">{icon}</span>

const Sidebar = ({ collapsed, onNavigate, showAccountEntry = false }: SidebarProps) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuthStore()

  // 根据用户角色决定是否显示后台管理菜单
  const isAdmin = user?.role === 'admin'

  const menuItems: MenuProps['items'] = [
    {
      key: '/dashboard',
      icon: renderMenuIcon(<DashboardOutlined />),
      label: '消息列表',
    },
    {
      key: '/statistics',
      icon: renderMenuIcon(<BarChartOutlined />),
      label: '统计信息',
    },
    // 只有管理员才显示后台管理菜单
    ...(isAdmin
      ? [
          {
            key: '/admin',
            icon: renderMenuIcon(<SettingOutlined />),
            label: '后台管理',
          },
        ]
      : []),
  ]

  const selectedMenuKey =
    menuItems
      .map((item) => String(item?.key ?? ''))
      .sort((left, right) => right.length - left.length)
      .find((key) => location.pathname === key || location.pathname.startsWith(`${key}/`)) ?? ''

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
    onNavigate?.()
  }

  return (
    <div className={`app-sidebar ${collapsed ? 'collapsed' : 'expanded'}`}>
      <Menu
        mode="inline"
        selectedKeys={selectedMenuKey ? [selectedMenuKey] : []}
        items={menuItems}
        onClick={handleMenuClick}
        className="sidebar-menu"
        inlineCollapsed={collapsed}
      />
      {showAccountEntry ? (
        <div className="sidebar-account-section">
          <UserAccountMenu variant="sidebar" collapsed={collapsed} />
        </div>
      ) : null}
    </div>
  )
}

export default Sidebar

