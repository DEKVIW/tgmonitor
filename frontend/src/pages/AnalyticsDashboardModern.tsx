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
import { getSystemConfig } from '@/api/admin'
import HintTooltip from '@/components/common/HintTooltip'
import type { SystemConfigResponse } from '@/types/admin'
import './AnalyticsDashboardModern.css'

const { Title } = Typography

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

  const dashboardUrl = config?.umami_share_url?.trim() || ''
  const dashboardReady = Boolean(dashboardUrl)
  const umamiReady = Boolean(
    config &&
      config.umami_enabled &&
      config.umami_script_url.trim() &&
      config.umami_website_id.trim()
  )
  const analyticsReadyLabel = useMemo(() => (umamiReady ? 'Umami 已接入' : 'Umami 未接入'), [umamiReady])
  const dashboardStatusLabel = useMemo(
    () => (dashboardReady ? '看板入口已配置' : '看板入口未配置'),
    [dashboardReady]
  )

  const checkItems = [
    {
      key: 'script',
      title: '追踪脚本',
      status: !!config?.umami_script_url,
      detail: config?.umami_script_url ? '脚本地址已配置' : '待填写脚本地址',
      hint: '决定前台是否会加载 Umami 的 tracker。',
    },
    {
      key: 'website',
      title: 'Website ID',
      status: !!config?.umami_website_id,
      detail: config?.umami_website_id ? '网站 ID 已绑定' : '待填写 Website ID',
      hint: '用于告诉 Umami 当前数据属于哪个站点。',
    },
    {
      key: 'events',
      title: '业务事件',
      status: umamiReady,
      detail: umamiReady ? '搜索、分页、广告与网盘点击已可上报' : '需先完成基础 Umami 配置',
      hint: '这里表示搜索、分页、网盘点击和广告点击的埋点链路已经接上。',
    },
    {
      key: 'share',
      title: '分享看板',
      status: dashboardReady,
      detail: dashboardReady ? '看板入口已配置' : '可选，当前未配置',
      hint: '配置 Umami Share 链接后，本页会提供一键打开与内嵌面板。',
    },
  ]

  return (
    <div className="analytics-modern-page">
      <Card className="analytics-modern-hero-card" variant="outlined">
        <div className="analytics-modern-hero-header">
          <div className="analytics-modern-hero-copy">
            <Title level={3} className="analytics-modern-page-title">
              数据分析
            </Title>
            <p className="analytics-modern-hero-subtitle">统一查看 Umami 的接入状态、追踪链路和分享看板入口。</p>
            <div className="analytics-modern-status-row">
              <Tag color={umamiReady ? 'cyan' : 'default'}>{analyticsReadyLabel}</Tag>
              <Tag color={dashboardReady ? 'processing' : 'default'}>{dashboardStatusLabel}</Tag>
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
        <div className="analytics-modern-content-stack">
          <Card
            className="analytics-modern-panel-card analytics-modern-overview-card"
            variant="outlined"
            title={
              <div className="analytics-modern-panel-heading">
                <span>接入总览</span>
                <HintTooltip content="这里只保留最关键的接线检查项，避免和下方看板信息重复。" />
              </div>
            }
          >
            <div className="analytics-modern-overview-stack">
              {!umamiReady ? (
                <Alert
                  className="analytics-modern-inline-alert"
                  type="warning"
                  showIcon
                  message="当前还没有完成 Umami 接入"
                  description="补全脚本地址和 Website ID 后，前台刷新页面即可开始写入访问与行为事件。"
                />
              ) : null}

              <div className="analytics-modern-health-grid">
                {checkItems.map((item) => (
                  <article className="analytics-modern-health-card" key={item.key}>
                    <div className="analytics-modern-health-top">
                      <div className="analytics-modern-health-title-row">
                        <span className={`analytics-modern-health-dot ${item.status ? 'is-ready' : 'is-pending'}`} />
                        <span className="analytics-modern-health-title">{item.title}</span>
                        <HintTooltip content={item.hint} />
                      </div>
                      <Tag color={item.status ? 'success' : 'default'}>{item.status ? '已就绪' : '待完善'}</Tag>
                    </div>
                    <p className="analytics-modern-health-detail">{item.detail}</p>
                  </article>
                ))}
              </div>
            </div>
          </Card>

          <Card
            className="analytics-modern-panel-card analytics-modern-embed-card"
            variant="outlined"
            title={
              <div className="analytics-modern-panel-heading">
                <span>看板预览</span>
                <HintTooltip content="这里直接嵌入 Umami 的分享看板，右上角保留当前配置状态和进入按钮。" />
              </div>
            }
            extra={
              <div className="analytics-modern-embed-extra">
                <Tag color={dashboardReady ? 'processing' : 'default'}>{dashboardReady ? '看板已配置' : '看板未配置'}</Tag>
                <Button
                  type="primary"
                  href={dashboardReady ? dashboardUrl : undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  disabled={!dashboardReady}
                >
                  进入 Umami
                </Button>
              </div>
            }
          >
            {dashboardReady ? (
              <div className="analytics-modern-embed-shell">
                <iframe
                  src={dashboardUrl}
                  title="Umami 分享看板"
                  className="analytics-modern-embed-frame"
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              </div>
            ) : (
              <Empty description="还没有配置 Umami 分享看板链接" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </div>
      )}
    </div>
  )
}

export default AnalyticsDashboardModern



