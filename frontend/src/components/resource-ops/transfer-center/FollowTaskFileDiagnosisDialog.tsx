import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Empty, InputNumber, Modal, Segmented, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { createPanTransferFollowSyncBatch, diagnosePanTransferFollowTaskFiles } from '@/api/panTransfer'
import type {
  PanTransferFollowTaskFileDiagnosisEntry,
  PanTransferFollowTaskFileDiagnosisPlanItem,
  PanTransferFollowTaskFileDiagnosisResponse,
  PanTransferFollowTaskItem,
} from '@/types/panTransfer'
import { formatServerDateTime } from '@/utils/dateTime'

import { getErrorMessage } from './shared'

const { Paragraph, Text } = Typography

type FollowTaskFileDiagnosisModalProps = {
  open: boolean
  task: PanTransferFollowTaskItem | null
  hasCandidate: boolean
  onClose: () => void
  onTaskChanged?: () => Promise<void> | void
}

type SourceKind = 'current' | 'candidate'

const STOP_REASON_LABELS: Record<string, string> = {
  contiguous_window_hit: '已命中连续更新，可直接生成增量补集计划',
  gap_before_next_episode: '下一集之前存在断档，系统先停在第一处缺口',
  no_source_video: '来源链接里还没有识别到可用视频文件',
  no_accepted_episode: '来源文件里有视频，但暂时没有识别到可信剧集',
}

