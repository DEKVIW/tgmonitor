import { ReactNode, useEffect, useState } from 'react'
import { Button, Input, Layout as AntLayout, Modal, Tooltip } from 'antd'
import { SearchOutlined, UserOutlined } from '@ant-design/icons'
import { NavLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

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
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchValue, setSearchValue] = useState('')

  useEffect(() => {
    setSearchValue(searchParams.get('search') || '')
  }, [searchParams])

  const submitSearch = () => {
    const value = searchValue.trim()
    setSearchOpen(false)
    const query = value ? `?search=${encodeURIComponent(value)}` : ''
    navigate(location.pathname.startsWith('/popular') ? `/popular${query}` : `/${query}`)
  }

  return (
    <AntLayout className="app-layout guest-layout">
      <header className="app-header guest-header">
        <div className="guest-brand">
          <div style={{ fontSize: '18px', fontWeight: 500 }}>{formatBrandTitle(siteBranding)}</div>
          <span className="guest-subtitle">{'\u516c\u5f00\u9875\u9762'}</span>
        </div>
        <nav className="guest-primary-nav" aria-label="公开页面导航">
          <NavLink to="/" end className={({ isActive }) => `guest-nav-link${isActive ? ' is-active' : ''}`}>消息列表</NavLink>
          <NavLink to="/popular" className={({ isActive }) => `guest-nav-link${isActive ? ' is-active' : ''}`}>影视墙</NavLink>
        </nav>
        {toolbar ? <div className="guest-header-toolbar">{toolbar}</div> : null}
        <div className="guest-header-actions">
          <Tooltip title="搜索" placement="bottomRight">
            <Button
              type="text"
              icon={<SearchOutlined />}
              className="guest-search-button"
              aria-label="搜索"
              onClick={() => setSearchOpen(true)}
            />
          </Tooltip>
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
      <Modal
        open={searchOpen}
        title={location.pathname.startsWith('/popular') ? '搜索影视' : '搜索消息'}
        okText="搜索"
        cancelText="取消"
        onOk={submitSearch}
        onCancel={() => setSearchOpen(false)}
        destroyOnClose
      >
        <Input
          autoFocus
          value={searchValue}
          prefix={<SearchOutlined />}
          placeholder={location.pathname.startsWith('/popular') ? '输入影视名称' : '输入消息、频道或网盘关键词'}
          onChange={(event) => setSearchValue(event.target.value)}
          onPressEnter={submitSearch}
        />
      </Modal>
    </AntLayout>
  )
}

export default GuestLayout
