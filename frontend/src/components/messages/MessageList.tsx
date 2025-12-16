/**
 * 消息列表组件
 */

import { useState, useEffect } from 'react'
import { Spin, Empty, Pagination, Alert } from 'antd'
import { getMessages } from '@/api/messages'
import { MessageListResponse } from '@/types/message'
import { useMessageStore } from '@/store/messageStore'
import MessageItem from './MessageItem'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import './MessageList.css'

interface MessageListProps {
  isGuestMode?: boolean
}

const MessageList = ({ isGuestMode = false }: MessageListProps) => {
  const { filters, setFilters, refreshInterval } = useMessageStore()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<MessageListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const isMobile = useMediaQuery('(max-width: 768px)')

  // 加载消息列表
  const loadMessages = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await getMessages(filters)
      setData(response)
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载消息失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  // 当筛选条件变化时重新加载
  useEffect(() => {
    loadMessages()
  }, [
    filters.search_query,
    filters.time_range,
    filters.selected_tags,
    filters.selected_netdisks,
    filters.min_content_length,
    filters.has_links_only,
    filters.page,
    filters.page_size,
  ])

  // 自动刷新
  useEffect(() => {
    if (!refreshInterval || refreshInterval <= 0) return
    const timer = setInterval(() => {
      loadMessages()
    }, refreshInterval * 1000)
    return () => clearInterval(timer)
  }, [refreshInterval, filters])

  const handlePageChange = (page: number, pageSize?: number) => {
    setFilters({ page, page_size: pageSize || filters.page_size })
  }

  if (loading && !data) {
    return (
      <div className="message-list-loading">
        <Spin size="large" tip="正在加载消息...">
          <div style={{ width: 1, height: 120 }} />
        </Spin>
      </div>
    )
  }

  if (error) {
    return <Alert message="错误" description={error} type="error" showIcon />
  }

  if (!data || data.messages.length === 0) {
    return <Empty description="没有找到匹配的消息" />
  }

  return (
    <div className="message-list">
      <div className="message-total-hint">
        共找到 {data.total} 条消息{isGuestMode && '（最近24小时）'}
      </div>
      {data.messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}

      {data.max_page > 1 && (
        <div className="message-list-pagination">
          <Pagination
            current={data.page}
            total={data.total}
            pageSize={data.page_size}
            simple={isMobile}
            showSizeChanger={!isMobile}
            showQuickJumper={!isMobile}
            showLessItems={isMobile}
            showTotal={!isMobile ? (total, range) =>
              `第 ${range[0]}-${range[1]} 条 / 共 ${total} 条`
              : undefined
            }
            onChange={handlePageChange}
            onShowSizeChange={handlePageChange}
            pageSizeOptions={['50', '100', '200']}
          />
        </div>
      )}
    </div>
  )
}

export default MessageList

