import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Empty, Input, Select, Space, Spin, Switch, Table, Tag, Typography, message } from 'antd'
import { BookOutlined, ExportOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import { formatServerDateTime } from '@/utils/dateTime'
import {
  getLearningAdminItems,
  getLearningAdminOverview,
  getPublicLearningCategories,
  getPublicLearningResources,
  retryLearningResource,
  updateLearningChannel,
  updateLearningVisibility,
} from '@/api/learningResources'
import type { LearningAdminItem, LearningAdminOverview, LearningCategory, LearningResource } from '@/types/learningResources'

import './LearningResourcesPage.css'

const { Text, Title } = Typography

const getRequestErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

const LearningResourcesPage = () => {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin'
  const [categories, setCategories] = useState<LearningCategory[]>([])
  const [resources, setResources] = useState<LearningResource[]>([])
  const [adminItems, setAdminItems] = useState<LearningAdminItem[]>([])
  const [overview, setOverview] = useState<LearningAdminOverview | null>(null)
  const [activeCategory, setActiveCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedChannelId, setSelectedChannelId] = useState<number | null>(null)
  const [channelDraft, setChannelDraft] = useState({
    is_enabled: false,
    target_account_id: undefined as number | undefined,
    save_root: '',
  })
  const [savingConfig, setSavingConfig] = useState(false)
  const [maintenanceBusyId, setMaintenanceBusyId] = useState<number | null>(null)

  const selectedChannel = useMemo(
    () => overview?.channels.find((channel) => channel.channel_id === selectedChannelId) ?? null,
    [overview, selectedChannelId],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [categoryData, resourceData] = await Promise.all([
        getPublicLearningCategories(),
        getPublicLearningResources({
          category: activeCategory === 'all' ? undefined : activeCategory,
          search: search.trim() || undefined,
        }),
      ])
      setCategories(categoryData)
      setResources(resourceData.items)
      if (isAdmin) {
        const [overviewData, adminData] = await Promise.all([
          getLearningAdminOverview(),
          getLearningAdminItems(search.trim() || undefined),
        ])
        setOverview(overviewData)
        setAdminItems(adminData)
        if (selectedChannelId === null && overviewData.channels.length > 0) {
          setSelectedChannelId(overviewData.channels[0].channel_id)
        }
      }
    } catch (loadError: unknown) {
      setError(getRequestErrorMessage(loadError, '学习资料加载失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }, [activeCategory, isAdmin, search, selectedChannelId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!selectedChannel) return
    setChannelDraft({
      is_enabled: selectedChannel.is_enabled,
      target_account_id: selectedChannel.target_account_id ?? undefined,
      save_root: selectedChannel.save_root,
    })
  }, [selectedChannel])

  const handleSaveConfig = async () => {
    if (!selectedChannel) return
    setSavingConfig(true)
    try {
      await updateLearningChannel(selectedChannel.channel_id, channelDraft)
      message.success(channelDraft.is_enabled ? '自动监听与转存已开启' : '自动监听与转存已暂停')
      await load()
    } catch (saveError: unknown) {
      message.error(getRequestErrorMessage(saveError, '保存学习资料配置失败'))
    } finally {
      setSavingConfig(false)
    }
  }

  const handleVisibility = async (item: LearningAdminItem) => {
    const visible = item.status !== 'published'
    setMaintenanceBusyId(item.id)
    try {
      await updateLearningVisibility(item.id, visible)
      message.success(visible ? '资源已恢复公开' : '资源已隐藏')
      await load()
    } catch (visibilityError: unknown) {
      message.error(getRequestErrorMessage(visibilityError, '更新资源状态失败'))
    } finally {
      setMaintenanceBusyId(null)
    }
  }

  const handleRetry = async (item: LearningAdminItem) => {
    setMaintenanceBusyId(item.id)
    try {
      await retryLearningResource(item.id)
      message.success('已重新加入转存队列')
      await load()
    } catch (retryError: unknown) {
      message.error(getRequestErrorMessage(retryError, '重试转存失败'))
    } finally {
      setMaintenanceBusyId(null)
    }
  }

  const tabs = [
    { key: 'all', label: '全部 ' + resources.length },
    ...categories.map((category) => ({
      key: category.slug,
      label: category.name + ' ' + category.resource_count,
    })),
  ]

  const columns = [
    {
      title: '资源标题',
      dataIndex: 'display_title',
      key: 'title',
      render: (title: string, row: LearningResource) => (
        <div className="learning-title-cell">
          <strong>{title}</strong>
          {row.tags.length > 0 ? <span>{row.tags.slice(0, 3).join(' · ')}</span> : null}
        </div>
      ),
    },
    {
      title: '分类',
      key: 'category',
      width: 150,
      render: (_value: unknown, row: LearningResource) => row.category?.name || '待分类',
    },
    {
      title: '网盘资源',
      key: 'share',
      width: 160,
      render: (_value: unknown, row: LearningResource) => (
        <Button type="link" icon={<ExportOutlined />} onClick={() => window.open(row.share_url, '_blank', 'noopener,noreferrer')}>
          打开分享
        </Button>
      ),
    },
    {
      title: '更新时间',
      key: 'updated',
      width: 180,
      render: (_value: unknown, row: LearningResource) => row.updated_at
        ? formatServerDateTime(row.updated_at, 'YYYY-MM-DD HH:mm', 'Asia/Shanghai')
        : '-',
    },
  ]

  const adminColumns = [
    { title: '资源标题', dataIndex: 'display_title', key: 'title' },
    { title: '分类', key: 'category', render: (_value: unknown, row: LearningAdminItem) => row.category?.name || '待分类' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (value: string) => <Tag color={value === 'published' ? 'green' : value === 'failed' ? 'red' : 'default'}>{value}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_value: unknown, row: LearningAdminItem) => row.status === 'failed' ? (
        <Button size="small" loading={maintenanceBusyId === row.id} onClick={() => void handleRetry(row)}>重试</Button>
      ) : (
        <Button size="small" loading={maintenanceBusyId === row.id} onClick={() => void handleVisibility(row)}>
          {row.status === 'published' ? '隐藏' : '恢复'}
        </Button>
      ),
    },
  ]

  return (
    <div className="learning-resources-page">
      <div className="learning-resources-heading">
        <div>
          <Text className="learning-eyebrow"><BookOutlined /> 学习资料库</Text>
          <Title level={2}>资料入口</Title>
          <Text type="secondary">按分类整理的公开学习资料，按最近入库时间优先展示。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>
      </div>

      {isAdmin && overview ? (
        <section className="learning-config-panel">
          <div className="learning-config-heading">
            <div>
              <Text strong>自动监听与转存</Text>
              <Text type="secondary">关闭时不创建新任务；已发布资料不会被删除。</Text>
            </div>
            <Tag color={channelDraft.is_enabled ? 'green' : 'default'}>{channelDraft.is_enabled ? '运行中' : '已暂停'}</Tag>
          </div>
          <Space wrap className="learning-config-controls">
            <Select
              value={selectedChannelId ?? undefined}
              placeholder="选择监听频道"
              options={overview.channels.map((channel) => ({ value: channel.channel_id, label: channel.channel_key + ' · ' + channel.channel_title }))}
              onChange={setSelectedChannelId}
              style={{ minWidth: 230 }}
            />
            <Select
              value={channelDraft.target_account_id}
              placeholder="夸克账号"
              options={overview.accounts.filter((account) => account.is_enabled).map((account) => ({ value: account.id, label: account.account_name }))}
              onChange={(value) => setChannelDraft((draft) => ({ ...draft, target_account_id: value }))}
              style={{ minWidth: 160 }}
            />
            <Input
              value={channelDraft.save_root}
              placeholder="学习资料根目录（可留空使用账号默认目录）"
              onChange={(event) => setChannelDraft((draft) => ({ ...draft, save_root: event.target.value }))}
              style={{ width: 280 }}
            />
            <Space size={6}>
              <Switch checked={channelDraft.is_enabled} onChange={(checked) => setChannelDraft((draft) => ({ ...draft, is_enabled: checked }))} />
              <Text>启用自动流程</Text>
            </Space>
            <Button type="primary" icon={<SaveOutlined />} loading={savingConfig} onClick={() => void handleSaveConfig()}>保存配置</Button>
          </Space>
          {selectedChannel?.last_error_message ? <Alert className="learning-config-error" type="warning" showIcon message={selectedChannel.last_error_message} /> : null}
        </section>
      ) : null}

      {error ? <Alert className="learning-alert" type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} /> : null}

      <section className="learning-sheet">
        <div className="learning-sheet-toolbar">
          <div className="learning-sheet-tabs">
            {tabs.map((tab) => (
              <button key={tab.key} type="button" className={activeCategory === tab.key ? 'active' : ''} onClick={() => setActiveCategory(tab.key)}>
                {tab.label}
              </button>
            ))}
          </div>
          <Input.Search value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索资源标题" allowClear style={{ width: 250 }} />
        </div>
        {loading ? <div className="learning-state"><Spin /></div> : resources.length === 0 ? <Empty description="暂无已发布学习资料" /> : (
          <Table<LearningResource> rowKey="id" columns={columns} dataSource={resources} pagination={false} size="middle" scroll={{ x: 720 }} />
        )}
      </section>

      {isAdmin ? (
        <section className="learning-admin-sheet">
          <div className="learning-admin-heading">
            <div>
              <Text strong>管理员维护</Text>
              <Text type="secondary">隐藏操作只影响前台展示，不删除原始消息或网盘文件。</Text>
            </div>
          </div>
          <Table<LearningAdminItem> rowKey="id" columns={adminColumns} dataSource={adminItems} pagination={{ pageSize: 10 }} size="small" />
        </section>
      ) : null}
    </div>
  )
}

export default LearningResourcesPage
