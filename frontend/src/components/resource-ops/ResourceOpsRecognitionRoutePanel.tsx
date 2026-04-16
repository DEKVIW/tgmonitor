import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Switch, Tag, Tooltip } from 'antd'
import { InfoCircleOutlined, RobotOutlined } from '@ant-design/icons'

import AppLogTerminal from '@/components/common/AppLogTerminal'
import type {
  ResourceOpsRecognitionStatus,
  ResourceOpsRuntimeSettingsResponse,
  ResourceOpsRuntimeSettingsUpdateRequest,
  ResourceOpsWorkBindingSummary,
} from '@/types/resourceOps'

interface RecognitionSummaryItem {
  label: string
  value: number
  hint: string
}

interface ResourceOpsRecognitionRoutePanelProps {
  loading: boolean
  settingsSaving: boolean
  pendingRunLoading: boolean
  allRunLoading: boolean
  logsClearing: boolean
  settingsDraft: ResourceOpsRuntimeSettingsUpdateRequest | null
  runtimeSettings: ResourceOpsRuntimeSettingsResponse | null
  bindingSummary: ResourceOpsWorkBindingSummary | null
  recognitionStatus: ResourceOpsRecognitionStatus | null
  recognitionSummaryItems: RecognitionSummaryItem[]
  formatNumber: (value?: number | null) => string
  formatDateTime: (value?: string | null) => string
  onPatchDraft: (key: keyof ResourceOpsRuntimeSettingsUpdateRequest, value: string | number | boolean) => void
  onClearLogs: () => void
  onRunRecognition: (mode: 'pending' | 'all') => void
  onSaveSettings: () => void
  onOpenAiCenter: () => void
}

const RECOGNITION_TOOLTIP =
  '资源运营只负责是否自动识别、当前队列状态和日志。底层 provider、模型刷新、失败切换和能力路由统一放在 AI 中心。'

const getRuntimeTag = (
  runtimeSettings: ResourceOpsRuntimeSettingsResponse,
  bindingSummary: ResourceOpsWorkBindingSummary | null,
  recognitionStatus: ResourceOpsRecognitionStatus | null
) => {
  if (!runtimeSettings.ai_route_ready) return { color: 'default' as const, label: 'AI 未就绪' }
  if (recognitionStatus?.is_running) return { color: 'processing' as const, label: 'Worker 运行中' }
  if ((bindingSummary?.pending_count || 0) > 0 && !recognitionStatus?.worker_alive) {
    return { color: 'warning' as const, label: 'Worker 离线' }
  }
  if ((bindingSummary?.pending_count || 0) > 0) return { color: 'gold' as const, label: '队列待处理' }
  return { color: 'success' as const, label: '空闲' }
}

const getWorkerStateLabel = (recognitionStatus: ResourceOpsRecognitionStatus | null) => {
  if (!recognitionStatus) return '未启动'
  if (recognitionStatus.is_running) return '正在处理'
  if (recognitionStatus.worker_alive) return '在线空闲'
  return '离线'
}

const getRecognitionLogTone = (line: string) => {
  const normalized = String(line || '').toLowerCase()
  if (
    normalized.includes('[error]') ||
    normalized.includes(' error ') ||
    normalized.includes(' failed') ||
    normalized.includes('exception') ||
    normalized.includes('traceback')
  ) {
    return 'error' as const
  }
  if (normalized.includes('[warning]') || normalized.includes(' warning ')) {
    return 'warning' as const
  }
  if (normalized.includes('[success]') || normalized.includes(' completed') || normalized.includes(' finished')) {
    return 'success' as const
  }
  return 'default' as const
}

const formatRecognitionLogLine = (line: string) => {
  const text = String(line || '').trim()
  if (text.startsWith('[OK] ')) {
    const payload = text.slice(5).trim()
    const [queryTitle, resolvedTitle] = payload.split('->').map((item) => item.trim())
    if (queryTitle && resolvedTitle) {
      return `识别成功 -> ${queryTitle} => ${resolvedTitle}`
    }
    return `识别成功 -> ${payload}`
  }
  if (text.startsWith('[ERR] ')) {
    const payload = text.slice(6).trim()
    const [queryTitle, reason] = payload.split('->').map((item) => item.trim())
    if (queryTitle && reason) {
      return `识别失败 -> ${queryTitle} => ${reason}`
    }
    return `识别失败 -> ${payload}`
  }
  return text
}

