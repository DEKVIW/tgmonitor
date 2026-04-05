/**
 * 主布局组件
 */

import { ReactNode, useEffect, useMemo, useState } from 'react'
import { Layout as AntLayout } from 'antd'
import { useLocation } from 'react-router-dom'
import Header from './Header'
import Sidebar from './Sidebar'
import BackToTopButton from './BackToTopButton'
import AuthenticatedDashboardToolbar from '@/components/messages/AuthenticatedDashboardToolbar'
import './Layout.css'

const { Content } = AntLayout

interface LayoutProps {
  children: ReactNode
}

const DESKTOP_BREAKPOINT = 768
const SIDEBAR_WIDTH = 216
const SIDEBAR_COLLAPSED_WIDTH = 80
const SIDEBAR_COLLAPSE_STORAGE_KEY = 'tg-layout-sidebar-collapsed'

const getIsMobileViewport = () => window.innerWidth <= DESKTOP_BREAKPOINT

const getInitialCollapsedState = () => {
  if (getIsMobileViewport()) {
    return true
  }

  const storedValue = window.localStorage.getItem(SIDEBAR_COLLAPSE_STORAGE_KEY)
  return storedValue === null ? false : storedValue === 'true'
}

const Layout = ({ children }: LayoutProps) => {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(getInitialCollapsedState)
  const [isMobile, setIsMobile] = useState(getIsMobileViewport)
  const showDashboardToolbar =
    location.pathname === '/dashboard' || location.pathname.startsWith('/dashboard/')

  useEffect(() => {
    const handleResize = () => {
      const mobile = getIsMobileViewport()
      setIsMobile(mobile)

      if (mobile) {
        setCollapsed(true)
      } else {
        const storedValue = window.localStorage.getItem(SIDEBAR_COLLAPSE_STORAGE_KEY)
        setCollapsed(storedValue === null ? false : storedValue === 'true')
      }
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (!isMobile) {
      window.localStorage.setItem(SIDEBAR_COLLAPSE_STORAGE_KEY, String(collapsed))
    }
  }, [collapsed, isMobile])

  const contentMarginLeft = useMemo(() => {
    if (isMobile) return 0
    return collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH
  }, [collapsed, isMobile])

  return (
    <AntLayout className="app-layout">
      <Header
        collapsed={collapsed}
        onToggle={() => setCollapsed((current) => !current)}
        toolbar={showDashboardToolbar ? <AuthenticatedDashboardToolbar /> : undefined}
      />
      <AntLayout>
        <Sidebar
          collapsed={collapsed}
          showAccountEntry={isMobile}
          onNavigate={() => {
            if (isMobile) {
              setCollapsed(true)
            }
          }}
        />
        {isMobile && !collapsed && (
          <button
            type="button"
            className="sidebar-backdrop"
            aria-label="关闭侧边栏"
            onClick={() => setCollapsed(true)}
          />
        )}
        <AntLayout className="layout-content" style={{ marginLeft: contentMarginLeft }}>
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
      <BackToTopButton />
    </AntLayout>
  )
}

export default Layout

