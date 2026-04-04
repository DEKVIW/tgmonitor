import { useEffect, useRef, useState } from 'react'
import dayjs, { Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  InputNumber,
  Modal,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import {
  DeleteOutlined,
  EyeOutlined,
  HistoryOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  applyLinkCheckCleanup,
  deleteLinkCheckHistories,
  deleteLinkCheckHistory,
  getActiveLinkCheckTask,
  getLinkCheckDateRange,
  getLinkCheckHistory,
  getLinkCheckResult,
  getLinkCheckTaskStatus,
  startLinkCheckTask,
  stopLinkCheckTask,
} from '@/api/admin'
import type {
  LinkCheckDateRange,
  LinkCheckHistoryBatchDeleteResult,
  LinkCheckTaskCreate,
  LinkCheckTaskHistory,
  LinkCheckTaskResult,
  LinkCheckTaskStatus,
  LinkCleanupApplyRequest,
} from '@/types/admin'

const { Paragraph, Text } = Typography

type DateRangeValue = [Dayjs, Dayjs]
type InvalidLinkDetail = LinkCheckTaskResult['details'][number]

const TASK_POLL_INTERVAL = 2000

const statusLabelMap: Record<string, string> = {
  running: '进行中',
  stopping: '停止中',
  stopped: '已停止',
  completed: '已完成',
  failed: '失败',
}

const statusColorMap: Record<string, string> = {
  running: 'processing',
  stopping: 'warning',
  stopped: 'default',
  completed: 'success',
  failed: 'error',
}

const phaseLabelMap: Record<string, string> = {
  queued: '等待启动',
  loading_messages: '读取消息',
  checking_links: '检测链接',
  saving_results: '写入结果',
  completed: '已完成',
  failed: '失败',
  stopped: '已停止',
}

const formatDateTime = (value?: string) => {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

const formatHistoryDateTime = (value?: string) => {
  if (!value) {
    return '-'
  }
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY/MM/DD HH:mm') : value
}

const formatDuration = (seconds?: number) => {
  if (seconds === undefined || seconds === null) {
    return '-'
  }
  if (seconds < 60) {
    return `${seconds.toFixed(1)} 秒`
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)} 分 ${(seconds % 60).toFixed(0)} 秒`
  }
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`
}

const LinkCheckManagerEnhanced = () => {
  const [dateBounds, setDateBounds] = useState<LinkCheckDateRange | null>(null)
  const [dateRange, setDateRange] = useState<DateRangeValue>(() => {
    const today = dayjs()
    return [today, today]
  })
  const [dateRangeLoading, setDateRangeLoading] = useState(false)
  const [taskStarting, setTaskStarting] = useState(false)
  const [taskStopping, setTaskStopping] = useState(false)
  const [maxConcurrent, setMaxConcurrent] = useState(5)
  const [currentTask, setCurrentTask] = useState<LinkCheckTaskStatus | null>(null)
  const [history, setHistory] = useState<LinkCheckTaskHistory[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [resultModalVisible, setResultModalVisible] = useState(false)
  const [selectedResult, setSelectedResult] = useState<LinkCheckTaskResult | null>(null)
  const [resultLoading, setResultLoading] = useState(false)
  const [cleanupMode, setCleanupMode] = useState<LinkCleanupApplyRequest['mode']>('remove_invalid_links')
  const [cleanupLoading, setCleanupLoading] = useState(false)
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logConsoleRef = useRef<HTMLDivElement | null>(null)
  const [selectedHistoryIds, setSelectedHistoryIds] = useState<number[]>([])

  const minDate = dateBounds?.min_date ? dayjs(dateBounds.min_date) : null
  const maxDate = dayjs(dateBounds?.max_date || dayjs().format('YYYY-MM-DD'))
  const currentTaskRunning = currentTask?.status === 'running' || currentTask?.status === 'stopping'
  const selectedHistoryRows = history.filter((item) => selectedHistoryIds.includes(item.id))
  const selectedHistoryCheckTimes = selectedHistoryRows.map((item) => item.check_time)

  useEffect(() => {
    void loadInitialData()

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (logConsoleRef.current) {
      logConsoleRef.current.scrollTop = logConsoleRef.current.scrollHeight
    }
  }, [currentTask?.logs?.length])

  useEffect(() => {
    setSelectedHistoryIds((previous) => previous.filter((id) => history.some((item) => item.id === id)))
  }, [history])

  const loadInitialData = async () => {
    await Promise.all([loadHistory(), loadDateBounds(), restoreActiveTask()])
  }

  const loadDateBounds = async () => {
    setDateRangeLoading(true)
    try {
      const data = await getLinkCheckDateRange()
      setDateBounds(data)

      const nextMinDate = data.min_date ? dayjs(data.min_date) : null
      const nextMaxDate = dayjs(data.max_date || dayjs().format('YYYY-MM-DD'))
      const latestMessageDate = data.latest_message_date ? dayjs(data.latest_message_date) : nextMaxDate
      const safeStart = nextMinDate && latestMessageDate.isBefore(nextMinDate) ? nextMinDate : latestMessageDate
      const safeEnd = latestMessageDate.isAfter(nextMaxDate) ? nextMaxDate : latestMessageDate
      setDateRange([safeStart, safeEnd])
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载日期范围失败')
    } finally {
      setDateRangeLoading(false)
    }
  }

  const loadHistory = async () => {
    setHistoryLoading(true)
    try {
      const data = await getLinkCheckHistory(20)
      setHistory(data)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载检测历史失败')
    } finally {
      setHistoryLoading(false)
    }
  }

  const restoreActiveTask = async () => {
    try {
      const task = await getActiveLinkCheckTask()
      setCurrentTask(task)
      startPolling(task.task_id)
    } catch (error: any) {
      if (error?.response?.status !== 404) {
        console.error('restoreActiveTask failed', error)
      }
    }
  }

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }

  const startPolling = (taskId: string) => {
    stopPolling()

    pollingIntervalRef.current = setInterval(async () => {
      try {
        const status = await getLinkCheckTaskStatus(taskId)
        setCurrentTask(status)

        if (status.status === 'completed' || status.status === 'failed' || status.status === 'stopped') {
          stopPolling()
          await loadHistory()
        }
      } catch (error: any) {
        if (error?.response?.status !== 404) {
          console.error('getLinkCheckTaskStatus failed', error)
        }
      }
    }, TASK_POLL_INTERVAL)
  }

  const handleStartDateChange = (value: Dayjs | null) => {
    if (!value) {
      return
    }
    const nextEnd = value.isAfter(dateRange[1]) ? value : dateRange[1]
    setDateRange([value, nextEnd])
  }

  const handleEndDateChange = (value: Dayjs | null) => {
    if (!value) {
      return
    }
    const nextStart = value.isBefore(dateRange[0]) ? value : dateRange[0]
    setDateRange([nextStart, value])
  }

  const handleStartTask = async () => {
    if (!dateRange[0] || !dateRange[1]) {
      message.error('请选择检测日期范围')
      return
    }

    setTaskStarting(true)
    try {
      const taskData: LinkCheckTaskCreate = {
        period: `${dateRange[0].format('YYYY-MM-DD')}:${dateRange[1].format('YYYY-MM-DD')}`,
        max_concurrent: maxConcurrent,
      }
      const task = await startLinkCheckTask(taskData)
      setCurrentTask(task)
      startPolling(task.task_id)

      if (task.reused_existing) {
        message.info('已有检测任务正在执行，已恢复到当前任务')
      } else {
        message.success('检测任务已启动')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '启动检测任务失败')
    } finally {
      setTaskStarting(false)
    }
  }

  const handleStopTask = () => {
    if (!currentTask?.task_id || !currentTaskRunning) {
      return
    }

    Modal.confirm({
      title: '停止当前检测任务？',
      content: '会安全地等待当前批次收尾，不会强行中断数据库写入。',
      okText: '停止任务',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setTaskStopping(true)
        try {
          const nextTask = await stopLinkCheckTask(currentTask.task_id)
          setCurrentTask(nextTask)
          message.success('已发送停止请求')
        } catch (error: any) {
          message.error(error.response?.data?.detail || '停止任务失败')
        } finally {
          setTaskStopping(false)
        }
      },
    })
  }

  const handleViewResult = async (checkTime: string) => {
    setResultModalVisible(true)
    setSelectedResult(null)
    setResultLoading(true)

    try {
      const result = await getLinkCheckResult(checkTime)
      setSelectedResult(result)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '获取检测结果失败')
      setResultModalVisible(false)
    } finally {
      setResultLoading(false)
    }
  }

  const handleDeleteHistory = (checkTime: string) => {
    Modal.confirm({
      title: '删除这次检测历史？',
      content: '只删除检测记录，不会恢复已经做过的死链清理。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteLinkCheckHistory(checkTime)
          setSelectedHistoryIds((previous) => previous.filter((id) => !history.some((item) => item.id === id && item.check_time === checkTime)))
          if (selectedResult?.stats.check_time === checkTime) {
            setResultModalVisible(false)
            setSelectedResult(null)
          }
          await loadHistory()
          message.success('检测历史已删除')
        } catch (error: any) {
          message.error(error.response?.data?.detail || '删除检测历史失败')
        }
      },
    })
  }

  const handleBatchDeleteHistory = () => {
    if (selectedHistoryCheckTimes.length === 0) {
      message.warning('请先选择要删除的检测历史')
      return
    }

    Modal.confirm({
      title: `删除已选中的 ${selectedHistoryCheckTimes.length} 条检测历史？`,
      content: '只删除检测记录，不会恢复已经做过的死链清理。',
      okText: '批量删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const result: LinkCheckHistoryBatchDeleteResult = await deleteLinkCheckHistories({
            check_times: selectedHistoryCheckTimes,
          })

          if (
            selectedResult?.stats.check_time &&
            selectedHistoryCheckTimes.includes(selectedResult.stats.check_time)
          ) {
            setResultModalVisible(false)
            setSelectedResult(null)
          }

          setSelectedHistoryIds([])
          await loadHistory()

          const missingText =
            result.missing_check_times.length > 0
              ? `，另有 ${result.missing_check_times.length} 条记录已不存在`
              : ''
          message.success(`已删除 ${result.deleted_runs} 条检测历史${missingText}`)
        } catch (error: any) {
          message.error(error.response?.data?.detail || '批量删除检测历史失败')
        }
      },
    })
  }

  const handleApplyCleanup = () => {
    if (!selectedResult?.stats?.check_time) {
      return
    }

    const actionText =
      cleanupMode === 'delete_message_if_empty'
        ? '会移除本次检测确认失效的网盘链接；如果消息清理后没有任何有效网盘链接，就会删除整条消息。'
        : '只移除本次检测确认失效的网盘链接，保留消息正文和其他仍然有效的链接。'

    Modal.confirm({
      title: '确认应用死链清理',
      content: actionText,
      okText: '开始清理',
      cancelText: '取消',
      okButtonProps: { danger: cleanupMode === 'delete_message_if_empty' },
      onOk: async () => {
        setCleanupLoading(true)
        try {
          const result = await applyLinkCheckCleanup(selectedResult.stats.check_time, {
            mode: cleanupMode,
            dry_run: false,
          })
          message.success(
            `清理完成：移除 ${result.removed_links} 个失效链接，更新 ${result.updated_messages} 条消息，删除 ${result.deleted_messages} 条消息`
          )
          const refreshedResult = await getLinkCheckResult(selectedResult.stats.check_time)
          setSelectedResult(refreshedResult)
          await loadHistory()
        } catch (error: any) {
          message.error(error.response?.data?.detail || '应用死链清理失败')
        } finally {
          setCleanupLoading(false)
        }
      },
    })
  }

  const disabledDate = (current: Dayjs) => {
    if (current.isAfter(maxDate.endOf('day'))) {
      return true
    }
    if (minDate && current.isBefore(minDate.startOf('day'))) {
      return true
    }
    return false
  }

  const disabledStartDate = (current: Dayjs) => {
    if (disabledDate(current)) {
      return true
    }
    return current.isAfter(dateRange[1].endOf('day'))
  }

  const disabledEndDate = (current: Dayjs) => {
    if (disabledDate(current)) {
      return true
    }
    return current.isBefore(dateRange[0].startOf('day'))
  }

  const toggleHistorySelection = (record: LinkCheckTaskHistory) => {
    setSelectedHistoryIds((previous) =>
      previous.includes(record.id) ? previous.filter((id) => id !== record.id) : [...previous, record.id]
    )
  }

  const historyColumns: TableProps<LinkCheckTaskHistory>['columns'] = [
    {
      title: '检测时间',
      dataIndex: 'check_time',
      key: 'check_time',
      width: 160,
      render: (value: string) => <span title={formatDateTime(value)}>{formatHistoryDateTime(value)}</span>,
    },
    {
      title: '总链接数',
      dataIndex: 'total_links',
      key: 'total_links',
      width: 100,
      align: 'right',
    },
    {
      title: '有效',
      dataIndex: 'valid_links',
      key: 'valid_links',
      width: 90,
      align: 'right',
      render: (value: number) => <Tag color="success">{value}</Tag>,
    },
    {
      title: '失效',
      dataIndex: 'invalid_links',
      key: 'invalid_links',
      width: 90,
      align: 'right',
      render: (value: number) => <Tag color="error">{value}</Tag>,
    },
    {
      title: '耗时',
      dataIndex: 'duration',
      key: 'duration',
      width: 120,
      render: (value?: number) => formatDuration(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (value: string) => <Tag color={statusColorMap[value] || 'default'}>{statusLabelMap[value] || value}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 132,
      render: (_: unknown, record: LinkCheckTaskHistory) => (
        <Space size="small" wrap={false}>
          <Button
            size="small"
            type="link"
            icon={<EyeOutlined />}
            onClick={(event) => {
              event.stopPropagation()
              void handleViewResult(record.check_time)
            }}
          >
            查看
          </Button>
          <Button
            size="small"
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={(event) => {
              event.stopPropagation()
              handleDeleteHistory(record.check_time)
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const invalidDetails = selectedResult?.details.filter((detail) => !detail.is_valid) || []

  return (
    <div className="link-check-manager">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card title="新建检测任务">
          <div className="link-check-task-form">
            <div className="link-check-form-field link-check-form-field-wide">
              <Text strong>时间段</Text>
              <div className="link-check-date-range">
                <DatePicker
                  allowClear={false}
                  inputReadOnly
                  value={dateRange[0]}
                  format="YYYY-MM-DD"
                  disabledDate={disabledStartDate}
                  onChange={handleStartDateChange}
                  placeholder="开始日期"
                />
                <span className="link-check-date-separator">至</span>
                <DatePicker
                  allowClear={false}
                  inputReadOnly
                  value={dateRange[1]}
                  format="YYYY-MM-DD"
                  disabledDate={disabledEndDate}
                  onChange={handleEndDateChange}
                  placeholder="结束日期"
                />
              </div>
              <Text type="secondary" className="link-check-helper-text">
                {dateRangeLoading
                  ? '正在加载可选日期范围...'
                  : `最早消息 ${dateBounds?.min_date || '暂无'}，最新消息 ${dateBounds?.latest_message_date || '暂无'}，最多可选到今天`}
              </Text>
            </div>

            <div className="link-check-form-field">
              <Text strong>并发数</Text>
              <InputNumber min={1} max={10} value={maxConcurrent} onChange={(value) => setMaxConcurrent(value || 5)} />
            </div>

            <div className="link-check-form-actions">
              <Space wrap>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={taskStarting}
                  disabled={currentTaskRunning || dateRangeLoading}
                  onClick={() => void handleStartTask()}
                >
                  开始检测
                </Button>
                <Button
                  icon={<PauseCircleOutlined />}
                  danger
                  loading={taskStopping}
                  disabled={!currentTaskRunning}
                  onClick={handleStopTask}
                >
                  停止任务
                </Button>
              </Space>
            </div>
          </div>
        </Card>

        {currentTask && (
          <Card title="检测进度">
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <div>
                <Progress
                  percent={currentTask.progress || 0}
                  status={currentTask.status === 'failed' ? 'exception' : currentTask.status === 'completed' ? 'success' : 'active'}
                />
                <Space wrap size={[12, 8]} style={{ marginTop: 12 }}>
                  <Text>
                    状态：
                    <Tag color={statusColorMap[currentTask.status] || 'default'}>
                      {statusLabelMap[currentTask.status] || currentTask.status}
                    </Tag>
                  </Text>
                  <Text>范围：{currentTask.period_desc || '-'}</Text>
                  <Text>阶段：{phaseLabelMap[currentTask.current_phase || ''] || currentTask.current_phase || '-'}</Text>
                  <Text>当前平台：{currentTask.current_platform || '-'}</Text>
                  <Text>
                    进度：{currentTask.checked_links || 0} / {currentTask.total_links || 0}
                  </Text>
                  <Text>
                    有效 <Tag color="success">{currentTask.valid_links || 0}</Tag>
                  </Text>
                  <Text>
                    失效 <Tag color="error">{currentTask.invalid_links || 0}</Tag>
                  </Text>
                </Space>
              </div>

              <div className="link-check-log-console">
                <div className="link-check-log-console-header">
                  <Text strong>检测日志</Text>
                  <Button size="small" icon={<ReloadOutlined />} onClick={() => currentTask.task_id && startPolling(currentTask.task_id)}>
                    继续轮询
                  </Button>
                </div>
                {currentTask.logs && currentTask.logs.length > 0 ? (
                  <div ref={logConsoleRef} className="link-check-log-lines">
                    {currentTask.logs.map((log, index) => (
                      <div key={`${index}-${log}`} className="link-check-log-line">
                        {log}
                      </div>
                    ))}
                  </div>
                ) : (
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    暂无日志输出
                  </Paragraph>
                )}
              </div>

              {currentTask.error && (
                <Alert
                  message={currentTask.status === 'stopped' ? '任务已停止' : '任务提示'}
                  description={currentTask.error}
                  type={currentTask.status === 'failed' ? 'error' : 'info'}
                  showIcon
                />
              )}
            </Space>
          </Card>
        )}

        <Card
          title={
            <Space>
              <HistoryOutlined />
              <span>检测历史</span>
              <Button size="small" loading={historyLoading} onClick={() => void loadHistory()}>
                刷新
              </Button>
            </Space>
          }
          extra={
            <Space wrap size={[8, 8]}>
              <Text type="secondary">已选 {selectedHistoryIds.length} 项</Text>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={selectedHistoryIds.length === 0}
                onClick={handleBatchDeleteHistory}
              >
                批量删除
              </Button>
            </Space>
          }
        >
          <Table
            className="link-check-history-table"
            columns={historyColumns}
            dataSource={history}
            rowKey="id"
            loading={historyLoading}
            rowSelection={{
              selectedRowKeys: selectedHistoryIds,
              onChange: (keys) => setSelectedHistoryIds(keys.map((key) => Number(key))),
            }}
            pagination={false}
            tableLayout="auto"
            scroll={{ x: 'max-content' }}
            onRow={(record) => ({
              onClick: (event) => {
                const target = event.target as HTMLElement
                if (target.closest('button,a,.ant-checkbox-wrapper,.ant-checkbox-input,.ant-btn')) {
                  return
                }
                toggleHistorySelection(record)
              },
            })}
          />
        </Card>
      </Space>

      <Modal
        title="检测结果详情"
        open={resultModalVisible}
        rootClassName="responsive-modal-root"
        onCancel={() => {
          setResultModalVisible(false)
          setSelectedResult(null)
        }}
        footer={null}
        width={1000}
      >
        {resultLoading ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
          </div>
        ) : selectedResult ? (
          <div>
            <Descriptions title="统计信息" bordered column={2} style={{ marginBottom: 24 }}>
              <Descriptions.Item label="检测时间">{formatDateTime(selectedResult.stats.check_time)}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColorMap[selectedResult.stats.status] || 'default'}>
                  {statusLabelMap[selectedResult.stats.status] || selectedResult.stats.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="总消息数">{selectedResult.stats.total_messages}</Descriptions.Item>
              <Descriptions.Item label="总链接数">{selectedResult.stats.total_links}</Descriptions.Item>
              <Descriptions.Item label="有效链接">
                <Tag color="success">{selectedResult.stats.valid_links}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="失效链接">
                <Tag color="error">{selectedResult.stats.invalid_links}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="已更新消息">{selectedResult.stats.updated_messages ?? 0}</Descriptions.Item>
              <Descriptions.Item label="已删除消息">{selectedResult.stats.deleted_messages ?? 0}</Descriptions.Item>
              <Descriptions.Item label="检测耗时">{formatDuration(selectedResult.stats.duration)}</Descriptions.Item>
            </Descriptions>

            {invalidDetails.length > 0 && (
              <Card size="small" style={{ marginBottom: 16 }}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Alert
                    type="info"
                    showIcon
                    message="死链清理只会修改消息里的 links 字段"
                    description="前台消息列表直接读取消息中的网盘链接，清理后对应网盘标签和下载地址会自动消失。"
                  />
                  <Space wrap>
                    <Text strong>处理策略</Text>
                    <Select
                      value={cleanupMode}
                      onChange={(value) => setCleanupMode(value as LinkCleanupApplyRequest['mode'])}
                      style={{ width: 280 }}
                      options={[
                        { value: 'remove_invalid_links', label: '仅移除失效网盘链接' },
                        { value: 'delete_message_if_empty', label: '移除失效链接，空消息则删整条' },
                      ]}
                    />
                    <Button
                      type="primary"
                      danger={cleanupMode === 'delete_message_if_empty'}
                      loading={cleanupLoading}
                      onClick={handleApplyCleanup}
                    >
                      应用死链清理
                    </Button>
                  </Space>
                </Space>
              </Card>
            )}

            <div>
              <Text strong>失效链接详情（最多显示 1000 条）</Text>
              <Table<InvalidLinkDetail>
                dataSource={invalidDetails}
                rowKey={(record, index) => `${record.url}-${index}`}
                pagination={{ pageSize: 20 }}
                size="small"
                columns={[
                  {
                    title: '链接',
                    dataIndex: 'url',
                    key: 'url',
                    ellipsis: true,
                  },
                  {
                    title: '网盘类型',
                    dataIndex: 'netdisk_type',
                    key: 'netdisk_type',
                  },
                  {
                    title: '响应时间',
                    dataIndex: 'response_time',
                    key: 'response_time',
                    width: 120,
                    render: (value?: number) => (value ? `${value.toFixed(2)} 秒` : '-'),
                  },
                  {
                    title: '错误原因',
                    dataIndex: 'error_reason',
                    key: 'error_reason',
                    ellipsis: true,
                  },
                ]}
                tableLayout="auto"
                scroll={{ x: 'max-content' }}
                style={{ marginTop: 16 }}
              />
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

export default LinkCheckManagerEnhanced
