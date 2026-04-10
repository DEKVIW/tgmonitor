import { Alert, Button, Card, Empty, Input, Progress, Select, Switch, Tag, Typography } from 'antd'
import { RobotOutlined } from '@ant-design/icons'

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

interface ResourceOpsRecognitionPanelProps {
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

const recognitionModeLabel = (mode?: string | null) => {
  if (mode === 'all') return '全部扫描'
  if (mode === 'pending') return '待处理'
  return '未开始'
}

const ResourceOpsRecognitionPanel = ({
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
}: ResourceOpsRecognitionPanelProps) => {
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

  return (
    <Card className="resource-ops-panel-card" loading={loading}>
      {settingsDraft && runtimeSettings ? (
        <div className="resource-ops-runtime-card">
          <div className="resource-ops-runtime-card-head">
            <div>
              <div className="resource-ops-runtime-title">
                <RobotOutlined />
                <span>作品归并</span>
              </div>
              <p className="resource-ops-runtime-hint">
                AI 只读取被点击链接对应的原始消息标题，提取影视剧名字后归并到同一主题。自动识别开启后，新点击会先进入待处理队列，再由后台持续消化。
              </p>
            </div>
            <div className="resource-ops-inline-switch resource-ops-inline-switch-compact">
              <div className="resource-ops-inline-switch-copy">
                <span>自动识别</span>
                <small>捕获到新点击后自动入队并后台处理</small>
              </div>
              <Switch
                checked={settingsDraft.auto_recognition_enabled}
                onChange={(checked) => onPatchDraft('auto_recognition_enabled', checked)}
              />
            </div>
          </div>

          <div className="resource-ops-summary-strip">
            {recognitionSummaryItems.map((item) => (
              <div key={item.label} className="resource-ops-summary-chip">
                <span>{item.label}</span>
                <strong>{formatNumber(item.value)}</strong>
                <small>{item.hint}</small>
              </div>
            ))}
          </div>

          {!runtimeSettings.ai_provider_ready ? (
            <Alert
              type="warning"
              showIcon
              message="请先配置可用的 AI"
              description="先填好 Base URL、API Key 和模型，再保存配置。模型填错也没关系，运行时会自动尝试切到可用模型。"
            />
          ) : null}

          {recognitionStatus?.last_error ? (
            <Alert
              type="error"
              showIcon
              message="最近一次识别出现异常"
              description={recognitionStatus.last_error}
            />
          ) : null}

          {aiTestResult ? (
            <Alert
              type="success"
              showIcon
              message={`测试结果：${aiTestResult.extracted_title || '未识别出影视名称'}`}
              description={`模型：${aiTestResult.model}${aiTestResult.reason ? ` / ${aiTestResult.reason}` : ''}`}
            />
          ) : null}

          <div className="resource-ops-recognition-grid">
            <div className="resource-ops-recognition-section">
              <div className="resource-ops-recognition-section-head">
                <div>
                  <div className="resource-ops-runtime-subtitle">AI 配置</div>
                  <small className="resource-ops-recognition-section-hint">只保留基础配置，不再额外做“启用 AI”开关。</small>
                </div>
                <div className="resource-ops-inline-actions">
                  <Button loading={aiModelsLoading} onClick={onLoadAiModels}>
                    刷新模型
                  </Button>
                </div>
              </div>

              <div className="resource-ops-runtime-meta-grid">
                <div className="resource-ops-runtime-meta-card">
                  <span>AI 状态</span>
                  <strong>{runtimeSettings.ai_provider_ready ? '已就绪' : '未就绪'}</strong>
                  <small>{runtimeSettings.ai_provider_ready ? '当前可以直接执行识别和归并' : '缺少可用的地址、密钥或模型'}</small>
                </div>
                <div className="resource-ops-runtime-meta-card">
                  <span>当前模型</span>
                  <strong>{settingsDraft.ai_model || '自动选择'}</strong>
                  <small>留空时会自动挑选可用模型</small>
                </div>
                <div className="resource-ops-runtime-meta-card">
                  <span>上次归并</span>
                  <strong>{formatDateTime(runtimeSettings.last_sync_at)}</strong>
                  <small>
                    成功 {formatNumber(runtimeSettings.last_sync_summary?.matched_count)} / 异常 {formatNumber(runtimeSettings.last_sync_summary?.error_count)}
                  </small>
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
                    placeholder={runtimeSettings.ai_api_key_configured ? '已配置，留空则不修改' : '输入当前使用的 API Key'}
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

              <div className="resource-ops-inline-actions">
                <Button loading={aiTesting} onClick={onTestAiConnection}>
                  测试识别
                </Button>
              </div>
            </div>

            <div className="resource-ops-recognition-section">
              <div className="resource-ops-recognition-section-head">
                <div>
                  <div className="resource-ops-runtime-subtitle">运行状态</div>
                  <small className="resource-ops-recognition-section-hint">全部扫描会重跑当前全部候选；处理待处理只消化积压与异常重试。</small>
                </div>
                <div className="resource-ops-inline-actions">
                  <Button
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

              <div className="resource-ops-runtime-meta-grid">
                <div className="resource-ops-runtime-meta-card">
                  <span>当前状态</span>
                  <strong>
                    {isRunning ? '运行中' : isQueued ? '已排队' : recognitionStatus?.finished_at ? '已完成' : '待命'}
                  </strong>
                  <small>{isRunning || isQueued ? recognitionModeLabel(runningMode || queuedMode) : '等待手动执行或新点击入队'}</small>
                </div>
                <div className="resource-ops-runtime-meta-card">
                  <span>本轮进度</span>
                  <strong>
                    {formatNumber(processedCount)} / {formatNumber(totalCount)}
                  </strong>
                  <small>
                    成功 {formatNumber(recognitionStatus?.matched_count)} / 异常 {formatNumber(recognitionStatus?.error_count)}
                  </small>
                </div>
                <div className="resource-ops-runtime-meta-card">
                  <span>时间</span>
                  <strong>{formatDateTime(recognitionStatus?.started_at || recognitionStatus?.finished_at)}</strong>
                  <small>
                    {recognitionStatus?.finished_at ? `完成：${formatDateTime(recognitionStatus.finished_at)}` : '当前还没有完成时间'}
                  </small>
                </div>
              </div>

              {(busy || recognitionStatus?.finished_at) && (
                <div className="resource-ops-recognition-progress">
                  <div className="resource-ops-recognition-progress-head">
                    <span>识别进度</span>
                    <Tag color={isRunning ? 'processing' : isQueued ? 'gold' : 'success'}>
                      {isRunning ? recognitionModeLabel(runningMode) : isQueued ? `${recognitionModeLabel(queuedMode)} 已排队` : '已完成'}
                    </Tag>
                  </div>
                  <Progress percent={progressPercent} status={isRunning ? 'active' : 'normal'} />
                </div>
              )}

              <div className="resource-ops-runtime-side-note">
                <span>待处理逻辑</span>
                <small>
                  待处理会接住新点击、瞬时积压和识别异常。自动模式会慢慢清空；AI 出错的条目也会留在这里，后续修复后可继续跑。
                </small>
              </div>

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
                      {bindingSummary?.pending_count ? '当前有待处理项，执行后这里会显示“原始标题 -> AI 提取结果”。' : '暂无运行日志'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="resource-ops-runtime-savebar">
            <Text type="secondary">保存后立即应用当前 AI 配置；自动识别是否入队只看“自动识别”开关和 AI 是否可用。</Text>
            <Button type="primary" loading={settingsSaving} onClick={onSaveSettings}>
              保存归并配置
            </Button>
          </div>
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无作品归并配置" />
      )}
    </Card>
  )
}

export default ResourceOpsRecognitionPanel
