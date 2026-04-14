import type {
  PanTransferAccountItem,
  PanTransferBatchSummaryItem,
  PanTransferManualPreviewRequest,
} from '@/types/panTransfer'
import { formatServerDateTime } from '@/utils/dateTime'

export type PreviewDraft = {
  recentMessageCount: number
  searchKeyword: string
  platforms: string[]
  healthFilter: 'all' | 'healthy_only' | 'exclude_invalid'
}

export type BatchCreateDraft = {
  startImmediately: boolean
  maxAttempts: number
  retryDelaySeconds: number
  transferLayout: 'independent' | 'batch_archive'
  batchFolderName: string
  itemFolderPreset: 'masked_cn' | 'coded' | 'custom'
  itemFolderTemplate: string
  shareTargetMode: 'resource_dir' | 'content_root'
}

export type TargetAccountSelectionMap = Record<string, number | undefined>

export type BatchPagination = {
  page: number
  pageSize: number
  total: number
}

export type ApiError = {
  response?: {
    data?: {
      detail?: string
    }
  }
  errorFields?: unknown
}

export const PLATFORM_OPTIONS = [
  { label: '百度网盘', value: '百度网盘' },
  { label: '夸克网盘', value: '夸克网盘' },
]

export const SHARE_MODE_OPTIONS = [
  { label: '转存后继续分享', value: 'public' },
  { label: '仅转存不公开', value: 'private' },
]

export const DEFAULT_PREVIEW_DRAFT: PreviewDraft = {
  recentMessageCount: 200,
  searchKeyword: '',
  platforms: ['夸克网盘'],
  healthFilter: 'all',
}

export const MASKED_CN_ITEM_TEMPLATE = '{title_masked_cn}'
export const CODED_ITEM_TEMPLATE = 'tg-transfer-{batch_id}-{item_id}-{title_slug}'

export const DEFAULT_BATCH_CREATE_DRAFT: BatchCreateDraft = {
  startImmediately: true,
  maxAttempts: 3,
  retryDelaySeconds: 10 * 60,
  transferLayout: 'batch_archive',
  batchFolderName: '剧集',
  itemFolderPreset: 'masked_cn',
  itemFolderTemplate: MASKED_CN_ITEM_TEMPLATE,
  shareTargetMode: 'content_root',
}

export const TRANSFER_LAYOUT_OPTIONS = [
  { label: '独立目录', value: 'independent' },
  { label: '批次归档', value: 'batch_archive' },
]

export const BATCH_FOLDER_NAME_OPTIONS = [
  { label: '剧集', value: '剧集' },
  { label: '动漫', value: '动漫' },
  { label: '电影', value: '电影' },
  { label: '综艺', value: '综艺' },
]

export const ITEM_FOLDER_TEMPLATE_PRESET_OPTIONS = [
  {
    label: '中文混淆标题模板',
    value: 'masked_cn',
    template: MASKED_CN_ITEM_TEMPLATE,
    description: '把原标题按原有字数混淆成中文目录名，默认推荐。',
  },
  {
    label: '自动编码目录',
    value: 'coded',
    template: CODED_ITEM_TEMPLATE,
    description: '使用批次号、项目号和 slug 生成技术型目录名。',
  },
  {
    label: '自定义模板',
    value: 'custom',
    template: MASKED_CN_ITEM_TEMPLATE,
    description: '手动填写模板，支持 title / title_masked_cn / title_slug 等变量。',
  },
]

export const SHARE_TARGET_MODE_OPTIONS = [
  { label: '原分享目录', value: 'content_root' },
  { label: '资源目录', value: 'resource_dir' },
]

export const HEALTH_FILTER_OPTIONS = [
  { label: '全部', value: 'all' },
  { label: '仅正常', value: 'healthy_only' },
  { label: '排除失效', value: 'exclude_invalid' },
]

export const RETRY_DELAY_OPTIONS = [
  { label: '不自动重试', value: 0 },
  { label: '1 分钟', value: 60 },
  { label: '5 分钟', value: 5 * 60 },
  { label: '10 分钟', value: 10 * 60 },
  { label: '30 分钟', value: 30 * 60 },
  { label: '60 分钟', value: 60 * 60 },
]

export const BATCH_STATUS_META: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  running: { color: 'processing', label: '执行中' },
  cancelled: { color: 'default', label: '已停止' },
  completed: { color: 'success', label: '已完成' },
  completed_with_errors: { color: 'warning', label: '部分失败' },
  failed: { color: 'error', label: '全部失败' },
}

