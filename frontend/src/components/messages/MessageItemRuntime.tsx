import { useState } from 'react'
import { Collapse, Space, Tag, Typography } from 'antd'
import { LinkOutlined } from '@ant-design/icons'

import type { MessageResponse, MessageTrackedLink } from '@/types/message'
import { API_BASE_URL, NETDISK_ICONS, TOKEN_KEY } from '@/utils/constants'
import { cleanPrefix, formatTime } from '@/utils/textUtils'

import './MessageItem.css'

const { Text, Paragraph } = Typography

const CLICK_SESSION_STORAGE_KEY = 'tg_resource_ops_session_key'
const PREPARED_LINK_TTL_MS = 1500

const NETDISK_LABEL_ALIASES: Record<string, string[]> = {
  百度网盘: ['百度网盘', '百度', 'baidu'],
  夸克网盘: ['夸克网盘', '夸克', 'quark', 'qk'],
  阿里云盘: ['阿里云盘', '阿里', 'aliyun', 'alipan'],
  天翼云盘: ['天翼云盘', '天翼', '189', 'ty'],
  迅雷网盘: ['迅雷网盘', '迅雷', 'xunlei', 'thunder', 'xl'],
  '115网盘': ['115网盘', '115', '115pan'],
  '123云盘': ['123云盘', '123', '123pan'],
  UC网盘: ['UC网盘', 'UC', 'ucdrive', 'ucdisk'],
  '139云盘': ['139云盘', '139', '139yun', '和彩云', 'caiyun'],
}

const normalizeNetdiskLabel = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/(网盘|云盘)$/g, '')

const formatLinkText = (name: string, label?: string | null) => {
  const trimmedLabel = label?.trim()
  if (!trimmedLabel) {
    return name
  }

  const aliasSet = new Set(
    (NETDISK_LABEL_ALIASES[name] || [name]).map((alias) => normalizeNetdiskLabel(alias))
  )
  if (aliasSet.has(normalizeNetdiskLabel(trimmedLabel))) {
    return name
  }
  return `${name} ${trimmedLabel}`
}

const getClickSessionKey = () => {
  const existing = window.sessionStorage.getItem(CLICK_SESSION_STORAGE_KEY)
  if (existing) {
    return existing
  }
  const nextValue =
    typeof window.crypto?.randomUUID === 'function'
      ? window.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  window.sessionStorage.setItem(CLICK_SESSION_STORAGE_KEY, nextValue)
  return nextValue
}

