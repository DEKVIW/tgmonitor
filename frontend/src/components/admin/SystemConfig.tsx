import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Input,
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
const { TextArea } = Input

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
  const hasUmamiConfigError =
    !!draft && draft.umami_enabled && (!draft.umami_script_url.trim() || !draft.umami_website_id.trim())
  const saveDisabled = !isDirty || hasConcurrencyError || hasUmamiConfigError

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
    if (hasUmamiConfigError) {
      message.error('启用 Umami 时必须填写脚本地址和网站 ID')
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
        <div className="system-config-heading">
          <Title level={4} className="system-config-title">
            系统配置
          </Title>
        </div>

        <div className="system-config-actions" role="group" aria-label="系统配置操作">
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
            disabled={saveDisabled}
          >
            保存配置
          </Button>
        </div>
      </div>

      <Row gutter={[16, 16]} align="stretch">
        <Col xs={24} xl={16}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="站点信息" loading={loading}>
              <div className="system-config-field-grid">
                <div className="system-config-field-card">
                  <Text strong>站点名称</Text>
                  <Input
                    value={draft.site_name}
                    onChange={(event) => updateDraft('site_name', event.target.value)}
                    placeholder="TG频道监控"
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>站点标题</Text>
                  <Input
                    value={draft.site_title}
                    onChange={(event) => updateDraft('site_title', event.target.value)}
                    placeholder="TG频道监控"
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>标题图标</Text>
                  <Input
                    value={draft.brand_icon}
                    onChange={(event) => updateDraft('brand_icon', event.target.value)}
                    placeholder="📱"
                    maxLength={32}
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>Favicon</Text>
                  <Input
                    value={draft.site_favicon_url}
                    onChange={(event) => updateDraft('site_favicon_url', event.target.value)}
                    placeholder="/favicon.svg"
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>站点描述</Text>
                  <TextArea
                    rows={4}
                    value={draft.site_description}
                    onChange={(event) => updateDraft('site_description', event.target.value)}
                    placeholder="Telegram 频道网盘资源监控与检索"
                    className="system-config-textarea"
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-card">
                  <Text strong>关键词</Text>
                  <TextArea
                    rows={4}
                    value={draft.site_keywords}
                    onChange={(event) => updateDraft('site_keywords', event.target.value)}
                    placeholder="telegram,网盘,频道监控,资源搜索"
                    className="system-config-textarea"
                    disabled={saving}
                  />
                </div>
              </div>
            </Card>

            <Card title="访问控制" loading={loading}>
              <div className="system-config-switch-row">
                <div className="system-config-switch-copy">
                  <Text strong>允许未登录用户访问消息列表</Text>
                  <Text type="secondary">
                    开启后，游客可直接访问首页消息流和公开统计页；后台管理仍然需要登录。
                  </Text>
                </div>
                <Switch
                  checked={draft.public_dashboard_enabled}
                  onChange={(checked) => updateDraft('public_dashboard_enabled', checked)}
                  disabled={saving}
                />
              </div>
            </Card>

            <Card title="流量分析" extra={<Tag color="cyan">Umami</Tag>} loading={loading}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <div className="system-config-switch-row">
                  <div className="system-config-switch-copy">
                    <Text strong>启用站点流量统计</Text>
                    <Text type="secondary">保存后前台会注入 Umami 追踪脚本，页面访问和业务事件会开始上报。</Text>
                  </div>
                  <Switch
                    checked={draft.umami_enabled}
                    onChange={(checked) => updateDraft('umami_enabled', checked)}
                    disabled={saving}
                  />
                </div>

                <div className="system-config-field-grid">
                  <div className="system-config-field-card">
                    <Text strong>脚本地址</Text>
                    <Text type="secondary">例如 https://analytics.example.com/script.js</Text>
                    <Input
                      value={draft.umami_script_url}
                      onChange={(event) => updateDraft('umami_script_url', event.target.value)}
                      placeholder="https://analytics.example.com/script.js"
                      status={draft.umami_enabled && !draft.umami_script_url.trim() ? 'error' : undefined}
                      disabled={saving}
                    />
                  </div>

                  <div className="system-config-field-card">
                    <Text strong>Website ID</Text>
                    <Text type="secondary">Umami 站点配置里的网站唯一标识。</Text>
                    <Input
                      value={draft.umami_website_id}
                      onChange={(event) => updateDraft('umami_website_id', event.target.value)}
                      placeholder="9d2d1f8f-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                      status={draft.umami_enabled && !draft.umami_website_id.trim() ? 'error' : undefined}
                      disabled={saving}
                    />
                  </div>

                  <div className="system-config-field-card">
                    <Text strong>Host URL</Text>
                    <Text type="secondary">可选，用于代理或自定义采集入口。</Text>
                    <Input
                      value={draft.umami_host_url}
                      onChange={(event) => updateDraft('umami_host_url', event.target.value)}
                      placeholder="https://analytics.example.com"
                      disabled={saving}
                    />
                  </div>

                  <div className="system-config-field-card">
                    <Text strong>分享看板链接</Text>
                    <Text type="secondary">可选，配置后“数据分析”页可直接打开 Umami 分享面板。</Text>
                    <Input
                      value={draft.umami_share_url}
                      onChange={(event) => updateDraft('umami_share_url', event.target.value)}
                      placeholder="https://analytics.example.com/share/xxxx"
                      disabled={saving}
                    />
                  </div>
                </div>

                {hasUmamiConfigError && (
                  <Alert
                    className="system-config-inline-alert"
                    type="error"
                    showIcon
                    message="Umami 配置不完整"
                    description="启用站点流量统计时，至少需要填写脚本地址和 Website ID。"
                  />
                )}
              </Space>
            </Card>

            <Card title="广告位" extra={<Tag color="processing">游客页</Tag>} loading={loading}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <div className="system-config-switch-row">
                  <div className="system-config-switch-copy">
                    <Text strong>启用游客页广告</Text>
                    <Text type="secondary">仅在游客消息页展示，当前支持顶部广告和信息流插播广告。</Text>
                  </div>
                  <Switch
                    checked={draft.public_ads_enabled}
                    onChange={(checked) => updateDraft('public_ads_enabled', checked)}
                    disabled={saving}
                  />
                </div>

                <div className="system-config-inline-row">
                  <div className="system-config-switch-copy">
                    <Text strong>插播间隔</Text>
                    <Text type="secondary">每展示 N 条消息后插入一条广告。</Text>
                  </div>
                  <InputNumber
                    min={2}
                    max={999}
                    value={draft.public_feed_inline_every_n}
                    onChange={(value) => {
                      if (typeof value !== 'number' || Number.isNaN(value)) {
                        return
                      }
                      updateDraft('public_feed_inline_every_n', value)
                    }}
                    addonAfter="条"
                    className="system-config-inline-number"
                    disabled={saving}
                  />
                </div>

                <div className="system-config-ad-grid">
                  <div className="system-config-ad-card">
                    <Text strong>顶部广告</Text>
                    <Text type="secondary">显示在“共找到 xx 条消息”下方，适合宽横幅素材。</Text>

                    <div className="system-config-ad-code-group">
                      <Text type="secondary">桌面端 HTML</Text>
                      <TextArea
                        rows={5}
                        value={draft.public_feed_top_ad_html_desktop}
                        onChange={(event) => updateDraft('public_feed_top_ad_html_desktop', event.target.value)}
                        placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                        className="system-config-textarea"
                        allowClear
                        disabled={saving}
                      />
                    </div>

                    <div className="system-config-ad-code-group">
                      <Text type="secondary">移动端 HTML</Text>
                      <TextArea
                        rows={4}
                        value={draft.public_feed_top_ad_html_mobile}
                        onChange={(event) => updateDraft('public_feed_top_ad_html_mobile', event.target.value)}
                        placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                        className="system-config-textarea"
                        allowClear
                        disabled={saving}
                      />
                    </div>
                  </div>

                  <div className="system-config-ad-card">
                    <Text strong>信息流插播广告</Text>
                    <Text type="secondary">插入在消息卡片之间，适合中矩形或紧凑型素材。</Text>

                    <div className="system-config-ad-code-group">
                      <Text type="secondary">桌面端 HTML</Text>
                      <TextArea
                        rows={5}
                        value={draft.public_feed_inline_ad_html_desktop}
                        onChange={(event) => updateDraft('public_feed_inline_ad_html_desktop', event.target.value)}
                        placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                        className="system-config-textarea"
                        allowClear
                        disabled={saving}
                      />
                    </div>

                    <div className="system-config-ad-code-group">
                      <Text type="secondary">移动端 HTML</Text>
                      <TextArea
                        rows={4}
                        value={draft.public_feed_inline_ad_html_mobile}
                        onChange={(event) => updateDraft('public_feed_inline_ad_html_mobile', event.target.value)}
                        placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                        className="system-config-textarea"
                        allowClear
                        disabled={saving}
                      />
                    </div>
                  </div>
                </div>
              </Space>
            </Card>

            <Card title="链接检测" extra={<Tag color="success">新任务立即生效</Tag>} loading={loading}>
              <div className="system-config-field-grid">
                <div className="system-config-field-card">
                  <Text strong>默认并发数</Text>
                  <Text type="secondary">创建链接检测任务时默认带入的并发值。</Text>
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
                  <Text type="secondary">后台页面轮询任务状态的频率，单位秒。</Text>
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

            <Card title="监控运行" extra={<Tag color="warning">保存后自动读取</Tag>} loading={loading}>
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
                type="info"
                showIcon
                message="监控配置已改为数据库存储"
                description="无需手动改 .env 或重启 tg-monitor。频道刷新周期会在下一轮刷新时按新值生效，写库重试策略会从后续新消息开始使用。"
              />
            </Card>
          </Space>
        </Col>

        <Col xs={24} xl={8}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="当前摘要" loading={loading}>
              <div className="system-config-summary">
                <div className="system-config-summary-item">
                  <Text type="secondary">站点名称</Text>
                  <Text strong>{draft.site_name}</Text>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">标题图标</Text>
                  <Text strong>{draft.brand_icon || '未设置'}</Text>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">Favicon</Text>
                  <Text strong>{draft.site_favicon_url ? '已配置' : '未配置'}</Text>
                </div>
                <Divider className="system-config-summary-divider" />
                <div className="system-config-summary-item">
                  <Text type="secondary">游客访问</Text>
                  <Tag color={draft.public_dashboard_enabled ? 'success' : 'default'}>
                    {draft.public_dashboard_enabled ? '已开启' : '已关闭'}
                  </Tag>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">游客广告</Text>
                  <Tag color={draft.public_ads_enabled ? 'processing' : 'default'}>
                    {draft.public_ads_enabled ? '已开启' : '已关闭'}
                  </Tag>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">流量统计</Text>
                  <Tag color={draft.umami_enabled ? 'cyan' : 'default'}>
                    {draft.umami_enabled ? 'Umami 已启用' : '未启用'}
                  </Tag>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">看板链接</Text>
                  <Text strong>{draft.umami_share_url ? '已配置' : '未配置'}</Text>
                </div>
                <div className="system-config-summary-item">
                  <Text type="secondary">插播间隔</Text>
                  <Text strong>每 {draft.public_feed_inline_every_n} 条</Text>
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
                    <Tag color="processing">监控下一轮生效</Tag>
                  </Space>
                </div>
                <Paragraph className="system-config-note">
                  <Text strong>即时生效：</Text>
                  站点名称/标题/图标、游客访问开关、广告位配置、Umami 埋点配置、链接检测安全阈值，保存后刷新前台或重新创建任务即可按新配置工作。
                </Paragraph>
                <Paragraph className="system-config-note">
                  <Text strong>监控读取节奏：</Text>
                  频道刷新周期、数据库写入重试次数和重试间隔由监控进程直接从数据库读取，无需重启
                  <Text code> tg-monitor </Text>
                  ，新值会在下一轮刷新或下一条新消息处理时生效。
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
