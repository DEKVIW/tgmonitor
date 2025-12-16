/**
 * 后台管理页面
 */

import { Tabs, Card } from 'antd'
import CredentialManager from '@/components/admin/CredentialManager'
import ChannelManager from '@/components/admin/ChannelManager'
import SystemConfig from '@/components/admin/SystemConfig'
import UserManager from '@/components/admin/UserManager'
import DataMaintenance from '@/components/admin/DataMaintenance'
import LinkCheckManager from '@/components/admin/LinkCheckManager'
import './Admin.css'

const Admin = () => {
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
      label: 'API凭据管理',
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
      <Card title="🔧 后台管理" className="admin-card" variant="outlined">
        <Tabs items={tabItems} />
      </Card>
    </div>
  )
}

export default Admin