export const ITEM_STATUS_META: Record<string, { color: string; label: string }> = {
  queued: { color: 'default', label: '排队中' },
  processing: { color: 'processing', label: '执行中' },
  retry_wait: { color: 'warning', label: '等待重试' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
}

export const VALIDATION_STATUS_META: Record<string, { color: string; label: string }> = {
  pending: { color: 'default', label: '待校验' },
  valid: { color: 'success', label: '有效' },
  warning: { color: 'warning', label: '存疑' },
  invalid: { color: 'error', label: '失效' },
  error: { color: 'error', label: '异常' },
}

export const REPLACEMENT_STATUS_META: Record<string, { color: string; label: string }> = {
  pending: { color: 'default', label: '待回写' },
  replaced: { color: 'success', label: '已回写' },
  failed: { color: 'error', label: '回写失败' },
}

export const HEALTH_META: Record<string, { color: string; label: string }> = {
  healthy: { color: 'success', label: '正常' },
  invalid: { color: 'error', label: '失效' },
  unknown: { color: 'default', label: '未知' },
}

export const formatRetryDelay = (value?: number | null) => {
  const normalized = Math.max(0, Number(value || 0))
  if (normalized <= 0) return '不自动重试'
  if (normalized < 60) return `${normalized} 秒`
  if (normalized % 3600 === 0) return `${normalized / 3600} 小时`
  if (normalized % 60 === 0) return `${normalized / 60} 分钟`
  return `${normalized} 秒`
}

export const formatDateTime = (value?: string | null) =>
  value ? formatServerDateTime(value, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai') : '-'

export const getErrorMessage = (error: unknown, fallback: string) =>
  (error as ApiError)?.response?.data?.detail || fallback

export const buildPreviewPayload = (
  draft: PreviewDraft,
  pagination?: { page?: number; pageSize?: number }
): PanTransferManualPreviewRequest => ({
  selection_mode: 'recent_messages',
  direction: 'newest_first',
  recent_message_count: draft.recentMessageCount,
  search_keyword: draft.searchKeyword.trim() || undefined,
  platforms: draft.platforms,
  health_filter: draft.healthFilter,
  only_healthy: draft.healthFilter === 'healthy_only',
  page: pagination?.page || 1,
  page_size: pagination?.pageSize || 10,
})

export const resolveBatchCreateTemplate = (draft: BatchCreateDraft) => {
  if (draft.itemFolderPreset === 'masked_cn') return MASKED_CN_ITEM_TEMPLATE
  if (draft.itemFolderPreset === 'coded') return CODED_ITEM_TEMPLATE
  return draft.itemFolderTemplate.trim() || MASKED_CN_ITEM_TEMPLATE
}

export const buildTargetAccountOptionsByPlatform = (
  accounts: PanTransferAccountItem[]
): Record<string, { label: string; value: number }[]> =>
  accounts
    .filter((account) => account.is_enabled)
    .reduce<Record<string, { label: string; value: number }[]>>((accumulator, account) => {
      const platform = account.platform
      if (!accumulator[platform]) {
        accumulator[platform] = []
      }
      accumulator[platform].push({
        label: account.account_name,
        value: account.id,
      })
      return accumulator
    }, {})

export const buildDefaultTargetAccountSelections = (
  accounts: PanTransferAccountItem[]
): TargetAccountSelectionMap => {
  const next: TargetAccountSelectionMap = {}
  const grouped = accounts
    .filter((account) => account.is_enabled)
    .reduce<Record<string, PanTransferAccountItem[]>>((accumulator, account) => {
      if (!accumulator[account.platform]) {
        accumulator[account.platform] = []
      }
      accumulator[account.platform].push(account)
      return accumulator
    }, {})

  Object.entries(grouped).forEach(([platform, platformAccounts]) => {
    const preferred = platformAccounts.find((account) => account.is_default) || platformAccounts[0]
    next[platform] = preferred?.id
  })
  return next
}

export const getBatchSummary = (batch: PanTransferBatchSummaryItem) => {
  const summary = (batch.result_json?.summary as Record<string, unknown> | undefined) || {}
  return {
    queued: Number(summary.queued_count || 0),
    processing: Number(summary.processing_count || 0),
    retryWait: Number(summary.retry_wait_count || 0),
    completed: Number(summary.completed_count || 0),
    failed: Number(summary.failed_count || 0),
  }
}
