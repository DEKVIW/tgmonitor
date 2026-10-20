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
  ReadOutlined,
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
  const messagePath = '/messages'
  const isMessageRoute =
    location.pathname === '/messages' ||
    location.pathname.startsWith('/messages/') ||
    location.pathname === '/dashboard' ||
    location.pathname.startsWith('/dashboard/')

  const menuItems: MenuProps['items'] = [
    {
      key: '/popular',
      icon: renderMenuIcon(<AppstoreOutlined />),
      label: '影视推荐',
    },
    {
      key: messagePath,
      icon: renderMenuIcon(<DashboardOutlined />),
      label: '资源动态',
    },
    {
      key: '/learning-resources',
      icon: renderMenuIcon(<ReadOutlined />),
      label: '学习资料',
    },
    {
      key: '/statistics',
      icon: renderMenuIcon(<BarChartOutlined />),
      label: '数据概览',
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
      .find((key) => location.pathname === key || location.pathname.startsWith(`${key}/`)) ??
    (isMessageRoute ? messagePath : '')

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
