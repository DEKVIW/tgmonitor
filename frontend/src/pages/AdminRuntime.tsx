import { useEffect, useState } from 'react'
import { Card, Tabs } from 'antd'
import CredentialManager from '@/components/admin/CredentialManager'
import ChannelManager from '@/components/admin/ChannelManagerEnhanced'
import SystemConfig from '@/components/admin/SystemConfig'
import UserManager from '@/components/admin/UserManager'
import DataMaintenance from '@/components/admin/DataMaintenance'
import LinkCheckManager from '@/components/admin/LinkCheckManagerEnhanced'
import './Admin.css'

const ADMIN_TAB_STORAGE_KEY = 'tg-admin-active-tab'

const AdminRuntime = () => {
  const [activeKey, setActiveKey] = useState(() => localStorage.getItem(ADMIN_TAB_STORAGE_KEY) || 'system')

  useEffect(() => {
    localStorage.setItem(ADMIN_TAB_STORAGE_KEY, activeKey)
  }, [activeKey])

  const tabItems = [
    {
      key: 'system',
      label: '系统配置',
      children: <SystemConfig />,
    },
    {
      key: 'users',
      label: '用户管理',
      children: <UserManager />,
    },
    {
      key: 'credentials',
      label: 'API 凭据管理',
      children: <CredentialManager />,
    },
    {
      key: 'channels',
      label: '监听频道管理',
      children: <ChannelManager />,
    },
    {
      key: 'maintenance',
      label: '数据维护',
      children: <DataMaintenance />,
    },
    {
      key: 'link-check',
      label: '链接检测',
      children: <LinkCheckManager />,
    },
  ]

  return (
    <div className="admin-page">
      <Card title="后台管理" className="admin-card" variant="outlined">
        <Tabs activeKey={activeKey} onChange={setActiveKey} items={tabItems} />
      </Card>
    </div>
  )
}

export default AdminRuntime
