import { CheckOutlined, CloseOutlined, DeleteOutlined, EditOutlined, ExportOutlined, MoreOutlined, ReloadOutlined } from '@ant-design/icons'
import { Dropdown } from 'antd'
import type { CSSProperties } from 'react'
import { formatServerDateTime } from '@/utils/dateTime'
import { cleanLearningSheetText } from '@/utils/learningResources'
import type { LearningResource } from '@/types/learningResources'

export interface LearningResourceEditDraft {
  display_title: string
  category: string
  tags: string
  share_url: string
}

interface LearningResourceSheetProps {
  resources: LearningResource[]
  total: number
  hasMore: boolean
  isAdmin: boolean
  loading: boolean
  editingId: number | null
  editDraft: LearningResourceEditDraft
  maintenanceBusyId: number | null
  onLoadMore: () => void
  onStartEditing: (resource: LearningResource) => void
  onCancelEditing: () => void
  onEditDraftChange: (field: keyof LearningResourceEditDraft, value: string) => void
  onSaveEditing: (resource: LearningResource) => void
  onDeleteRow: (resource: LearningResource, deleteRemoteResource: boolean) => void
  onRetry: (resource: LearningResource) => void
}

const cleanTags = (tags: string[]) => tags.map(cleanLearningSheetText).filter(Boolean)

const LEARNING_STATUS_META: Record<string, { label: string; tone: string }> = {
  pending: { label: '待处理', tone: 'pending' },
  transferring: { label: '转存中', tone: 'transferring' },
  published: { label: '已发布', tone: 'published' },
  failed: { label: '失败', tone: 'failed' },
  hidden: { label: '已隐藏', tone: 'hidden' },
}

const getLearningStatusMeta = (status?: string | null) => {
  const normalized = String(status || 'pending').trim().toLowerCase() || 'pending'
  return LEARNING_STATUS_META[normalized] || { label: status || '待处理', tone: 'default' }
}

const SheetInput = ({
  value,
  onChange,
  className = '',
}: {
  value: string
  onChange: (value: string) => void
  className?: string
}) => (
  <input
    className={`learning-sheet-input ${className}`.trim()}
    value={value}
    onChange={(event) => onChange(event.target.value)}
    onKeyDown={(event) => event.stopPropagation()}
  />
)