const createEventToken = () =>
  typeof window.crypto?.randomUUID === 'function'
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`

const sendTrackingBeacon = (payload: {
  link_ref_id: number
  event_token: string
  session_key: string
  source_page?: string
  search_query?: string
}) => {
  const token = window.localStorage.getItem(TOKEN_KEY)
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  void fetch(`${API_BASE_URL}/resource-ops/clicks/track`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    keepalive: true,
    credentials: 'same-origin',
  }).catch(() => undefined)
}

type LegacyLink = {
  provider_label: string
  link_label?: string | null
  display_text: string
  target_url: string
}

interface MessageItemProps {
  message: MessageResponse
  audience?: 'guest' | 'authenticated'
  sourcePage?: string
  searchQuery?: string
}

const MessageItemRuntime = ({
  message,
  audience = 'authenticated',
  sourcePage,
  searchQuery,
}: MessageItemProps) => {
  const [expanded, setExpanded] = useState(false)

  const trackedLinks = message.tracked_links || []

  const legacyLinks: LegacyLink[] = []
  if (trackedLinks.length === 0 && message.links) {
    Object.entries(message.links).forEach(([name, value]) => {
      if (Array.isArray(value)) {
        value.forEach((item) => {
          if (typeof item === 'object' && item?.url) {
            legacyLinks.push({
              provider_label: name,
              link_label: item.label,
              display_text: formatLinkText(name, item.label),
              target_url: item.url,
            })
          }
        })
        return
      }
      if (typeof value === 'string') {
        legacyLinks.push({
          provider_label: name,
          display_text: name,
          target_url: value,
        })
        return
      }
      if (typeof value === 'object' && value?.url) {
        legacyLinks.push({
          provider_label: name,
          link_label: value.label,
          display_text: formatLinkText(name, value.label),
          target_url: value.url,
        })
      }
    })
  }

  const renderNetdiskTags = () => {
    if (!message.links || Object.keys(message.links).length === 0) {
      return null
    }

    return Object.keys(message.links).map((name) => (
      <span key={name} className="netdisk-plain">
        {NETDISK_ICONS[name] || '🔗'} {name}
      </span>
    ))
  }

  const prepareTrackedNavigation = (anchor: HTMLAnchorElement, link: MessageTrackedLink) => {
    const now = Date.now()
    const preparedAt = Number(anchor.dataset.preparedAt || '0')
    if (preparedAt > 0 && now - preparedAt < PREPARED_LINK_TTL_MS) {
      return
    }

    const eventToken = createEventToken()
    const sessionKey = getClickSessionKey()
    const redirectUrl = new URL(link.redirect_url, window.location.origin)
    redirectUrl.searchParams.set('et', eventToken)
    redirectUrl.searchParams.set('sk', sessionKey)
    if (sourcePage) {
      redirectUrl.searchParams.set('sp', sourcePage)
    }
    const normalizedQuery = searchQuery?.trim()
    if (normalizedQuery) {
      redirectUrl.searchParams.set('sq', normalizedQuery.slice(0, 120))
    }

    anchor.href = redirectUrl.toString()
    anchor.dataset.preparedAt = String(now)

    sendTrackingBeacon({
      link_ref_id: link.link_ref_id,
      event_token: eventToken,
      session_key: sessionKey,
      source_page: sourcePage,
      search_query: normalizedQuery?.slice(0, 120),
    })
  }

  const renderTrackedLink = (link: MessageTrackedLink) => (
    <a
      key={`tracked-${link.link_ref_id}`}
      href={link.redirect_url}
      target="_blank"
      rel="noopener noreferrer"
      className="netdisk-link"
      data-umami-event="netdisk_click"
      data-umami-event-provider={link.provider_label}
      data-umami-event-link_text={link.display_text}
      data-umami-event-message_id={String(message.id)}
      data-umami-event-audience={audience}
      onMouseDown={(event) => {
        if (event.button === 0 || event.button === 1) {
          prepareTrackedNavigation(event.currentTarget, link)
        }
      }}
      onAuxClick={(event) => {
        if (event.button === 1) {
          prepareTrackedNavigation(event.currentTarget, link)
        }
      }}
      onClick={(event) => {
        prepareTrackedNavigation(event.currentTarget, link)
      }}
    >
      {link.display_text}
    </a>
  )

  const renderLegacyLink = (link: LegacyLink, index: number) => (
    <a
      key={`legacy-${link.provider_label}-${index}`}
      href={link.target_url}
      target="_blank"
      rel="noopener noreferrer"
      className="netdisk-link"
      data-umami-event="netdisk_click"
      data-umami-event-provider={link.provider_label}
      data-umami-event-link_text={link.display_text}
      data-umami-event-message_id={String(message.id)}
      data-umami-event-audience={audience}
    >
      {link.display_text}
    </a>
  )

  const renderLinks = () => {
    const linkElements =
      trackedLinks.length > 0
        ? trackedLinks.map((link) => renderTrackedLink(link))
        : legacyLinks.map((link, index) => renderLegacyLink(link, index))

    if (linkElements.length === 0) {
      return null
    }

    return (
      <div className="message-links">
        <Text strong>
          <LinkOutlined /> 下载链接:
        </Text>
        <Space wrap style={{ marginTop: 8 }}>
          {linkElements}
        </Space>
      </div>
    )
  }

  const renderTags = () => {
    if (!message.tags || message.tags.length === 0) {
      return null
    }

    return (
      <div className="message-tags">
        <Text strong>标签:</Text>
        <Space wrap style={{ marginTop: 8 }}>
          {message.tags.map((tag) => (
            <Tag key={tag} color="blue" className="message-tag">
              #{tag}
            </Tag>
          ))}
        </Space>
      </div>
    )
  }

  const timeStr = formatTime(message.timestamp)
  const netdiskTags = renderNetdiskTags()

  return (
    <div className="message-item">
      <Collapse
        activeKey={expanded ? ['1'] : []}
        onChange={(keys) => {
          if (Array.isArray(keys)) {
            setExpanded(keys.includes('1'))
          } else {
            setExpanded(keys === '1')
          }
        }}
        bordered
        className="message-collapse"
        expandIconPosition="end"
        expandIcon={({ isActive }) => (
          <span className="collapse-arrow">{isActive ? '▼' : '▶'}</span>
        )}
        items={[
          {
            key: '1',
            label: (
              <div className="message-header">
                <Text strong className="message-title">
                  {message.title || '无标题'} <span className="message-time-inline">{timeStr}</span>
                  {netdiskTags ? <span className="netdisk-tags-inline">{netdiskTags}</span> : null}
                </Text>
              </div>
            ),
            children: (
              <div className="message-content">
                <div className="message-detail-time">
                  <Text type="secondary">详细时间: {new Date(message.timestamp).toLocaleString('zh-CN')}</Text>
                </div>

                {message.description ? (
                  <Paragraph className="message-description">
                    <Text strong>描述:</Text>
                    {cleanPrefix(message.description)}
                  </Paragraph>
                ) : null}

                {renderLinks()}
                {renderTags()}
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}

export default MessageItemRuntime
