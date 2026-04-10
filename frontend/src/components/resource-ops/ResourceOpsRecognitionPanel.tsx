import { Alert, Button, Card, Empty, Input, InputNumber, Progress, Select, Switch, Typography } from 'antd'
import { RobotOutlined } from '@ant-design/icons'

import type {
  ResourceOpsAiModelItem,
  ResourceOpsAiTestResponse,
  ResourceOpsRuntimeSettingsResponse,
  ResourceOpsRuntimeSettingsUpdateRequest,
  ResourceOpsWorkBindingSummary,
} from '@/types/resourceOps'
import { formatServerDateTime } from '@/utils/dateTime'

const { Text } = Typography

interface RecognitionSummaryItem {
  label: string
  value: number
  hint: string
}

interface ResourceOpsRecognitionPanelProps {
  loading: boolean
  settingsSaving: boolean
  recognitionRunning: boolean
  aiModelsLoading: boolean
  aiTesting: boolean
  settingsDraft: ResourceOpsRuntimeSettingsUpdateRequest | null
  runtimeSettings: ResourceOpsRuntimeSettingsResponse | null
  bindingSummary: ResourceOpsWorkBindingSummary | null
  recognitionSummaryItems: RecognitionSummaryItem[]
  aiApiKeyInput: string
  aiModelOptions: ResourceOpsAiModelItem[]
  aiTestResult: ResourceOpsAiTestResponse | null
  formatNumber: (value?: number | null) => string
  onPatchDraft: (key: keyof ResourceOpsRuntimeSettingsUpdateRequest, value: string | number | boolean) => void
  onAiApiKeyInputChange: (value: string) => void
  onLoadAiModels: () => void
  onTestAiConnection: () => void
  onRunRecognition: (mode: 'pending' | 'full') => void
  onSaveSettings: () => void
}

