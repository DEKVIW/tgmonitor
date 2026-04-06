import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  AreaChartOutlined,
  EyeOutlined,
  GlobalOutlined,
  LinkOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { getSystemConfig } from '@/api/admin'
import type { SystemConfigResponse } from '@/types/admin'
import './Analytics.css'

const { Paragraph, Text, Title } = Typography

const trackedEvents = [
  {
    key: 'pageview',
    title: '页面访问',
    description: '由 Umami 自动采集，统计 PV、UV、来源、设备和访问路径。',
    icon: <AreaChartOutlined />,
  },
  {
    key: 'search',
    title: '搜索与筛选',
    description: '已记录搜索词、时间范围切换、页容量切换、筛选应用与重置。',
    icon: <SearchOutlined />,
  },
  {
    key: 'netdisk',
    title: '网盘点击',
    description: '点击网盘按钮时会上报 provider、按钮文案、消息 ID 和访客类型。',
    icon: <LinkOutlined />,
  },
  {
    key: 'ads',
    title: '广告表现',
    description: '已统计顶部和插播广告的曝光、点击、设备类型与目标域名。',
    icon: <EyeOutlined />,
  },
]

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

const AnalyticsDashboard = () => {
  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState<SystemConfigResponse | null>(null)

  useEffect(() => {
    const loadConfig = async () => {
      setLoading(true)
      try {
        const response = await getSystemConfig()
        setConfig(response)
      } catch (error: any) {
        message.error(error.response?.data?.detail || '加载分析配置失败')
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

  return (
    <div className="analytics-page">
      <Card className="analytics-hero-card" variant="outlined">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div className="analytics-hero-header">
            <div>
              <Title level={3} className="analytics-page-title">
                数据分析
              </Title>
              <Paragraph className="analytics-page-subtitle">
                这里现在直接承接 Umami 接入状态、当前埋点覆盖范围，以及分享看板入口。
              </Paragraph>
            </div>
            <Space wrap size={[8, 8]}>
              <Tag color={umamiReady ? 'cyan' : 'default'}>{umamiReady ? 'Umami 已接入' : 'Umami 未接入'}</Tag>
              <Tag color={config?.umami_share_url ? 'processing' : 'default'}>
                {config?.umami_share_url ? '看板已配置' : '看板未配置'}
              </Tag>
            </Space>
          </div>

          <div className="analytics-hero-strip">
            <div className="analytics-hero-chip">
              <Text strong>流量</Text>
              <Text type="secondary">PV / UV / 来源 / 设备 / 路径</Text>
            </div>
            <div className="analytics-hero-chip">
              <Text strong>行为</Text>
              <Text type="secondary">搜索 / 筛选 / 分页 / 网盘点击</Text>
            </div>
            <div className="analytics-hero-chip">
              <Text strong>广告</Text>
              <Text type="secondary">顶部位 / 插播位曝光和点击</Text>
            </div>
          </div>
        </Space>
      </Card>

      {loading ? (
        <Card className="analytics-panel-card" variant="outlined">
          <div className="analytics-loading">
            <Spin size="large" />
          </div>
        </Card>
      ) : (
        <>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} xl={6}>
              <Card className="analytics-metric-card" variant="borderless">
                <Statistic
                  title="接入状态"
                  value={umamiReady ? '已启用' : '未启用'}
                  prefix={
                    <span className="analytics-metric-icon">
                      <GlobalOutlined />
                    </span>
                  }
                />
                <Text type="secondary">由系统配置中的 Umami 开关控制。</Text>
              </Card>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Card className="analytics-metric-card" variant="borderless">
                <Statistic
                  title="脚本域名"
                  value={scriptHost || '未填写'}
                  prefix={
                    <span className="analytics-metric-icon">
                      <AreaChartOutlined />
                    </span>
                  }
                />
                <Text type="secondary">前台注入的追踪脚本来源。</Text>
              </Card>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Card className="analytics-metric-card" variant="borderless">
                <Statistic
                  title="Website ID"
                  value={config?.umami_website_id || '未填写'}
                  prefix={
                    <span className="analytics-metric-icon">
                      <EyeOutlined />
                    </span>
                  }
                />
                <Text type="secondary">Umami 站点唯一标识。</Text>
              </Card>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Card className="analytics-metric-card" variant="borderless">
                <Statistic
                  title="分享看板"
                  value={dashboardHost || '未配置'}
                  prefix={
                    <span className="analytics-metric-icon">
                      <LinkOutlined />
                    </span>
                  }
                />
                <Text type="secondary">配置分享链接后可从这里直接进入。</Text>
              </Card>
            </Col>
          </Row>

          {!umamiReady && (
            <Alert
              type="warning"
              showIcon
              message="当前还没有完成 Umami 接入"
              description="请到后台系统配置填写脚本地址和 Website ID，并开启 Umami 开关。"
            />
          )}

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="当前已接入的事件" className="analytics-panel-card" variant="outlined">
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {trackedEvents.map((eventItem) => (
                    <div className="analytics-bullet-line" key={eventItem.key}>
                      <div className="analytics-bullet-copy">
                        <Text strong>{eventItem.title}</Text>
                        <Text type="secondary">{eventItem.description}</Text>
                      </div>
                      <span className="analytics-bullet-icon">{eventItem.icon}</span>
                    </div>
                  ))}
                </Space>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="看板入口" className="analytics-panel-card" variant="outlined">
                {config?.umami_share_url ? (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Alert
                      type="info"
                      showIcon
                      message="已配置 Umami 分享看板"
                      description="如果你的 Umami 分享页允许嵌入，下面会直接显示；如果被浏览器拦截，可点击按钮新开标签页。"
                    />
                    <Space wrap>
                      <Button type="primary" href={config.umami_share_url} target="_blank" rel="noopener noreferrer">
                        打开 Umami 看板
                      </Button>
                    </Space>
                    <div className="analytics-embed-shell">
                      <iframe
                        src={config.umami_share_url}
                        title="Umami 分享看板"
                        className="analytics-embed-frame"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                    </div>
                  </Space>
                ) : (
                  <Empty description="还没有配置 Umami 分享看板链接" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  )
}

export default AnalyticsDashboard
