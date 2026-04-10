import { Alert, Button, Card, Collapse, Empty, Input, Progress, Select, Switch, Tag, Tooltip, Typography } from 'antd'
import { InfoCircleOutlined, RobotOutlined } from '@ant-design/icons'

import type {
  ResourceOpsAiModelItem,
  ResourceOpsAiTestResponse,
  ResourceOpsRecognitionStatus,
  ResourceOpsRuntimeSettingsResponse,
  ResourceOpsRuntimeSettingsUpdateRequest,
  ResourceOpsWorkBindingSummary,
} from '@/types/resourceOps'

const { Text } = Typography

interface RecognitionSummaryItem {
  label: string
  value: number
  hint: string
}

interface ResourceOpsRecognitionPanelCompactProps {
  loading: boolean
  settingsSaving: boolean
  pendingRunLoading: boolean
  allRunLoading: boolean
  aiModelsLoading: boolean
  aiTesting: boolean
  settingsDraft: ResourceOpsRuntimeSettingsUpdateRequest | null
  runtimeSettings: ResourceOpsRuntimeSettingsResponse | null
  bindingSummary: ResourceOpsWorkBindingSummary | null
  recognitionStatus: ResourceOpsRecognitionStatus | null
  recognitionSummaryItems: RecognitionSummaryItem[]
  aiApiKeyInput: string
  aiTestInput: string
  aiModelOptions: ResourceOpsAiModelItem[]
  aiTestResult: ResourceOpsAiTestResponse | null
  formatNumber: (value?: number | null) => string
  formatDateTime: (value?: string | null) => string
  onPatchDraft: (key: keyof ResourceOpsRuntimeSettingsUpdateRequest, value: string | number | boolean) => void
  onAiApiKeyInputChange: (value: string) => void
  onAiTestInputChange: (value: string) => void
  onLoadAiModels: () => void
  onTestAiConnection: () => void
  onRunRecognition: (mode: 'pending' | 'all') => void
  onSaveSettings: () => void
}

const RECOGNITION_TOOLTIP =
  'AI 只读取被点击链接对应的原始消息标题，提取影视剧名字后归并到同一主题。自动识别开启并保存后，新点击会先进入待处理队列，再由后台持续消化。'

const recognitionModeLabel = (mode?: string | null) => {
  if (mode === 'all') return '全部扫描'
  if (mode === 'pending') return '处理待处理'
  return '未开始'
}

const getRuntimeTag = (
  recognitionStatus: ResourceOpsRecognitionStatus | null,
  runtimeSettings: ResourceOpsRuntimeSettingsResponse
) => {
  const queuedMode = recognitionStatus?.requested_mode || null
  const runningMode = recognitionStatus?.current_mode || null
  const isRunning = Boolean(recognitionStatus?.is_running)
  const isQueued = Boolean(queuedMode) && !isRunning

  if (isRunning) {
    return { color: 'processing' as const, label: `运行中 · ${recognitionModeLabel(runningMode)}` }
  }
  if (isQueued) {
    return { color: 'gold' as const, label: `排队中 · ${recognitionModeLabel(queuedMode)}` }
  }
  if (!runtimeSettings.ai_provider_ready) {
    return { color: 'default' as const, label: 'AI 未就绪' }
  }
  if (recognitionStatus?.last_error) {
    return { color: 'error' as const, label: '最近有异常' }
  }
  return { color: 'success' as const, label: '已就绪' }
}

const getRuntimeStateLabel = (recognitionStatus: ResourceOpsRecognitionStatus | null) => {
  const queuedMode = recognitionStatus?.requested_mode || null
  const runningMode = recognitionStatus?.current_mode || null
  const isRunning = Boolean(recognitionStatus?.is_running)
  const isQueued = Boolean(queuedMode) && !isRunning

  if (isRunning) return `运行中 · ${recognitionModeLabel(runningMode)}`
  if (isQueued) return `排队中 · ${recognitionModeLabel(queuedMode)}`
  if (recognitionStatus?.finished_at) return '最近一轮已完成'
  return '等待任务'
}

