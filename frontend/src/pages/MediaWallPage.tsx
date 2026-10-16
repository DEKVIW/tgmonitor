import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Alert, Button, Empty, Image, Skeleton, Spin, Tabs, Tag, Typography } from 'antd'
import { ArrowLeftOutlined, ExportOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'

import { getPublicMediaWall, getPublicMediaWallCategories, getPublicMediaWallItem } from '@/api/mediaWall'
import type { MediaWallCategory, MediaWallItem } from '@/types/mediaWall'
import { formatServerDateTime } from '@/utils/dateTime'
import { sanitizeHtml } from '@/utils/safeHtml'

import './MediaWallPage.css'

const { Title, Text } = Typography

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
  }
  return labels[platform] || platform || '其他网盘'
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

const MediaWallCard = ({ item, onClick }: { item: MediaWallItem; onClick: () => void }) => {
  const [imageError, setImageError] = useState(false)

  return (
    <button type="button" className="media-wall-card" onClick={onClick}>
      <div className="media-wall-card-poster">
        {item.poster_url && !imageError ? (
          <Image
            src={item.poster_url}
            preview={false}
            alt={item.display_title}
            onError={() => setImageError(true)}
          />
        ) : <PosterPlaceholder title={item.display_title} />}
        <div className="media-wall-card-overlay">
          <span>{item.link_count ? `${item.link_count} 个资源入口` : '暂无资源入口'}</span>
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
  const enabledLinks = item.links.filter((link) => link.is_enabled)
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
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack} className="media-wall-back-button">
        返回影视墙
      </Button>
      <section className="media-wall-detail-hero">
        <div className="media-wall-detail-poster">
          {item.poster_url ? <Image src={item.poster_url} preview={false} alt={item.display_title} /> : <PosterPlaceholder title={item.display_title} />}
        </div>
        <div className="media-wall-detail-copy">
          <div className="media-wall-detail-title-row">
            <Title level={1}>{item.display_title}</Title>
            {item.progress.episode ? <Tag color="blue" className="media-wall-detail-progress-tag">{progressLabel}</Tag> : null}
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
        </div>
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
            <Text type="secondary">选择对应网盘打开分享页面，可及时转存保存。</Text>
          </div>
          <Tag icon={<LinkOutlined />}>{enabledLinks.length} 个链接</Tag>
        </div>
        {enabledLinks.length ? (
          <div className="media-wall-link-list">
            {enabledLinks.map((link) => (
              <div key={link.id} className="media-wall-link-row">
                <div>
                  <strong>{getPlatformLabel(link.platform)}</strong>
                  <span>{link.label || (link.is_primary ? '主链接' : '备用链接')}</span>
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

      {item.updated_at ? <Text className="media-wall-detail-updated">条目更新于 {formatServerDateTime(item.updated_at, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai')}</Text> : null}
    </div>
  )
}

const MediaWallPage = () => {
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

  const loadList = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [categoryData, listData] = await Promise.all([
        getPublicMediaWallCategories(),
        getPublicMediaWall({ category: selectedCategory, search: searchQuery || undefined }),
      ])
      setCategories(categoryData)
      setItems(listData.items)
    } catch (loadError: unknown) {
      setError(getRequestErrorMessage(loadError, '影视墙加载失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }, [searchQuery, selectedCategory])

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
    if (category === 'all') {
      nextParams.delete('category')
      navigate('/popular' + (nextParams.toString() ? `?${nextParams.toString()}` : ''))
      return
    }
    nextParams.delete('category')
    navigate(`/popular/category/${encodeURIComponent(category)}${nextParams.toString() ? `?${nextParams.toString()}` : ''}`)
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
        <div className="media-wall-tabs-wrap">
          <Tabs
            activeKey={selectedCategory}
            onChange={handleCategoryChange}
            items={tabItems}
            className="media-wall-tabs"
            destroyInactiveTabPane={false}
          />
        </div>
        <Button
          type="text"
          icon={<ReloadOutlined />}
          onClick={() => void loadList()}
          loading={loading}
          aria-label="刷新影视墙"
        />
      </div>

      {error ? <Alert type="error" showIcon message={error} className="media-wall-alert" /> : null}
      {loading ? (
        <div className="media-wall-grid">
          {Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} active className="media-wall-skeleton" />)}
        </div>
      ) : items.length ? (
        <div className="media-wall-grid">
          {items.map((item) => <MediaWallCard key={item.id} item={item} onClick={() => navigate(`/popular/item/${item.id}`)} />)}
        </div>
      ) : (
        <div className="media-wall-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={searchQuery ? '没有找到匹配的影视' : '当前分类暂无公开影视'} /></div>
      )}
    </div>
  )
}

export default MediaWallPage