const ResourceOpsRecognitionPanel = ({
  loading,
  settingsSaving,
  recognitionRunning,
  aiModelsLoading,
  aiTesting,
  settingsDraft,
  runtimeSettings,
  bindingSummary,
  recognitionSummaryItems,
  aiApiKeyInput,
  aiModelOptions,
  aiTestResult,
  formatNumber,
  onPatchDraft,
  onAiApiKeyInputChange,
  onLoadAiModels,
  onTestAiConnection,
  onRunRecognition,
  onSaveSettings,
}: ResourceOpsRecognitionPanelProps) => {
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
              <p className="resource-ops-runtime-hint">AI 只读取被点击链接对应的原始消息标题，并提取影视剧名称后做同名归并。</p>
            </div>
            <div className="resource-ops-inline-switch">
              <div className="resource-ops-inline-switch-copy">
                <span>自动识别</span>
                <small>按批次自动处理待归并候选</small>
              </div>
              <Switch
                checked={settingsDraft.auto_bind_enabled}
                onChange={(checked) => onPatchDraft('auto_bind_enabled', checked)}
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

          <div className="resource-ops-runtime-meta-grid">
            <div className="resource-ops-runtime-meta-card">
              <span>AI 状态</span>
              <strong>{runtimeSettings.ai_provider_ready ? '已就绪' : '未就绪'}</strong>
              <small>{runtimeSettings.ai_provider_ready ? '可直接执行归并' : '先补齐 Base URL、API Key 和模型'}</small>
            </div>
            <div className="resource-ops-runtime-meta-card">
              <span>上次归并</span>
              <strong>{formatServerDateTime(runtimeSettings.last_sync_at)}</strong>
              <small>
                成功 {formatNumber(runtimeSettings.last_sync_summary?.matched_count)}，异常{' '}
                {formatNumber(runtimeSettings.last_sync_summary?.error_count)}
              </small>
            </div>
            <div className="resource-ops-runtime-meta-card">
              <span>全量进度</span>
              <strong>
                {bindingSummary?.full_sync_processed || 0} / {bindingSummary?.full_sync_total || 0}
              </strong>
              <small>
                {bindingSummary?.full_sync_active
                  ? `进行中，已完成 ${bindingSummary.full_sync_progress}%`
                  : '未运行全量归并'}
              </small>
            </div>
          </div>

          {!runtimeSettings.ai_provider_ready ? (
            <Alert
              type="warning"
              showIcon
              message="请先配置可用 AI"
              description="先填写 Base URL、API Key 和模型，再保存配置。模型无效时运行时会自动尝试切换可用模型。"
            />
          ) : null}

          {bindingSummary?.full_sync_active ? (
            <Alert
              type="info"
              showIcon
              message="全量归并进行中"
              description={
                <div className="resource-ops-progress-note">
                  <Progress percent={bindingSummary.full_sync_progress} size="small" status="active" />
                  <div>
                    已处理 {bindingSummary.full_sync_processed} / {bindingSummary.full_sync_total}，开始时间{' '}
                    {formatServerDateTime(bindingSummary.full_sync_started_at)}
                  </div>
                </div>
              }
            />
          ) : null}

          {aiTestResult ? (
            <Alert
              type="success"
              showIcon
              message={`测试识别结果：${aiTestResult.extracted_title || '未识别到作品名'}`}
              description={`模型 ${aiTestResult.model}${aiTestResult.reason ? ` / ${aiTestResult.reason}` : ''}`}
            />
          ) : null}

          <div className="resource-ops-runtime-subsection">
            <div className="resource-ops-runtime-subtitle">AI 配置</div>
            <div className="resource-ops-runtime-form-grid">
              <div className="resource-ops-inline-switch">
                <div className="resource-ops-inline-switch-copy">
                  <span>启用 AI</span>
                  <small>关闭后暂停归并接口和自动识别</small>
                </div>
                <Switch checked={settingsDraft.ai_enabled} onChange={(checked) => onPatchDraft('ai_enabled', checked)} />
              </div>

              <div className="resource-ops-form-field resource-ops-field-span-2">
                <label>Base URL</label>
                <Input
                  value={settingsDraft.ai_base_url}
                  placeholder="例如：https://api.example.com"
                  onChange={(event) => onPatchDraft('ai_base_url', event.target.value)}
                />
              </div>

              <div className="resource-ops-form-field resource-ops-field-span-2">
                <label>API Key</label>
                <Input.Password
                  value={aiApiKeyInput}
                  placeholder={runtimeSettings.ai_api_key_configured ? '已配置，留空则不修改' : '输入当前使用的 API Key'}
                  onChange={(event) => onAiApiKeyInputChange(event.target.value)}
                />
              </div>

              <div className="resource-ops-form-field resource-ops-field-span-2">
                <label>模型</label>
                {aiModelOptions.length > 0 ? (
                  <Select
                    showSearch
                    optionFilterProp="label"
                    value={settingsDraft.ai_model || undefined}
                    placeholder="先刷新模型列表再选择"
                    options={aiModelOptions.map((item) => ({
                      value: item.id,
                      label: item.label || item.id,
                    }))}
                    onChange={(value) => onPatchDraft('ai_model', value)}
                  />
                ) : (
                  <Input
                    value={settingsDraft.ai_model}
                    placeholder="可手动填写，也可先刷新模型列表"
                    onChange={(event) => onPatchDraft('ai_model', event.target.value)}
                  />
                )}
              </div>
            </div>
            <div className="resource-ops-inline-actions">
              <Button loading={aiModelsLoading} onClick={onLoadAiModels}>
                刷新模型
              </Button>
              <Button loading={aiTesting} onClick={onTestAiConnection}>
                测试识别
              </Button>
            </div>
          </div>

          <div className="resource-ops-runtime-subsection">
            <div className="resource-ops-runtime-subtitle">调度</div>
            <div className="resource-ops-runtime-form-grid">
              <div className="resource-ops-form-field resource-ops-form-field-compact">
                <label>每批数量</label>
                <InputNumber
                  min={1}
                  max={100}
                  value={settingsDraft.sync_batch_size}
                  onChange={(value) => onPatchDraft('sync_batch_size', Number(value || 1))}
                />
              </div>
              <div className="resource-ops-form-field resource-ops-form-field-compact">
                <label>间隔分钟</label>
                <InputNumber
                  min={5}
                  max={1440}
                  value={settingsDraft.sync_interval_minutes}
                  onChange={(value) => onPatchDraft('sync_interval_minutes', Number(value || 5))}
                />
              </div>
            </div>
            <div className="resource-ops-card-actions">
              <Button
                loading={recognitionRunning}
                disabled={!runtimeSettings.ai_provider_ready}
                onClick={() => onRunRecognition('pending')}
              >
                跑一批待处理
              </Button>
              <Button
                loading={recognitionRunning}
                disabled={!runtimeSettings.ai_provider_ready}
                onClick={() => onRunRecognition('full')}
              >
                {bindingSummary?.full_sync_active ? '继续全量跑' : '全部跑一遍'}
              </Button>
            </div>
          </div>

          <div className="resource-ops-runtime-savebar">
            <Text type="secondary">保存后立即应用 AI 归并配置。</Text>
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
