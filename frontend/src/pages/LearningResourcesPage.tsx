import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Empty, Input, List, Modal, Popconfirm, Select, Space, Spin, Switch, Table, Tag, Typography, Upload, message } from 'antd'
import { ArrowLeftOutlined, BookOutlined, CheckOutlined, CloseOutlined, DeleteOutlined, EditOutlined, ExportOutlined, FolderOpenOutlined, ReloadOutlined, SaveOutlined, UploadOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/store/authStore'
import { formatServerDateTime } from '@/utils/dateTime'
import {
  deleteAllImportedLearningResources,
  deleteLearningResource,
  getLearningAdminItems,
  getLearningAdminOverview,
  getLearningDirectories,
  getPublicLearningCategories,
  getPublicLearningResources,
  confirmLearningImport,
  previewLearningImport,
  retryLearningResource,
  updateLearningResource,
  updateLearningChannel,
} from '@/api/learningResources'
import type {
  LearningAdminOverview,
  LearningCategory,
  LearningDirectory,
  LearningImportPreview,
  LearningResource,
} from '@/types/learningResources'

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
  const [resourceTotal, setResourceTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 50
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
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState({ display_title: '', category: '', tags: '', share_url: '' })
  const [deletingAll, setDeletingAll] = useState(false)
  const [importPreview, setImportPreview] = useState<LearningImportPreview | null>(null)
  const [importMode, setImportMode] = useState<'direct' | 'transfer' | 'collect'>('direct')
  const [importAccountId, setImportAccountId] = useState<number | undefined>(undefined)
  const [importRoot, setImportRoot] = useState('')
  const [importConfirming, setImportConfirming] = useState(false)
  const [directoryModalOpen, setDirectoryModalOpen] = useState(false)
  const [directoryTarget, setDirectoryTarget] = useState<'channel' | 'import'>('channel')
  const [directoryAccountId, setDirectoryAccountId] = useState<number | undefined>(undefined)
  const [directoryLoading, setDirectoryLoading] = useState(false)
  const [directoryItems, setDirectoryItems] = useState<LearningDirectory[]>([])
  const [directoryStack, setDirectoryStack] = useState<Array<{ id: string; name: string; path: string }>>([])

  const selectedChannel = useMemo(
    () => overview?.channels.find((channel) => channel.channel_id === selectedChannelId) ?? null,
    [overview, selectedChannelId],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (isAdmin) {
        const [overviewData, adminData] = await Promise.all([
          getLearningAdminOverview(),
          getLearningAdminItems({
            category: activeCategory === 'all' ? undefined : activeCategory,
            search: search.trim() || undefined,
            page,
            page_size: pageSize,
          }),
        ])
        setOverview(overviewData)
        setCategories(overviewData.categories.map((category) => ({
          id: category.id,
          name: category.name,
          slug: category.slug,
          sort_order: category.sort_order,
          resource_count: category.resource_count,
        })))
        setResources(adminData.items.map((item) => ({ ...item, share_url: item.share_url || '', platform: item.platform || '' })))
        setResourceTotal(adminData.total)
        if (selectedChannelId === null && overviewData.channels.length > 0) {
          setSelectedChannelId(overviewData.channels[0].channel_id)
        }
      } else {
        const [categoryData, resourceData] = await Promise.all([
          getPublicLearningCategories(),
          getPublicLearningResources({
            category: activeCategory === 'all' ? undefined : activeCategory,
            search: search.trim() || undefined,
            page,
            page_size: pageSize,
          }),
        ])
        setCategories(categoryData)
        setResources(resourceData.items)
        setResourceTotal(resourceData.total)
      }
    } catch (loadError: unknown) {
      setError(getRequestErrorMessage(loadError, '学习资料加载失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }, [activeCategory, isAdmin, page, search, selectedChannelId])

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

  const loadDirectories = async (accountId: number, parentId: string) => {
    setDirectoryLoading(true)
    try {
      setDirectoryItems(await getLearningDirectories(accountId, parentId))
    } catch (directoryError: unknown) {
      message.error(getRequestErrorMessage(directoryError, '读取网盘目录失败'))
      setDirectoryItems([])
    } finally {
      setDirectoryLoading(false)
    }
  }

  const openDirectoryPicker = async (target: 'channel' | 'import') => {
    const accountId = target === 'channel' ? channelDraft.target_account_id : importAccountId
    if (!accountId) {
      message.warning('请先选择已配置的夸克账号')
      return
    }
    setDirectoryTarget(target)
    setDirectoryAccountId(accountId)
    setDirectoryStack([{ id: '0', name: '网盘根目录', path: '' }])
    setDirectoryModalOpen(true)
    await loadDirectories(accountId, '0')
  }

  const enterDirectory = async (directory: LearningDirectory) => {
    if (!directoryAccountId) return
    const currentPath = directoryStack[directoryStack.length - 1]?.path || ''
    const path = [currentPath, directory.name].filter(Boolean).join('/')
    setDirectoryStack((current) => [...current, { id: directory.id, name: directory.name, path }])
    await loadDirectories(directoryAccountId, directory.id)
  }

  const handleDirectoryBack = async () => {
    if (!directoryAccountId || directoryStack.length <= 1) return
    const nextStack = directoryStack.slice(0, -1)
    setDirectoryStack(nextStack)
    await loadDirectories(directoryAccountId, nextStack[nextStack.length - 1].id)
  }

  const handleDirectorySelect = () => {
    const currentPath = directoryStack[directoryStack.length - 1]?.path || ''
    if (directoryTarget === 'channel') {
      setChannelDraft((draft) => ({ ...draft, save_root: currentPath }))
    } else {
      setImportRoot(currentPath)
    }
    setDirectoryModalOpen(false)
  }

  const handlePreviewImport = async (file: File) => {
    try {
      setImportPreview(await previewLearningImport(file))
      setImportMode('direct')
    } catch (importError: unknown) {
      message.error(getRequestErrorMessage(importError, '解析学习资料文件失败'))
    }
  }

  const handleConfirmImport = async () => {
    if (!importPreview) return
    if (importMode === 'transfer' && (!importAccountId || !importRoot.trim())) {
      message.warning('提交转存前请选择夸克账号和资料根目录')
      return
    }
    setImportConfirming(true)
    try {
      const result = await confirmLearningImport(importPreview.id, {
        mode: importMode,
        target_account_id: importMode === 'transfer' ? importAccountId : undefined,
        save_root: importMode === 'transfer' ? importRoot.trim() : undefined,
      })
      message.success(result.queued_count > 0 ? `已导入并排队 ${result.queued_count} 个转存任务` : '学习资料已导入')
      setImportPreview(null)
      await load()
    } catch (importError: unknown) {
      message.error(getRequestErrorMessage(importError, '确认学习资料导入失败'))
    } finally {
      setImportConfirming(false)
    }
  }

  const startEditing = (item: LearningResource) => {
    setEditingId(item.id)
    setEditDraft({
      display_title: item.display_title,
      category: item.category?.name || '待分类',
      tags: item.tags.join('、'),
      share_url: item.share_url || '',
    })
  }

  const cancelEditing = () => {
    setEditingId(null)
    setEditDraft({ display_title: '', category: '', tags: '', share_url: '' })
  }

  const handleSaveEditing = async (item: LearningResource) => {
    setMaintenanceBusyId(item.id)
    try {
      const updated = await updateLearningResource(item.id, {
        display_title: editDraft.display_title.trim(),
        category: editDraft.category.trim() || '待分类',
        tags: editDraft.tags.split(/[、,，|]/).map((tag) => tag.trim()).filter(Boolean),
        share_url: editDraft.share_url.trim(),
      })
      message.success('资源已保存')
      cancelEditing()
      setResources((current) => current.map((row) => row.id === item.id ? { ...row, ...updated, share_url: updated.share_url || '' } : row))
    } catch (editError: unknown) {
      message.error(getRequestErrorMessage(editError, '保存资源失败'))
    } finally {
      setMaintenanceBusyId(null)
    }
  }

  const handleDeleteRow = async (item: LearningResource) => {
    setMaintenanceBusyId(item.id)
    try {
      await deleteLearningResource(item.id)
      message.success('资源及其学习资料记录已删除')
      if (resources.length === 1 && page > 1) setPage((current) => current - 1)
      else await load()
    } catch (deleteError: unknown) {
      message.error(getRequestErrorMessage(deleteError, '删除资源失败'))
    } finally {
      setMaintenanceBusyId(null)
    }
  }

  const handleDeleteAllImported = async () => {
    setDeletingAll(true)
    try {
      const result = await deleteAllImportedLearningResources()
      message.success(`已删除 ${result.deleted_resources} 条手动导入资料及其关联记录`)
      setPage(1)
      cancelEditing()
      if (page === 1) await load()
    } catch (deleteError: unknown) {
      message.error(getRequestErrorMessage(deleteError, '删除手动导入资料失败'))
    } finally {
      setDeletingAll(false)
    }
  }

  const handleRetry = async (item: LearningResource) => {
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
    { key: 'all', label: '全部 ' + resourceTotal },
    ...categories.map((category) => ({
      key: category.slug,
      label: category.name + ' ' + category.resource_count,
    })),
  ]

  const columns = [
    {
      title: '#',
      key: 'row-number',
      width: 58,
      fixed: 'left' as const,
      render: (_value: unknown, _row: LearningResource, index: number) => (page - 1) * pageSize + index + 1,
    },
    {
      title: '资源标题',
      dataIndex: 'display_title',
      key: 'title',
      render: (title: string, row: LearningResource) => (
        editingId === row.id ? (
          <Input value={editDraft.display_title} onChange={(event) => setEditDraft((draft) => ({ ...draft, display_title: event.target.value }))} />
        ) : (
          <div className="learning-title-cell" onDoubleClick={() => isAdmin && startEditing(row)}>
            <strong>{title}</strong>
            {row.tags.length > 0 ? <span>{row.tags.slice(0, 3).join(' · ')}</span> : null}
          </div>
        )
      ),
    },
    {
      title: '分类',
      key: 'category',
      width: 150,
      render: (_value: unknown, row: LearningResource) => editingId === row.id ? (
        <Input
          value={editDraft.category || '待分类'}
          onChange={(event) => setEditDraft((draft) => ({ ...draft, category: event.target.value }))}
        />
      ) : row.category?.name || '待分类',
    },
    {
      title: '标签',
      key: 'tags',
      width: 180,
      render: (_value: unknown, row: LearningResource) => editingId === row.id ? (
        <Input value={editDraft.tags} onChange={(event) => setEditDraft((draft) => ({ ...draft, tags: event.target.value }))} />
      ) : row.tags.join('、') || '-',
    },
    {
      title: '网盘资源',
      key: 'share',
      width: 240,
      render: (_value: unknown, row: LearningResource) => editingId === row.id ? (
        <Input value={editDraft.share_url} onChange={(event) => setEditDraft((draft) => ({ ...draft, share_url: event.target.value }))} />
      ) : row.share_url ? (
        <Button type="link" icon={<ExportOutlined />} onClick={() => window.open(row.share_url, '_blank', 'noopener,noreferrer')}>
          打开分享
        </Button>
      ) : <Tag color="orange">暂无链接</Tag>,
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
  if (isAdmin) {
    columns.push({
      title: '状态',
      key: 'status',
      width: 100,
      render: (_value: unknown, row: LearningResource) => (
        <Tag color={row.status === 'published' ? 'green' : row.status === 'failed' ? 'red' : 'default'}>{row.status || 'pending'}</Tag>
      ),
    })
    columns.push({
      title: '操作',
      key: 'action',
      width: 190,
      render: (_value: unknown, row: LearningResource) => editingId === row.id ? (
        <Space size={4}>
          <Button size="small" type="primary" icon={<CheckOutlined />} loading={maintenanceBusyId === row.id} onClick={() => void handleSaveEditing(row)}>保存</Button>
          <Button size="small" icon={<CloseOutlined />} onClick={cancelEditing}>取消</Button>
        </Space>
      ) : (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => startEditing(row)}>编辑</Button>
          {row.status === 'failed' ? <Button size="small" loading={maintenanceBusyId === row.id} onClick={() => void handleRetry(row)}>重试</Button> : null}
          <Popconfirm title="确认删除这条资源？" description="只删除本项目中的学习资料记录，不删除网盘远端文件。" okText="删除" cancelText="取消" onConfirm={() => void handleDeleteRow(row)}>
            <Button size="small" danger icon={<DeleteOutlined />} loading={maintenanceBusyId === row.id}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    })
  }

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
              style={{ width: 220 }}
            />
            <Button
              icon={<FolderOpenOutlined />}
              onClick={() => void openDirectoryPicker('channel')}
              disabled={!channelDraft.target_account_id}
            >
              选择目录
            </Button>
            <Space size={6}>
              <Switch checked={channelDraft.is_enabled} onChange={(checked) => setChannelDraft((draft) => ({ ...draft, is_enabled: checked }))} />
              <Text>启用自动流程</Text>
            </Space>
            <Button type="primary" icon={<SaveOutlined />} loading={savingConfig} onClick={() => void handleSaveConfig()}>保存配置</Button>
          </Space>
          {selectedChannel?.last_error_message ? <Alert className="learning-config-error" type="warning" showIcon message={selectedChannel.last_error_message} /> : null}
        </section>
      ) : null}

      {isAdmin && overview ? (
        <section className="learning-import-panel">
          <div className="learning-admin-heading">
            <div>
              <Text strong>批量导入学习资料</Text>
              <Text type="secondary">支持 TXT / XLSX；先预览，确认后再入库或排队转存。</Text>
            </div>
            <Upload
              accept=".txt,.xlsx,.xlsm"
              showUploadList={false}
              beforeUpload={(file) => {
                void handlePreviewImport(file)
                return false
              }}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </div>
          {importPreview ? (
            <div className="learning-import-preview">
              <Alert
                type="info"
                showIcon
                message={`已解析 ${importPreview.total_records} 个资源、${importPreview.total_links} 个链接，${importPreview.invalid_count} 行异常`}
              />
              <Space wrap className="learning-import-controls">
                <Select
                  value={importMode}
                  options={[
                    { value: 'direct', label: '直接入库（已有自有分享）' },
                    { value: 'transfer', label: '提交夸克转存' },
                    { value: 'collect', label: '仅收集，暂不公开' },
                  ]}
                  onChange={setImportMode}
                  style={{ minWidth: 220 }}
                />
                {importMode === 'transfer' ? (
                  <>
                    <Select
                      value={importAccountId}
                      placeholder="选择夸克账号"
                      options={overview.accounts.filter((account) => account.is_enabled).map((account) => ({ value: account.id, label: account.account_name }))}
                      onChange={(value) => setImportAccountId(value)}
                      style={{ minWidth: 180 }}
                    />
                    <Input value={importRoot} placeholder="选择资料根目录" readOnly style={{ width: 220 }} />
                    <Button icon={<FolderOpenOutlined />} onClick={() => void openDirectoryPicker('import')} disabled={!importAccountId}>
                      选择目录
                    </Button>
                  </>
                ) : null}
                <Button type="primary" loading={importConfirming} onClick={() => void handleConfirmImport()}>确认导入</Button>
                <Button onClick={() => setImportPreview(null)}>取消</Button>
              </Space>
              <Table
                rowKey={(record) => `${record.display_title}-${record.category}`}
                size="small"
                pagination={{ pageSize: 8 }}
                dataSource={importPreview.records}
                columns={[
                  { title: '资源标题', dataIndex: 'display_title' },
                  { title: '分类', dataIndex: 'category', width: 120 },
                  { title: '标签', dataIndex: 'tags', render: (tags: string[]) => tags.join('、') || '-' },
                  { title: '链接数', dataIndex: 'links', render: (links: unknown[]) => links.length, width: 80 },
                ]}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      {error ? <Alert className="learning-alert" type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} /> : null}

      <section className="learning-sheet">
        <div className="learning-sheet-toolbar">
          <div className="learning-sheet-tabs">
            {tabs.map((tab) => (
              <button key={tab.key} type="button" className={activeCategory === tab.key ? 'active' : ''} onClick={() => { setActiveCategory(tab.key); setPage(1) }}>
                {tab.label}
              </button>
            ))}
          </div>
          <Space>
            <Input.Search value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="搜索资源标题" allowClear style={{ width: 250 }} />
            {isAdmin ? (
              <Popconfirm
                title="删除全部手动导入资料？"
                description="将永久删除项目中的手动导入记录、链接、转存任务和导入记录，不删除 Telegram 原消息或网盘远端文件。"
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={() => void handleDeleteAllImported()}
              >
                <Button danger loading={deletingAll} icon={<DeleteOutlined />}>删除全部导入</Button>
              </Popconfirm>
            ) : null}
          </Space>
        </div>
        {loading ? <div className="learning-state"><Spin /></div> : resources.length === 0 ? <Empty description="暂无已发布学习资料" /> : (
          <Table<LearningResource>
            rowKey="id"
            columns={columns}
            dataSource={resources}
            pagination={{
              current: page,
              pageSize,
              total: resourceTotal,
              showSizeChanger: false,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (nextPage) => setPage(nextPage),
            }}
            size="middle"
            scroll={{ x: 1160 }}
          />
        )}
      </section>

      <Modal
        open={directoryModalOpen}
        title="选择网盘资料根目录"
        onCancel={() => setDirectoryModalOpen(false)}
        onOk={handleDirectorySelect}
        okText="选择当前目录"
        cancelText="取消"
      >
        <div className="learning-directory-path">当前路径：{directoryStack[directoryStack.length - 1]?.path || '网盘根目录'}</div>
        <Space style={{ marginBottom: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => void handleDirectoryBack()} disabled={directoryStack.length <= 1}>
            返回上级
          </Button>
        </Space>
        <List
          loading={directoryLoading}
          bordered
          dataSource={directoryItems}
          locale={{ emptyText: '当前目录没有子目录' }}
          renderItem={(directory) => (
            <List.Item
              actions={[<Button key={directory.id} type="link" onClick={() => void enterDirectory(directory)}>打开</Button>]}
            >
              <Space><FolderOpenOutlined />{directory.name}</Space>
            </List.Item>
          )}
        />
      </Modal>
    </div>
  )
}

export default LearningResourcesPage
