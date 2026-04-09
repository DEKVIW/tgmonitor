import { useEffect, useState } from 'react'
import dayjs from 'dayjs'
import { Alert, Button, Card, Descriptions, Drawer, Empty, Input, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import ResourceOpsTrendChart from '@/components/resource-ops/ResourceOpsTrendChart'
import type {
  ResourceOpsCandidateRefItem,
  ResourceOpsWorkbenchDetailResponse,
  ResourceOpsWorkbenchUpdateRequest,
} from '@/types/resourceOps'

const { Paragraph, Text } = Typography

const formatDateTime = (value?: string | null) => {
  if (!value) {
    return '-'
  }
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

interface ResourceOpsWorkbenchDrawerProps {
  open: boolean
  loading: boolean
  saving: boolean
  data: ResourceOpsWorkbenchDetailResponse | null
  onClose: () => void
  onSave: (payload: ResourceOpsWorkbenchUpdateRequest) => Promise<void>
}

const refColumns: ColumnsType<ResourceOpsCandidateRefItem> = [
  {
    title: '消息标题',
    dataIndex: 'message_title',
    key: 'message_title',
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
    width: 168,
    render: (value?: string | null) => formatDateTime(value),
  },
]

const ResourceOpsWorkbenchDrawer = ({
  open,
  loading,
  saving,
  data,
  onClose,
  onSave,
}: ResourceOpsWorkbenchDrawerProps) => {
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

  const handleSave = async () => {
    await onSave({
      operation_status: operationStatus,
      value_status: valueStatus,
      manual_resource_kind: manualResourceKind || '',
      note,
    })
  }

  return (
    <Drawer
      title="候选资源详情"
      width={840}
      open={open}
      onClose={onClose}
      className="responsive-drawer-root"
    >
      {loading ? (
        <Card loading />
      ) : !data ? (
        <Alert type="info" showIcon message="当前还没有可展示的候选资源详情" />
      ) : (
        <div className="resource-ops-drawer-stack">
          <Card variant="outlined">
            <div className="resource-ops-drawer-head">
              <div>
                <Text type="secondary">候选资源</Text>
                <Paragraph className="resource-ops-drawer-title" ellipsis={{ rows: 2, expandable: false }}>
                  {data.item.display_text}
                </Paragraph>
              </div>
              <Space wrap size={[6, 6]}>
                <Tag color={data.item.value_status_source === 'manual' ? 'gold' : 'default'}>
                  {data.item.effective_value_status_label}
                </Tag>
                <Tag color={data.item.resource_kind_source === 'manual' ? 'cyan' : 'default'}>
                  {data.item.effective_resource_kind_label}
                </Tag>
                <Tag color={data.item.latest_link_health === 'invalid' ? 'error' : data.item.latest_link_health === 'warning' ? 'processing' : 'success'}>
                  {data.item.latest_link_health_label}
                </Tag>
              </Space>
            </div>

            <Descriptions column={2} size="small" className="resource-ops-drawer-descriptions">
              <Descriptions.Item label="平台">{data.item.platform}</Descriptions.Item>
              <Descriptions.Item label="分享键">{data.item.share_key || '-'}</Descriptions.Item>
              <Descriptions.Item label="建议动作">{data.item.suggested_action}</Descriptions.Item>
              <Descriptions.Item label="更新模式">{data.item.update_mode_label}</Descriptions.Item>
              <Descriptions.Item label="最近点击">{formatDateTime(data.item.last_clicked_at)}</Descriptions.Item>
              <Descriptions.Item label="最近出现">{formatDateTime(data.item.last_message_time)}</Descriptions.Item>
            </Descriptions>

            <div className="resource-ops-score-grid">
              <div className="resource-ops-score-card">
                <span>需求分</span>
                <strong>{data.item.demand_score.toFixed(1)}</strong>
              </div>
              <div className="resource-ops-score-card">
                <span>收益分</span>
                <strong>{data.item.value_score.toFixed(1)}</strong>
              </div>
              <div className="resource-ops-score-card resource-ops-score-card-risk">
                <span>成本分</span>
                <strong>{data.item.cost_score.toFixed(1)}</strong>
              </div>
              <div className="resource-ops-score-card resource-ops-score-card-risk">
                <span>风险分</span>
                <strong>{data.item.risk_score.toFixed(1)}</strong>
              </div>
              <div className="resource-ops-score-card resource-ops-score-card-highlight">
                <span>综合分</span>
                <strong>{data.item.overall_score.toFixed(1)}</strong>
              </div>
            </div>
          </Card>

          <Card title="运营策略" variant="outlined">
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
                    { value: 'unreviewed', label: '跟随系统建议' },
                    { value: 'not_worth', label: '不建议' },
                    { value: 'observe', label: '可观察' },
                    { value: 'worth', label: '值得做' },
                    { value: 'priority', label: '高优先' },
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
              <label>运营备注</label>
              <Input.TextArea value={note} onChange={(event) => setNote(event.target.value)} rows={4} maxLength={2000} />
            </div>
            <div className="resource-ops-drawer-actions">
              <Button type="primary" loading={saving} onClick={() => void handleSave()}>
                保存策略
              </Button>
              <Button href={data.item.target_url} target="_blank" rel="noopener noreferrer">
                打开原链接
              </Button>
            </div>
          </Card>

          <Card title="判断依据" variant="outlined">
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
            {data.auto_reasons.length > 0 && (
              <div className="resource-ops-auto-reasons">
                {data.auto_reasons.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            )}
          </Card>

          <Card title="近 14 天热度趋势" variant="outlined">
            <ResourceOpsTrendChart data={data.trend} height={260} />
          </Card>

          <Card title="最近关联消息" variant="outlined">
            <Table
              rowKey="message_id"
              dataSource={data.recent_refs}
              columns={refColumns}
              pagination={false}
              size="small"
              scroll={{ x: 680 }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无关联消息" /> }}
            />
          </Card>

          <Card title="操作日志" variant="outlined">
            {data.logs.length > 0 ? (
              <div className="resource-ops-log-list">
                {data.logs.map((log) => (
                  <div key={log.id} className="resource-ops-log-item">
                    <div className="resource-ops-log-head">
                      <strong>{log.action_summary}</strong>
                      <span>{formatDateTime(log.created_at)}</span>
                    </div>
                    <div className="resource-ops-log-meta">
                      操作人：{log.operator || '-'}
                    </div>
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

export default ResourceOpsWorkbenchDrawer
