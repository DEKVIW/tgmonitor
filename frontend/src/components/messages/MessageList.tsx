/**
 * 消息列表组件
 */

import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Empty, Pagination, Spin } from 'antd'
import { getPublicConfig } from '@/api/admin'
import { getMessages } from '@/api/messages'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useMessageStore } from '@/store/messageStore'
import type { PublicSystemConfigResponse } from '@/types/admin'
import { MessageListResponse } from '@/types/message'
import { trackEvent } from '@/utils/analytics'
import { PUBLIC_DASHBOARD_MAX_DAYS } from '@/utils/publicDashboard'
import PublicAdSlot from './PublicAdSlot'
import MessageItem from './MessageItemRuntime'
import './MessageList.css'

interface MessageListProps {
  isGuestMode?: boolean
}

const MessageList = ({ isGuestMode = false }: MessageListProps) => {
  const { filters, setFilters, refreshInterval, reloadToken } = useMessageStore()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<MessageListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [publicConfig, setPublicConfig] = useState<PublicSystemConfigResponse | null>(null)
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

  useEffect(() => {
    if (!isGuestMode) {
      setPublicConfig(null)
      return
    }

    let cancelled = false

    const loadPublicConfig = async () => {
      try {
        const config = await getPublicConfig()
        if (!cancelled) {
          setPublicConfig(config)
        }
      } catch {
        if (!cancelled) {
          setPublicConfig(null)
        }
      }
    }

    void loadPublicConfig()

    return () => {
      cancelled = true
    }
  }, [isGuestMode])

  const handlePageChange = (page: number, pageSize?: number) => {
    const nextPageSize = pageSize || filters.page_size
    setFilters({ page, page_size: nextPageSize })
    trackEvent('pagination_change', {
      audience: isGuestMode ? 'guest' : 'authenticated',
      page,
      page_size: nextPageSize || 0,
    })
  }

  const pickAdHtml = useCallback(
    (desktopHtml: string | undefined, mobileHtml: string | undefined) => {
      const desktop = (desktopHtml || '').trim()
      const mobile = (mobileHtml || '').trim()
      return isMobile ? mobile || desktop : desktop || mobile
    },
    [isMobile]
  )

  const adsEnabled = isGuestMode && !!publicConfig?.public_ads_enabled
  const topAdHtml = adsEnabled
    ? pickAdHtml(publicConfig?.public_feed_top_ad_html_desktop, publicConfig?.public_feed_top_ad_html_mobile)
    : ''
  const inlineAdHtml = adsEnabled
    ? pickAdHtml(publicConfig?.public_feed_inline_ad_html_desktop, publicConfig?.public_feed_inline_ad_html_mobile)
    : ''
  const inlineEvery = adsEnabled ? Math.max(publicConfig?.public_feed_inline_every_n || 0, 0) : 0

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
        {isGuestMode ? `（公开页面最多显示近 ${PUBLIC_DASHBOARD_MAX_DAYS} 天数据）` : ''}
      </div>

      {topAdHtml ? <PublicAdSlot placement="top" html={topAdHtml} /> : null}

      {data.messages.map((message, index) => (
        <Fragment key={message.id}>
          <MessageItem
            message={message}
            audience={isGuestMode ? 'guest' : 'authenticated'}
            sourcePage={isGuestMode ? 'public_dashboard' : 'dashboard'}
            searchQuery={filters.search_query || ''}
          />
          {inlineAdHtml && inlineEvery > 0 && (index + 1) % inlineEvery === 0 && index + 1 < data.messages.length ? (
            <PublicAdSlot placement="inline" html={inlineAdHtml} />
          ) : null}
        </Fragment>
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
