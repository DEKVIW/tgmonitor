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
import { TIME_RANGES, PAGE_SIZES, NETDISK_TYPES } from '@/utils/constants'
import { getTagStats } from '@/api/messages'
import { TagStatsResponse } from '@/types/message'
import './MessageFilters.css'

const { Search } = Input
const { Option } = Select

interface MessageFiltersProps {
  disabled?: boolean
}

const MessageFilters = ({ disabled = false }: MessageFiltersProps) => {
  const { filters, setFilters, resetFilters, refreshInterval, setRefreshInterval } = useMessageStore()
  const [tagOptions, setTagOptions] = useState<TagStatsResponse[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)

  const [draft, setDraft] = useState(filters)

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

  const handleSearch = (value: string) => {
    setFilters({ search_query: value })
  }

  const timeRangeOptions = useMemo(
    () =>
      TIME_RANGES.map((range) => (
        <Option key={range.value} value={range.value}>
          {range.label}
        </Option>
      )),
    []
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
    setDrawerOpen(false)
  }

  const resetAdvanced = () => {
    resetFilters()
    setDrawerOpen(false)
  }

  return (
    <div className="filters-toolbar">
      <div className="filters-left">
        <Search
          placeholder="搜索消息（关键词用空格分隔）"
          allowClear
          enterButton={<SearchOutlined />}
          value={filters.search_query}
          onSearch={handleSearch}
          onChange={(e) => setFilters({ search_query: e.target.value })}
          disabled={disabled}
        />
      </div>
      <div className="filters-right">
        <Space size={12}>
          <Select
            value={filters.time_range}
            onChange={(value) => setFilters({ time_range: value })}
            style={{ width: 160 }}
            disabled={disabled}
          >
            {timeRangeOptions}
          </Select>
          <Select
            value={filters.page_size}
            onChange={(value) => setFilters({ page_size: value })}
            style={{ width: 120 }}
            disabled={disabled}
          >
            {pageSizeOptions}
          </Select>
          <Tooltip title="高级筛选">
            <Button icon={<FilterOutlined />} onClick={() => setDrawerOpen(true)} disabled={disabled}>
              高级筛选
            </Button>
          </Tooltip>
          <Tooltip title="重置筛选">
            <Button icon={<ClearOutlined />} onClick={resetFilters} disabled={disabled} />
          </Tooltip>
          <Tooltip title="刷新数据">
            <Button icon={<ReloadOutlined />} onClick={() => setFilters({ ...filters })} disabled={disabled} />
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

