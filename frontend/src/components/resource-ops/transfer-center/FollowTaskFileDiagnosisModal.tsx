export { default } from './FollowTaskFileDiagnosisModalV2'

/*
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
  contiguous_window_hit: '已命中连续更新，可直接生成增量同步计划',
  gap_before_next_episode: '候选里存在断档，系统先停在第一处缺口，避免误自动补集',
  no_source_video: '源链接暂时没有扫到可识别的视频文件',
  no_accepted_episode: '源文件有视频，但暂时没有匹配到可信的剧集结果',
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

const FollowTaskFileDiagnosisModal = ({
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
  }, [open, task, hasCandidate])

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
      message.error(getErrorMessage(error, '生成智能诊断失败'))
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
          <Tag color={record.parse_level === 'full' ? 'processing' : 'default'}>{record.parse_level === 'full' ? '完整解析' : '快速解析'}</Tag>
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
      title: '目标位置',
      dataIndex: 'target_relative_path',
      key: 'target_relative_path',
      width: 170,
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
      return `已推荐补齐 ${summary.recommended_episode_numbers.join(', ')}`
    }
    return STOP_REASON_LABELS[summary.stop_reason] || '本次没有形成可直接执行的增量计划'
  }, [summary])

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={1180}
      destroyOnHidden
      title="智能诊断与推荐补集"
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
            创建推荐增量同步
          </Button>
        </Space>
      }
    >
      {task ? (
        <div className="resource-ops-follow-diagnosis-stack">
          <Paragraph className="resource-ops-transfer-copy">
            系统会同时扫描当前资源目录和所选来源链接，优先按最新文件与当前进度附近的剧集做完整解析，再输出可直接复用的增量同步计划。
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
              <InputNumber min={1} max={30} value={nearEpisodeWindow} onChange={(value) => setNearEpisodeWindow(Number(value || 5))} style={{ width: '100%' }} />
            </div>
            <div className="resource-ops-follow-diagnosis-target">
              <Text type="secondary">目标资源目录</Text>
              <strong>{task.fixed_save_path || '-'}</strong>
            </div>
          </div>

          {summary ? (
            <>
              <div className="resource-ops-follow-diagnosis-summary-grid">
                <Card size="small" className="resource-ops-follow-sync-card">
                  <div className="resource-ops-follow-sync-meta">
                    <span>{summary.tracked_core_title || summary.tracked_resource_title}</span>
                    <small>{summary.tracked_resource_title}</small>
                    <small>
                      {[
                        summary.tracked_season ? `季 ${summary.tracked_season}` : null,
                        summary.tracked_episode ? `当前进度 ${summary.tracked_episode}` : null,
                        summary.latest_target_episode ? `目录最新 ${summary.latest_target_episode}` : null,
                        summary.anchor_episode ? `锚点 ${summary.anchor_episode}` : null,
                      ]
                        .filter(Boolean)
                        .join(' · ') || '尚未识别到稳定进度'}
                    </small>
                  </div>
                </Card>

                <Card size="small" className="resource-ops-follow-sync-card">
                  <div className="resource-ops-follow-sync-meta">
                    <span>扫描效率</span>
                    <small>{`源 ${summary.source_dir_count} 目录 / ${summary.source_video_count} 视频 · 目标 ${summary.target_dir_count} 目录 / ${summary.target_video_count} 视频`}</small>
                    <small>{`快速解析 ${summary.quick_parsed_count} · 完整解析 ${summary.full_parsed_count} · 超窗跳过 ${summary.skipped_outside_window_count}`}</small>
                  </div>
                </Card>

                <Card size="small" className="resource-ops-follow-sync-card">
                  <div className="resource-ops-follow-sync-meta">
                    <span>推荐结果</span>
                    <small>{recommendationText}</small>
                    <small>{summary.inferred_target_relative_path ? `建议写入 ${summary.inferred_target_relative_path}` : '建议写入资源目录根层'}</small>
                  </div>
                </Card>
              </div>

              <Alert
                type={summary.recommended_entry_count > 0 ? 'success' : 'warning'}
                showIcon
                message={summary.recommended_entry_count > 0 ? '已生成可执行增量计划' : '本次没有生成可执行计划'}
                description={recommendationText}
              />
              {diagnosisConfigDirty ? (
                <Alert
                  type="info"
                  showIcon
                  message="诊断条件已变更"
                  description="你已调整诊断来源或近窗范围，请先重新诊断，再创建推荐增量同步。"
                />
              ) : null}
            </>
          ) : null}

          <Card size="small" title="推荐补集" className="resource-ops-follow-sync-card">
            {diagnosis?.recommended_plan_items?.length ? (
              <Table rowKey={(record) => `${record.path || record.name}-${record.episodes.join('-')}`} size="small" columns={planColumns} dataSource={diagnosis.recommended_plan_items} pagination={false} />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有形成可直接执行的推荐补集计划" />
            )}
          </Card>

          <Collapse
            className="resource-ops-follow-advanced-collapse"
            items={[
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

export default FollowTaskFileDiagnosisModal
*/
