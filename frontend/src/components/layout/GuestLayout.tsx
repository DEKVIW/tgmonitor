import { ReactNode } from 'react'
import AppShell from './AppShell'

interface GuestLayoutProps {
  children: ReactNode
}

const GuestLayout = ({ children }: GuestLayoutProps) => {
  return <AppShell publicShell>{children}</AppShell>
}

export default GuestLayout