const ResourceOpsRecognitionRoutePanel = ({
  loading,
  settingsSaving,
  pendingRunLoading,
  allRunLoading,
  logsClearing,
  settingsDraft,
  runtimeSettings,
  bindingSummary,
  recognitionStatus,
  recognitionSummaryItems,
  formatNumber,
  formatDateTime,
  onPatchDraft,
  onClearLogs,
  onRunRecognition,
  onSaveSettings,
  onOpenAiCenter,
}: ResourceOpsRecognitionRoutePanelProps) => {
  const [clearedLogCount, setClearedLogCount] = useState(0)
  const recognitionLogs = recognitionStatus?.logs || []

  useEffect(() => {
    setClearedLogCount((current) => Math.min(current, recognitionLogs.length))
  }, [recognitionLogs.length])

  const visibleRecognitionLogs = useMemo(
    () => recognitionLogs.slice(clearedLogCount),
    [recognitionLogs, clearedLogCount]
  )

  const visibleRecognitionLogLines = useMemo(
    () =>
      visibleRecognitionLogs.map((line, index) => ({
        key: `${clearedLogCount + index}-${line}`,
        text: formatRecognitionLogLine(line),
        tone: getRecognitionLogTone(line),
      })),
    [clearedLogCount, visibleRecognitionLogs]
  )

  return (
    <Card className="resource-ops-panel-card" loading={loading}>
      {settingsDraft && runtimeSettings ? (
        <Collapse
          ghost
          defaultActiveKey={[]}
          className="resource-ops-runtime-collapse resource-ops-recognition-collapse"
          items={[
            {
              key: 'recognition',
              label: (
                <div className="resource-ops-recognition-overview">
                  <div className="resource-ops-recognition-overview-head">
                    <div className="resource-ops-recognition-overview-copy">
                      <div className="resource-ops-runtime-title">
                        <RobotOutlined />
                        <span>作品归并</span>
                        <Tooltip title={RECOGNITION_TOOLTIP}>
                          <InfoCircleOutlined className="resource-ops-title-help" />
                        </Tooltip>
                      </div>
                      <Tag color={getRuntimeTag(runtimeSettings, bindingSummary, recognitionStatus).color}>
                        {getRuntimeTag(runtimeSettings, bindingSummary, recognitionStatus).label}
                      </Tag>
                    </div>

                    <div className="resource-ops-recognition-toolbar" onClick={(event) => event.stopPropagation()}>
                      <div className="resource-ops-recognition-toolbar-item resource-ops-recognition-toolbar-switch">
                        <div className="resource-ops-inline-switch-copy">
                          <span>自动识别</span>
                          <small>新点击自动进入识别队列</small>
                        </div>
                        <Switch checked={settingsDraft.auto_recognition_enabled} onChange={(checked) => onPatchDraft('auto_recognition_enabled', checked)} />
                      </div>

                      <Button type="primary" loading={pendingRunLoading} disabled={!runtimeSettings.ai_route_ready} onClick={() => onRunRecognition('pending')}>
                        处理待处理
                      </Button>

                      <Button loading={allRunLoading} disabled={!runtimeSettings.ai_route_ready} onClick={() => onRunRecognition('all')}>
                        全部扫描
                      </Button>
                    </div>
                  </div>

                  <div className="resource-ops-summary-strip resource-ops-summary-strip-compact">
                    {recognitionSummaryItems.map((item) => (
                      <div key={item.label} className="resource-ops-summary-chip resource-ops-summary-chip-compact">
                        <span>{item.label}</span>
                        <strong>{formatNumber(item.value)}</strong>
                        <small>{item.hint}</small>
                      </div>
                    ))}
                  </div>
                </div>
              ),
              children: (
                <div className="resource-ops-runtime-stack">
                  {!runtimeSettings.ai_route_ready ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="作品归并 AI 路由还未就绪"
                      description="请到 AI 中心配置 resource_ops_title_extract 的 provider 和模型后，再执行识别。"
                      action={<Button size="small" onClick={onOpenAiCenter}>打开 AI 中心</Button>}
                    />
                  ) : (
                    <Alert
                      type="info"
                      showIcon
                      message={`当前路由：${runtimeSettings.ai_route_key || 'resource_ops_title_extract'}`}
                      description={`Provider：${runtimeSettings.ai_route_provider_label || '-'}；模型：${runtimeSettings.ai_route_model || '自动选择'}`}
                      action={<Button size="small" onClick={onOpenAiCenter}>管理 AI 中心</Button>}
                    />
                  )}

                  {(bindingSummary?.pending_count || 0) > 0 && !recognitionStatus?.worker_alive ? (
                    <Alert type="warning" showIcon message="检测到待处理队列，但 tg-worker 当前不在线" />
                  ) : null}

                  {recognitionStatus?.last_error ? (
                    <Alert type="error" showIcon message="最近一次处理出现异常" description={recognitionStatus.last_error} />
                  ) : null}

                  <div className="resource-ops-mini-stats">
                    <div className="resource-ops-mini-stat">
                      <span>Worker</span>
                      <strong>{getWorkerStateLabel(recognitionStatus)}</strong>
                    </div>
                    <div className="resource-ops-mini-stat">
                      <span>最近同步</span>
                      <strong>{formatDateTime(runtimeSettings.last_sync_at)}</strong>
                    </div>
                    <div className="resource-ops-mini-stat">
                      <span>自动识别</span>
                      <strong>{settingsDraft.auto_recognition_enabled ? '已开启' : '已关闭'}</strong>
                    </div>
                  </div>

                  <div className="resource-ops-inline-actions resource-ops-inline-actions-tight">
                    <Button type="primary" loading={settingsSaving} onClick={onSaveSettings}>保存识别设置</Button>
                  </div>

                  <AppLogTerminal
                    description="这里按真实运行顺序输出作品归并 worker 日志，便于确认排队、识别和失败原因。"
                    items={visibleRecognitionLogLines}
                    emptyText="暂无线程日志"
                    isCleared={clearedLogCount > 0}
                    onClearDisplay={() => setClearedLogCount(recognitionLogs.length)}
                    onShowAll={() => setClearedLogCount(0)}
                    canShowAll={clearedLogCount > 0}
                    copyPayload={visibleRecognitionLogLines.map((item) => item.text)}
                    copyEmptyText="当前没有可复制的日志"
                    copySuccessText="已复制当前日志"
                    onClearBackend={onClearLogs}
                    clearBackendLoading={logsClearing}
                    clearBackendDisabled={recognitionLogs.length <= 0}
                    clearBackendConfirmTitle="确认清理作品归并的后端日志？"
                    clearBackendConfirmDescription="这会删除当前保存的运行日志，但不会影响识别队列和绑定结果。"
                  />
                </div>
              ),
            },
          ]}
        />
      ) : null}
    </Card>
  )
}

export default ResourceOpsRecognitionRoutePanel
