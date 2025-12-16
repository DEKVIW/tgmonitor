/**
 * 游客模式布局组件（无侧边栏）
 */

import { ReactNode } from 'react'
import { Layout as AntLayout } from 'antd'
import { useNavigate } from 'react-router-dom'
import { Button } from 'antd'
import './Layout.css'

const { Content } = AntLayout

interface GuestLayoutProps {
  children: ReactNode
}

const GuestLayout = ({ children }: GuestLayoutProps) => {
  const navigate = useNavigate()

  return (
    <AntLayout className="app-layout guest-layout">
      <AntLayout.Header
        style={{
          background: '#fff',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid #f0f0f0',
        }}
      >
        <div style={{ fontSize: '18px', fontWeight: 500 }}>TG频道监控</div>
        <Button type="primary" onClick={() => navigate('/login')}>
          登录
        </Button>
      </AntLayout.Header>
      <Content className="content-wrapper guest-content-wrapper">
        {children}
      </Content>
    </AntLayout>
  )
}

export default GuestLayout

