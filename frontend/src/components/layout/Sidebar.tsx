/**
 * 侧边栏组件
 */

import { Menu } from 'antd'
import { useNavigate, useLocation } from 'react-router-dom'
import { DashboardOutlined, BarChartOutlined, SettingOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import './Sidebar.css'

interface SidebarProps {
  collapsed: boolean
}

const Sidebar = ({ collapsed }: SidebarProps) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuthStore()

  // 根据用户角色决定是否显示后台管理菜单
  const isAdmin = user?.role === 'admin'

  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: '消息列表',
    },
    {
      key: '/statistics',
      icon: <BarChartOutlined />,
      label: '统计信息',
    },
    // 只有管理员才显示后台管理菜单
    ...(isAdmin
      ? [
          {
            key: '/admin',
            icon: <SettingOutlined />,
            label: '后台管理',
          },
        ]
      : []),
  ]

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
  }

  return (
    <div className={`app-sidebar ${collapsed ? 'collapsed' : 'expanded'}`}>
      <Menu
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={handleMenuClick}
        className="sidebar-menu"
        inlineCollapsed={collapsed}
      />
    </div>
  )
}

export default Sidebar