const ResourceOpsRecognitionPanelCompact = ({
  loading,
  settingsSaving,
  pendingRunLoading,
  allRunLoading,
  aiModelsLoading,
  aiTesting,
  settingsDraft,
  runtimeSettings,
  bindingSummary,
  recognitionStatus,
  recognitionSummaryItems,
  aiApiKeyInput,
  aiTestInput,
  aiModelOptions,
  aiTestResult,
  formatNumber,
  formatDateTime,
  onPatchDraft,
  onAiApiKeyInputChange,
  onAiTestInputChange,
  onLoadAiModels,
  onTestAiConnection,
  onRunRecognition,
  onSaveSettings,
}: ResourceOpsRecognitionPanelCompactProps) => {
  const queuedMode = recognitionStatus?.requested_mode || null
  const runningMode = recognitionStatus?.current_mode || null
  const isRunning = Boolean(recognitionStatus?.is_running)
  const isQueued = Boolean(queuedMode) && !isRunning
  const busy = isRunning || isQueued
  const totalCount = Number(recognitionStatus?.total_count || 0)
  const processedCount = Number(recognitionStatus?.processed_count || 0)
  const progressPercent =
    totalCount > 0
      ? Math.max(0, Math.min(100, Math.round((processedCount / totalCount) * 100)))
      : recognitionStatus?.finished_at
        ? 100
        : 0
  const logLines = recognitionStatus?.logs || []
  const runtimeTag = runtimeSettings ? getRuntimeTag(recognitionStatus, runtimeSettings) : null

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
                      {runtimeTag ? <Tag color={runtimeTag.color}>{runtimeTag.label}</Tag> : null}
                    </div>

                    <div className="resource-ops-recognition-toolbar" onClick={(event) => event.stopPropagation()}>
                      <div className="resource-ops-recognition-toolbar-item resource-ops-recognition-toolbar-switch">
                        <div className="resource-ops-inline-switch-copy">
                          <span>自动识别</span>
                          <small>新点击入队，保存后生效</small>
                        </div>
                        <Switch
                          checked={settingsDraft.auto_recognition_enabled}
                          onChange={(checked) => onPatchDraft('auto_recognition_enabled', checked)}
                        />
                      </div>

                      <Button
                        type="primary"
                        loading={pendingRunLoading}
                        disabled={!runtimeSettings.ai_provider_ready || busy}
                        onClick={() => onRunRecognition('pending')}
                      >
                        处理待处理
                      </Button>

                      <Button
                        loading={allRunLoading}
                        disabled={!runtimeSettings.ai_provider_ready || busy}
                        onClick={() => onRunRecognition('all')}
                      >
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
                  {!runtimeSettings.ai_provider_ready ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="请先配置可用的 AI"
                      description="先填好 Base URL、API Key 和模型，再保存配置。模型留空也可以，运行时会自动尝试可用模型。"
                    />
                  ) : null}

                  {recognitionStatus?.last_error ? (
                    <Alert type="error" showIcon message="最近一轮识别出现异常" description={recognitionStatus.last_error} />
                  ) : null}

                  {aiTestResult ? (
                    <Alert
                      type="success"
                      showIcon
                      message={`测试结果：${aiTestResult.extracted_title || '未识别出影视剧名称'}`}
                      description={`模型：${aiTestResult.model}${aiTestResult.reason ? ` / ${aiTestResult.reason}` : ''}`}
                    />
                  ) : null}

                  <div className="resource-ops-recognition-grid">
                    <div className="resource-ops-recognition-section">
                      <div className="resource-ops-recognition-section-head">
                        <div>
                          <div className="resource-ops-runtime-subtitle">AI 配置</div>
                          <small className="resource-ops-recognition-section-hint">
                            修改 Base URL、模型、API Key、自动识别后，需要点保存才会写入后台。
                          </small>
                        </div>
                        <div className="resource-ops-inline-actions resource-ops-inline-actions-tight">
                          <Button loading={aiModelsLoading} onClick={onLoadAiModels}>
                            刷新模型
                          </Button>
                          <Button type="primary" loading={settingsSaving} onClick={onSaveSettings}>
                            保存配置
                          </Button>
                        </div>
                      </div>

                      <div className="resource-ops-mini-stats">
                        <div className="resource-ops-mini-stat">
                          <span>AI 状态</span>
                          <strong>{runtimeSettings.ai_provider_ready ? '已就绪' : '未就绪'}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>当前模型</span>
                          <strong>{settingsDraft.ai_model || '自动选择'}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>上次归并</span>
                          <strong>{formatDateTime(runtimeSettings.last_sync_at)}</strong>
                        </div>
                      </div>

                      <div className="resource-ops-runtime-form-grid">
                        <div className="resource-ops-form-field resource-ops-field-span-2">
                          <label>Base URL</label>
                          <Input
                            value={settingsDraft.ai_base_url}
                            placeholder="例如：https://api.example.com"
                            onChange={(event) => onPatchDraft('ai_base_url', event.target.value)}
                          />
                        </div>

                        <div className="resource-ops-form-field">
                          <label>模型</label>
                          {aiModelOptions.length > 0 ? (
                            <Select
                              showSearch
                              allowClear
                              optionFilterProp="label"
                              value={settingsDraft.ai_model || undefined}
                              placeholder="留空则自动选择"
                              options={aiModelOptions.map((item) => ({
                                value: item.id,
                                label: item.label || item.id,
                              }))}
                              onChange={(value) => onPatchDraft('ai_model', value || '')}
                            />
                          ) : (
                            <Input
                              value={settingsDraft.ai_model}
                              placeholder="可手动填写，也可先刷新模型"
                              onChange={(event) => onPatchDraft('ai_model', event.target.value)}
                            />
                          )}
                        </div>

                        <div className="resource-ops-form-field">
                          <label>API Key</label>
                          <Input.Password
                            value={aiApiKeyInput}
                            placeholder={
                              runtimeSettings.ai_api_key_configured ? '已配置，留空则不修改' : '输入当前使用的 API Key'
                            }
                            onChange={(event) => onAiApiKeyInputChange(event.target.value)}
                          />
                        </div>
                      </div>

                      <div className="resource-ops-form-field">
                        <label>测试识别文本</label>
                        <Input.TextArea
                          value={aiTestInput}
                          rows={3}
                          maxLength={500}
                          placeholder="直接输入一条原始消息标题，例如：月鳞绮纪 2026 第17集 无字幕 鞠婧祎 曾舜晞 陈都灵"
                          onChange={(event) => onAiTestInputChange(event.target.value)}
                        />
                      </div>

                      <div className="resource-ops-inline-actions resource-ops-inline-actions-tight">
                        <Button loading={aiTesting} onClick={onTestAiConnection}>
                          测试识别
                        </Button>
                      </div>
                    </div>

                    <div className="resource-ops-recognition-section">
                      <div className="resource-ops-recognition-section-head">
                        <div>
                          <div className="resource-ops-runtime-subtitle">运行日志</div>
                          <small className="resource-ops-recognition-section-hint">
                            这里会显示“原始标题 -&gt; AI 提取结果”的实时日志，方便看归并是否正常。
                          </small>
                        </div>
                      </div>

                      <div className="resource-ops-mini-stats">
                        <div className="resource-ops-mini-stat">
                          <span>当前状态</span>
                          <strong>{getRuntimeStateLabel(recognitionStatus)}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>本轮进度</span>
                          <strong>
                            {formatNumber(processedCount)} / {formatNumber(totalCount)}
                          </strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>时间</span>
                          <strong>{formatDateTime(recognitionStatus?.started_at || recognitionStatus?.finished_at)}</strong>
                        </div>
                      </div>

                      {(busy || recognitionStatus?.finished_at) && (
                        <div className="resource-ops-recognition-progress">
                          <div className="resource-ops-recognition-progress-head">
                            <span>识别进度</span>
                            <Tag color={isRunning ? 'processing' : isQueued ? 'gold' : 'success'}>
                              {isRunning
                                ? recognitionModeLabel(runningMode)
                                : isQueued
                                  ? `${recognitionModeLabel(queuedMode)} 已排队`
                                  : '已完成'}
                            </Tag>
                          </div>
                          <Progress percent={progressPercent} status={isRunning ? 'active' : 'normal'} />
                        </div>
                      )}

                      <div className="resource-ops-form-field">
                        <label>终端日志</label>
                        <div className="resource-ops-terminal">
                          {logLines.length > 0 ? (
                            logLines.map((line, index) => (
                              <div key={`${index}-${line}`} className="resource-ops-terminal-line">
                                {line}
                              </div>
                            ))
                          ) : (
                            <div className="resource-ops-terminal-empty">
                              {bindingSummary?.pending_count
                                ? '当前有待处理项，执行后这里会显示“原始标题 -> AI 提取结果”。'
                                : '暂无运行日志'}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="resource-ops-runtime-side-note resource-ops-runtime-side-note-compact">
                        <span>待处理说明</span>
                        <small>
                          新点击、瞬时积压、识别失败重试，都会先放进待处理队列。AI 短时异常时也会先留在这里，后续修复后再继续消化。
                        </small>
                      </div>
                    </div>
                  </div>

                  <Text type="secondary">
                    自动识别是否入队，只看“自动识别”开关是否开启并保存，以及当前 AI 配置是否可用。
                  </Text>
                </div>
              ),
            },
          ]}
        />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无作品归并配置" />
      )}
    </Card>
  )
}

export default ResourceOpsRecognitionPanelCompact
