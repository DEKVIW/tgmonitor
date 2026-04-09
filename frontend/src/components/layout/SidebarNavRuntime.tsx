import type { ReactNode } from 'react'
import { Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  BarChartOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  LineChartOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import UserAccountMenu from './UserAccountMenu'
import './Sidebar.css'

interface SidebarProps {
  collapsed: boolean
  onNavigate?: () => void
  showAccountEntry?: boolean
}

const renderMenuIcon = (icon: ReactNode) => <span className="sidebar-icon-shell">{icon}</span>

const SidebarNavRuntime = ({ collapsed, onNavigate, showAccountEntry = false }: SidebarProps) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuthStore()
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
    ...(isAdmin
      ? [
          {
            key: '/analytics',
            icon: renderMenuIcon(<LineChartOutlined />),
            label: '数据分析',
          },
          {
            key: '/resource-ops',
            icon: renderMenuIcon(<ThunderboltOutlined />),
            label: '资源运营',
          },
          {
            key: '/backups',
            icon: renderMenuIcon(<CloudUploadOutlined />),
            label: '备份管理',
          },
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

export default SidebarNavRuntime
