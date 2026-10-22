import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Alert, Button, Empty, Image, Pagination, Skeleton, Spin, Tabs, Tag, Typography } from 'antd'
import { ArrowLeftOutlined, ArrowRightOutlined, CloseOutlined, ExportOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'

import { getPublicMediaWall, getPublicMediaWallCategories, getPublicMediaWallItem } from '@/api/mediaWall'
import type { MediaWallCategory, MediaWallItem } from '@/types/mediaWall'
import { formatRelativeServerDateTime, formatServerDateTime } from '@/utils/dateTime'
import { sanitizeHtml } from '@/utils/safeHtml'

import './MediaWallPage.css'

const { Title, Text } = Typography
const MEDIA_WALL_PAGE_SIZE = 24

const parsePage = (value: string | null) => {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

const getRequestErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return fallback
}

const getPlatformLabel = (platform: string) => {
  const labels: Record<string, string> = {
    quark: '夸克网盘',
    baidu: '百度网盘',
    aliyun: '阿里云盘',
    '115': '115 网盘',
    '123': '123 云盘',
    tianyi: '天翼云盘',
    uc: 'UC 网盘',
    xunlei: '迅雷云盘',
    unknown: '其他网盘',
    '夸克网盘': '夸克网盘',
    '百度网盘': '百度网盘',
    '阿里云盘': '阿里云盘',
    '115网盘': '115 网盘',
    '123云盘': '123 云盘',
    '天翼云盘': '天翼云盘',
    'UC网盘': 'UC 网盘',
    '迅雷网盘': '迅雷网盘',
  }
  return labels[platform] || platform || '其他网盘'
}

const getLinkStatus = (status: string) => {
  const normalized = status.toLowerCase()
  if (normalized === 'valid' || normalized === 'healthy') return { label: '有效', color: 'green' as const }
  if (normalized === 'requires_code') return { label: '需提取码', color: 'orange' as const }
  if (normalized === 'rate_limited' || normalized === 'uncertain' || normalized === 'unknown') return { label: '待复核', color: 'orange' as const }
  return { label: '待检测', color: 'default' as const }
}

const PosterPlaceholder = ({ title }: { title: string }) => (
  <div className="media-wall-poster-placeholder" aria-label={`${title}暂无海报`}>
    <span>{title.slice(0, 1)}</span>
  </div>
)

const isProgressRemark = (remark: string | null | undefined, episode: number | null | undefined) => {
  if (!remark || !episode || !/(更新至|更至)/.test(remark)) {
    return false
  }
  const episodeNumbers = remark.match(/\d+/g) || []
  return episodeNumbers.some((value) => Number(value) === episode)
}

const MediaWallCard = ({ item, onClick, imageLoading }: { item: MediaWallItem; onClick: () => void; imageLoading: 'eager' | 'lazy' }) => {
  const [imageError, setImageError] = useState(false)

  return (
    <button type="button" className="media-wall-card" onClick={onClick}>
      <div className="media-wall-card-poster">
        {item.poster_url && !imageError ? (
          <Image
            src={item.poster_url}
            preview={false}
            alt={item.display_title}
            loading={imageLoading}
            onError={() => setImageError(true)}
          />
        ) : <PosterPlaceholder title={item.display_title} />}
        <div className="media-wall-card-overlay">
          <span>{item.link_count ? `${item.link_count} 个资源入口` : '暂无资源入口'}</span>
          {item.last_content_updated_at ? (
            <time
              dateTime={item.last_content_updated_at}
              title={`最后更新：${formatServerDateTime(item.last_content_updated_at, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai')}`}
            >
              {formatRelativeServerDateTime(item.last_content_updated_at)}
            </time>
          ) : null}
        </div>
      </div>
      <div className="media-wall-card-body">
        <strong title={item.display_title}>{item.display_title}</strong>
        <span>{item.progress.label}</span>
      </div>
    </button>
  )
}

const MediaWallDetail = ({ item, onBack }: { item: MediaWallItem; onBack: () => void }) => {
  const enabledLinks = item.links.filter((link) => link.is_enabled && link.last_status !== 'invalid')
  const progressLabel = item.progress.label.replace(/\s+/g, '')
  const showRemarks = item.remarks && !isProgressRemark(item.remarks, item.progress.episode)
  const metadataRows: Array<[string, string | null | undefined]> = [
    ['类型', item.type_name],
    ['年份', item.year],
    ['地区', item.area],
    ['导演', item.director],
    ['主演', item.actor],
  ]
  if (showRemarks) {
    metadataRows.push(['备注', item.remarks])
  }
  const visibleMetadataRows = metadataRows.filter((row): row is [string, string] => Boolean(row[1]))

  return (
    <div className="media-wall-detail-page">
      <section className="media-wall-detail-hero">
        <div className="media-wall-detail-heading">
          <div className="media-wall-detail-title-row">
            <Title level={1}>{item.display_title}</Title>
            {item.progress.episode ? <Tag color="blue" className="media-wall-detail-progress-tag">{progressLabel}</Tag> : null}
          </div>
          <Button
            type="text"
            icon={<CloseOutlined />}
            onClick={onBack}
            className="media-wall-detail-close"
            aria-label="关闭影视详情"
          />
        </div>
        <div className="media-wall-detail-poster">
          {item.poster_url ? <Image src={item.poster_url} preview={false} alt={item.display_title} /> : <PosterPlaceholder title={item.display_title} />}
        </div>
        {visibleMetadataRows.length ? (
          <div className="media-wall-detail-meta">
            {visibleMetadataRows.map(([label, value]) => (
              <div key={label} className="media-wall-detail-meta-item" title={`${label}: ${value}`}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        ) : null}
        {item.summary ? (
          <div
            className="media-wall-detail-summary"
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(item.summary) }}
          />
        ) : null}
      </section>

      <section className="media-wall-links-section">
        <div className="media-wall-section-heading">
          <div>
            <Title level={3}>网盘资源入口</Title>
          </div>
          <Tag icon={<LinkOutlined />}>{enabledLinks.length} 个链接</Tag>
        </div>
        {enabledLinks.length ? (
          <div className="media-wall-link-list">
            {enabledLinks.map((link) => (
              <div key={link.id} className="media-wall-link-row">
                <div>
                  <div className="media-wall-link-title"><strong>{getPlatformLabel(link.platform)}</strong><Tag color={getLinkStatus(link.last_status).color}>{getLinkStatus(link.last_status).label}</Tag></div>
                  {link.source_type === 'sync' ? null : (
                    <span>{link.label || (link.is_primary ? '主链接' : '备用链接')}</span>
                  )}
                  {link.source_type === 'sync' ? <span>追更任务自动管理</span> : null}
                </div>
                <Button
                  type="primary"
                  icon={<ExportOutlined />}
                  onClick={() => window.open(link.url, '_blank', 'noopener,noreferrer')}
                >
                  打开分享
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂未配置网盘入口" />
        )}
      </section>

      {item.last_content_updated_at ? <Text className="media-wall-detail-updated">最近更新于 {formatServerDateTime(item.last_content_updated_at, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai')}</Text> : null}
    </div>
  )
}

const MediaWallPage = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const { itemId, categorySlug } = useParams<{ itemId?: string; categorySlug?: string }>()
  const [searchParams] = useSearchParams()
  const [categories, setCategories] = useState<MediaWallCategory[]>([])
  const [items, setItems] = useState<MediaWallItem[]>([])
  const [detail, setDetail] = useState<MediaWallItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedCategory = searchParams.get('category') || categorySlug || 'all'
  const searchQuery = searchParams.get('search') || ''
  const currentPage = parsePage(searchParams.get('page'))
  const [total, setTotal] = useState(0)

  const loadList = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [categoryData, listData] = await Promise.all([
        getPublicMediaWallCategories(),
        getPublicMediaWall({
          category: selectedCategory,
          search: searchQuery || undefined,
          page: currentPage,
          page_size: MEDIA_WALL_PAGE_SIZE,
        }),
      ])
      setCategories(categoryData)
      const totalPages = Math.max(1, Math.ceil(listData.total / MEDIA_WALL_PAGE_SIZE))
      if (listData.total > 0 && currentPage > totalPages) {
        const nextParams = new URLSearchParams(location.search)
        if (totalPages === 1) nextParams.delete('page')
        else nextParams.set('page', String(totalPages))
        navigate(`${location.pathname}${nextParams.toString() ? `?${nextParams.toString()}` : ''}`, { replace: true })
        return
      }
      if (searchQuery.trim() && listData.items.length === 0 && currentPage === 1) {
        const fallbackParams = new URLSearchParams({ search: searchQuery.trim() })
        navigate(`/messages?${fallbackParams.toString()}`, { replace: true })
        return
      }
      setItems(listData.items)
      setTotal(listData.total)
    } catch (loadError: unknown) {
      setError(getRequestErrorMessage(loadError, '影视推荐加载失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }, [currentPage, location.pathname, location.search, navigate, searchQuery, selectedCategory])

  useEffect(() => {
    if (!itemId) {
      setDetail(null)
      void loadList()
      return
    }

    setDetailLoading(true)
    setError('')
    void getPublicMediaWallItem(Number(itemId))
      .then(setDetail)
      .catch((loadError: unknown) => setError(getRequestErrorMessage(loadError, '影视详情加载失败')))
      .finally(() => setDetailLoading(false))
  }, [itemId, loadList])

  const tabItems = useMemo(
    () => categories.map((category) => ({ key: category.slug, label: category.name })),
    [categories]
  )

  const handleCategoryChange = (category: string) => {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('page')
    if (category === 'all') {
      nextParams.delete('category')
      navigate('/popular' + (nextParams.toString() ? `?${nextParams.toString()}` : ''))
      return
    }
    nextParams.delete('category')
    navigate(`/popular/category/${encodeURIComponent(category)}${nextParams.toString() ? `?${nextParams.toString()}` : ''}`)
  }

  const handlePageChange = (nextPage: number) => {
    const nextParams = new URLSearchParams(location.search)
    if (nextPage === 1) nextParams.delete('page')
    else nextParams.set('page', String(nextPage))
    navigate(`${location.pathname}${nextParams.toString() ? `?${nextParams.toString()}` : ''}`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleMoreResources = () => {
    const query = searchQuery.trim()
    navigate(`/messages${query ? `?search=${encodeURIComponent(query)}` : ''}`)
  }

  if (itemId) {
    if (detailLoading) {
      return <div className="media-wall-state"><Spin size="large" /></div>
    }
    if (error || !detail) {
      return <div className="media-wall-page"><Alert type="error" showIcon message={error || '影视详情不存在'} action={<Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/popular')}>返回</Button>} /></div>
    }
    return <MediaWallDetail item={detail} onBack={() => navigate('/popular')} />
  }

  return (
    <div className="media-wall-page">
      <div className="media-wall-tabs-header">
        <div className="media-wall-tabs-row">
          <div className="media-wall-tabs-wrap">
            <Tabs
              activeKey={selectedCategory}
              onChange={handleCategoryChange}
              items={tabItems}
              className="media-wall-tabs"
              destroyInactiveTabPane={false}
            />
          </div>
        </div>
        <div className="media-wall-actions">
          <Button
            type="link"
            size="small"
            icon={<ArrowRightOutlined />}
            onClick={handleMoreResources}
            className="media-wall-more-button"
          >
            查看更多资源
          </Button>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={() => void loadList()}
            loading={loading}
            aria-label="刷新影视推荐"
            className="media-wall-refresh-button"
          />
        </div>
      </div>

      {error ? <Alert type="error" showIcon message={error} className="media-wall-alert" /> : null}
      {loading ? (
        <div className="media-wall-grid">
          {Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} active className="media-wall-skeleton" />)}
        </div>
      ) : items.length ? (
        <div className="media-wall-grid">
          {items.map((item, index) => <MediaWallCard key={item.id} item={item} imageLoading={index < 6 ? 'eager' : 'lazy'} onClick={() => navigate(`/popular/item/${item.id}`)} />)}
        </div>
      ) : (
        <div className="media-wall-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={searchQuery ? '没有找到匹配的影视推荐' : '当前分类暂无公开影视推荐'} /></div>
      )}

      {!loading && total > MEDIA_WALL_PAGE_SIZE ? (
        <div className="media-wall-pagination">
          <Pagination
            current={currentPage}
            pageSize={MEDIA_WALL_PAGE_SIZE}
            total={total}
            responsive
            showLessItems
            showSizeChanger={false}
            showTotal={(count) => `共 ${count} 部`}
            onChange={handlePageChange}
          />
        </div>
      ) : null}
    </div>
  )
}

export default MediaWallPage
