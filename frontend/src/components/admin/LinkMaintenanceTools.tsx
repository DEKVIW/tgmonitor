import { useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  Alert,
  Button,
  Card,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tag,
  TimePicker,
  Typography,
  message,
} from 'antd'
import {
  DeleteOutlined,
  ReloadOutlined,
  SaveOutlined,
  SyncOutlined,
} from '@ant-design/icons'

import {
  clearLinkCheckData,
  clearOldLinkCheckData,
  dedupLinks,
  getDedupRuntimeSettings,
  updateDedupRuntimeSettings,
} from '@/api/admin'
import type {
  DedupRuntimeSettingsResponse,
  DedupRuntimeSettingsUpdate,
  MaintenanceResult,
} from '@/types/admin'
import './LinkMaintenanceTools.css'

const { Text } = Typography

type DedupDraft = {
  enabled: boolean
  scope_mode: 'all_history' | 'recent_hours'
  lookback_hours: number
  schedule_time: Dayjs
  timezone: string
  stats_retention_hours: number
}

const TIMEZONE_OPTIONS = [
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai' },
  { value: 'UTC', label: 'UTC' },
]

const SCOPE_OPTIONS = [
  { value: 'all_history', label: '全量历史' },
  { value: 'recent_hours', label: '最近小时' },
]

const toScheduleTime = (hour: number, minute: number) =>
  dayjs().hour(hour).minute(minute).second(0).millisecond(0)

const parseBackendDateTime = (value?: string | null) => {
  const normalized = value?.trim()
  if (!normalized) {
    return null
  }
  const hasTimezoneSuffix = /([zZ]|[+-]\d{2}:\d{2})$/.test(normalized)
  const parsed = dayjs(hasTimezoneSuffix ? normalized : `${normalized}Z`)
  return parsed.isValid() ? parsed : null
}

const formatDateTime = (value?: string | null, format = 'YYYY-MM-DD HH:mm') => {
  const parsed = parseBackendDateTime(value)
  return parsed ? parsed.format(format) : '-'
}

