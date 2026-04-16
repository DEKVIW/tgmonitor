import type { ReactNode } from 'react'
import { Button, Popconfirm, message } from 'antd'

import './AppLogTerminal.css'

export type AppLogTerminalTone = 'default' | 'error' | 'warning' | 'success'

export interface AppLogTerminalLine {
  key: string | number
  text: string
  tone?: AppLogTerminalTone
}

interface AppLogTerminalProps {
  items: AppLogTerminalLine[]
  description?: ReactNode
  controls?: ReactNode
  emptyText?: string
  clearedText?: string
  compact?: boolean
  isCleared?: boolean
  canShowAll?: boolean
  onClearDisplay?: (() => void) | null
  onShowAll?: (() => void) | null
  copyPayload?: string | string[]
  copyEmptyText?: string
  copySuccessText?: string
  copyButtonLabel?: string
  onClearBackend?: (() => void) | null
  clearBackendLabel?: string
  clearBackendLoading?: boolean
  clearBackendDisabled?: boolean
  clearBackendConfirmTitle?: string
  clearBackendConfirmDescription?: string
}

const joinCopyPayload = (value: string | string[] | undefined, items: AppLogTerminalLine[]) => {
  if (Array.isArray(value)) {
    return value.join('\n').trim()
  }
  if (typeof value === 'string') {
    return value.trim()
  }
  return items
    .map((item) => item.text)
    .join('\n')
    .trim()
}

const getLineClassName = (tone?: AppLogTerminalTone) => {
  if (tone === 'error') return 'app-log-terminal__line is-error'
  if (tone === 'warning') return 'app-log-terminal__line is-warning'
  if (tone === 'success') return 'app-log-terminal__line is-success'
  return 'app-log-terminal__line'
}

const AppLogTerminal = ({
  items,
  description,
  controls,
  emptyText = '暂无日志',
  clearedText = '当前显示已清空，新的日志会继续追加。',
  compact = false,
  isCleared = false,
  canShowAll = false,
  onClearDisplay,
  onShowAll,
  copyPayload,
  copyEmptyText = '当前没有可复制的日志',
  copySuccessText = '已复制当前日志',
  copyButtonLabel = '复制日志',
  onClearBackend,
  clearBackendLabel = '清理后端日志',
  clearBackendLoading = false,
  clearBackendDisabled = false,
  clearBackendConfirmTitle,
  clearBackendConfirmDescription,
}: AppLogTerminalProps) => {
  const handleCopy = async () => {
    const content = joinCopyPayload(copyPayload, items)
    if (!content) {
      message.info(copyEmptyText)
      return
    }
    try {
      await navigator.clipboard.writeText(content)
      message.success(copySuccessText)
    } catch {
      message.error('复制失败，请检查浏览器权限')
    }
  }

  const clearBackendButton =
    typeof onClearBackend === 'function' ? (
      <Button
        size="small"
        loading={clearBackendLoading}
        disabled={clearBackendDisabled}
        onClick={clearBackendConfirmTitle ? undefined : () => void onClearBackend()}
      >
        {clearBackendLabel}
      </Button>
    ) : null

  return (
    <div className="app-log-terminal">
      <div className="app-log-terminal__toolbar">
        <div className="app-log-terminal__toolbar-main">
          {description ? <div className="app-log-terminal__description">{description}</div> : null}
          {controls ? <div className="app-log-terminal__controls">{controls}</div> : null}
        </div>
        <div className="app-log-terminal__actions">
          {typeof onClearDisplay === 'function' ? (
            <Button size="small" onClick={() => void onClearDisplay()}>
              清空当前显示
            </Button>
          ) : null}
          {typeof onShowAll === 'function' ? (
            <Button size="small" disabled={!canShowAll} onClick={() => void onShowAll()}>
              显示全部
            </Button>
          ) : null}
          <Button size="small" onClick={() => void handleCopy()}>
            {copyButtonLabel}
          </Button>
          {clearBackendButton && clearBackendConfirmTitle ? (
            <Popconfirm
              title={clearBackendConfirmTitle}
              description={clearBackendConfirmDescription}
              okText="清理"
              cancelText="取消"
              onConfirm={() => void onClearBackend?.()}
            >
              {clearBackendButton}
            </Popconfirm>
          ) : (
            clearBackendButton
          )}
        </div>
      </div>
      <div className={`app-log-terminal__surface${compact ? ' is-compact' : ''}`}>
        {items.length > 0 ? (
          items.map((item) => (
            <div key={item.key} className={getLineClassName(item.tone)}>
              {item.text}
            </div>
          ))
        ) : (
          <div className="app-log-terminal__empty">{isCleared ? clearedText : emptyText}</div>
        )}
      </div>
    </div>
  )
}

export default AppLogTerminal
