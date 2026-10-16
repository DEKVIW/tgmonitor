import { NavLink } from 'react-router-dom'
import { AppstoreOutlined, MessageOutlined } from '@ant-design/icons'

interface PublicNavigationProps {
  messagePath: string
}

const PublicNavigation = ({ messagePath }: PublicNavigationProps) => (
  <nav className="public-primary-nav" aria-label="公开页面导航">
    <NavLink to={messagePath} end className={({ isActive }) => `public-nav-link${isActive ? ' is-active' : ''}`}>
      <MessageOutlined aria-hidden="true" />
      <span>消息列表</span>
    </NavLink>
    <NavLink to="/popular" className={({ isActive }) => `public-nav-link${isActive ? ' is-active' : ''}`}>
      <AppstoreOutlined aria-hidden="true" />
      <span>影视墙</span>
    </NavLink>
  </nav>
)

export default PublicNavigation