const buildDraft = (config: DedupRuntimeSettingsResponse): DedupDraft => ({
  enabled: config.enabled,
  scope_mode: config.scope_mode === 'recent_hours' ? 'recent_hours' : 'all_history',
  lookback_hours: Math.max(1, config.lookback_hours || 72),
  schedule_time: toScheduleTime(config.schedule_hour, config.schedule_minute),
  timezone: config.timezone || 'Asia/Shanghai',
  stats_retention_hours: Math.max(10, config.stats_retention_hours || 240),
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

  useEffect(() => {
    void loadConfig()
  }, [])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const result = await getDedupRuntimeSettings()
      setConfig(result)
      setDraft(buildDraft(result))
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载去重计划失败')
    } finally {
      setLoading(false)
    }
  }

  const payload = useMemo<DedupRuntimeSettingsUpdate | null>(() => {
    if (!draft) {
      return null
    }
    return {
      enabled: draft.enabled,
      scope_mode: draft.scope_mode,
      lookback_hours: draft.lookback_hours,
      schedule_hour: draft.schedule_time.hour(),
      schedule_minute: draft.schedule_time.minute(),
      timezone: draft.timezone,
      stats_retention_hours: draft.stats_retention_hours,
    }
  }, [draft])

  const draftChanged = useMemo(() => {
    if (!config || !payload) {
      return false
    }
    return JSON.stringify(payload) !== JSON.stringify({
      enabled: config.enabled,
      scope_mode: config.scope_mode === 'recent_hours' ? 'recent_hours' : 'all_history',
      lookback_hours: config.lookback_hours,
      schedule_hour: config.schedule_hour,
      schedule_minute: config.schedule_minute,
      timezone: config.timezone,
      stats_retention_hours: config.stats_retention_hours,
    })
  }, [config, payload])

  const handleSave = async () => {
    if (!payload) {
      return
    }
    setSaving(true)
    try {
      const result = await updateDedupRuntimeSettings(payload)
      setConfig(result)
      setDraft(buildDraft(result))
      message.success('去重计划已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存去重计划失败')
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
      message.error(error.response?.data?.detail || '执行去重失败')
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
        message.error(result.error || '清空失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '清空检测记录失败')
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
        message.error(result.error || '清理失败')
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '清理旧检测记录失败')
    } finally {
      setClearOldDataLoading(false)
    }
  }

  const summary = config?.last_run_summary || {}

  return (
    <Card
      className="link-check-runtime-card"
      loading={loading}
      title={
        <div className="link-check-runtime-card-heading">
          <div className="link-check-runtime-card-heading-main">
            <span className="link-check-runtime-card-title">维护工具</span>
            <Text type="secondary">统一管理自动去重和检测记录清理</Text>
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
            <div>
              <div className="maintenance-tools-panel-title">链接去重</div>
              <Text type="secondary">后台手动和自动计划都走同一套去重规则</Text>
            </div>
            <Space size={[8, 8]} wrap>
              <Tag color={config?.enabled ? 'success' : 'default'}>
                {config?.enabled ? '自动开启' : '自动关闭'}
              </Tag>
              <Tag>{config?.scope_label || '全量历史'}</Tag>
              <Tag>{config?.timezone || 'Asia/Shanghai'}</Tag>
            </Space>
          </div>

          <div className="maintenance-tools-summary-grid">
            <div className="maintenance-tools-summary-card">
              <span className="maintenance-tools-summary-label">上次删除</span>
              <span className="maintenance-tools-summary-value">{summary.deleted_count ?? 0}</span>
              <span className="maintenance-tools-summary-meta">手动和自动都会写入去重统计图</span>
            </div>
            <div className="maintenance-tools-summary-card">
              <span className="maintenance-tools-summary-label">扫描消息</span>
              <span className="maintenance-tools-summary-value">{summary.scanned_messages ?? 0}</span>
              <span className="maintenance-tools-summary-meta">范围 {config?.scope_label || '全量历史'}</span>
            </div>
            <div className="maintenance-tools-summary-card">
              <span className="maintenance-tools-summary-label">下次执行</span>
              <span className="maintenance-tools-summary-value">{formatDateTime(config?.next_run_at, 'MM-DD HH:mm')}</span>
              <span className="maintenance-tools-summary-meta">
                上次 {formatDateTime(config?.last_run_at, 'MM-DD HH:mm')}
              </span>
            </div>
          </div>

          <div className="maintenance-tools-field-grid">
            <div className="maintenance-tools-field">
              <span className="maintenance-tools-field-label">自动计划</span>
              <Switch
                checked={draft?.enabled}
                onChange={(checked) =>
                  setDraft((current) => (current ? { ...current, enabled: checked } : current))
                }
              />
            </div>

            <div className="maintenance-tools-field">
              <span className="maintenance-tools-field-label">执行时间</span>
              <TimePicker
                allowClear={false}
                format="HH:mm"
                value={draft?.schedule_time}
                onChange={(value) =>
                  setDraft((current) => (current && value ? { ...current, schedule_time: value } : current))
                }
              />
            </div>

            <div className="maintenance-tools-field">
              <span className="maintenance-tools-field-label">时区</span>
              <Select
                value={draft?.timezone}
                options={TIMEZONE_OPTIONS}
                onChange={(value) =>
                  setDraft((current) => (current ? { ...current, timezone: value } : current))
                }
              />
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
                          lookback_hours: Math.max(1, Number(value || current.lookback_hours || 72)),
                        }
                      : current
                  )
                }
              />
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
                          stats_retention_hours: Math.max(10, Number(value || current.stats_retention_hours || 240)),
                        }
                      : current
                  )
                }
              />
            </div>
          </div>

          <Alert
            showIcon
            type="info"
            message={config?.status_summary || '自动去重已关闭'}
            description="到点只会排一轮去重；如果当前已有去重在跑，会自动顺延 30 分钟，不会并发删除。"
          />

          {lastRunResult && !lastRunResult.success ? (
            <Alert showIcon type="warning" message={lastRunResult.error || '去重任务未执行'} />
          ) : null}

          {config?.last_error_message ? (
            <Alert showIcon type={config.last_status === 'failed' ? 'error' : 'warning'} message={config.last_error_message} />
          ) : null}

          <div className="maintenance-tools-actions">
            <Button icon={<SaveOutlined />} type="primary" loading={saving} disabled={!draftChanged} onClick={handleSave}>
              保存计划
            </Button>
            <Button icon={<SyncOutlined />} loading={running} onClick={handleRun}>
              立即去重
            </Button>
          </div>
        </section>

        <section className="maintenance-tools-panel">
          <div className="maintenance-tools-panel-head">
            <div>
              <div className="maintenance-tools-panel-title">记录清理</div>
              <Text type="secondary">只清理链接检测结果，不会删消息正文</Text>
            </div>
          </div>

          <div className="maintenance-tools-cleanup-stack">
            <div className="maintenance-tools-inline-row">
              <span className="maintenance-tools-field-label">保留天数</span>
              <InputNumber min={1} max={3650} value={clearDays} onChange={(value) => setClearDays(Number(value || 30))} />
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
