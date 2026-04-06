import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Empty,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  AreaChartOutlined,
  CheckCircleFilled,
  EyeOutlined,
  GlobalOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import { getSystemConfig } from '@/api/admin'
import HintTooltip from '@/components/common/HintTooltip'
import type { SystemConfigResponse } from '@/types/admin'
import './AnalyticsDashboardModern.css'

const { Text, Title } = Typography

const getHostName = (value: string) => {
  if (!value) {
    return ''
  }

  try {
    return new URL(value).host
  } catch {
    return value
  }
}

const truncateMiddle = (value: string, max = 30) => {
  if (!value || value.length <= max) {
    return value
  }

  const sliceLength = Math.max(6, Math.floor((max - 1) / 2))
  return `${value.slice(0, sliceLength)}…${value.slice(-sliceLength)}`
}

const AnalyticsDashboardModern = () => {
  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState<SystemConfigResponse | null>(null)

  useEffect(() => {
    const loadConfig = async () => {
      setLoading(true)
      try {
        const response = await getSystemConfig()
        setConfig(response)
      } catch (error: any) {
        message.error(error.response?.data?.detail || '加载数据分析配置失败')
      } finally {
        setLoading(false)
      }
    }

    void loadConfig()
  }, [])

  useEffect(() => {
    const handleConfigUpdated = (event: Event) => {
      const detail = (event as CustomEvent<SystemConfigResponse>).detail
      if (detail) {
        setConfig(detail)
      }
    }

    window.addEventListener('tg-system-config-updated', handleConfigUpdated)
    return () => window.removeEventListener('tg-system-config-updated', handleConfigUpdated)
  }, [])

  const umamiReady = Boolean(
    config &&
      config.umami_enabled &&
      config.umami_script_url.trim() &&
      config.umami_website_id.trim()
  )

  const scriptHost = useMemo(() => getHostName(config?.umami_script_url || ''), [config?.umami_script_url])
  const dashboardHost = useMemo(() => getHostName(config?.umami_share_url || ''), [config?.umami_share_url])

  const metricItems = [
    {
      key: 'status',
      label: '接入状态',
      hint: '这里只表示前端与 Umami 的接线配置状态，不代表某个具体事件一定已经在看板里出现。',
      icon: <GlobalOutlined />,
      value: umamiReady ? '已启用' : '未启用',
      meta: umamiReady ? '前台会向 Umami 上报访问与业务事件' : '请先补全脚本地址和 Website ID',
    },
    {
      key: 'script',
      label: '脚本域名',
      hint: '当前前台注入的 Umami 脚本来源域名。',
      icon: <AreaChartOutlined />,
      value: scriptHost || '未配置',
      meta: config?.umami_script_url ? '脚本地址已接入' : '等待填写脚本地址',
    },
    {
      key: 'website-id',
      label: 'Website ID',
      hint: 'Umami 为当前网站生成的唯一标识。过长时会做中间省略，但完整值仍可复制。',
      icon: <EyeOutlined />,
      value: config?.umami_website_id ? truncateMiddle(config.umami_website_id, 26) : '未配置',
      rawValue: config?.umami_website_id || '',
      meta: config?.umami_website_id ? '点击复制完整 ID' : '等待填写 Website ID',
      mono: true,
    },
    {
      key: 'share',
      label: '看板域名',
      hint: '填写分享看板链接后，这里会显示对应域名，并在下方提供直接打开与嵌入入口。',
      icon: <LinkOutlined />,
      value: dashboardHost || '未配置',
      meta: config?.umami_share_url ? '分享看板已接入' : '可选，未配置时不影响采集',
    },
  ]

  const configChecks = [
    {
      key: 'script',
      title: '追踪脚本',
      status: !!config?.umami_script_url,
      detail: config?.umami_script_url ? '已配置脚本地址' : '待填写脚本地址',
      hint: '决定前台是否会加载 Umami 的 tracker。',
    },
    {
      key: 'website',
      title: 'Website ID',
      status: !!config?.umami_website_id,
      detail: config?.umami_website_id ? '已绑定网站 ID' : '待填写 Website ID',
      hint: '用于告诉 Umami 当前数据属于哪个站点。',
    },
    {
      key: 'events',
      title: '业务事件接线',
      status: umamiReady,
      detail: umamiReady ? '搜索、分页、网盘点击、广告事件已接线' : '等待 Umami 基础配置完成',
      hint: '这里只表示前端埋点代码已接上，不代表该事件已经被触发过。',
    },
    {
      key: 'share',
      title: '分享看板',
      status: !!config?.umami_share_url,
      detail: config?.umami_share_url ? '可从本页直接打开或嵌入看板' : '未配置，不影响数据采集',
      hint: '配置 Umami Share 链接后，本页会提供一键打开与内嵌面板。',
    },
  ]

  return (
    <div className="analytics-modern-page">
      <Card className="analytics-modern-hero-card" variant="outlined">
        <div className="analytics-modern-hero-header">
          <div>
            <Title level={3} className="analytics-modern-page-title">
              数据分析
            </Title>
            <div className="analytics-modern-status-row">
              <Tag color={umamiReady ? 'cyan' : 'default'}>{umamiReady ? 'Umami 已接入' : 'Umami 未接入'}</Tag>
              <Tag color={config?.umami_share_url ? 'processing' : 'default'}>
                {config?.umami_share_url ? '看板入口已配置' : '看板入口未配置'}
              </Tag>
            </div>
          </div>
          <div className="analytics-modern-chip-row">
            <span className="analytics-modern-chip">流量采集</span>
            <span className="analytics-modern-chip">行为事件</span>
            <span className="analytics-modern-chip">广告表现</span>
          </div>
        </div>
      </Card>

      {loading ? (
        <Card className="analytics-modern-panel-card" variant="outlined">
          <div className="analytics-modern-loading">
            <Spin size="large" />
          </div>
        </Card>
      ) : (
        <>
          <section className="analytics-modern-metric-grid">
            {metricItems.map((item) => (
              <Card className="analytics-modern-metric-card" key={item.key} variant="borderless">
                <div className="analytics-modern-metric-head">
                  <div className="analytics-modern-metric-label-row">
                    <span className="analytics-modern-metric-label">{item.label}</span>
                    <HintTooltip content={item.hint} />
                  </div>
                  <span className="analytics-modern-metric-icon">{item.icon}</span>
                </div>
                <div
                  className={`analytics-modern-metric-value ${item.mono ? 'analytics-modern-metric-value--mono' : ''}`}
                  title={item.rawValue || item.value}
                >
                  {item.value}
                </div>
                <div className="analytics-modern-metric-foot">
                  <span className="analytics-modern-metric-meta">{item.meta}</span>
                  {item.rawValue ? <Text copyable={{ text: item.rawValue }}>复制</Text> : null}
                </div>
              </Card>
            ))}
          </section>

          {!umamiReady && (
            <Alert
              type="warning"
              showIcon
              message="当前还没有完成 Umami 接入"
              
            />
          )}

          <Card
            className="analytics-modern-panel-card"
            variant="outlined"
            title={
              <div className="analytics-modern-panel-heading">
                <span>配置检查</span>
                <HintTooltip content="这里显示的是当前页面能确认的接线状态，帮助你快速判断配置是否完整。" />
              </div>
            }
          >
            <div className="analytics-modern-check-grid">
              {configChecks.map((item) => (
                <div className="analytics-modern-check-item" key={item.key}>
                  <div className={`analytics-modern-check-badge ${item.status ? 'is-ready' : 'is-pending'}`}>
                    <CheckCircleFilled />
                  </div>
                  <div className="analytics-modern-check-copy">
                    <div className="analytics-modern-check-title-row">
                      <span className="analytics-modern-check-title">{item.title}</span>
                      <HintTooltip content={item.hint} />
                    </div>
                    <span className="analytics-modern-check-detail">{item.detail}</span>
                  </div>
                  <Tag color={item.status ? 'success' : 'default'}>{item.status ? '已就绪' : '待完善'}</Tag>
                </div>
              ))}
            </div>
          </Card>

          <Card
            className="analytics-modern-panel-card"
            variant="outlined"
            title={
              <div className="analytics-modern-panel-heading">
                <span>看板入口</span>
                <HintTooltip content="配置 Umami 分享看板链接后，这里会提供一键打开和内嵌面板。未配置时不影响数据采集。" />
              </div>
            }
          >
            {config?.umami_share_url ? (
              <div className="analytics-modern-dashboard-stack">
                <div className="analytics-modern-dashboard-topbar">
                  <div className="analytics-modern-dashboard-meta">
                    <Tag color="processing">已配置</Tag>
                    <div className="analytics-modern-dashboard-link" title={config.umami_share_url}>
                      {config.umami_share_url}
                    </div>
                  </div>
                  <Button type="primary" href={config.umami_share_url} target="_blank" rel="noopener noreferrer">
                    打开 Umami 看板
                  </Button>
                </div>

                <div className="analytics-modern-embed-shell">
                  <iframe
                    src={config.umami_share_url}
                    title="Umami 分享看板"
                    className="analytics-modern-embed-frame"
                    loading="lazy"
                    referrerPolicy="no-referrer"
                  />
                </div>
              </div>
            ) : (
              <Empty description="还没有配置 Umami 分享看板链接" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </>
      )}
    </div>
  )
}

export default AnalyticsDashboardModern



