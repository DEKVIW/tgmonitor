import { useEffect, useState } from 'react'
import {
  Alert,
  Card,
  Col,
  Row,
  Space,
  Statistic,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import {
  AimOutlined,
  AreaChartOutlined,
  GlobalOutlined,
  LinkOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import './Analytics.css'

const { Paragraph, Text, Title } = Typography

const ANALYTICS_TAB_STORAGE_KEY = 'tg-analytics-active-tab'

const trafficMetrics = [
  {
    key: 'pv',
    title: '站点 PV',
    hint: '页面访问量',
    icon: <AreaChartOutlined />,
  },
  {
    key: 'uv',
    title: '站点 UV',
    hint: '独立访客数',
    icon: <GlobalOutlined />,
  },
  {
    key: 'search',
    title: '搜索次数',
    hint: '搜索与筛选行为',
    icon: <SearchOutlined />,
  },
  {
    key: 'netdisk',
    title: '网盘点击',
    hint: '资源详情点击行为',
    icon: <LinkOutlined />,
  },
]

const adMetrics = [
  {
    key: 'top-impression',
    title: '顶部广告曝光',
    hint: 'public_feed_top',
    icon: <AimOutlined />,
  },
  {
    key: 'top-click',
    title: '顶部广告点击',
    hint: 'CTR 与点击趋势',
    icon: <AreaChartOutlined />,
  },
  {
    key: 'inline-impression',
    title: '插播广告曝光',
    hint: 'public_feed_inline',
    icon: <AimOutlined />,
  },
  {
    key: 'inline-click',
    title: '插播广告点击',
    hint: '桌面 / 移动对比',
    icon: <AreaChartOutlined />,
  },
]

const Analytics = () => {
  const [activeKey, setActiveKey] = useState(
    () => window.localStorage.getItem(ANALYTICS_TAB_STORAGE_KEY) || 'traffic'
  )

  useEffect(() => {
    window.localStorage.setItem(ANALYTICS_TAB_STORAGE_KEY, activeKey)
  }, [activeKey])

  const tabItems = [
    {
      key: 'traffic',
      label: '流量概览',
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="当前为流量分析模块骨架"
            description="下一步适合接入 Umami 或自建 analytics_events 事件表，把 PV、UV、来源、设备、搜索与网盘点击统一汇总到这里。"
          />

          <Row gutter={[16, 16]}>
            {trafficMetrics.map((metric) => (
              <Col xs={24} sm={12} xl={6} key={metric.key}>
                <Card className="analytics-metric-card" variant="borderless">
                  <Statistic
                    title={metric.title}
                    value="待接入"
                    prefix={<span className="analytics-metric-icon">{metric.icon}</span>}
                  />
                  <Text type="secondary">{metric.hint}</Text>
                </Card>
              </Col>
            ))}
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card title="第一批建议接入的数据源" className="analytics-panel-card" variant="outlined">
                <Timeline
                  items={[
                    {
                      color: 'blue',
                      children: '基础流量：PV、UV、访客来源、设备分布、访问时段',
                    },
                    {
                      color: 'blue',
                      children: '行为数据：搜索提交、筛选切换、分页切换、网盘按钮点击',
                    },
                    {
                      color: 'blue',
                      children: '页面维度：热门页面、落地页、游客与登录用户占比',
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card title="后续要看的核心指标" className="analytics-panel-card" variant="outlined">
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div className="analytics-bullet-line">
                    <Text strong>月 PV / UV</Text>
                    <Text type="secondary">决定站点基础量级</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>设备占比</Text>
                    <Text type="secondary">决定广告素材和版位策略</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>热门搜索词</Text>
                    <Text type="secondary">反映真实需求和转化方向</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>网盘点击排行</Text>
                    <Text type="secondary">判断最有价值的内容区块</Text>
                  </div>
                </Space>
              </Card>
            </Col>
          </Row>
        </Space>
      ),
    },
    {
      key: 'ads',
      label: '广告分析',
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="广告分析页已预留结构"
            description="当前建议先打通广告曝光、广告点击和联盟链接来源标记，后面这里就能直接看顶部位与插播位的 CTR 和转化价值。"
          />

          <Row gutter={[16, 16]}>
            {adMetrics.map((metric) => (
              <Col xs={24} sm={12} xl={6} key={metric.key}>
                <Card className="analytics-metric-card" variant="borderless">
                  <Statistic
                    title={metric.title}
                    value="待接入"
                    prefix={<span className="analytics-metric-icon">{metric.icon}</span>}
                  />
                  <Text type="secondary">{metric.hint}</Text>
                </Card>
              </Col>
            ))}
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="广告位事件建议" className="analytics-panel-card" variant="outlined">
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div className="analytics-bullet-line">
                    <Text strong>`ad_impression_top`</Text>
                    <Text type="secondary">顶部广告首屏曝光</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>`ad_click_top`</Text>
                    <Text type="secondary">顶部广告点击</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>`ad_impression_inline`</Text>
                    <Text type="secondary">信息流插播曝光</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>`ad_click_inline`</Text>
                    <Text type="secondary">信息流插播点击</Text>
                  </div>
                </Space>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="联盟归因建议" className="analytics-panel-card" variant="outlined">
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div className="analytics-bullet-line">
                    <Text strong>`slot=top_banner`</Text>
                    <Text type="secondary">区分顶部广告位转化</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>`slot=feed_inline`</Text>
                    <Text type="secondary">区分插播广告位转化</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>`device=desktop/mobile`</Text>
                    <Text type="secondary">分析素材在不同端的价值</Text>
                  </div>
                  <div className="analytics-bullet-line">
                    <Text strong>`creative_key`</Text>
                    <Text type="secondary">对比不同 banner 素材表现</Text>
                  </div>
                </Space>
              </Card>
            </Col>
          </Row>
        </Space>
      ),
    },
  ]

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
                这个板块从后台管理里独立出来，后续专门承载流量、广告、搜索与点击行为数据。
              </Paragraph>
            </div>
            <Space wrap size={[8, 8]}>
              <Tag color="blue">新模块</Tag>
              <Tag color="processing">可持续扩展</Tag>
            </Space>
          </div>

          <div className="analytics-hero-strip">
            <div className="analytics-hero-chip">
              <Text strong>流量</Text>
              <Text type="secondary">PV / UV / 来源 / 设备</Text>
            </div>
            <div className="analytics-hero-chip">
              <Text strong>广告</Text>
              <Text type="secondary">曝光 / 点击 / CTR / 归因</Text>
            </div>
            <div className="analytics-hero-chip">
              <Text strong>行为</Text>
              <Text type="secondary">搜索 / 筛选 / 网盘点击</Text>
            </div>
          </div>
        </Space>
      </Card>

      <Card className="analytics-tabs-card" variant="outlined">
        <Tabs activeKey={activeKey} onChange={setActiveKey} items={tabItems} />
      </Card>
    </div>
  )
}

export default Analytics
