/**
 * 消息列表组件
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Empty, Pagination, Spin } from 'antd'
import { getMessages } from '@/api/messages'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useMessageStore } from '@/store/messageStore'
import { MessageListResponse } from '@/types/message'
import MessageItem from './MessageItem'
import './MessageList.css'

interface MessageListProps {
  isGuestMode?: boolean
}

const MessageList = ({ isGuestMode = false }: MessageListProps) => {
  const { filters, setFilters, refreshInterval, reloadToken } = useMessageStore()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<MessageListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const isMobile = useMediaQuery('(max-width: 768px)')
  const requestIdRef = useRef(0)

  const loadMessages = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setLoading(true)
    setError(null)

    try {
      const response = await getMessages(filters)
      if (requestId !== requestIdRef.current) {
        return
      }
      setData(response)
    } catch (err: unknown) {
      if (requestId !== requestIdRef.current) {
        return
      }
      const message =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      setError(message || '加载消息失败')
      setData(null)
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
      }
    }
  }, [filters])

  useEffect(() => {
    loadMessages()
  }, [loadMessages, reloadToken])

  useEffect(() => {
    if (!refreshInterval || refreshInterval <= 0) {
      return
    }

    const timer = window.setInterval(() => {
      loadMessages()
    }, refreshInterval * 1000)

    return () => window.clearInterval(timer)
  }, [loadMessages, refreshInterval])

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
        共找到 {data.total} 条消息
        {isGuestMode ? '（最近 24 小时）' : ''}
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
            showTotal={
              !isMobile
                ? (total, range) => `第 ${range[0]}-${range[1]} 条 / 共 ${total} 条`
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
