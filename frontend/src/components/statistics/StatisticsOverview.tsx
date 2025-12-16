/**
 * 统计概览组件
 */

import { Card, Row, Col, Statistic } from 'antd'
import { FileTextOutlined, CalendarOutlined, LinkOutlined } from '@ant-design/icons'
import { StatisticsOverview as StatisticsOverviewType } from '@/types/statistics'
import './StatisticsOverview.css'

interface StatisticsOverviewProps {
  data: StatisticsOverviewType
}

const StatisticsOverview = ({ data }: StatisticsOverviewProps) => {
  return (
    <Row gutter={16} className="statistics-overview">
      <Col xs={24} sm={8}>
        <Card variant="outlined">
          <Statistic
            title="今日消息"
            value={data.today_messages}
            prefix={<CalendarOutlined />}
            valueStyle={{ color: '#52c41a' }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card variant="outlined">
          <Statistic
            title="总消息数"
            value={data.total_messages}
            prefix={<FileTextOutlined />}
            valueStyle={{ color: '#409eff' }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card variant="outlined">
          <Statistic
            title="总链接数"
            value={data.total_links}
            prefix={<LinkOutlined />}
            valueStyle={{ color: '#faad14' }}
          />
        </Card>
      </Col>
    </Row>
  )
}

export default StatisticsOverview

