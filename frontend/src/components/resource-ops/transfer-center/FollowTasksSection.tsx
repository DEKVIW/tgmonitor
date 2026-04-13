import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Descriptions, Drawer, Empty, Popconfirm, Segmented, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

import {
  deletePanTransferFollowTask,
  getPanTransferFollowTaskDetail,
  listPanTransferFollowTasks,
  pausePanTransferFollowTask,
  queuePanTransferFollowTaskCheck,
  resumePanTransferFollowTask,
} from '@/api/panTransfer'
import type { PanTransferFollowTaskDetailResponse, PanTransferFollowTaskItem } from '@/types/panTransfer'
import { formatServerDateTime } from '@/utils/dateTime'

import { getErrorMessage } from './shared'

const { Title, Paragraph, Text } = Typography

type FollowTasksSectionProps = {
  refreshToken: number
}

type FollowStatusFilter = 'all' | 'active' | 'paused'

const TASK_STATUS_META: Record<string, { color: string; label: string }> = {
  active: { color: 'processing', label: '启用中' },
  paused: { color: 'default', label: '已暂停' },
}

const TASK_STATE_META: Record<string, { color: string; label: string }> = {
  idle: { color: 'success', label: '正常跟踪' },
  queued: { color: 'processing', label: '等待检查' },
  checking: { color: 'processing', label: '检查中' },
  candidate_found: { color: 'warning', label: '发现候选更新' },
  source_invalid: { color: 'error', label: '原链失效' },
  share_invalid: { color: 'error', label: '新分享异常' },
  error: { color: 'error', label: '检查失败' },
}

const LINK_STATUS_META: Record<string, { color: string; label: string }> = {
  valid: { color: 'success', label: '有效' },
  healthy: { color: 'success', label: '有效' },
  warning: { color: 'warning', label: '存疑' },
  invalid: { color: 'error', label: '失效' },
  error: { color: 'error', label: '异常' },
  unknown: { color: 'default', label: '未知' },
}

const FOLLOW_CHANGE_LABELS: Record<string, string> = {
  candidate_found: '发现候选更新',
  source_invalid: '原链失效',
  share_invalid: '新分享异常',
  no_change: '本次无变化',
}

const formatDateTime = (value?: string | null, format = 'YYYY-MM-DD HH:mm') =>
  value ? formatServerDateTime(value, format, 'Asia/Shanghai') : '-'

const formatTerminalLine = (level: string, stage: string, createdAt?: string | null, messageText?: string | null) =>
  `[${formatDateTime(createdAt, 'HH:mm:ss')}] [${stage || 'general'}] [${String(level || 'info').toUpperCase()}] ${messageText || ''}`

const getTerminalLineClassName = (level: string) => {
  const normalized = String(level || '').toLowerCase()
  if (normalized === 'error') return 'resource-ops-transfer-terminal-line is-error'
  if (normalized === 'warning') return 'resource-ops-transfer-terminal-line is-warning'
  return 'resource-ops-transfer-terminal-line'
}

