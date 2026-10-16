import { ReactNode, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Input, InputNumber, Modal, Segmented, Select, Space, Tag } from 'antd'
import { ClearOutlined, SearchOutlined } from '@ant-design/icons'
import { useMessageStore } from '@/store/messageStore'
import { useAuthStore } from '@/store/authStore'
import TurnstileWidget from '@/components/security/TurnstileWidget'
import { verifySearchTurnstile } from '@/api/security'
import { trackEvent } from '@/utils/analytics'
import { NETDISK_TYPES, TIME_RANGES } from '@/utils/constants'
import { getTagStats } from '@/api/messages'
import { MessageFilters as MessageFiltersState, MessageSortMode, TagStatsResponse } from '@/types/message'
import {
  clearSearchChallengeClearance,
  isSearchChallengeRequiredForAudience,
  readSearchChallengeClearance,
  usePublicSecurityConfig,
  writeSearchChallengeClearance,
} from '@/utils/securityConfig'
import './MessageFilters.css'

const { Option } = Select

const DEFAULT_REFRESH_INTERVAL = 60
const SORT_MODE_OPTIONS: { label: string; value: MessageSortMode }[] = [
  { label: '综合排序', value: 'relevance' },
  { label: '最新优先', value: 'newest' },
]

const sanitizeHiddenFilters = (value: MessageFiltersState): MessageFiltersState => ({
  ...value,
  has_links_only: false,
  min_content_length: 0,
})

const normalizeRefreshInterval = (value: number | null | undefined) => {
  const numericValue = Number(value || DEFAULT_REFRESH_INTERVAL)
  if (!Number.isFinite(numericValue)) {
    return DEFAULT_REFRESH_INTERVAL
  }
  return Math.min(300, Math.max(30, numericValue))
}

interface MessageFiltersProps {
  trigger: ReactNode
  disabled?: boolean
  layoutVariant?: 'guest-header' | 'default'
  allowedTimeRanges?: readonly string[]
  fallbackTimeRange?: string
}

interface PendingQuery {
  filters: MessageFiltersState
  refreshInterval: number
}

