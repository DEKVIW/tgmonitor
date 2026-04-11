import { Alert, Button, Card, Collapse, Empty, Input, Select, Switch, Tag, Tooltip, Typography } from 'antd'
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

interface ResourceOpsRecognitionQueuePanelProps {
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
  'AI 只读取被点击链接对应的原始消息标题，提取影视剧名称后归并到同一主题。开启自动识别并保存后，新点击会自动进入待处理队列，由 tg-worker 持续消化。'

const getApiModeLabel = (value?: string | null) =>
  (
    {
      auto: '自动兜底',
      chat_completions: 'Chat',
      chat_completions_stream: 'Chat 流式',
      responses: 'Responses',
    } as Record<string, string>
  )[value || 'auto'] || '自动兜底'

const getRuntimeTag = (
  runtimeSettings: ResourceOpsRuntimeSettingsResponse,
  bindingSummary: ResourceOpsWorkBindingSummary | null,
  recognitionStatus: ResourceOpsRecognitionStatus | null
) => {
  if (!runtimeSettings.ai_provider_ready) {
    return { color: 'default' as const, label: 'AI 未就绪' }
  }
  if (recognitionStatus?.is_running) {
    return { color: 'processing' as const, label: 'Worker 运行中' }
  }
  if ((bindingSummary?.pending_count || 0) > 0 && !recognitionStatus?.worker_alive) {
    return { color: 'warning' as const, label: 'Worker 离线' }
  }
  if ((bindingSummary?.pending_count || 0) > 0) {
    return { color: 'gold' as const, label: '队列待处理' }
  }
  return { color: 'success' as const, label: '空闲' }
}

const getWorkerStateLabel = (recognitionStatus: ResourceOpsRecognitionStatus | null) => {
  if (!recognitionStatus) return '未启动'
  if (recognitionStatus.is_running) return '正在处理'
  if (recognitionStatus.worker_alive) return '在线空闲'
  return '离线'
}

const ResourceOpsRecognitionQueuePanel = ({
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
}: ResourceOpsRecognitionQueuePanelProps) => {
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
                          <small>新点击自动入队</small>
                        </div>
                        <Switch
                          checked={settingsDraft.auto_recognition_enabled}
                          onChange={(checked) => onPatchDraft('auto_recognition_enabled', checked)}
                        />
                      </div>

                      <Button
                        type="primary"
                        loading={pendingRunLoading}
                        disabled={!runtimeSettings.ai_provider_ready || pendingRunLoading}
                        onClick={() => onRunRecognition('pending')}
                      >
                        处理待处理
                      </Button>

                      <Button
                        loading={allRunLoading}
                        disabled={!runtimeSettings.ai_provider_ready || allRunLoading}
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
                      description="先填写 Base URL、API Key 和模型，再保存配置。模型留空也可以，运行时会自动尝试可用模型。"
                    />
                  ) : null}

                  {(bindingSummary?.pending_count || 0) > 0 && !recognitionStatus?.worker_alive ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="检测到待处理队列，但 tg-worker 未运行"
                      description="请启动独立的 tg-worker 服务，否则新点击和手动入队的主题都不会继续消化。"
                    />
                  ) : null}

                  {recognitionStatus?.last_error ? (
                    <Alert type="error" showIcon message="最近一次处理出现异常" description={recognitionStatus.last_error} />
                  ) : null}

                  {aiTestResult ? (
                    <Alert
                      type="success"
                      showIcon
                      message={`测试结果：${aiTestResult.extracted_title || '未识别出主题'}`}
                      description={`模型：${aiTestResult.model} / 模式：${getApiModeLabel(aiTestResult.used_api_mode)}${aiTestResult.reason ? ` / ${aiTestResult.reason}` : ''}`}
                    />
                  ) : null}

                  <div className="resource-ops-recognition-grid">
                    <div className="resource-ops-recognition-section">
                      <div className="resource-ops-recognition-section-head">
                        <div>
                          <div className="resource-ops-runtime-subtitle">AI 配置</div>
                          <small className="resource-ops-recognition-section-hint">
                            修改 Base URL、模型、API Key 或自动识别后，需要点保存才会写入后台。
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
                          <span>识别策略</span>
                          <strong>后端自动兜底</strong>
                        </div>
                      </div>

                      <div className="resource-ops-mini-stats">
                        <div className="resource-ops-mini-stat">
                          <span>最近归并</span>
                          <strong>{formatDateTime(runtimeSettings.last_sync_at)}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>自动识别</span>
                          <strong>{settingsDraft.auto_recognition_enabled ? '已开启' : '已关闭'}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>保存说明</span>
                          <strong>改完要保存</strong>
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
                              placeholder="可手填，也可先刷新模型"
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
                          placeholder="直接输入一条原始消息标题，测试 AI 会提取出什么影视剧名称"
                          onChange={(event) => onAiTestInputChange(event.target.value)}
                        />
                      </div>

                      <div className="resource-ops-inline-actions resource-ops-inline-actions-tight">
                        <Button loading={aiTesting} onClick={onTestAiConnection}>
                          测试识别
                        </Button>
                      </div>

                      <div className="resource-ops-runtime-side-note resource-ops-runtime-side-note-compact">
                        <span>识别说明</span>
                        <small>
                          后端会自动按“普通 Chat、流式 Chat、Responses”顺序兜底，优先帮你拿到可用结果，不需要手动切模式。
                        </small>
                      </div>
                    </div>

                    <div className="resource-ops-recognition-section">
                      <div className="resource-ops-recognition-section-head">
                        <div>
                          <div className="resource-ops-runtime-subtitle">运行状态</div>
                          <small className="resource-ops-recognition-section-hint">
                            这里展示真实队列与 worker 心跳，不再显示旧的批次进度。
                          </small>
                        </div>
                      </div>

                      <div className="resource-ops-mini-stats">
                        <div className="resource-ops-mini-stat">
                          <span>Worker</span>
                          <strong>{getWorkerStateLabel(recognitionStatus)}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>队列</span>
                          <strong>
                            {formatNumber(bindingSummary?.queued_count)} / {formatNumber(bindingSummary?.processing_count)} /{' '}
                            {formatNumber(bindingSummary?.retry_wait_count)}
                          </strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>最近心跳</span>
                          <strong>{formatDateTime(recognitionStatus?.last_heartbeat_at)}</strong>
                        </div>
                      </div>

                      <div className="resource-ops-mini-stats">
                        <div className="resource-ops-mini-stat">
                          <span>最近处理</span>
                          <strong>{formatDateTime(recognitionStatus?.last_processed_at)}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>当前来源</span>
                          <strong>{recognitionStatus?.current_source || '-'}</strong>
                        </div>
                        <div className="resource-ops-mini-stat">
                          <span>失败累计</span>
                          <strong>{formatNumber(bindingSummary?.failed_count)}</strong>
                        </div>
                      </div>

                      {recognitionStatus?.current_link_target_id ? (
                        <Alert
                          type="info"
                          showIcon
                          message={`正在处理 link_target ${recognitionStatus.current_link_target_id}`}
                          description={recognitionStatus.current_title || '等待写入当前标题'}
                        />
                      ) : null}

                      <div className="resource-ops-form-field">
                        <label>终端日志</label>
                        <div className="resource-ops-terminal">
                          {recognitionStatus?.logs?.length ? (
                            recognitionStatus.logs.map((line, index) => (
                              <div key={`${index}-${line}`} className="resource-ops-terminal-line">
                                {line}
                              </div>
                            ))
                          ) : (
                            <div className="resource-ops-terminal-empty">
                              {(bindingSummary?.pending_count || 0) > 0
                                ? '当前有待处理项，worker 跑起来后这里会显示 “原始标题 -> AI 提取结果”。'
                                : '暂无运行日志'}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="resource-ops-runtime-side-note resource-ops-runtime-side-note-compact">
                        <span>状态说明</span>
                        <small>
                          队列统计依次为：排队中 / 处理中 / 重试等待。已归并来自绑定结果，异常来自队列最终失败，不再混用旧批次概念。
                        </small>
                      </div>
                    </div>
                  </div>

                  <Text type="secondary">
                    只有保存后的自动识别开关才会影响新点击是否自动入队；手动“处理待处理 / 全部扫描”始终只负责入队，不负责直接执行。
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

export default ResourceOpsRecognitionQueuePanel
