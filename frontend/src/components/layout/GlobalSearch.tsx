import { useEffect, useState } from 'react'
import { Button, Input, Modal, Tooltip } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import MessageFilters from '@/components/messages/MessageFilters'
import {
  PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES,
  PUBLIC_DASHBOARD_FALLBACK_TIME_RANGE,
} from '@/utils/publicDashboard'

const MediaWallSearch = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchValue, setSearchValue] = useState('')

  useEffect(() => {
    setSearchValue(searchParams.get('search') || '')
  }, [searchParams])

  const submitSearch = () => {
    const value = searchValue.trim()
    setSearchOpen(false)
    const query = value ? `?search=${encodeURIComponent(value)}` : ''
    navigate(`/popular${query}`)
  }

  return (
    <>
      <Tooltip title="搜索" placement="bottomRight">
        <Button
          type="text"
          icon={<SearchOutlined />}
          className="public-search-button"
          aria-label="搜索"
          onClick={() => setSearchOpen(true)}
        />
      </Tooltip>
      <Modal
        open={searchOpen}
        title="搜索影视"
        okText="搜索"
        cancelText="取消"
        onOk={submitSearch}
        onCancel={() => setSearchOpen(false)}
        destroyOnClose
      >
        <Input
          autoFocus
          allowClear
          value={searchValue}
          prefix={<SearchOutlined />}
          placeholder="输入影视名称"
          onChange={(event) => setSearchValue(event.target.value)}
          onPressEnter={submitSearch}
        />
      </Modal>
    </>
  )
}

const GlobalSearch = () => {
  const location = useLocation()
  const { isAuthenticated } = useAuthStore()
  const isMediaWall = location.pathname.startsWith('/popular')

  if (isMediaWall) {
    return <MediaWallSearch />
  }

  return (
    <MessageFilters
      layoutVariant={isAuthenticated ? 'default' : 'guest-header'}
      allowedTimeRanges={isAuthenticated ? undefined : PUBLIC_DASHBOARD_ALLOWED_TIME_RANGES}
      fallbackTimeRange={isAuthenticated ? undefined : PUBLIC_DASHBOARD_FALLBACK_TIME_RANGE}
      trigger={
        <Tooltip title="搜索与筛选" placement="bottomRight">
          <Button
            type="text"
            icon={<SearchOutlined />}
            className="public-search-button"
            aria-label="搜索与筛选"
          />
        </Tooltip>
      }
    />
  )
}

export default GlobalSearch
