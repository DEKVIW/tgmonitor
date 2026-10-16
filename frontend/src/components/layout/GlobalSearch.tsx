import { useEffect, useState } from 'react'
import { Button, Input, Modal, Space, Tooltip } from 'antd'
import { ClearOutlined, SearchOutlined } from '@ant-design/icons'
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
        title={
          <div className="public-search-modal-title">
            <SearchOutlined />
            <span>搜索影视</span>
          </div>
        }
        onOk={submitSearch}
        onCancel={() => setSearchOpen(false)}
        destroyOnClose
        width={600}
        className="public-search-modal"
        rootClassName="public-search-modal-root"
        footer={
          <div className="public-search-modal-footer">
            <Button icon={<ClearOutlined />} onClick={() => setSearchValue('')}>清空</Button>
            <Space>
              <Button onClick={() => setSearchOpen(false)}>取消</Button>
              <Button type="primary" icon={<SearchOutlined />} onClick={submitSearch}>搜索影视</Button>
            </Space>
          </div>
        }
      >
        <div className="public-search-modal-body">
          <Input
            autoFocus
            allowClear
            size="large"
            value={searchValue}
            prefix={<SearchOutlined />}
            placeholder="输入影视名称"
            onChange={(event) => setSearchValue(event.target.value)}
            onPressEnter={submitSearch}
          />
        </div>
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
