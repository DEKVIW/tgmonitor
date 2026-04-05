/**
 * 消息项组件
 */

import { useState } from 'react'
import { Collapse, Tag, Space, Typography } from 'antd'
import { LinkOutlined } from '@ant-design/icons'
import { MessageResponse } from '@/types/message'
import { formatTime, cleanPrefix } from '@/utils/textUtils'
import { NETDISK_ICONS } from '@/utils/constants'
import './MessageItem.css'

const { Text, Paragraph } = Typography

const NETDISK_LABEL_ALIASES: Record<string, string[]> = {
  百度网盘: ['百度网盘', '百度', '百度盘', 'baidu'],
  夸克网盘: ['夸克网盘', '夸克', 'quark', 'qk'],
  阿里云盘: ['阿里云盘', '阿里', '阿里云', 'aliyun', 'alipan'],
  天翼云盘: ['天翼云盘', '天翼', '189', 'ty'],
  迅雷: ['迅雷', 'xunlei', 'thunder', 'xl'],
  '115网盘': ['115网盘', '115', '115pan'],
  '123云盘': ['123云盘', '123', '123pan'],
  UC网盘: ['UC网盘', 'UC', 'ucdrive', 'ucdisk'],
  '139云盘': ['139云盘', '139', '139yun', '移动云', 'caiyun'],
}

const normalizeNetdiskLabel = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/(网盘|云盘)$/g, '')
    .replace(/盘$/g, '')

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

interface MessageItemProps {
  message: MessageResponse
}

const MessageItem = ({ message }: MessageItemProps) => {
  const [expanded, setExpanded] = useState(false)

  // 生成网盘标签（用于标题行内联展示）
  const renderNetdiskTags = () => {
    if (!message.links || Object.keys(message.links).length === 0) {
      return null
    }

    const tags: JSX.Element[] = []
    Object.keys(message.links).forEach((name) => {
      const icon = NETDISK_ICONS[name] || '💾'
      tags.push(
        <span key={name} className="netdisk-plain">
          {icon} {name}
        </span>
      )
    })
    return tags
  }

  // 渲染链接
  const renderLinks = () => {
    if (!message.links) return null

    const linkElements: JSX.Element[] = []
    Object.entries(message.links).forEach(([name, value]) => {
      if (Array.isArray(value)) {
        value.forEach((item, idx) => {
          if (typeof item === 'object' && item.url) {
            linkElements.push(
              <a
                key={`${name}-${idx}`}
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="netdisk-link"
              >
                {formatLinkText(name, item.label)}
              </a>
            )
          }
        })
      } else if (typeof value === 'string') {
        linkElements.push(
          <a
            key={name}
            href={value}
            target="_blank"
            rel="noopener noreferrer"
            className="netdisk-link"
          >
            {name}
          </a>
        )
      } else if (typeof value === 'object' && value.url) {
        linkElements.push(
          <a
            key={name}
            href={value.url}
            target="_blank"
            rel="noopener noreferrer"
            className="netdisk-link"
          >
            {formatLinkText(name, value.label)}
          </a>
        )
      }
    })

    if (linkElements.length === 0) return null

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

  // 渲染标签
  const renderTags = () => {
    if (!message.tags || message.tags.length === 0) return null

    return (
      <div className="message-tags">
        <Text strong>🏷️ 标签:</Text>
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

  const items = [
    {
      key: '1',
      label: (
        <div className="message-header">
          <Text strong className="message-title">
            {message.title || '无标题'}{' '}
            <span className="message-time-inline">{timeStr}</span>
            {netdiskTags && (
              <span className="netdisk-tags-inline">{netdiskTags}</span>
            )}
          </Text>
        </div>
      ),
      children: (
        <div className="message-content">
          {/* 详细时间 */}
          <div className="message-detail-time">
            <Text type="secondary">
              🕒 详细时间: {new Date(message.timestamp).toLocaleString('zh-CN')}
            </Text>
          </div>

          {/* 描述 */}
          {message.description && (
            <Paragraph className="message-description">
              <Text strong>📝 描述：</Text>
              {cleanPrefix(message.description)}
            </Paragraph>
          )}

          {/* 链接 */}
          {renderLinks()}

          {/* 标签 */}
          {renderTags()}
        </div>
      ),
    },
  ]

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
          <span className="collapse-arrow">{isActive ? '▾' : '▸'}</span>
        )}
        items={items}
      >
      </Collapse>
    </div>
  )
}

export default MessageItem