const LearningResourceSheet = ({
  resources,
  total,
  hasMore,
  isAdmin,
  loading,
  editingId,
  editDraft,
  maintenanceBusyId,
  onLoadMore,
  onStartEditing,
  onCancelEditing,
  onEditDraftChange,
  onSaveEditing,
  onDeleteRow,
  onRetry,
}: LearningResourceSheetProps) => {
  const columnTemplate = isAdmin
    ? '48px minmax(360px, 1fr) 150px 240px minmax(220px, 260px) 160px 112px 204px'
    : '48px minmax(360px, 1fr) 150px 240px minmax(220px, 260px) 160px'
  const gridStyle = { '--learning-sheet-columns': columnTemplate } as CSSProperties

  if (loading && resources.length === 0) {
    return <div className="learning-sheet-state">正在加载资料…</div>
  }

  if (resources.length === 0) {
    return <div className="learning-sheet-state">暂无已发布学习资料</div>
  }

  return (
    <div className="learning-sheet-grid-wrap">
      <div
        className="learning-sheet-grid-scroll"
        onScroll={(event) => {
          const target = event.currentTarget
          if (hasMore && !loading && target.scrollHeight - target.scrollTop - target.clientHeight < 480) {
            onLoadMore()
          }
        }}
      >
        <div className="learning-sheet-grid" style={gridStyle}>
        <div className="learning-sheet-row learning-sheet-header" role="row">
          <div className="learning-sheet-cell learning-sheet-row-number" role="columnheader">#</div>
          <div className="learning-sheet-cell" role="columnheader">资源标题</div>
          <div className="learning-sheet-cell" role="columnheader">分类</div>
          <div className="learning-sheet-cell" role="columnheader">标签</div>
          <div className="learning-sheet-cell" role="columnheader">网盘资源</div>
          <div className="learning-sheet-cell" role="columnheader">更新时间</div>
          {isAdmin ? <div className="learning-sheet-cell" role="columnheader">状态</div> : null}
          {isAdmin ? <div className="learning-sheet-cell" role="columnheader">操作</div> : null}
        </div>

        {resources.map((resource, index) => {
          const isEditing = editingId === resource.id
          const rowNumber = index + 1
          const title = cleanLearningSheetText(resource.display_title)
          const category = cleanLearningSheetText(resource.category?.name || '待分类')
          const tags = cleanTags(resource.tags)
          const statusMeta = getLearningStatusMeta(resource.status)
          const updatedAt = resource.latest_source_at
            ? formatServerDateTime(resource.latest_source_at, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai', true)
            : resource.updated_at
              ? formatServerDateTime(resource.updated_at, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai')
            : '-'

          return (
            <div className="learning-sheet-row" role="row" key={resource.id}>
              <div className="learning-sheet-cell learning-sheet-row-number" role="cell">{rowNumber}</div>
              <div className="learning-sheet-cell learning-sheet-title" role="cell" title={title}>
                {isEditing ? (
                  <SheetInput value={editDraft.display_title} onChange={(value) => onEditDraftChange('display_title', value)} />
                ) : (
                  <span className="learning-sheet-cell-text">{title || '未命名资源'}</span>
                )}
              </div>
              <div className="learning-sheet-cell" role="cell" title={category}>
                {isEditing ? (
                  <SheetInput value={editDraft.category} onChange={(value) => onEditDraftChange('category', value)} />
                ) : (
                  <span className="learning-sheet-cell-text">{category}</span>
                )}
              </div>
              <div className="learning-sheet-cell" role="cell" title={tags.join('、')}>
                {isEditing ? (
                  <SheetInput value={editDraft.tags} onChange={(value) => onEditDraftChange('tags', value)} />
                ) : (
                  <span className="learning-sheet-cell-text">{tags.join(' · ') || '-'}</span>
                )}
              </div>
              <div className="learning-sheet-cell" role="cell" title={resource.share_url || undefined}>
                {isEditing ? (
                  <SheetInput value={editDraft.share_url} onChange={(value) => onEditDraftChange('share_url', value)} />
                ) : resource.share_url ? (
                  <a className="learning-sheet-link" href={resource.share_url} target="_blank" rel="noreferrer">
                    <ExportOutlined />
                    <span className="learning-sheet-cell-text">打开分享</span>
                  </a>
                ) : (
                  <span className="learning-sheet-muted">暂无链接</span>
                )}
              </div>
              <div className="learning-sheet-cell" role="cell" title={updatedAt}>
                <span className="learning-sheet-cell-text">{updatedAt}</span>
              </div>
              {isAdmin ? (
                <div className="learning-sheet-cell" role="cell">
                  <span
                    className={`learning-sheet-status learning-sheet-status-${statusMeta.tone}`}
                    title={resource.status || 'pending'}
                  >
                    {statusMeta.label}
                  </span>
                </div>
              ) : null}
              {isAdmin ? (
                <div className="learning-sheet-cell learning-sheet-actions" role="cell">
                  {isEditing ? (
                    <div className="learning-sheet-actions-content">
                      <button
                        type="button"
                        className="learning-sheet-action-button learning-sheet-action-button-primary"
                        disabled={maintenanceBusyId === resource.id}
                        aria-label="保存资源"
                        onClick={() => void onSaveEditing(resource)}
                      >
                        <CheckOutlined />
                        保存
                      </button>
                      <button
                        type="button"
                        className="learning-sheet-action-button"
                        aria-label="取消编辑"
                        onClick={onCancelEditing}
                      >
                        <CloseOutlined />
                        取消
                      </button>
                    </div>
                  ) : (
                    <div className="learning-sheet-actions-content">
                      <button
                        type="button"
                        className="learning-sheet-action-button"
                        aria-label="编辑资源"
                        onClick={() => onStartEditing(resource)}
                      >
                        <EditOutlined />
                        编辑
                      </button>
                      {resource.status === 'failed' ? (
                        <button
                          type="button"
                          className="learning-sheet-action-button"
                          disabled={maintenanceBusyId === resource.id}
                          aria-label="重试转存"
                          onClick={() => void onRetry(resource)}
                        >
                          <ReloadOutlined />
                          重试
                        </button>
                      ) : null}
                      <Dropdown
                        trigger={['click']}
                        menu={{
                          items: [
                            {
                              key: 'record-only',
                              label: '仅删除系统记录',
                              icon: <DeleteOutlined />,
                            },
                            ...(resource.remote_cleanup_available
                              ? [{
                                key: 'record-and-remote',
                                label: '删除记录并清理网盘',
                                icon: <DeleteOutlined />,
                                danger: true,
                              }]
                              : []),
                          ],
                          onClick: ({ key }) => onDeleteRow(resource, key === 'record-and-remote'),
                        }}
                      >
                        <button
                          type="button"
                          className="learning-sheet-action-button learning-sheet-action-button-danger"
                          disabled={maintenanceBusyId === resource.id}
                          aria-label="更多删除操作"
                        >
                          <MoreOutlined />
                          更多
                        </button>
                      </Dropdown>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )
        })}
        </div>
      </div>

      <div className="learning-sheet-footer">
        <span>已显示 {resources.length} / {total} 条资料</span>
        <span>{loading ? '正在加载下一批…' : hasMore ? '下滑加载更多' : '已全部加载'}</span>
      </div>
    </div>
  )
}

export default LearningResourceSheet
