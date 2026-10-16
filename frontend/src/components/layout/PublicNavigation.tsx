import { NavLink } from 'react-router-dom'

interface PublicNavigationProps {
  messagePath: string
}

const PublicNavigation = ({ messagePath }: PublicNavigationProps) => (
  <nav className="public-primary-nav" aria-label="公开页面导航">
    <NavLink to={messagePath} end className={({ isActive }) => `public-nav-link${isActive ? ' is-active' : ''}`}>
      消息列表
    </NavLink>
    <NavLink to="/popular" className={({ isActive }) => `public-nav-link${isActive ? ' is-active' : ''}`}>
      影视墙
    </NavLink>
  </nav>
)

export default PublicNavigation
