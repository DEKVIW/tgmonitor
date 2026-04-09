import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, InputNumber, Popconfirm, Select, Switch, Tag, Typography, message } from 'antd'
import { DeleteOutlined, ReloadOutlined, SaveOutlined, SyncOutlined } from '@ant-design/icons'

import {
  clearLinkCheckData,
  clearOldLinkCheckData,
  dedupLinks,
  getDedupRuntimeSettings,
  updateDedupRuntimeSettings,
} from '@/api/admin'
import type { DedupRuntimeSettingsResponse, DedupRuntimeSettingsUpdate, MaintenanceResult } from '@/types/admin'
import { formatServerDateTime } from '@/utils/dateTime'

import './LinkMaintenanceTools.css'

const { Text } = Typography

const AUTO_TIMEZONE = 'Asia/Shanghai'
const DEFAULT_INTERVAL_HOURS = 1
const DEFAULT_LOOKBACK_HOURS = 72
const DEFAULT_RETENTION_HOURS = 240

type DedupDraft = {
  enabled: boolean
  scope_mode: 'all_history' | 'recent_hours'
  lookback_hours: number
  schedule_interval_hours: number
  stats_retention_hours: number
}

const SCOPE_OPTIONS = [
  { value: 'all_history', label: '全量历史' },
  { value: 'recent_hours', label: '最近小时' },
]

const normalizeScopeMode = (value?: string | null): DedupDraft['scope_mode'] =>
  value === 'recent_hours' ? 'recent_hours' : 'all_history'

const buildScopeLabel = (scopeMode: DedupDraft['scope_mode'], lookbackHours: number) =>
  scopeMode === 'recent_hours' ? `最近 ${lookbackHours} 小时` : '全量历史'

const buildDraft = (config: DedupRuntimeSettingsResponse): DedupDraft => ({
  enabled: config.enabled,
  scope_mode: normalizeScopeMode(config.scope_mode),
  lookback_hours: Math.max(1, config.lookback_hours || DEFAULT_LOOKBACK_HOURS),
  schedule_interval_hours: Math.max(1, config.schedule_interval_hours || DEFAULT_INTERVAL_HOURS),
  stats_retention_hours: Math.max(10, config.stats_retention_hours || DEFAULT_RETENTION_HOURS),
})

