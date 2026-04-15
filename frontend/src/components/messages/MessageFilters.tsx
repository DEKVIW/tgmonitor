import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Input, InputNumber, Modal, Segmented, Select, Space, Tag, Tooltip } from 'antd'
import { ClearOutlined, CloseCircleFilled, FilterOutlined, SearchOutlined } from '@ant-design/icons'
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
  disabled?: boolean
  layoutVariant?: 'default' | 'guest-header' | 'header-strip'
  allowedTimeRanges?: readonly string[]
  fallbackTimeRange?: string
}

const MessageFilters = ({
  disabled = false,
  layoutVariant = 'default',
  allowedTimeRanges,
  fallbackTimeRange,
}: MessageFiltersProps) => {
  const { user } = useAuthStore()
  const securityConfig = usePublicSecurityConfig()
  const { filters, setFilters, resetFilters, refreshInterval, setRefreshInterval } = useMessageStore()
  const [tagOptions, setTagOptions] = useState<TagStatsResponse[]>([])
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [challengeOpen, setChallengeOpen] = useState(false)
  const [challengeError, setChallengeError] = useState('')
  const [challengeBusy, setChallengeBusy] = useState(false)
  const [challengeResetKey, setChallengeResetKey] = useState(0)
  const [pendingSearchValue, setPendingSearchValue] = useState<string | null>(null)
  const [searchValue, setSearchValue] = useState(filters.search_query || '')
  const [draft, setDraft] = useState<MessageFiltersState>(() => sanitizeHiddenFilters(filters))
  const [draftRefreshInterval, setDraftRefreshInterval] = useState(refreshInterval)
  const [searchChallengeVersion, setSearchChallengeVersion] = useState(0)

  const allowedTimeRangeSet = useMemo(
    () => (allowedTimeRanges ? new Set(allowedTimeRanges) : null),
    [allowedTimeRanges]
  )

  const toolbarClassName = useMemo(
    () =>
      [
        'filters-toolbar',
        layoutVariant === 'guest-header' ? 'filters-toolbar--guest' : '',
        layoutVariant === 'header-strip' ? 'filters-toolbar--header-strip' : '',
      ]
        .filter(Boolean)
        .join(' '),
    [layoutVariant]
  )

  const audience = layoutVariant === 'guest-header' ? 'guest' : 'authenticated'
  const searchChallengeRequired = isSearchChallengeRequiredForAudience(securityConfig, user)
  const searchChallengeClearance = useMemo(
    () => readSearchChallengeClearance(user),
    [searchChallengeVersion, user?.username]
  )
  const hasSearchChallengeClearance = Boolean(searchChallengeClearance)
  const hasAdvancedSelections =
    Boolean(filters.selected_tags?.length) ||
    Boolean(filters.selected_netdisks?.length) ||
    normalizeRefreshInterval(refreshInterval) !== DEFAULT_REFRESH_INTERVAL

  const buildFilterEventData = (
    nextFilters: MessageFiltersState,
    nextRefreshInterval: number = refreshInterval
  ) => ({
    audience,
    sort_mode: nextFilters.sort_mode || 'newest',
    time_range: nextFilters.time_range || '',
    tags_count: nextFilters.selected_tags?.length || 0,
    netdisk_count: nextFilters.selected_netdisks?.length || 0,
    refresh_interval: normalizeRefreshInterval(nextRefreshInterval),
  })

  const applySearch = (value: string) => {
    setFilters({ search_query: value })
    const normalizedQuery = value.trim()
    if (normalizedQuery) {
      trackEvent('search_submit', {
        audience,
        query: normalizedQuery,
        query_length: normalizedQuery.length,
      })
    }
  }

  const ensureSearchChallenge = (value: string) => {
    const normalizedQuery = value.trim()
    if (!normalizedQuery) {
      return false
    }
    if (!searchChallengeRequired) {
      return false
    }
    if (hasSearchChallengeClearance) {
      return false
    }

    setPendingSearchValue(value)
    setChallengeError('')
    setChallengeOpen(true)
    return true
  }

  useEffect(() => {
    getTagStats(50)
      .then(setTagOptions)
      .catch((error) => console.error('获取标签失败:', error))
  }, [])

  useEffect(() => {
    setDraft(sanitizeHiddenFilters(filters))
  }, [filters])

  useEffect(() => {
    setDraftRefreshInterval(refreshInterval)
  }, [refreshInterval])

  useEffect(() => {
    setSearchValue(filters.search_query || '')
  }, [filters.search_query])

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

  useEffect(() => {
    if ((filters.search_query || '') === searchValue) {
      return
    }

    const timer = window.setTimeout(() => {
      if (searchValue.trim() && searchChallengeRequired && !hasSearchChallengeClearance) {
        return
      }

      applySearch(searchValue)
    }, 350)

    return () => window.clearTimeout(timer)
  }, [filters.search_query, hasSearchChallengeClearance, searchChallengeRequired, searchValue, setFilters])

  const handleSearch = (value: string) => {
    setSearchValue(value)
    if ((filters.search_query || '') === value) {
      return
    }

    if (ensureSearchChallenge(value)) {
      return
    }

    applySearch(value)
  }

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

  const tagSelectOptions = useMemo(
    () =>
      tagOptions.map((tag) => (
        <Option key={tag.tag} value={tag.tag} label={`${tag.tag} (${tag.count})`}>
          {tag.tag} ({tag.count})
        </Option>
      )),
    [tagOptions]
  )

  const handleAdvancedOpen = () => {
    setDraft(sanitizeHiddenFilters(filters))
    setDraftRefreshInterval(refreshInterval)
    setAdvancedOpen(true)
  }

  const handleAdvancedClose = () => {
    setDraft(sanitizeHiddenFilters(filters))
    setDraftRefreshInterval(refreshInterval)
    setAdvancedOpen(false)
  }

  const handleClearSearch = () => {
    if (!searchValue && !filters.search_query) {
      return
    }

    setSearchValue('')
    setPendingSearchValue(null)
    setChallengeOpen(false)
    setChallengeError('')
    applySearch('')
    trackEvent('search_clear', { audience })
  }

  const handleSortModeChange = (value: MessageSortMode) => {
    if ((filters.sort_mode || 'newest') === value) {
      return
    }

    setFilters({ sort_mode: value })
    trackEvent('search_sort_change', {
      audience,
      sort_mode: value,
      has_query: Boolean((filters.search_query || '').trim()),
    })
  }

  const applyAdvanced = () => {
    const nextFilters = sanitizeHiddenFilters(draft)
    const nextRefreshInterval = normalizeRefreshInterval(draftRefreshInterval)

    setFilters(nextFilters)
    setRefreshInterval(nextRefreshInterval)
    trackEvent('filters_apply', buildFilterEventData(nextFilters, nextRefreshInterval))
    setAdvancedOpen(false)
  }

  const handleToolbarReset = () => {
    resetFilters()
    trackEvent('filters_reset', { audience, source: 'toolbar' })
  }

  const handleSearchChallengeClose = () => {
    setChallengeOpen(false)
    setChallengeError('')
    setPendingSearchValue(null)
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
      const nextSearchValue = pendingSearchValue ?? searchValue
      if (nextSearchValue.trim()) {
        applySearch(nextSearchValue)
      }
      setPendingSearchValue(null)
    } catch (error: any) {
      clearSearchChallengeClearance(user)
      setSearchChallengeVersion((current) => current + 1)
      setChallengeResetKey((current) => current + 1)
      setChallengeError(error.response?.data?.detail || '人机验证失败，请稍后重试')
    } finally {
      setChallengeBusy(false)
    }
  }

  return (
    <div className={toolbarClassName}>
      <div className="filters-search-shell">
        <SearchOutlined className="filters-search-shell__lead" />
        <Input
          className="filters-search-input"
          bordered={false}
          placeholder="搜索"
          value={searchValue}
          onPressEnter={() => handleSearch(searchValue)}
          onChange={(event) => setSearchValue(event.target.value)}
          disabled={disabled}
        />
        {searchValue || filters.search_query ? (
          <Tooltip title="清空搜索">
            <Button
              type="text"
              className="toolbar-icon-button filters-search-clear-button"
              icon={<CloseCircleFilled />}
              onClick={handleClearSearch}
              disabled={disabled}
            />
          </Tooltip>
        ) : null}
        <Segmented
          className="filters-sort-toggle"
          options={SORT_MODE_OPTIONS}
          value={filters.sort_mode || 'newest'}
          onChange={(value) => handleSortModeChange(value as MessageSortMode)}
          disabled={disabled}
          size="small"
        />
        <div className="filters-search-actions">
          <Tooltip title="高级筛选">
            <Button
              type="text"
              className={`toolbar-icon-button ${hasAdvancedSelections ? 'toolbar-icon-button--active' : ''}`}
              icon={<FilterOutlined />}
              onClick={handleAdvancedOpen}
              disabled={disabled}
            />
          </Tooltip>
          <Tooltip title="重置筛选">
            <Button
              type="text"
              className="toolbar-icon-button"
              icon={<ClearOutlined />}
              onClick={handleToolbarReset}
              disabled={disabled}
            />
          </Tooltip>
        </div>
      </div>

      <Modal
        title="搜索验证"
        open={challengeOpen}
        onCancel={handleSearchChallengeClose}
        footer={null}
        destroyOnClose
        width={420}
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

      <Modal
        title="高级筛选"
        open={advancedOpen}
        onCancel={handleAdvancedClose}
        onOk={applyAdvanced}
        okText="应用筛选"
        cancelText="取消"
        width={560}
        maskClosable={!disabled}
        className="filters-advanced-modal"
      >
        <div className="filters-advanced-grid">
          <div className="filters-modal-field filters-modal-field--full">
            <div className="filters-modal-label">时间范围</div>
            <Select
              value={draft.time_range}
              onChange={(value) => setDraft({ ...draft, time_range: value })}
              style={{ width: '100%' }}
              disabled={disabled}
            >
              {timeRangeOptions}
            </Select>
          </div>

          <div className="filters-modal-field filters-modal-field--full">
            <div className="filters-modal-label">标签</div>
            <Select
              mode="multiple"
              showSearch
              value={draft.selected_tags || []}
              onChange={(value) => setDraft({ ...draft, selected_tags: value })}
              style={{ width: '100%' }}
              maxTagCount="responsive"
              placeholder="选择标签"
              disabled={disabled}
            >
              {tagSelectOptions}
            </Select>
            <div className="filters-modal-tags-preview">
              {(draft.selected_tags || []).slice(0, 6).map((tag) => (
                <Tag key={tag} color="blue">
                  #{tag}
                </Tag>
              ))}
            </div>
          </div>

          <div className="filters-modal-field filters-modal-field--full">
            <div className="filters-modal-label">网盘类型</div>
            <Select
              mode="multiple"
              value={draft.selected_netdisks || []}
              onChange={(value) => setDraft({ ...draft, selected_netdisks: value })}
              style={{ width: '100%' }}
              placeholder="选择网盘类型"
              disabled={disabled}
            >
              {netdiskOptions}
            </Select>
          </div>

          <div className="filters-modal-field filters-modal-field--full">
            <div className="filters-modal-label">自动刷新间隔</div>
            <InputNumber
              min={30}
              max={300}
              step={30}
              value={draftRefreshInterval}
              onChange={(value) => setDraftRefreshInterval(normalizeRefreshInterval(value))}
              controls
              style={{ width: '100%' }}
              disabled={disabled}
            />
            <div className="filters-modal-help">单位：秒，默认 60 秒自动刷新一次。</div>
          </div>
        </div>
      </Modal>
    </div>
  )
}

export default MessageFilters
