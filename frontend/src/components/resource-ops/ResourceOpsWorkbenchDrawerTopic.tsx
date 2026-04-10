import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Descriptions, Drawer, Empty, Input, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import ResourceOpsTrendChart from '@/components/resource-ops/ResourceOpsTrendChart'
import type {
  ResourceOpsCandidateRefItem,
  ResourceOpsWorkbenchDetailResponse,
  ResourceOpsWorkbenchUpdateRequest,
} from '@/types/resourceOps'
import { formatServerDateTime } from '@/utils/dateTime'

const { Paragraph, Text } = Typography

interface ResourceOpsWorkbenchDrawerTopicProps {
  open: boolean
  loading: boolean
  saving: boolean
  data: ResourceOpsWorkbenchDetailResponse | null
  onClose: () => void
  onSave: (payload: ResourceOpsWorkbenchUpdateRequest) => Promise<void>
}

const getHealthColor = (status: string) => {
  if (status === 'invalid') return 'error'
  if (status === 'warning') return 'processing'
  if (status === 'healthy') return 'success'
  return 'default'
}

const buildLinkLabel = (platform: string, displayText: string, shareKey?: string | null) => {
  const normalizedText = displayText?.trim()
  if (normalizedText) {
    return normalizedText
  }
  if (shareKey) {
    return `${platform || '链接'} · ${shareKey}`
  }
  return platform || '打开链接'
}