const LinkMaintenanceTools = () => {
  const [config, setConfig] = useState<DedupRuntimeSettingsResponse | null>(null)
  const [draft, setDraft] = useState<DedupDraft | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [clearDataLoading, setClearDataLoading] = useState(false)
  const [clearOldDataLoading, setClearOldDataLoading] = useState(false)
  const [clearDays, setClearDays] = useState(30)
  const [lastRunResult, setLastRunResult] = useState<MaintenanceResult | null>(null)

  const loadConfig = async () => {
    setLoading(true)
    try {
      const result = await getDedupRuntimeSettings()
      setConfig(result)
      setDraft(buildDraft(result))
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载链接去重配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadConfig()
  }, [])

  const payload = useMemo<DedupRuntimeSettingsUpdate | null>(() => {
    if (!draft) {
      return null
    }
    return {
      enabled: draft.enabled,
      scope_mode: draft.scope_mode,
      lookback_hours: draft.lookback_hours,
      schedule_interval_hours: draft.schedule_interval_hours,
      schedule_minute: 0,
      timezone: AUTO_TIMEZONE,
      stats_retention_hours: draft.stats_retention_hours,
    }
  }, [draft])

  const draftChanged = useMemo(() => {
    if (!config || !payload) {
      return false
    }

    const baseline: DedupRuntimeSettingsUpdate = {
      enabled: config.enabled,
      scope_mode: normalizeScopeMode(config.scope_mode),
      lookback_hours: Math.max(1, config.lookback_hours || DEFAULT_LOOKBACK_HOURS),
      schedule_interval_hours: Math.max(1, config.schedule_interval_hours || DEFAULT_INTERVAL_HOURS),
      schedule_minute: 0,
      timezone: AUTO_TIMEZONE,
      stats_retention_hours: Math.max(10, config.stats_retention_hours || DEFAULT_RETENTION_HOURS),
    }

    return JSON.stringify(payload) !== JSON.stringify(baseline)
  }, [config, payload])

  const currentScopeLabel = draft
    ? buildScopeLabel(draft.scope_mode, draft.lookback_hours)
    : config?.scope_label || '全量历史'

  const summary = config?.last_run_summary || {}

  const handleSave = async () => {
    if (!payload) {
      return
    }

    setSaving(true)
    try {
      const result = await updateDedupRuntimeSettings(payload)
      setConfig(result)
      setDraft(buildDraft(result))
      message.success('链接去重计划已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存链接去重计划失败')
    } finally {
      setSaving(false)
    }
  }

  const handleRun = async () => {
    setRunning(true)
    try {
      const result = await dedupLinks()
      setLastRunResult(result)
      if (result.success) {
        message.success(`去重完成，删除 ${result.deleted_count || 0} 条重复消息`)
      } else {
        message.warning(result.error || '去重任务未执行')
      }
      await loadConfig()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '执行链接去重失败')
    } finally {
      setRunning(false)
    }
  }

  const handleClearLinkCheckData = async () => {
    setClearDataLoading(true)
    try {
      const result = await clearLinkCheckData()
      if (result.success) {
        message.success(`已清空 ${result.deleted_details || 0} 条详情、${result.deleted_stats || 0} 条统计`)
      } else {
        message.error(result.error || '清空检测记录失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '清空链接检测记录失败')
    } finally {
      setClearDataLoading(false)
    }
  }

  const handleClearOldData = async () => {
    setClearOldDataLoading(true)
    try {
      const result = await clearOldLinkCheckData({ days: clearDays })
      if (result.success) {
        message.success(`已清理 ${result.deleted_details || 0} 条详情、${result.deleted_stats || 0} 条统计`)
      } else {
        message.error(result.error || '清理旧检测记录失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '清理旧检测记录失败')
    } finally {
      setClearOldDataLoading(false)
    }
  }

  return (
    <Card
      className="link-check-runtime-card"
      loading={loading}
      title={
        <div className="link-check-runtime-card-heading">
          <div className="link-check-runtime-card-heading-main">
            <span className="link-check-runtime-card-title">维护工具</span>
            <Text type="secondary">统一管理链接去重与检测记录清理</Text>
          </div>
        </div>
      }
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => void loadConfig()}>
          刷新
        </Button>
      }
    >
      <div className="maintenance-tools-grid">
        <section className="maintenance-tools-panel is-wide">
          <div className="maintenance-tools-panel-head">
            <div className="maintenance-tools-panel-copy">
              <div className="maintenance-tools-panel-title">链接去重</div>
              <Text type="secondary">手动执行和自动执行共用同一套去重逻辑，结果都会进入去重统计图。</Text>
            </div>
            <div className="maintenance-tools-panel-head-actions">
              <Tag>{currentScopeLabel}</Tag>
              <div className="maintenance-tools-switch-pill">
                <span>{draft?.enabled ? '自动开启' : '自动关闭'}</span>
                <Switch
                  checked={draft?.enabled}
                  onChange={(checked) =>
                    setDraft((current) => (current ? { ...current, enabled: checked } : current))
                  }
                />
              </div>
            </div>
          </div>

          <div className="maintenance-tools-summary-grid">
            <div className="maintenance-tools-summary-card">
              <span className="maintenance-tools-summary-label">上次删除</span>
              <span className="maintenance-tools-summary-value">{summary.deleted_count ?? 0}</span>
              <span className="maintenance-tools-summary-meta">手动去重和自动去重都会写入这份统计。</span>
            </div>
            <div className="maintenance-tools-summary-card">
              <span className="maintenance-tools-summary-label">自动节奏</span>
              <span className="maintenance-tools-summary-value">每 {draft?.schedule_interval_hours || 1} 小时</span>
              <span className="maintenance-tools-summary-meta">固定按上海时区排队，不再单独配置时区。</span>
            </div>
            <div className="maintenance-tools-summary-card">
              <span className="maintenance-tools-summary-label">运行时间</span>
              <span className="maintenance-tools-summary-value">
                {formatServerDateTime(config?.next_run_at, 'MM-DD HH:mm')}
              </span>
              <span className="maintenance-tools-summary-meta">
                上次 {formatServerDateTime(config?.last_run_at, 'MM-DD HH:mm')}
              </span>
            </div>
          </div>

          <div className="maintenance-tools-field-grid maintenance-tools-field-grid-compact">
            <div className="maintenance-tools-field">
              <span className="maintenance-tools-field-label">自动间隔</span>
              <InputNumber
                min={1}
                max={24 * 7}
                value={draft?.schedule_interval_hours}
                onChange={(value) =>
                  setDraft((current) =>
                    current
                      ? {
                          ...current,
                          schedule_interval_hours: Math.max(
                            1,
                            Number(value || current.schedule_interval_hours || DEFAULT_INTERVAL_HOURS)
                          ),
                        }
                      : current
                  )
                }
              />
              <small className="maintenance-tools-field-help">
                到点只排一条任务；上一轮还没跑完，会自动顺延，不会并发删除。
              </small>
            </div>

            <div className="maintenance-tools-field">
              <span className="maintenance-tools-field-label">扫描范围</span>
              <Select
                value={draft?.scope_mode}
                options={SCOPE_OPTIONS}
                onChange={(value) =>
                  setDraft((current) =>
                    current ? { ...current, scope_mode: value as DedupDraft['scope_mode'] } : current
                  )
                }
              />
              <small className="maintenance-tools-field-help">全量历史会扫全部消息，最近小时只扫一个滑动窗口。</small>
            </div>

            <div className="maintenance-tools-field">
              <span className="maintenance-tools-field-label">最近小时</span>
              <InputNumber
                min={1}
                max={24 * 365}
                disabled={draft?.scope_mode !== 'recent_hours'}
                value={draft?.lookback_hours}
                onChange={(value) =>
                  setDraft((current) =>
                    current
                      ? {
                          ...current,
                          lookback_hours: Math.max(
                            1,
                            Number(value || current.lookback_hours || DEFAULT_LOOKBACK_HOURS)
                          ),
                        }
                      : current
                  )
                }
              />
              <small className="maintenance-tools-field-help">
                只在“最近小时”模式生效，表示仅扫描最近 N 小时内的消息。
              </small>
            </div>

            <div className="maintenance-tools-field">
              <span className="maintenance-tools-field-label">统计保留</span>
              <InputNumber
                min={10}
                max={24 * 365}
                value={draft?.stats_retention_hours}
                onChange={(value) =>
                  setDraft((current) =>
                    current
                      ? {
                          ...current,
                          stats_retention_hours: Math.max(
                            10,
                            Number(value || current.stats_retention_hours || DEFAULT_RETENTION_HOURS)
                          ),
                        }
                      : current
                  )
                }
              />
              <small className="maintenance-tools-field-help">
                只影响去重统计图保留多久，不会删除消息正文和业务数据。
              </small>
            </div>
          </div>

          <Alert
            showIcon
            type="info"
            message={config?.status_summary || '自动去重已关闭'}
            description="自动计划现在按小时排队执行；如果当前已经有去重在跑，会顺延 30 分钟继续排队。"
          />

          {lastRunResult && !lastRunResult.success ? (
            <Alert showIcon type="warning" message={lastRunResult.error || '去重任务未执行'} />
          ) : null}

          {config?.last_error_message ? (
            <Alert
              showIcon
              type={config.last_status === 'failed' ? 'error' : 'warning'}
              message={config.last_error_message}
            />
          ) : null}

          <div className="maintenance-tools-actions">
            <Button
              icon={<SaveOutlined />}
              type="primary"
              loading={saving}
              disabled={!draftChanged}
              onClick={handleSave}
            >
              保存计划
            </Button>
            <Button icon={<SyncOutlined />} loading={running} onClick={handleRun}>
              立即去重
            </Button>
          </div>
        </section>

        <section className="maintenance-tools-panel">
          <div className="maintenance-tools-panel-head">
            <div className="maintenance-tools-panel-copy">
              <div className="maintenance-tools-panel-title">记录清理</div>
              <Text type="secondary">这里只清理链接检测结果，不会删除消息正文。</Text>
            </div>
          </div>

          <div className="maintenance-tools-cleanup-stack">
            <div className="maintenance-tools-inline-row">
              <span className="maintenance-tools-field-label">保留天数</span>
              <InputNumber
                min={1}
                max={3650}
                value={clearDays}
                onChange={(value) => setClearDays(Math.max(1, Number(value || 30)))}
              />
              <Popconfirm
                title={`确认清理 ${clearDays} 天前的检测记录？`}
                description="只删除历史检测详情和统计，不影响消息数据。"
                onConfirm={handleClearOldData}
                okText="确认"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button danger icon={<DeleteOutlined />} loading={clearOldDataLoading}>
                  清理旧记录
                </Button>
              </Popconfirm>
            </div>

            <Popconfirm
              title="确认清空全部检测记录？"
              description="该操作不可恢复，但只影响链接检测历史。"
              onConfirm={handleClearLinkCheckData}
              okText="确认"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button danger icon={<DeleteOutlined />} loading={clearDataLoading}>
                清空全部记录
              </Button>
            </Popconfirm>
          </div>
        </section>
      </div>
    </Card>
  )
}

export default LinkMaintenanceTools
