import { ReactNode } from 'react'
import { Button, Layout as AntLayout, Tooltip } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

import { formatBrandTitle, useSiteBranding } from '@/utils/siteBranding'
import { LOGIN_PATH } from '@/utils/routes'
import { useAuthStore } from '@/store/authStore'

import BackToTopButton from './BackToTopButton'
import GlobalSearch from './GlobalSearch'
import PublicNavigation from './PublicNavigation'
import SiteFooter from './SiteFooter'
import UserAccountMenu from './UserAccountMenu'
import './Layout.css'
import './Header.css'
import './GuestLayout.css'

const { Content } = AntLayout

interface GuestLayoutProps {
  children: ReactNode
}

const GuestLayout = ({ children }: GuestLayoutProps) => {
  const siteBranding = useSiteBranding()
  const navigate = useNavigate()
  const { isAuthenticated, token } = useAuthStore()

  return (
    <AntLayout className="app-layout guest-layout">
      <header className="app-header guest-header">
        <div className="guest-brand">
          <div style={{ fontSize: '18px', fontWeight: 500 }}>{formatBrandTitle(siteBranding)}</div>
          <span className="guest-subtitle">{'\u516c\u5f00\u9875\u9762'}</span>
        </div>
        <PublicNavigation messagePath="/" />
        <div className="guest-header-actions">
          <GlobalSearch />
          {isAuthenticated && token ? (
            <UserAccountMenu variant="header" />
          ) : (
            <Tooltip title="登录" placement="bottomRight">
              <Button
                type="text"
                icon={<UserOutlined />}
                className="guest-login-button"
                aria-label="登录"
                onClick={() => navigate(LOGIN_PATH)}
              />
            </Tooltip>
          )}
        </div>
      </header>
      <Content className="content-wrapper guest-content-wrapper">{children}</Content>
      <SiteFooter />
      <BackToTopButton />
    </AntLayout>
  )
}

export default GuestLayout
