import type { ReactNode } from 'react'
import { Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  BarChartOutlined,
  AppstoreOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  LineChartOutlined,
  RobotOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import './Sidebar.css'

interface SidebarProps {
  collapsed: boolean
  onNavigate?: () => void
}

const renderMenuIcon = (icon: ReactNode) => <span className="sidebar-icon-shell">{icon}</span>

const SidebarNavRuntime = ({ collapsed, onNavigate }: SidebarProps) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, isAuthenticated, token } = useAuthStore()
  const isGuest = !isAuthenticated || !token
  const isAdmin = user?.role === 'admin'
  const messagePath = isGuest ? '/' : '/dashboard'

  const menuItems: MenuProps['items'] = [
    {
      key: messagePath,
      icon: renderMenuIcon(<DashboardOutlined />),
      label: '消息列表',
    },
    {
      key: '/statistics',
      icon: renderMenuIcon(<BarChartOutlined />),
      label: '统计信息',
    },
    {
      key: '/popular',
      icon: renderMenuIcon(<AppstoreOutlined />),
      label: '影视墙',
    },
    ...(!isGuest && isAdmin
      ? [
          {
            key: '/analytics',
            icon: renderMenuIcon(<LineChartOutlined />),
            label: '数据分析',
          },
          {
            key: '/ai-center',
            icon: renderMenuIcon(<RobotOutlined />),
            label: 'AI 中心',
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
    </div>
  )
}

export default SidebarNavRuntime