const ResourceOpsWorkbenchDrawerTopic = ({
  open,
  loading,
  saving,
  data,
  onClose,
  onSave,
}: ResourceOpsWorkbenchDrawerTopicProps) => {
  const [operationStatus, setOperationStatus] = useState('pending_review')
  const [valueStatus, setValueStatus] = useState('unreviewed')
  const [manualResourceKind, setManualResourceKind] = useState<'' | 'fixed' | 'rolling' | 'stopped'>('')
  const [note, setNote] = useState('')

  useEffect(() => {
    if (!data?.item) {
      return
    }
    setOperationStatus(data.item.operation_status || 'pending_review')
    setValueStatus(data.item.value_status_source === 'manual' ? data.item.effective_value_status : 'unreviewed')
    setManualResourceKind(
      data.item.resource_kind_source === 'manual' &&
        ['fixed', 'rolling', 'stopped'].includes(data.item.effective_resource_kind)
        ? (data.item.effective_resource_kind as 'fixed' | 'rolling' | 'stopped')
        : ''
    )
    setNote(data.item.note || '')
  }, [data])

  const refColumns = useMemo<ColumnsType<ResourceOpsCandidateRefItem>>(
    () => [
      {
        title: '消息标题',
        dataIndex: 'message_title',
        key: 'message_title',
        width: 320,
        render: (value: string) => (
          <span className="resource-ops-ellipsis" title={value || '-'}>
            {value || '-'}
          </span>
        ),
      },
      {
        title: '频道',
        dataIndex: 'channel',
        key: 'channel',
        width: 180,
        render: (value: string) => value || '-',
      },
      {
        title: '时间',
        dataIndex: 'message_timestamp',
        key: 'message_timestamp',
        width: 170,
        render: (value?: string | null) => formatServerDateTime(value),
      },
      {
        title: '链接',
        dataIndex: 'links',
        key: 'links',
        render: (links: ResourceOpsCandidateRefItem['links']) =>
          links && links.length > 0 ? (
            <div className="resource-ops-ref-links">
              {links.map((link) => (
                <Button
                  key={`${link.link_target_id}-${link.target_url}`}
                  size="small"
                  href={link.target_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="resource-ops-ref-link-button"
                  title={buildLinkLabel(link.platform, link.display_text, link.share_key)}
                >
                  <span className="resource-ops-ellipsis">
                    {buildLinkLabel(link.platform, link.display_text, link.share_key)}
                  </span>
                </Button>
              ))}
            </div>
          ) : (
            <span className="resource-ops-text-muted">-</span>
          ),
      },
    ],
    []
  )

  const handleSave = async () => {
    await onSave({
      operation_status: operationStatus,
      value_status: valueStatus,
      manual_resource_kind: manualResourceKind || '',
      note,
    })
  }

  return (
    <Drawer title="主题详情" width={920} open={open} onClose={onClose} className="responsive-drawer-root">
      {loading ? (
        <Card loading />
      ) : !data ? (
        <Alert type="info" showIcon message="当前没有可展示的主题详情" />
      ) : (
        <div className="resource-ops-drawer-stack">
          <Card>
            <div className="resource-ops-drawer-head">
              <div className="resource-ops-drawer-head-copy">
                <Text type="secondary">资源主题</Text>
                <Paragraph className="resource-ops-drawer-title" ellipsis={{ rows: 2, expandable: false }}>
                  {data.item.topic_title}
                </Paragraph>
                <p
                  className="resource-ops-drawer-subtitle"
                  title={data.item.topic_latest_message_title || data.item.latest_message_title || '-'}
                >
                  最近关联消息：{data.item.topic_latest_message_title || data.item.latest_message_title || '-'}
                </p>
              </div>
              <Space wrap size={[6, 6]}>
                <Tag color={data.item.work_match_status === 'matched' ? 'success' : data.item.work_match_status === 'error' ? 'error' : 'default'}>
                  {data.item.work_match_status_label}
                </Tag>
                <Tag color={data.item.value_status_source === 'manual' ? 'gold' : 'default'}>
                  {data.item.effective_value_status_label}
                </Tag>
                <Tag color={data.item.resource_kind_source === 'manual' ? 'cyan' : 'default'}>
                  {data.item.effective_resource_kind_label}
                </Tag>
                <Tag color={getHealthColor(data.item.latest_link_health)}>{data.item.latest_link_health_label}</Tag>
              </Space>
            </div>

            <div className="resource-ops-topic-grid">
              <div className="resource-ops-topic-card">
                <span>7天点击</span>
                <strong>{data.item.topic_clicks_7d}</strong>
                <small>最近 7 天主题总点击</small>
              </div>
              <div className="resource-ops-topic-card">
                <span>30天点击</span>
                <strong>{data.item.topic_clicks_30d}</strong>
                <small>最近 30 天主题总点击</small>
              </div>
              <div className="resource-ops-topic-card">
                <span>消息 / 链接</span>
                <strong>
                  {data.item.topic_message_count} / {data.item.topic_link_target_count}
                </strong>
                <small>原始消息数 / 成员链接数</small>
              </div>
              <div className="resource-ops-topic-card">
                <span>最近活动</span>
                <strong>{formatServerDateTime(data.item.topic_last_activity_at)}</strong>
                <small>主题聚合后的最后活跃时间</small>
              </div>
            </div>

            <Descriptions column={2} size="small" className="resource-ops-drawer-descriptions">
              <Descriptions.Item label="AI 结果">{data.item.work_title || '待归并'}</Descriptions.Item>
              <Descriptions.Item label="识别时间">{formatServerDateTime(data.item.work_matched_at || data.item.work_last_attempted_at)}</Descriptions.Item>
              <Descriptions.Item label="建议动作">{data.item.suggested_action}</Descriptions.Item>
              <Descriptions.Item label="更新模式">{data.item.update_mode_label}</Descriptions.Item>
              <Descriptions.Item label="健康概览">
                已检测 {data.item.checked_link_target_count} / {data.item.topic_link_target_count}
              </Descriptions.Item>
              <Descriptions.Item label="失效链接">{data.item.invalid_link_target_count}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title="运营策略">
            <div className="resource-ops-form-grid">
              <div className="resource-ops-form-field">
                <label>运营状态</label>
                <Select
                  value={operationStatus}
                  options={[
                    { value: 'pending_review', label: '待评估' },
                    { value: 'observing', label: '观察中' },
                    { value: 'ready_to_mirror', label: '待转存' },
                    { value: 'ignored', label: '已忽略' },
                  ]}
                  onChange={setOperationStatus}
                />
              </div>
              <div className="resource-ops-form-field">
                <label>价值判断</label>
                <Select
                  value={valueStatus}
                  options={[
                    { value: 'unreviewed', label: '跟随系统判断' },
                    { value: 'not_worth', label: '不值得做' },
                    { value: 'observe', label: '继续观察' },
                    { value: 'worth', label: '值得做' },
                    { value: 'priority', label: '优先处理' },
                  ]}
                  onChange={setValueStatus}
                />
              </div>
              <div className="resource-ops-form-field">
                <label>资源类型</label>
                <Select
                  value={manualResourceKind}
                  options={[
                    { value: '', label: '跟随系统判断' },
                    { value: 'fixed', label: '固定资源' },
                    { value: 'rolling', label: '持续更新' },
                    { value: 'stopped', label: '已停更' },
                  ]}
                  onChange={setManualResourceKind}
                />
              </div>
            </div>
            <div className="resource-ops-form-field">
              <label>备注</label>
              <Input.TextArea value={note} onChange={(event) => setNote(event.target.value)} rows={4} maxLength={2000} />
            </div>
            <div className="resource-ops-drawer-actions">
              <Button type="primary" loading={saving} onClick={() => void handleSave()}>
                保存
              </Button>
              {data.item.target_url ? (
                <Button href={data.item.target_url} target="_blank" rel="noopener noreferrer">
                  打开代表链接
                </Button>
              ) : null}
            </div>
          </Card>

          <Card title="判断依据">
            <Space wrap size={[8, 8]}>
              {data.item.evidence_tags.map((tag) => (
                <Tag key={tag} className="resource-ops-evidence-tag">
                  {tag}
                </Tag>
              ))}
            </Space>
            <Paragraph className="resource-ops-detail-note">
              链接健康说明：{data.item.latest_link_health_reason || '暂无'}
            </Paragraph>
            {data.auto_reasons.length > 0 ? (
              <div className="resource-ops-auto-reasons">
                {data.auto_reasons.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            ) : null}
          </Card>

          <Card title="近14天热度走势">
            <ResourceOpsTrendChart data={data.trend} height={260} />
          </Card>

          <Card title="关联原始消息">
            <Table
              rowKey="message_id"
              dataSource={data.recent_refs}
              columns={refColumns}
              pagination={{ pageSize: 10, showSizeChanger: false }}
              size="small"
              scroll={{ x: 920 }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无关联消息" /> }}
            />
          </Card>

          <Card title="操作日志">
            {data.logs.length > 0 ? (
              <div className="resource-ops-log-list">
                {data.logs.map((log) => (
                  <div key={log.id} className="resource-ops-log-item">
                    <div className="resource-ops-log-head">
                      <strong>{log.action_summary}</strong>
                      <span>{formatServerDateTime(log.created_at)}</span>
                    </div>
                    <div className="resource-ops-log-meta">操作人：{log.operator || '-'}</div>
                    {log.note ? <div className="resource-ops-log-note">{log.note}</div> : null}
                  </div>
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有操作日志" />
            )}
          </Card>
        </div>
      )}
    </Drawer>
  )
}

export default ResourceOpsWorkbenchDrawerTopic
