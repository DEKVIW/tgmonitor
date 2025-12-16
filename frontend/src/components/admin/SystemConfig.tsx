/**
 * 系统配置组件
 */

import { useState, useEffect } from 'react'
import { Card, Switch, message, Space, Typography, Alert } from 'antd'
import { getSystemConfig, updateSystemConfig } from '@/api/admin'
import { SystemConfigResponse } from '@/types/admin'

const { Text } = Typography

const SystemConfig = () => {
  const [loading, setLoading] = useState(false)
  const [config, setConfig] = useState<SystemConfigResponse | null>(null)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await getSystemConfig()
      setConfig(data)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载系统配置失败')
    } finally {
      setLoading(false)
    }
  }

  const handleToggleGuestMode = async (enabled: boolean) => {
    try {
      await updateSystemConfig({ public_dashboard_enabled: enabled })
      setConfig({ public_dashboard_enabled: enabled })
      message.success('系统配置已更新')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新系统配置失败')
      // 恢复原值
      if (config) {
        setConfig({ ...config })
      }
    }
  }

  if (!config) {
    return <Card loading={loading}>加载中...</Card>
  }

  return (
    <div className="system-config">
      <Card title="⚙️ 系统配置" loading={loading}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Text strong>允许未登录用户访问消息列表</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: '12px' }}>
                    开启后，未登录用户可直接访问根路径查看消息列表
                  </Text>
                </div>
                <Switch
                  checked={config.public_dashboard_enabled}
                  onChange={handleToggleGuestMode}
                  loading={loading}
                />
              </div>
              {config.public_dashboard_enabled && (
                <Alert
                  message="游客模式已开启"
                  description="未登录用户可以访问消息列表页面，但无法访问统计和管理功能"
                  type="info"
                  showIcon
                  style={{ marginTop: 8 }}
                />
              )}
            </Space>
          </Card>

          <Card title="系统信息">
            <Space direction="vertical" size="small">
              <div>
                <Text strong>版本: </Text>
                <Text>1.0.0</Text>
              </div>
              <div>
                <Text strong>运行状态: </Text>
                <Text type="success">正常</Text>
              </div>
            </Space>
          </Card>
        </Space>
      </Card>
    </div>
  )
}

export default SystemConfig