const FollowTasksSection = ({ refreshToken }: FollowTasksSectionProps) => {
  const [tasks, setTasks] = useState<PanTransferFollowTaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<FollowStatusFilter>('all')
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10, total: 0 })
  const [queueingTaskId, setQueueingTaskId] = useState<number | null>(null)
  const [togglingTaskId, setTogglingTaskId] = useState<number | null>(null)
  const [deletingTaskId, setDeletingTaskId] = useState<number | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<PanTransferFollowTaskDetailResponse | null>(null)

  const loadTasks = async (page = pagination.page, pageSize = pagination.pageSize, filter = statusFilter) => {
    setLoading(true)
    try {
      const response = await listPanTransferFollowTasks(page, pageSize, filter === 'all' ? undefined : filter)
      setTasks(response.items)
      setPagination({ page: response.page, pageSize: response.page_size, total: response.total })
    } catch (error) {
      message.error(getErrorMessage(error, '加载追更任务失败'))
    } finally {
      setLoading(false)
    }
  }

  const loadTaskDetail = async (taskId: number, options?: { open?: boolean; silent?: boolean }) => {
    if (!(options?.silent ?? false)) {
      setDetailLoading(true)
    }
    try {
      const response = await getPanTransferFollowTaskDetail(taskId)
      setDetailData(response)
      if (options?.open ?? true) {
        setDetailOpen(true)
      }
    } catch (error) {
      message.error(getErrorMessage(error, '加载追更任务详情失败'))
    } finally {
      if (!(options?.silent ?? false)) {
        setDetailLoading(false)
      }
    }
  }

  useEffect(() => {
    void loadTasks(1, pagination.pageSize, statusFilter)
  }, [refreshToken, statusFilter])

  useEffect(() => {
    if (!detailOpen || !detailData) return
    if (!['queued', 'checking'].includes(detailData.task.task_state)) return

    const taskId = detailData.task.id
    const timer = window.setInterval(() => {
      void loadTaskDetail(taskId, { open: false, silent: true })
      void loadTasks(pagination.page, pagination.pageSize, statusFilter)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [detailOpen, detailData?.task.id, detailData?.task.task_state, pagination.page, pagination.pageSize, statusFilter])

  const summary = useMemo(() => {
    const activeCount = tasks.filter((item) => item.status === 'active').length
    const alertCount = tasks.filter((item) => ['candidate_found', 'source_invalid', 'share_invalid', 'error'].includes(item.task_state)).length
    const pausedCount = tasks.filter((item) => item.status === 'paused').length
    return { activeCount, alertCount, pausedCount }
  }, [tasks])

  const columns: ColumnsType<PanTransferFollowTaskItem> = [
    {
      title: '任务',
      dataIndex: 'task_name',
      key: 'task_name',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-title-cell">
          <span className="resource-ops-transfer-title-main">{record.task_name}</span>
          <span className="resource-ops-transfer-title-sub">
            {record.work_title || record.topic_title || `任务 #${record.id}`}
          </span>
        </div>
      ),
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 96,
      render: (value) => <Tag>{value}</Tag>,
    },
    {
      title: '原链',
      dataIndex: 'source_url',
      key: 'source_url',
      width: 240,
      render: (value: string) => (
        <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
          {value}
        </a>
      ),
    },
    {
      title: '目标账号 / 目录',
      key: 'target',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>{record.target_account_name || '未指定账号'}</small>
          <small title={record.fixed_save_path}>{record.fixed_save_path || '未记录固定目录'}</small>
        </div>
      ),
    },
    {
      title: '当前对外分享',
      dataIndex: 'current_share_url',
      key: 'current_share_url',
      width: 240,
      render: (value?: string | null) =>
        value ? (
          <a href={value} target="_blank" rel="noreferrer" className="resource-ops-transfer-url" title={value}>
            {value}
          </a>
        ) : (
          <Text type="secondary">尚未记录</Text>
        ),
    },
    {
      title: '原链状态',
      dataIndex: 'source_link_status',
      key: 'source_link_status',
      width: 110,
      render: (value) => {
        const meta = LINK_STATUS_META[String(value || '').toLowerCase()] || { color: 'default', label: value || '未知' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '新分享状态',
      dataIndex: 'current_share_status',
      key: 'current_share_status',
      width: 110,
      render: (value) => {
        const meta = LINK_STATUS_META[String(value || '').toLowerCase()] || { color: 'default', label: value || '未知' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '最近变化',
      key: 'last_change_type',
      width: 220,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <Space wrap size={[6, 6]}>
            <Tag color={(TASK_STATUS_META[record.status] || { color: 'default' }).color}>
              {(TASK_STATUS_META[record.status] || { label: record.status }).label}
            </Tag>
            <Tag color={(TASK_STATE_META[record.task_state] || { color: 'default' }).color}>
              {(TASK_STATE_META[record.task_state] || { label: record.task_state }).label}
            </Tag>
          </Space>
          <small>{FOLLOW_CHANGE_LABELS[record.last_change_type || ''] || '等待首次检查'}</small>
          {record.last_candidate_title ? <small>{record.last_candidate_title}</small> : null}
        </div>
      ),
    },
    {
      title: '同步时间',
      key: 'sync_time',
      width: 176,
      render: (_, record) => (
        <div className="resource-ops-transfer-validation">
          <small>上次 {formatDateTime(record.last_checked_at)}</small>
          <small>下次 {formatDateTime(record.next_check_at)}</small>
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 230,
      fixed: 'right',
      render: (_, record) => (
        <Space wrap size={[6, 6]}>
          <Button size="small" onClick={() => void loadTaskDetail(record.id, { open: true })}>
            详情
          </Button>
          <Button
            size="small"
            loading={queueingTaskId === record.id}
            disabled={record.status !== 'active'}
            onClick={() => void (async () => {
              setQueueingTaskId(record.id)
              try {
                const response = await queuePanTransferFollowTaskCheck(record.id)
                setDetailData((current) => (current?.task.id === record.id ? response : current))
                message.success(`追更任务 #${record.id} 已加入立即检查队列`)
                await loadTasks(pagination.page, pagination.pageSize, statusFilter)
              } catch (error) {
                message.error(getErrorMessage(error, '加入检查队列失败'))
              } finally {
                setQueueingTaskId(null)
              }
            })()}
          >
            立即检查
          </Button>
          {record.status === 'active' ? (
            <Button
              size="small"
              loading={togglingTaskId === record.id}
              onClick={() => void (async () => {
                setTogglingTaskId(record.id)
                try {
                  const response = await pausePanTransferFollowTask(record.id)
                  setDetailData((current) => (current?.task.id === record.id ? response : current))
                  message.success(`追更任务 #${record.id} 已暂停`)
                  await loadTasks(pagination.page, pagination.pageSize, statusFilter)
                } catch (error) {
                  message.error(getErrorMessage(error, '暂停追更任务失败'))
                } finally {
                  setTogglingTaskId(null)
                }
              })()}
            >
              暂停
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              loading={togglingTaskId === record.id}
              onClick={() => void (async () => {
                setTogglingTaskId(record.id)
                try {
                  const response = await resumePanTransferFollowTask(record.id)
                  setDetailData((current) => (current?.task.id === record.id ? response : current))
                  message.success(`追更任务 #${record.id} 已恢复`)
                  await loadTasks(pagination.page, pagination.pageSize, statusFilter)
                } catch (error) {
                  message.error(getErrorMessage(error, '恢复追更任务失败'))
                } finally {
                  setTogglingTaskId(null)
                }
              })()}
            >
              恢复
            </Button>
          )}
          <Popconfirm
            title={`确认删除追更任务 #${record.id} 吗？`}
            description="仅删除追更跟踪记录和日志，不会删除已转存的数据或前台消息。"
            onConfirm={() => void (async () => {
              setDeletingTaskId(record.id)
              try {
                await deletePanTransferFollowTask(record.id)
                if (detailData?.task.id === record.id) {
                  setDetailOpen(false)
                  setDetailData(null)
                }
                message.success(`追更任务 #${record.id} 已删除`)
                const nextPage = pagination.page > 1 && tasks.length === 1 ? pagination.page - 1 : pagination.page
                await loadTasks(nextPage, pagination.pageSize, statusFilter)
              } catch (error) {
                message.error(getErrorMessage(error, '删除追更任务失败'))
              } finally {
                setDeletingTaskId(null)
              }
            })()}
          >
            <Button size="small" danger loading={deletingTaskId === record.id}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <Card className="resource-ops-panel-card">
        <div className="resource-ops-transfer-card-head">
          <div>
            <Title level={4}>追更同步</Title>
            <Paragraph className="resource-ops-transfer-copy">
              跟踪已经完成转存的资源，持续检查原链与当前对外分享的状态，并记录同主题的新候选来源。
              当前由现有 `tg-worker` 负责按间隔自动巡检，也支持管理员手动立即检查。
            </Paragraph>
          </div>
          <Segmented
            value={statusFilter}
            options={[
              { label: '全部任务', value: 'all' },
              { label: '启用中', value: 'active' },
              { label: '已暂停', value: 'paused' },
            ]}
            onChange={(value) => setStatusFilter(value as FollowStatusFilter)}
          />
        </div>

        <div className="resource-ops-transfer-summary">
          <div className="resource-ops-transfer-summary-item">
            <span>任务总数</span>
            <strong>{pagination.total}</strong>
            <small>当前筛选条件下的追更任务总量</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页启用中</span>
            <strong>{summary.activeCount}</strong>
            <small>仍会被 worker 按间隔自动检查</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页待关注</span>
            <strong>{summary.alertCount}</strong>
            <small>候选更新、原链失效、新分享异常都算在内</small>
          </div>
          <div className="resource-ops-transfer-summary-item">
            <span>当前页已暂停</span>
            <strong>{summary.pausedCount}</strong>
            <small>暂停后不会继续自动检查，恢复时会立即重新排队</small>
          </div>
        </div>

        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          loading={loading}
          dataSource={tasks}
          columns={columns}
          onChange={(tablePagination: TablePaginationConfig) =>
            void loadTasks(tablePagination.current || 1, tablePagination.pageSize || pagination.pageSize, statusFilter)
          }
          pagination={{
            current: pagination.page,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
          }}
          scroll={{ x: 1860 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无追更任务" /> }}
        />
      </Card>

      <Drawer
        width={980}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailData ? `追更任务 #${detailData.task.id}` : '追更任务详情'}
        extra={
          detailData ? (
            <Space>
              <Button loading={detailLoading} onClick={() => void loadTaskDetail(detailData.task.id, { open: false })}>
                刷新详情
              </Button>
              {detailData.task.status === 'active' ? (
                <Button
                  loading={queueingTaskId === detailData.task.id}
                  onClick={() => void (async () => {
                    setQueueingTaskId(detailData.task.id)
                    try {
                      const response = await queuePanTransferFollowTaskCheck(detailData.task.id)
                      setDetailData(response)
                      message.success(`追更任务 #${detailData.task.id} 已加入立即检查队列`)
                      await loadTasks(pagination.page, pagination.pageSize, statusFilter)
                    } catch (error) {
                      message.error(getErrorMessage(error, '加入检查队列失败'))
                    } finally {
                      setQueueingTaskId(null)
                    }
                  })()}
                >
                  立即检查
                </Button>
              ) : null}
            </Space>
          ) : null
        }
      >
        {detailData ? (
          <div className="resource-ops-transfer-drawer-stack">
            <Descriptions
              size="small"
              column={2}
              bordered
              items={[
                {
                  key: 'status',
                  label: '任务状态',
                  children: (
                    <Space wrap size={[6, 6]}>
                      <Tag color={(TASK_STATUS_META[detailData.task.status] || { color: 'default' }).color}>
                        {(TASK_STATUS_META[detailData.task.status] || { label: detailData.task.status }).label}
                      </Tag>
                      <Tag color={(TASK_STATE_META[detailData.task.task_state] || { color: 'default' }).color}>
                        {(TASK_STATE_META[detailData.task.task_state] || { label: detailData.task.task_state }).label}
                      </Tag>
                    </Space>
                  ),
                },
                { key: 'topic', label: '资源主题', children: detailData.task.work_title || detailData.task.topic_title },
                { key: 'account', label: '目标账号', children: detailData.task.target_account_name || '-' },
                { key: 'path', label: '固定目标目录', children: detailData.task.fixed_save_path || '-' },
                { key: 'source', label: '原链状态', children: detailData.task.source_link_status || '-' },
                { key: 'share', label: '新分享状态', children: detailData.task.current_share_status || '-' },
                { key: 'last_checked', label: '上次同步', children: formatDateTime(detailData.task.last_checked_at) },
                { key: 'next_check', label: '下次检查', children: formatDateTime(detailData.task.next_check_at) },
              ]}
            />

            <Card size="small" title="执行终端" className="resource-ops-transfer-log-card">
              <Paragraph className="resource-ops-transfer-copy">
                这里按真实执行顺序输出追更巡检日志，优先用于定位“原链是否失效”“新分享是否异常”“是否发现新的候选来源”。
              </Paragraph>
              <div className="resource-ops-terminal resource-ops-transfer-terminal">
                {detailData.logs.length > 0 ? (
                  detailData.logs.map((log) => (
                    <div key={log.id} className={getTerminalLineClassName(log.level)}>
                      {formatTerminalLine(log.level, log.stage, log.created_at, log.message)}
                    </div>
                  ))
                ) : (
                  <div className="resource-ops-terminal-empty">暂无追更巡检日志</div>
                )}
              </div>
            </Card>
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无追更任务详情" />
        )}
      </Drawer>
    </>
  )
}

export default FollowTasksSection
