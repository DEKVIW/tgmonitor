/**
 * 主布局组件
 */

import { ReactNode } from 'react'
import AppShell from './AppShell'

interface LayoutProps {
  children: ReactNode
}

const Layout = ({ children }: LayoutProps) => {
  return <AppShell>{children}</AppShell>
}

export default Layout

