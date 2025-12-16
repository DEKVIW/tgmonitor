/**
 * 主布局组件
 */

import { ReactNode, useEffect, useMemo, useState } from 'react'
import { Layout as AntLayout } from 'antd'
import Header from './Header'
import Sidebar from './Sidebar'
import './Layout.css'

const { Content } = AntLayout

interface LayoutProps {
  children: ReactNode
}

const Layout = ({ children }: LayoutProps) => {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth <= 768)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768)

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 768
      setIsMobile(mobile)
      // 在移动端保持默认折叠
      if (mobile) {
        setCollapsed(true)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const contentMarginLeft = useMemo(() => {
    if (isMobile) return 0
    return collapsed ? 64 : 200
  }, [collapsed, isMobile])

  return (
    <AntLayout className="app-layout">
      <Header collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <AntLayout>
        <Sidebar collapsed={collapsed} />
        <AntLayout
          className="layout-content"
          style={{ marginLeft: contentMarginLeft }}
        >
          <Content
            className="content-wrapper"
            onClick={() => {
              if (isMobile && !collapsed) {
                setCollapsed(true)
              }
            }}
          >
            {children}
          </Content>
        </AntLayout>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout

