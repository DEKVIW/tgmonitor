import { ReactNode } from 'react'
import { Button, Layout as AntLayout, Tooltip } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

import { formatBrandTitle, useSiteBranding } from '@/utils/siteBranding'
import { LOGIN_PATH } from '@/utils/routes'

import BackToTopButton from './BackToTopButton'
import SiteFooter from './SiteFooter'
import './Layout.css'
import './Header.css'
import './GuestLayout.css'

const { Content } = AntLayout

interface GuestLayoutProps {
  children: ReactNode
  toolbar?: ReactNode
}

const GuestLayout = ({ children, toolbar }: GuestLayoutProps) => {
  const siteBranding = useSiteBranding()
  const navigate = useNavigate()

  return (
    <AntLayout className="app-layout guest-layout">
      <header className="app-header guest-header">
        <div className="guest-brand">
          <div style={{ fontSize: '18px', fontWeight: 500 }}>{formatBrandTitle(siteBranding)}</div>
          <span className="guest-subtitle">{'\u516c\u5f00\u9875\u9762'}</span>
        </div>
        {toolbar ? <div className="guest-header-toolbar">{toolbar}</div> : null}
        <div className="guest-header-actions">
          <Tooltip title="登录" placement="bottomRight">
            <Button
              type="text"
              icon={<UserOutlined />}
              className="guest-login-button"
              aria-label="登录"
              onClick={() => navigate(LOGIN_PATH)}
            />
          </Tooltip>
        </div>
      </header>
      <Content className="content-wrapper guest-content-wrapper">{children}</Content>
      <SiteFooter />
      <BackToTopButton />
    </AntLayout>
  )
}

export default GuestLayout