const MessageFilters = ({
  trigger,
  disabled = false,
  layoutVariant = 'default',
  allowedTimeRanges,
  fallbackTimeRange,
}: MessageFiltersProps) => {
  const { user } = useAuthStore()
  const securityConfig = usePublicSecurityConfig()
  const { filters, setFilters, resetFilters, refreshInterval, setRefreshInterval } = useMessageStore()
  const [tagOptions, setTagOptions] = useState<TagStatsResponse[]>([])
  const [queryOpen, setQueryOpen] = useState(false)
  const [challengeOpen, setChallengeOpen] = useState(false)
  const [challengeError, setChallengeError] = useState('')
  const [challengeBusy, setChallengeBusy] = useState(false)
  const [challengeResetKey, setChallengeResetKey] = useState(0)
  const [pendingQuery, setPendingQuery] = useState<PendingQuery | null>(null)
  const [searchValue, setSearchValue] = useState(filters.search_query || '')
  const [draft, setDraft] = useState<MessageFiltersState>(() => sanitizeHiddenFilters(filters))
  const [draftRefreshInterval, setDraftRefreshInterval] = useState(refreshInterval)
  const [searchChallengeVersion, setSearchChallengeVersion] = useState(0)

  const allowedTimeRangeSet = useMemo(
    () => (allowedTimeRanges ? new Set(allowedTimeRanges) : null),
    [allowedTimeRanges]
  )
  const audience = layoutVariant === 'guest-header' ? 'guest' : 'authenticated'
  const searchChallengeRequired = isSearchChallengeRequiredForAudience(securityConfig, user)
  const searchChallengeClearance = useMemo(
    () => readSearchChallengeClearance(user),
    [searchChallengeVersion, user?.username]
  )
  const hasSearchChallengeClearance = Boolean(searchChallengeClearance)
  const defaultTimeRangeValue = fallbackTimeRange || '最近24小时'

  const syncDraftFromStore = () => {
    setSearchValue(filters.search_query || '')
    setDraft(sanitizeHiddenFilters(filters))
    setDraftRefreshInterval(refreshInterval)
  }

  const buildFilterEventData = (
    nextFilters: MessageFiltersState,
    nextRefreshInterval: number
  ) => ({
    audience,
    sort_mode: nextFilters.sort_mode || 'newest',
    time_range: nextFilters.time_range || '',
    tags_count: nextFilters.selected_tags?.length || 0,
    netdisk_count: nextFilters.selected_netdisks?.length || 0,
    refresh_interval: normalizeRefreshInterval(nextRefreshInterval),
  })

  const commitQuery = (pending: PendingQuery) => {
    setFilters(pending.filters)
    setRefreshInterval(pending.refreshInterval)

    const normalizedQuery = pending.filters.search_query?.trim() || ''
    if (normalizedQuery) {
      trackEvent('search_submit', {
        audience,
        query: normalizedQuery,
        query_length: normalizedQuery.length,
      })
    }
    trackEvent('filters_apply', buildFilterEventData(pending.filters, pending.refreshInterval))
    setQueryOpen(false)
    setPendingQuery(null)
  }

  const openQuery = () => {
    syncDraftFromStore()
    setQueryOpen(true)
  }

  const closeQuery = () => {
    syncDraftFromStore()
    setQueryOpen(false)
  }

  const handleApply = () => {
    const nextQuery: PendingQuery = {
      filters: {
        ...sanitizeHiddenFilters(draft),
        search_query: searchValue.trim(),
      },
      refreshInterval: normalizeRefreshInterval(draftRefreshInterval),
    }

    if (nextQuery.filters.search_query && searchChallengeRequired && !hasSearchChallengeClearance) {
      setPendingQuery(nextQuery)
      setChallengeError('')
      setChallengeOpen(true)
      return
    }

    commitQuery(nextQuery)
  }

  const handleReset = () => {
    resetFilters()
    setFilters({ time_range: defaultTimeRangeValue })
    setRefreshInterval(DEFAULT_REFRESH_INTERVAL)
    setSearchValue('')
    setDraft({
      ...sanitizeHiddenFilters(filters),
      search_query: '',
      sort_mode: 'newest',
      time_range: defaultTimeRangeValue,
      selected_tags: [],
      selected_netdisks: [],
      page: 1,
    })
    setDraftRefreshInterval(DEFAULT_REFRESH_INTERVAL)
    trackEvent('filters_reset', { audience, source: 'query-modal' })
  }

  const handleSearchChallengeVerify = async (token: string) => {
    setChallengeBusy(true)
    setChallengeError('')

    try {
      const response = await verifySearchTurnstile({
        action: 'search',
        turnstile_token: token,
      })
      writeSearchChallengeClearance(user, response)
      setSearchChallengeVersion((current) => current + 1)
      setChallengeOpen(false)
      if (pendingQuery) {
        commitQuery(pendingQuery)
      }
    } catch (error: any) {
      clearSearchChallengeClearance(user)
      setSearchChallengeVersion((current) => current + 1)
      setChallengeResetKey((current) => current + 1)
      setChallengeError(error.response?.data?.detail || '人机验证失败，请稍后重试')
    } finally {
      setChallengeBusy(false)
    }
  }

  useEffect(() => {
    if (!queryOpen) {
      return
    }

    getTagStats(50)
      .then(setTagOptions)
      .catch((error) => console.error('获取标签失败:', error))
  }, [queryOpen])

  useEffect(() => {
    if (!allowedTimeRangeSet || !fallbackTimeRange) {
      return
    }

    if (filters.time_range && !allowedTimeRangeSet.has(filters.time_range)) {
      setFilters({ time_range: fallbackTimeRange })
    }
  }, [allowedTimeRangeSet, fallbackTimeRange, filters.time_range, setFilters])

  useEffect(() => {
    if (!filters.has_links_only && !(filters.min_content_length || 0)) {
      return
    }
    setFilters({ has_links_only: false, min_content_length: 0 })
  }, [filters.has_links_only, filters.min_content_length, setFilters])

  const timeRangeOptions = useMemo(
    () =>
      TIME_RANGES.map((range) => (
        <Option
          key={range.value}
          value={range.value}
          disabled={allowedTimeRangeSet ? !allowedTimeRangeSet.has(String(range.value)) : false}
        >
          {range.label}
        </Option>
      )),
    [allowedTimeRangeSet]
  )

  const netdiskOptions = useMemo(
    () =>
      NETDISK_TYPES.map((type) => (
        <Option key={type} value={type}>
          {type}
        </Option>
      )),
    []
  )

  return (
    <>
      <span onClick={disabled ? undefined : openQuery}>{trigger}</span>
      <Modal
        open={queryOpen}
        title={
          <div className="message-query-modal-title">
            <SearchOutlined />
            <span>搜索消息</span>
          </div>
        }
        onCancel={closeQuery}
        footer={
          <div className="message-query-modal-footer">
            <Button icon={<ClearOutlined />} onClick={handleReset} disabled={disabled}>
              重置条件
            </Button>
            <Space>
              <Button onClick={closeQuery} disabled={disabled}>取消</Button>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleApply} disabled={disabled}>
                应用搜索
              </Button>
            </Space>
          </div>
        }
        destroyOnClose
        width={760}
        maskClosable={!disabled}
        className="message-query-modal"
        rootClassName="message-query-modal-root"
      >
        <div className="message-query-grid">
          <div className="message-query-field message-query-field--search">
            <label htmlFor="message-query-search">关键词</label>
            <Input
              id="message-query-search"
              allowClear
              prefix={<SearchOutlined />}
              value={searchValue}
              placeholder="搜索消息、频道或网盘关键词"
              onChange={(event) => setSearchValue(event.target.value)}
              onPressEnter={handleApply}
              disabled={disabled}
            />
          </div>

          <div className="message-query-quick-row">
            <div className="message-query-field">
              <label>排序方式</label>
              <Segmented
                block
                options={SORT_MODE_OPTIONS}
                value={draft.sort_mode || 'newest'}
                onChange={(value) => setDraft({ ...draft, sort_mode: value as MessageSortMode })}
                disabled={disabled}
              />
            </div>

            <div className="message-query-field">
              <label>时间范围</label>
              <Select
                value={draft.time_range || defaultTimeRangeValue}
                onChange={(value) => setDraft({ ...draft, time_range: value })}
                disabled={disabled}
              >
                {timeRangeOptions}
              </Select>
            </div>
          </div>

          <div className="message-query-filter-grid">
            <div className="message-query-field">
              <label>标签</label>
              <Select
                mode="multiple"
                showSearch={false}
                allowClear
                value={draft.selected_tags || []}
                onChange={(value) => setDraft({ ...draft, selected_tags: value })}
                maxTagCount="responsive"
                placeholder="全部标签"
                disabled={disabled}
                options={tagOptions.map((tag) => ({ label: `${tag.tag} (${tag.count})`, value: tag.tag }))}
              />
            </div>

            <div className="message-query-field">
              <label>网盘类型</label>
              <Select
                mode="multiple"
                showSearch={false}
                allowClear
                value={draft.selected_netdisks || []}
                onChange={(value) => setDraft({ ...draft, selected_netdisks: value })}
                maxTagCount="responsive"
                placeholder="全部网盘"
                disabled={disabled}
              >
                {netdiskOptions}
              </Select>
            </div>

            <div className="message-query-field">
              <label>自动刷新间隔</label>
              <InputNumber
                min={30}
                max={300}
                step={30}
                value={draftRefreshInterval}
                onChange={(value) => setDraftRefreshInterval(normalizeRefreshInterval(value))}
                controls
                addonAfter="秒"
                disabled={disabled}
              />
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        title="搜索验证"
        open={challengeOpen}
        onCancel={() => {
          setChallengeOpen(false)
          setChallengeError('')
          setPendingQuery(null)
        }}
        footer={null}
        destroyOnClose
        width={420}
        className="message-query-challenge-modal"
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="搜索前需要先完成人机验证"
            description="验证通过后，当前身份会在一段时间内保持搜索权限。"
          />
          {challengeError ? <Alert type="error" showIcon message={challengeError} /> : null}
          <TurnstileWidget
            key={challengeResetKey}
            siteKey={securityConfig.turnstile_site_key}
            action="search"
            onVerify={handleSearchChallengeVerify}
            onExpire={() => undefined}
            onError={(messageText) => setChallengeError(messageText)}
          />
          {challengeBusy ? <Tag color="processing">正在校验中</Tag> : null}
        </Space>
      </Modal>
    </>
  )
}

export default MessageFilters
