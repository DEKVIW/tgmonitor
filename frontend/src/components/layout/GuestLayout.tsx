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
  toolbar?: ReactNode
}

const GuestLayout = ({ children, toolbar }: GuestLayoutProps) => {
  return (
    <AntLayout className="app-layout guest-layout">
      <header className="app-header guest-header">
        <div className="guest-brand">
          <div style={{ fontSize: '18px', fontWeight: 500 }}>TG频道监控</div>
          <span className="guest-subtitle">公开页面</span>
        </div>
        {toolbar ? <div className="guest-header-toolbar">{toolbar}</div> : null}
      </header>
      <Content className="content-wrapper guest-content-wrapper">
        {children}
      </Content>
    </AntLayout>
  )
}

export default GuestLayout