const formatDateTime = (value?: string | null) =>
  value ? formatServerDateTime(value, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai') : '-'

const formatSize = (value?: number | null) => {
  if (!value || value <= 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 2)} ${units[index]}`
}

const formatSourceKind = (value?: string | null) =>
  String(value || '').trim().toLowerCase() === 'candidate' ? '候选原链' : '当前原链'

const formatEpisodeValue = (value?: number | null) => (value == null ? '待识别' : `EP ${value}`)

const joinEpisodeNumbers = (values?: number[]) => (values && values.length > 0 ? values.join(', ') : '暂无')

const FollowTaskFileDiagnosisDialog = ({
  open,
  task,
  hasCandidate,
  onClose,
  onTaskChanged,
}: FollowTaskFileDiagnosisModalProps) => {
  const [sourceKind, setSourceKind] = useState<SourceKind>('candidate')
  const [nearEpisodeWindow, setNearEpisodeWindow] = useState(5)
  const [loading, setLoading] = useState(false)
  const [creatingSync, setCreatingSync] = useState(false)
  const [diagnosis, setDiagnosis] = useState<PanTransferFollowTaskFileDiagnosisResponse | null>(null)

  useEffect(() => {
    if (!open || !task) return
    setSourceKind(hasCandidate ? 'candidate' : 'current')
    setNearEpisodeWindow(5)
    setDiagnosis(null)
  }, [open, task?.id, hasCandidate])

  const runDiagnosis = async (nextSourceKind = sourceKind, nextWindow = nearEpisodeWindow) => {
    if (!task) return
    setLoading(true)
    try {
      const response = await diagnosePanTransferFollowTaskFiles(task.id, {
        source_kind: nextSourceKind,
        near_episode_window: nextWindow,
      })
      setDiagnosis(response)
      await onTaskChanged?.()
    } catch (error) {
      message.error(getErrorMessage(error, '生成补集诊断失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open || !task) return
    void runDiagnosis(hasCandidate ? 'candidate' : 'current', 5)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, task?.id])

  const createRecommendedSync = async () => {
    if (!task || !diagnosis || diagnosis.recommended_selection_groups.length <= 0) return
    setCreatingSync(true)
    try {
      const response = await createPanTransferFollowSyncBatch(task.id, {
        source_kind: sourceKind,
        sync_mode: 'incremental',
        selection_groups: diagnosis.recommended_selection_groups,
        reuse_existing_share_if_valid: true,
        update_publish_record: true,
      })
      message.success(`已创建推荐增量同步批次 #${response.batch_id}`)
      await onTaskChanged?.()
      onClose()
    } catch (error) {
      message.error(getErrorMessage(error, '创建推荐增量同步失败'))
    } finally {
      setCreatingSync(false)
    }
  }

  const sourceColumns: ColumnsType<PanTransferFollowTaskFileDiagnosisEntry> = [
    {
      title: '文件',
      dataIndex: 'name',
      key: 'name',
      render: (_, record) => (
        <div className="resource-ops-follow-file-name">
          <span>{record.name}</span>
          <small>{record.parent_path || record.parent_name || '根目录'}</small>
        </div>
      ),
    },
    {
      title: '集数',
      dataIndex: 'episode_numbers',
      key: 'episode_numbers',
      width: 138,
      render: (value: number[]) => (value?.length ? value.join(', ') : '-'),
    },
    {
      title: '解析',
      key: 'parse',
      width: 172,
      render: (_, record) => (
        <div className="resource-ops-follow-file-parse">
          <Tag color={record.parse_level === 'full' ? 'processing' : 'default'}>
            {record.parse_level === 'full' ? '完整解析' : '快速解析'}
          </Tag>
          <small>{record.parse_reason}</small>
        </div>
      ),
    },
    {
      title: '规格',
      dataIndex: 'quality_tags',
      key: 'quality_tags',
      width: 180,
      render: (value: string[]) =>
        value?.length ? (
          <div className="resource-ops-follow-chip-row">
            {value.slice(0, 4).map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>
        ) : (
          '-'
        ),
    },
    {
      title: '修改时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 156,
      render: (value?: string | null) => formatDateTime(value),
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      key: 'size_bytes',
      width: 120,
      render: (value?: number | null) => formatSize(value),
    },
    {
      title: '状态',
      key: 'state',
      width: 146,
      render: (_, record) => (
        <Space size={[4, 4]} wrap>
          {record.accepted ? <Tag color="success">可用</Tag> : <Tag>待确认</Tag>}
          {record.selected ? <Tag color="processing">已推荐</Tag> : null}
        </Space>
      ),
    },
  ]

  const planColumns: ColumnsType<PanTransferFollowTaskFileDiagnosisPlanItem> = [
    {
      title: '推荐文件',
      dataIndex: 'name',
      key: 'name',
      render: (_, record) => (
        <div className="resource-ops-follow-file-name">
          <span>{record.name}</span>
          <small>{record.parent_path || '根目录'}</small>
        </div>
      ),
    },
    {
      title: '补齐集数',
      dataIndex: 'episodes',
      key: 'episodes',
      width: 138,
      render: (value: number[]) => (value?.length ? value.join(', ') : '-'),
    },
    {
      title: '写入位置',
      dataIndex: 'target_relative_path',
      key: 'target_relative_path',
      width: 180,
      render: (value?: string | null) => value || '资源目录根层',
    },
    {
      title: '规格',
      dataIndex: 'quality_tags',
      key: 'quality_tags',
      width: 180,
      render: (value: string[]) =>
        value?.length ? (
          <div className="resource-ops-follow-chip-row">
            {value.slice(0, 4).map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>
        ) : (
          '-'
        ),
    },
    {
      title: '修改时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 156,
      render: (value?: string | null) => formatDateTime(value),
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      key: 'size_bytes',
      width: 120,
      render: (value?: number | null) => formatSize(value),
    },
  ]

  const summary = diagnosis?.summary
  const diagnosisConfigDirty = Boolean(
    summary &&
      (summary.source_kind !== sourceKind || summary.near_episode_window !== nearEpisodeWindow)
  )
  const canCreateRecommendedSync = Boolean(
    diagnosis &&
      diagnosis.recommended_selection_groups.length > 0 &&
      !diagnosisConfigDirty &&
      !loading
  )

  const recommendationText = useMemo(() => {
    if (!summary) return ''
    if (summary.recommended_episode_numbers.length > 0) {
      return `建议补齐 ${summary.recommended_episode_numbers.join(', ')}`
    }
    return STOP_REASON_LABELS[summary.stop_reason] || '本次还没有形成可直接执行的增量补集计划'
  }, [summary])

  const keyFacts = useMemo(() => {
    if (!summary || !task) return []
    return [
      {
        label: '当前进度',
        value: formatEpisodeValue(summary.tracked_episode),
        note:
          [
            summary.latest_target_episode != null ? `资源目录最新 ${formatEpisodeValue(summary.latest_target_episode)}` : null,
            summary.anchor_episode != null ? `锚点 ${formatEpisodeValue(summary.anchor_episode)}` : null,
            summary.target_scope_relative_path ? `诊断范围 ${summary.target_scope_relative_path}` : null,
          ]
            .filter(Boolean)
            .join(' · ') || '资源目录里还没识别到稳定进度',
      },
      {
        label: '来源最新',
        value: formatEpisodeValue(summary.source_latest_episode),
        note:
          summary.source_episode_numbers.length > 0
            ? `识别到 ${joinEpisodeNumbers(summary.source_episode_numbers)}`
            : '来源里还没识别到可信集数',
      },
      {
        label: '待补集数',
        value: summary.recommended_episode_numbers.length > 0 ? joinEpisodeNumbers(summary.recommended_episode_numbers) : '暂无',
        note: recommendationText,
      },
      {
        label: '写入位置',
        value: summary.inferred_target_relative_path || '资源目录根层',
        note: `锁定目录 ${task.fixed_save_path || '-'}`,
      },
      {
        label: '诊断来源',
        value: formatSourceKind(summary.source_kind),
        note: `近窗 ${summary.near_episode_window} 集`,
      },
    ]
  }, [recommendationText, summary, task])

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={1120}
      destroyOnHidden
      title="补集诊断"
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <Button onClick={() => void runDiagnosis()} loading={loading}>
            重新诊断
          </Button>
          <Button
            type="primary"
            disabled={!canCreateRecommendedSync}
            loading={creatingSync}
            onClick={() => void createRecommendedSync()}
          >
            按推荐结果增量同步
          </Button>
        </Space>
      }
    >
      {task ? (
        <div className="resource-ops-follow-diagnosis-stack">
          <Paragraph className="resource-ops-transfer-copy">
            系统会优先围绕当前进度附近的来源文件做识别，判断来源最新进度、可直接补齐的集数，以及建议写入的位置。
          </Paragraph>

          <div className="resource-ops-follow-diagnosis-toolbar">
            <div className="resource-ops-follow-settings-field">
              <label>诊断来源</label>
              <Segmented
                value={sourceKind}
                options={[
                  { label: '当前原链', value: 'current' },
                  { label: '候选原链', value: 'candidate', disabled: !hasCandidate },
                ]}
                onChange={(value) => setSourceKind(value as SourceKind)}
              />
            </div>
            <div className="resource-ops-follow-settings-field resource-ops-follow-settings-field--narrow">
              <label>近窗范围</label>
              <InputNumber
                min={1}
                max={30}
                value={nearEpisodeWindow}
                onChange={(value) => setNearEpisodeWindow(Number(value || 5))}
                style={{ width: '100%' }}
              />
            </div>
            <div className="resource-ops-follow-diagnosis-target">
              <Text type="secondary">锁定资源目录</Text>
              <strong>{task.fixed_save_path || '-'}</strong>
            </div>
          </div>

          {summary ? (
            <>
              <div className="resource-ops-follow-diagnosis-keyfacts">
                {keyFacts.map((fact) => (
                  <div key={fact.label} className="resource-ops-follow-diagnosis-fact">
                    <span>{fact.label}</span>
                    <strong>{fact.value}</strong>
                    <small>{fact.note}</small>
                  </div>
                ))}
              </div>

              <div className="resource-ops-follow-diagnosis-alerts">
                <Alert
                  type={summary.recommended_entry_count > 0 ? 'success' : 'warning'}
                  showIcon
                  message={summary.recommended_entry_count > 0 ? '已生成可直接执行的补集计划' : '本次还没有形成可直接执行的补集计划'}
                  description={recommendationText}
                />
                {diagnosisConfigDirty ? (
                  <Alert
                    type="info"
                    showIcon
                    message="诊断条件已变更"
                    description="你已经调整了诊断来源或近窗范围，请先重新诊断，再按推荐结果创建增量同步。"
                  />
                ) : null}
                {summary.warnings.length > 0 ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="诊断提示"
                    description={summary.warnings.join('；')}
                  />
                ) : null}
              </div>
            </>
          ) : null}

          <Card size="small" title="推荐补集文件" className="resource-ops-follow-sync-card">
            {diagnosis?.recommended_plan_items?.length ? (
              <Table
                rowKey={(record) => `${record.path || record.name}-${record.episodes.join('-')}`}
                size="small"
                columns={planColumns}
                dataSource={diagnosis.recommended_plan_items}
                pagination={false}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有形成可直接执行的推荐补集计划" />
            )}
          </Card>

          <Collapse
            className="resource-ops-follow-advanced-collapse"
            items={[
              {
                key: 'stats',
                label: '诊断明细',
                children: summary ? (
                  <div className="resource-ops-follow-diagnosis-technical">
                    <small>{`来源目录 ${summary.source_dir_count} · 来源文件 ${summary.source_file_count} · 来源视频 ${summary.source_video_count}`}</small>
                    <small>{`资源目录 ${summary.target_dir_count} · 资源文件 ${summary.target_file_count} · 资源视频 ${summary.target_video_count}`}</small>
                    <small>{`快速解析 ${summary.quick_parsed_count} · 完整解析 ${summary.full_parsed_count} · 窗外跳过 ${summary.skipped_outside_window_count}`}</small>
                    <small>{`最近补充完整解析 ${summary.recent_without_episode_full_parse_count} · 全量替换可选 ${summary.full_entry_count}`}</small>
                  </div>
                ) : null,
              },
              {
                key: 'source',
                label: `来源文件 (${diagnosis?.source_entries.length || 0})`,
                children: (
                  <Table
                    rowKey={(record) => `${record.path || record.name}-${record.entry_id || record.parent_path || 'root'}`}
                    size="small"
                    columns={sourceColumns}
                    dataSource={diagnosis?.source_entries || []}
                    pagination={false}
                    scroll={{ y: 280 }}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可展示的来源视频文件" /> }}
                  />
                ),
              },
              {
                key: 'target',
                label: `资源目录文件 (${diagnosis?.target_entries.length || 0})`,
                children: (
                  <Table
                    rowKey={(record) => `${record.path || record.name}-${record.entry_id || record.parent_path || 'root'}`}
                    size="small"
                    columns={sourceColumns}
                    dataSource={diagnosis?.target_entries || []}
                    pagination={false}
                    scroll={{ y: 280 }}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可展示的资源目录视频文件" /> }}
                  />
                ),
              },
            ]}
          />
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有可诊断的追更任务" />
      )}
    </Modal>
  )
}

export default FollowTaskFileDiagnosisDialog
