/**
 * 链接检测管理组件
 */

import { useState, useEffect, useRef } from 'react'
import {
  Card,
  Button,
  Select,
  InputNumber,
  message,
  Progress,
  Table,
  Space,
  Typography,
  Modal,
  Tag,
  Descriptions,
  Alert,
  List,
  Spin,
} from 'antd'
import {
  PlayCircleOutlined,
  HistoryOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import {
  startLinkCheckTask,
  getLinkCheckTaskStatus,
  getLinkCheckHistory,
  getLinkCheckResult,
  applyLinkCheckCleanup,
} from '@/api/admin'
import {
  LinkCleanupApplyRequest,
  LinkCheckTaskCreate,
  LinkCheckTaskStatus,
  LinkCheckTaskHistory,
  LinkCheckTaskResult,
} from '@/types/admin'

const { Option } = Select
const { Text } = Typography

const LinkCheckManager = () => {
  const [period, setPeriod] = useState('today')
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
  const pollingNotFoundCountRef = useRef(0)

  useEffect(() => {
    loadHistory()

    // 清理轮询
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [])

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

  const startTask = async () => {
    try {
      const taskData: LinkCheckTaskCreate = {
        period,
        max_concurrent: maxConcurrent,
      }
      const task = await startLinkCheckTask(taskData)
      setCurrentTask(task)
      pollingNotFoundCountRef.current = 0
      message.success('检测任务已启动')

      // 开始轮询任务状态
      startPolling(task.task_id)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '启动检测任务失败')
    }
  }

  const startPolling = (taskId: string) => {
    pollingNotFoundCountRef.current = 0
    // 清除之前的轮询
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
    }

    // 开始新的轮询
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const status = await getLinkCheckTaskStatus(taskId)
        pollingNotFoundCountRef.current = 0
        setCurrentTask(status)

        // 如果任务完成或失败，停止轮询
        if (status.status === 'completed' || status.status === 'failed') {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
          loadHistory() // 刷新历史记录
        }
      } catch (error: any) {
        if (error?.response?.status === 404) {
          pollingNotFoundCountRef.current += 1
          return
        }
        console.error('获取任务状态失败:', error)
      }
    }, 2000) // 每2秒轮询一次
  }

  const handleViewResult = async (checkTime: string) => {
    setResultLoading(true)
    setResultModalVisible(true)
    setSelectedResult(null)

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

  const handleApplyCleanup = () => {
    if (!selectedResult?.stats?.check_time) return

    const actionText =
      cleanupMode === 'delete_message_if_empty'
        ? '移除本次检测确认失效的网盘链接；如果消息已没有有效链接，则删除整条消息。'
        : '仅移除本次检测确认失效的网盘链接，保留消息正文和其他有效网盘链接。'

    Modal.confirm({
      title: '确认应用死链清理？',
      content: actionText,
      okText: '确认清理',
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

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '-'
    if (seconds < 60) return `${seconds.toFixed(1)}秒`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分${(seconds % 60).toFixed(0)}秒`
    return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分`
  }

  const historyColumns = [
    {
      title: '检测时间',
      dataIndex: 'check_time',
      key: 'check_time',
      ellipsis: true,
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '时间段',
      dataIndex: 'period_desc',
      key: 'period_desc',
      ellipsis: true,
      render: () => '最近检测',
    },
    {
      title: '链接总数',
      dataIndex: 'total_links',
      key: 'total_links',
      width: 100,
      align: 'right' as const,
    },
    {
      title: '有效',
      dataIndex: 'valid_links',
      width: 80,
      align: 'right' as const,
      key: 'valid_links',
      render: (count: number) => <Tag color="success">{count}</Tag>,
    },
    {
      title: '失效',
      dataIndex: 'invalid_links',
      key: 'invalid_links',
      width: 80,
      align: 'right' as const,
      render: (count: number) => <Tag color="error">{count}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'processing'}>
          {status === 'completed' ? '完成' : status === 'failed' ? '失败' : '进行中'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: LinkCheckTaskHistory) => (
        <Button
          type="link"
          icon={<EyeOutlined />}
          onClick={() => handleViewResult(record.check_time)}
        >
          查看
        </Button>
      ),
    },
  ]

  const invalidDetails = selectedResult?.details.filter((detail) => !detail.is_valid) || []

  return (
    <div className="link-check-manager">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 新建检测任务 */}
        <Card title="🔗 新建检测任务">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Text strong>时间段: </Text>
              <Select
                value={period}
                onChange={setPeriod}
                style={{ width: 200, marginLeft: 8 }}
              >
                <Option value="today">今天</Option>
                <Option value="yesterday">昨天</Option>
                <Option value="week">最近7天</Option>
                <Option value="month">最近30天</Option>
                <Option value="year">最近365天</Option>
              </Select>
            </div>

            <div>
              <Text strong>并发数: </Text>
              <InputNumber
                min={1}
                max={10}
                value={maxConcurrent}
                onChange={(value) => setMaxConcurrent(value || 5)}
                style={{ marginLeft: 8 }}
              />
            </div>

            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={startTask}
              disabled={currentTask?.status === 'running'}
            >
              开始检测
            </Button>
          </Space>
        </Card>

        {/* 检测进度 */}
        {currentTask && (
          <Card title="📊 检测进度">
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <div>
                <Progress
                  percent={currentTask.progress}
                  status={currentTask.status === 'failed' ? 'exception' : 'active'}
                />
                <div style={{ marginTop: 8 }}>
                  <Text>
                    状态: {currentTask.status === 'running' ? '进行中' : currentTask.status === 'completed' ? '完成' : '失败'}
                  </Text>
                  {currentTask.total_links && (
                    <Text style={{ marginLeft: 16 }}>
                      已检测: {currentTask.checked_links || 0} / {currentTask.total_links}
                    </Text>
                  )}
                  {currentTask.valid_links !== undefined && (
                    <Text style={{ marginLeft: 16 }}>
                      有效: <Tag color="success">{currentTask.valid_links}</Tag>
                    </Text>
                  )}
                  {currentTask.invalid_links !== undefined && (
                    <Text style={{ marginLeft: 8 }}>
                      失效: <Tag color="error">{currentTask.invalid_links}</Tag>
                    </Text>
                  )}
                </div>
              </div>

              {currentTask.logs && currentTask.logs.length > 0 && (
                <div>
                  <Text strong>日志:</Text>
                  <List
                    size="small"
                    dataSource={currentTask.logs}
                    renderItem={(log) => <List.Item>{log}</List.Item>}
                    style={{ maxHeight: 200, overflow: 'auto', marginTop: 8 }}
                  />
                </div>
              )}

              {currentTask.error && (
                <Alert
                  message="错误"
                  description={currentTask.error}
                  type="error"
                  showIcon
                />
              )}

              {currentTask.status === 'completed' && (
                <Alert
                  message="检测完成"
                  description={`检测耗时: ${formatDuration(currentTask.duration)}`}
                  type="success"
                  showIcon
                />
              )}
            </Space>
          </Card>
        )}

        {/* 检测历史 */}
        <Card
          title={
            <Space>
              <HistoryOutlined />
              <span>检测历史</span>
              <Button
                size="small"
                onClick={loadHistory}
                loading={historyLoading}
              >
                刷新
              </Button>
            </Space>
          }
        >
          <Table
            columns={historyColumns}
            dataSource={history}
            rowKey="id"
            loading={historyLoading}
            tableLayout="auto"
            scroll={{ x: 'max-content' }}
            pagination={false}
          />
        </Card>
      </Space>

      {/* 检测结果Modal */}
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
              <Descriptions.Item label="检测时间">
                {new Date(selectedResult.stats.check_time).toLocaleString('zh-CN')}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={selectedResult.stats.status === 'completed' ? 'success' : 'error'}>
                  {selectedResult.stats.status === 'completed' ? '完成' : '失败'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="总消息数">
                {selectedResult.stats.total_messages}
              </Descriptions.Item>
              <Descriptions.Item label="总链接数">
                {selectedResult.stats.total_links}
              </Descriptions.Item>
              <Descriptions.Item label="有效链接">
                <Tag color="success">{selectedResult.stats.valid_links}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="失效链接">
                <Tag color="error">{selectedResult.stats.invalid_links}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="已更新消息">
                {selectedResult.stats.updated_messages ?? 0}
              </Descriptions.Item>
              <Descriptions.Item label="已删除消息">
                {selectedResult.stats.deleted_messages ?? 0}
              </Descriptions.Item>
              <Descriptions.Item label="检测耗时">
                {formatDuration(selectedResult.stats.duration)}
              </Descriptions.Item>
            </Descriptions>

            {invalidDetails.length > 0 && (
              <Card size="small" style={{ marginBottom: 16 }}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Alert
                    type="info"
                    showIcon
                    message="死链清理会修改消息数据，但不会删除这次检测历史记录"
                    description="普通前台消息页直接读取消息里的 links 字段，因此清理后，对应网盘标签和下载链接会自动消失。"
                  />
                  <Space wrap>
                    <Text strong>处理策略:</Text>
                    <Select<LinkCleanupApplyRequest['mode']>
                      value={cleanupMode}
                      onChange={setCleanupMode}
                      style={{ width: 260 }}
                    >
                      <Option value="remove_invalid_links">仅移除失效网盘链接</Option>
                      <Option value="delete_message_if_empty">移除失效链接，空消息则删除整条</Option>
                    </Select>
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
              <Text strong>失效链接详情（最多显示1000条）:</Text>
              <Table
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
                    width: 100,
                    render: (time?: number) => (time ? `${time.toFixed(2)}秒` : '-'),
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

export default LinkCheckManager
