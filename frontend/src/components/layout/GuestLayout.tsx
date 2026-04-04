/**
 * 游客模式布局组件（无侧边栏）
 */

import { ReactNode } from 'react'
import { Layout as AntLayout } from 'antd'
import './Layout.css'
import './Header.css'
import './GuestLayout.css'

const { Content } = AntLayout

interface GuestLayoutProps {
  children: ReactNode
}

const GuestLayout = ({ children }: GuestLayoutProps) => {
  return (
    <AntLayout className="app-layout guest-layout">
      <header className="app-header guest-header">
        <div style={{ fontSize: '18px', fontWeight: 500 }}>TG频道监控</div>
        <span className="guest-subtitle" aria-hidden="true">
          登录
        </span>
      </header>
      <Content className="content-wrapper guest-content-wrapper">
        {children}
      </Content>
    </AntLayout>
  )
}

export default GuestLayout

