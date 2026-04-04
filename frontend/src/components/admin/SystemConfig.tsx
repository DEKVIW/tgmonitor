import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  InputNumber,
  Row,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { getSystemConfig, updateSystemConfig } from '@/api/admin'
import type { SystemConfigResponse, SystemConfigUpdate } from '@/types/admin'
import './SystemConfig.css'

const { Paragraph, Text, Title } = Typography

const SystemConfig = () => {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [config, setConfig] = useState<SystemConfigResponse | null>(null)
  const [draft, setDraft] = useState<SystemConfigUpdate | null>(null)

  useEffect(() => {
    void loadConfig()
  }, [])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await getSystemConfig()
      setConfig(data)
      setDraft({ ...data })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载系统配置失败')
    } finally {
      setLoading(false)
    }
  }

  const updateDraft = <K extends keyof SystemConfigUpdate>(key: K, value: SystemConfigUpdate[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const isDirty = useMemo(() => {
    if (!config || !draft) {
      return false
    }
    return JSON.stringify(config) !== JSON.stringify(draft)
  }, [config, draft])

  const hasConcurrencyError =
    !!draft && draft.link_check_default_max_concurrent > draft.link_check_max_allowed_concurrent

  const handleReset = () => {
    if (!config) {
      return
    }
    setDraft({ ...config })
  }

  const handleSave = async () => {
    if (!draft) {
      return
    }
    if (hasConcurrencyError) {
      message.error('链接检测默认并发不能大于系统允许的最大并发')
      return
    }

    setSaving(true)
    try {
      const updated = await updateSystemConfig(draft)
      setConfig(updated)
      setDraft({ ...updated })
      window.dispatchEvent(new CustomEvent<SystemConfigResponse>('tg-system-config-updated', { detail: updated }))
      message.success('系统配置已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新系统配置失败')
    } finally {
      setSaving(false)
    }
  }

  if (!draft || !config) {
    return <Card loading={loading}>加载中...</Card>
  }

  return (
    <div className="system-config-page">
      <div className="system-config-toolbar">
        <div>
          <Title level={4} className="system-config-title">
            系统配置
          </Title>
          <Paragraph className="system-config-subtitle">
            只保留当前项目里已经有明确生效路径的全局配置。链接检测相关配置会立即影响新任务，监控运行类配置保存后需重启
            <Text strong> tg-monitor </Text>
            才会生效。
          </Paragraph>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void loadConfig()} loading={loading || saving}>
            重新加载
          </Button>
          <Button onClick={handleReset} disabled={!isDirty || saving}>
            撤销修改
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={() => void handleSave()}
            loading={saving}
            disabled={!isDirty || hasConcurrencyError}
          >
            保存配置
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={16}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="访问控制" loading={loading}>
              <div className="system-config-switch-row">
                <div className="system-config-switch-copy">
                  <Text strong>允许未登录用户访问消息列表</Text>
                  <Text type="secondary">
                    开启后，游客可直接访问首页消息流；统计页和后台管理仍然需要登录。
                  </Text>
                </div>
                <Switch
                  checked={draft.public_dashboard_enabled}
                  onChange={(checked) => updateDraft('public_dashboard_enabled', checked)}
                  disabled={saving}
                />
              </div>
              {draft.public_dashboard_enabled && (
                <Alert
                  className="system-config-inline-alert"
                  type="info"
                  showIcon
                  message="游客模式已开启"
                  description="这个开关立即生效，前台未登录用户刷新页面后就能看到公开消息列表。"
                />
              )}
            </Card>

            <Card
              title="链接检测"
              extra={<Tag color="success">新任务即时生效</Tag>}
              loading={loading}
            >
              <div className="system-config-field-grid">
                <div className="system-config-field-card">
                  <Text strong>默认并发数</Text>
                  <Text type="secondary">链接检测页创建任务时默认带入的并发值。</Text>
                  <InputNumber
                    min={1}
                    max={10}
                    value={draft.link_check_default_max_concurrent}
                    onChange={(value) => updateDraft('link_check_default_max_concurrent', Number(value || 1))}
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>允许最大并发</Text>
                  <Text type="secondary">后端安全阈值，超过会直接拦截任务。</Text>
                  <InputNumber
                    min={1}
                    max={10}
                    value={draft.link_check_max_allowed_concurrent}
                    onChange={(value) => updateDraft('link_check_max_allowed_concurrent', Number(value || 1))}
                    status={hasConcurrencyError ? 'error' : ''}
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>允许最大链接数</Text>
                  <Text type="secondary">单次检测任务最多允许处理的链接数量。</Text>
                  <InputNumber
                    min={100}
                    max={5000}
                    step={100}
                    value={draft.link_check_max_allowed_links}
                    onChange={(value) => updateDraft('link_check_max_allowed_links', Number(value || 100))}
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>任务轮询间隔</Text>
                  <Text type="secondary">后台管理页轮询任务状态的频率，单位秒。</Text>
                  <InputNumber
                    min={1}
                    max={30}
                    value={draft.link_check_poll_interval_seconds}
                    onChange={(value) => updateDraft('link_check_poll_interval_seconds', Number(value || 1))}
                    addonAfter="秒"
                    disabled={saving}
                  />
                </div>
              </div>

              {hasConcurrencyError && (
                <Alert
                  className="system-config-inline-alert"
                  type="error"
                  showIcon
                  message="并发配置不合法"
                  description="链接检测默认并发不能大于系统允许的最大并发。"
                />
              )}
            </Card>

            <Card
              title="监控运行"
              extra={<Tag color="warning">保存后重启 tg-monitor</Tag>}
              loading={loading}
            >
              <div className="system-config-field-grid">
                <div className="system-config-field-card">
                  <Text strong>频道刷新周期</Text>
                  <Text type="secondary">监控服务刷新频道映射和频道信息的间隔。</Text>
                  <InputNumber
                    min={10}
                    max={3600}
                    value={draft.monitor_channel_refresh_interval_seconds}
                    onChange={(value) => updateDraft('monitor_channel_refresh_interval_seconds', Number(value || 10))}
                    addonAfter="秒"
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>数据库写入重试次数</Text>
                  <Text type="secondary">监控消息入库失败时的最大重试次数。</Text>
                  <InputNumber
                    min={1}
                    max={10}
                    value={draft.monitor_db_write_max_retries}
                    onChange={(value) => updateDraft('monitor_db_write_max_retries', Number(value || 1))}
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>数据库写入重试间隔</Text>
                  <Text type="secondary">监控消息入库失败后，下一次重试前等待多久。</Text>
                  <InputNumber
                    min={0.1}
                    max={30}
                    step={0.1}
                    value={draft.monitor_db_write_retry_delay_seconds}
                    onChange={(value) => updateDraft('monitor_db_write_retry_delay_seconds', Number(value || 0.1))}
                    addonAfter="秒"
                    disabled={saving}
                  />
                </div>
              </div>

              <Alert
                className="system-config-inline-alert"
                type="warning"
                showIcon
                message="监控进程不会热更新 .env"
                description="这组配置保存后会写入 .env，但已经运行中的 tg-monitor 不会自动重新读取，需要手动重启服务后才会按新值运行。"
              />
            </Card>
          </Space>
        </Col>

        <Col xs={24} xl={8}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="当前摘要" loading={loading}>
              <div className="system-config-summary">
                <div className="system-config-summary-item">
                  <Text type="secondary">游客访问</Text>
                  <Tag color={draft.public_dashboard_enabled ? 'success' : 'default'}>
                    {draft.public_dashboard_enabled ? '已开启' : '已关闭'}
                  </Tag>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">检测默认并发</Text>
                  <Text strong>{draft.link_check_default_max_concurrent}</Text>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">检测最大并发</Text>
                  <Text strong>{draft.link_check_max_allowed_concurrent}</Text>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">检测最大链接数</Text>
                  <Text strong>{draft.link_check_max_allowed_links}</Text>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">轮询间隔</Text>
                  <Text strong>{draft.link_check_poll_interval_seconds} 秒</Text>
                </div>
                <Divider className="system-config-summary-divider" />
                <div className="system-config-summary-item">
                  <Text type="secondary">频道刷新周期</Text>
                  <Text strong>{draft.monitor_channel_refresh_interval_seconds} 秒</Text>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">写库重试</Text>
                  <Text strong>
                    {draft.monitor_db_write_max_retries} 次 / {draft.monitor_db_write_retry_delay_seconds} 秒
                  </Text>
                </div>
              </div>
            </Card>

            <Card title="生效说明" loading={loading}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <div>
                  <Space wrap>
                    <Tag color="success">即时生效</Tag>
                    <Tag color="warning">需重启 tg-monitor</Tag>
                  </Space>
                </div>
                <Paragraph className="system-config-note">
                  <Text strong>即时生效：</Text>
                  游客访问开关、链接检测安全阈值。新的链接检测任务会立刻使用这里的限制值。
                </Paragraph>
                <Paragraph className="system-config-note">
                  <Text strong>刷新后可见：</Text>
                  链接检测页的默认并发和轮询间隔属于管理端默认值，切到链接检测页或刷新页面后会按新配置展示。
                </Paragraph>
                <Paragraph className="system-config-note">
                  <Text strong>重启后生效：</Text>
                  频道刷新周期、数据库写入重试次数和重试间隔由监控进程读取，保存后请重启
                  <Text code> tg-monitor </Text>
                  。
                </Paragraph>
              </Space>
            </Card>
          </Space>
        </Col>
      </Row>
    </div>
  )
}

export default SystemConfig

