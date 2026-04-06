/**
 * 消息筛选组件（顶部工具条 + 高级筛选抽屉）
 */

import { useEffect, useMemo, useState } from 'react'
import {
  Input,
  Button,
  Space,
  Select,
  Drawer,
  Switch,
  InputNumber,
  Divider,
  Tag,
  Tooltip,
} from 'antd'
import {
  SearchOutlined,
  FilterOutlined,
  ReloadOutlined,
  ClearOutlined,
} from '@ant-design/icons'
import { useMessageStore } from '@/store/messageStore'
import { trackEvent } from '@/utils/analytics'
import { TIME_RANGES, PAGE_SIZES, NETDISK_TYPES } from '@/utils/constants'
import { getTagStats } from '@/api/messages'
import { MessageFilters as MessageFiltersState, TagStatsResponse } from '@/types/message'
import './MessageFilters.css'

const { Search } = Input
const { Option } = Select

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
  const {
    filters,
    setFilters,
    resetFilters,
    refreshInterval,
    setRefreshInterval,
    triggerReload,
  } = useMessageStore()
  const [tagOptions, setTagOptions] = useState<TagStatsResponse[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [searchValue, setSearchValue] = useState(filters.search_query || '')
  const [draft, setDraft] = useState(filters)
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

  const buildFilterEventData = (nextFilters: MessageFiltersState) => ({
    audience,
    time_range: nextFilters.time_range || '',
    page_size: nextFilters.page_size || 0,
    tags_count: nextFilters.selected_tags?.length || 0,
    netdisk_count: nextFilters.selected_netdisks?.length || 0,
    has_links_only: nextFilters.has_links_only ? 'true' : 'false',
    min_content_length: nextFilters.min_content_length || 0,
  })

  // 加载标签选项
  useEffect(() => {
    getTagStats(50)
      .then(setTagOptions)
      .catch((error) => console.error('获取标签失败:', error))
  }, [])

  // 同步 store 改变到抽屉草稿
  useEffect(() => {
    setDraft(filters)
  }, [filters])

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
    if ((filters.search_query || '') === searchValue) {
      return
    }

    const timer = window.setTimeout(() => {
      setFilters({ search_query: searchValue })
      const normalizedQuery = searchValue.trim()
      if (normalizedQuery) {
        trackEvent('search_submit', {
          audience,
          query: normalizedQuery,
          query_length: normalizedQuery.length,
        })
      }
    }, 350)

    return () => window.clearTimeout(timer)
  }, [audience, filters.search_query, searchValue, setFilters])

  const handleSearch = (value: string) => {
    setSearchValue(value)
    if ((filters.search_query || '') !== value) {
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

  const pageSizeOptions = useMemo(
    () =>
      PAGE_SIZES.map((size) => (
        <Option key={size} value={size}>
          {size} 条/页
        </Option>
      )),
    []
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

  const applyAdvanced = () => {
    setFilters(draft)
    trackEvent('filters_apply', buildFilterEventData(draft))
    setDrawerOpen(false)
  }

  const resetAdvanced = () => {
    resetFilters()
    trackEvent('filters_reset', { audience, source: 'drawer' })
    setDrawerOpen(false)
  }

  const handleToolbarReset = () => {
    resetFilters()
    trackEvent('filters_reset', { audience, source: 'toolbar' })
  }

  const handleReload = () => {
    triggerReload()
    trackEvent('feed_refresh', { audience })
  }

  const handleTimeRangeChange = (value: string) => {
    setFilters({ time_range: value })
    trackEvent('filter_change', { audience, control: 'time_range', value })
  }

  const handlePageSizeChange = (value: number) => {
    setFilters({ page_size: value })
    trackEvent('filter_change', { audience, control: 'page_size', value })
  }

  return (
    <div className={toolbarClassName}>
      <div className="filters-left">
        <Search
          className="filters-search"
          placeholder="搜索消息（关键词用空格分隔）"
          allowClear
          enterButton={<SearchOutlined />}
          value={searchValue}
          onSearch={handleSearch}
          onChange={(e) => setSearchValue(e.target.value)}
          disabled={disabled}
        />
      </div>
      <div className="filters-right">
        <Space size={10} className="filters-actions" wrap={false}>
          <Select
            className="toolbar-select toolbar-select--time"
            value={filters.time_range}
            onChange={handleTimeRangeChange}
            style={{ width: 160 }}
            disabled={disabled}
          >
            {timeRangeOptions}
          </Select>
          <Select
            className="toolbar-select toolbar-select--page"
            value={filters.page_size}
            onChange={handlePageSizeChange}
            style={{ width: 120 }}
            disabled={disabled}
          >
            {pageSizeOptions}
          </Select>
          <Tooltip title="高级筛选">
            <Button
              className="toolbar-button toolbar-button--advanced"
              icon={<FilterOutlined />}
              onClick={() => setDrawerOpen(true)}
              disabled={disabled}
            >
              高级筛选
            </Button>
          </Tooltip>
          <Tooltip title="重置筛选">
            <Button
              className="toolbar-button"
              icon={<ClearOutlined />}
              onClick={handleToolbarReset}
              disabled={disabled}
            />
          </Tooltip>
          <Tooltip title="刷新数据">
            <Button className="toolbar-button" icon={<ReloadOutlined />} onClick={handleReload} disabled={disabled} />
          </Tooltip>
          <div className="refresh-inline">
            <span className="refresh-label">自动刷新</span>
            <InputNumber
              min={30}
              max={300}
              step={30}
              value={refreshInterval}
              onChange={(v) => setRefreshInterval(v || 30)}
              controls
              size="small"
              style={{ width: 110 }}
              disabled={disabled}
            />
            <span className="refresh-unit">秒</span>
          </div>
        </Space>
      </div>

      <Drawer
        title="高级筛选"
        placement="right"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={360}
        maskClosable={!disabled}
        rootClassName="responsive-drawer-root"
      >
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div className="drawer-block">
            <div className="drawer-block-title">时间范围</div>
            <Select
              value={draft.time_range}
              onChange={(value) => setDraft({ ...draft, time_range: value })}
              style={{ width: '100%' }}
              disabled={disabled}
            >
              {timeRangeOptions}
            </Select>
          </div>

          <div className="drawer-block">
            <div className="drawer-block-title">标签</div>
            <Select
              mode="multiple"
              showSearch
              value={draft.selected_tags}
              onChange={(value) => setDraft({ ...draft, selected_tags: value })}
              style={{ width: '100%' }}
              maxTagCount="responsive"
              placeholder="选择标签"
              disabled={disabled}
            >
              {tagSelectOptions}
            </Select>
            <div className="drawer-tags-preview">
              {draft.selected_tags?.slice(0, 4)?.map((t) => (
                <Tag key={t} color="blue">
                  #{t}
                </Tag>
              ))}
            </div>
          </div>

          <div className="drawer-block">
            <div className="drawer-block-title">网盘类型</div>
            <Select
              mode="multiple"
              value={draft.selected_netdisks}
              onChange={(value) => setDraft({ ...draft, selected_netdisks: value })}
              style={{ width: '100%' }}
              placeholder="选择网盘类型"
              disabled={disabled}
            >
              {netdiskOptions}
            </Select>
          </div>

          <div className="drawer-block">
            <div className="drawer-block-title">只看有链接</div>
            <Switch
              checked={draft.has_links_only}
              onChange={(checked) => setDraft({ ...draft, has_links_only: checked })}
              disabled={disabled}
            />
          </div>

          <div className="drawer-block">
            <div className="drawer-block-title">最小内容长度</div>
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              value={draft.min_content_length}
              onChange={(value) => setDraft({ ...draft, min_content_length: value || 0 })}
              placeholder="例如 20，表示标题+描述长度至少 20"
              disabled={disabled}
            />
          </div>

          <div className="drawer-block">
            <div className="drawer-block-title">每页显示</div>
            <Select
              value={draft.page_size}
              onChange={(value) => setDraft({ ...draft, page_size: value })}
              style={{ width: '100%' }}
              disabled={disabled}
            >
              {pageSizeOptions}
            </Select>
          </div>

          <Divider style={{ margin: '8px 0' }} />
          <Space>
            <Button onClick={resetAdvanced} disabled={disabled}>重置</Button>
            <Button type="primary" onClick={applyAdvanced} disabled={disabled}>
              应用筛选
            </Button>
          </Space>
        </Space>
      </Drawer>
    </div>
  )
}

export default MessageFilters

