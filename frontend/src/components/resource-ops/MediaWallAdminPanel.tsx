import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Upload, message } from 'antd'
import type { UploadProps } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, SafetyOutlined, UploadOutlined } from '@ant-design/icons'

import {
  addMediaWallLink,
  confirmMediaWallImport,
  createMediaWallCategory,
  createMediaWallItem,
  createMediaWallSource,
  deleteMediaWallItem,
  deleteMediaWallItems,
  disableMediaWallCategory,
  getMediaWallCategories,
  getMediaWallItems,
  getMediaWallSources,
  getMediaWallSyncTasks,
  previewMediaWallImport,
  testMediaWallSource,
  updateMediaWallCategory,
  updateMediaWallItem,
  updateMediaWallSource,
} from '@/api/mediaWall'
import type { MediaWallCategory, MediaWallImportPreview, MediaWallItem, MediaWallSource, MediaWallSyncTask } from '@/types/mediaWall'

import './MediaWallAdminPanel.css'

const getRequestErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return fallback
}

interface ItemFormValues {
  display_title: string
  metadata_query_title?: string
  visibility: string
  sort_order: number
  category_ids: number[]
  sync_task_id?: number
  custom_poster_url?: string
  links_text?: string
}

interface CategoryFormValues {
  name: string
  slug?: string
  sort_order: number
  is_enabled: boolean
}

interface SourceFormValues {
  name: string
  source_url: string
  source_type: string
  is_enabled: boolean
  priority: number
  timeout_seconds: number
}

const parseLinks = (value?: string) => (value || '')
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter(Boolean)
  .map((line) => {
    const [url, label] = line.split(/\t+|\s+\|\s+/, 2)
    return { url: url.trim(), label: label?.trim() || undefined, source_type: 'manual', is_primary: false }
  })

const MediaWallAdminPanel = () => {
  const [categories, setCategories] = useState<MediaWallCategory[]>([])
  const [items, setItems] = useState<MediaWallItem[]>([])
  const [sources, setSources] = useState<MediaWallSource[]>([])
  const [syncTasks, setSyncTasks] = useState<MediaWallSyncTask[]>([])
  const [loading, setLoading] = useState(false)
  const [itemModalOpen, setItemModalOpen] = useState(false)
  const [categoryModalOpen, setCategoryModalOpen] = useState(false)
  const [sourceModalOpen, setSourceModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<MediaWallItem | null>(null)
  const [editingCategory, setEditingCategory] = useState<MediaWallCategory | null>(null)
  const [editingSource, setEditingSource] = useState<MediaWallSource | null>(null)
  const [importPreview, setImportPreview] = useState<MediaWallImportPreview | null>(null)
  const [importCategoryIds, setImportCategoryIds] = useState<number[]>([])
  const [importVisibility, setImportVisibility] = useState('draft')
  const [itemCategoryFilter, setItemCategoryFilter] = useState<number | undefined>()
  const [selectedItemKeys, setSelectedItemKeys] = useState<number[]>([])
  const [itemForm] = Form.useForm<ItemFormValues>()
  const [categoryForm] = Form.useForm<CategoryFormValues>()
  const [sourceForm] = Form.useForm<SourceFormValues>()

  const loadData = async (categoryId = itemCategoryFilter) => {
    setLoading(true)
    try {
      const [categoryData, itemData, sourceData, taskData] = await Promise.all([
        getMediaWallCategories(),
        getMediaWallItems({ category_id: categoryId }),
        getMediaWallSources(),
        getMediaWallSyncTasks(),
      ])
      setCategories(categoryData)
      setItems(itemData)
      setSources(sourceData)
      setSyncTasks(taskData)
      setSelectedItemKeys((current) => current.filter((itemId) => itemData.some((item) => item.id === itemId)))
    } catch (error: unknown) {
      message.error(getRequestErrorMessage(error, '影视墙数据加载失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadData() }, [])

  const categoryOptions = useMemo(() => categories.filter((category) => category.is_enabled).map((category) => ({ label: category.name, value: category.id })), [categories])
  const categoryFilterOptions = useMemo(() => categories.map((category) => ({ label: category.name, value: category.id })), [categories])
  const syncTaskOptions = useMemo(() => syncTasks.map((task) => ({ label: `${task.work_title || task.topic_title} · ${task.progress.label}`, value: task.id })), [syncTasks])

  const openItemModal = (item?: MediaWallItem) => {
    setEditingItem(item || null)
    itemForm.setFieldsValue(item ? {
      display_title: item.display_title,
      metadata_query_title: item.metadata_query_title || undefined,
      visibility: item.visibility,
      sort_order: item.sort_order,
      category_ids: item.categories.map((category) => category.id),
      sync_task_id: item.sync_task_id || undefined,
      custom_poster_url: item.poster_url || undefined,
      links_text: item.links.map((link) => `${link.url}\t${link.label || ''}`).join('\n'),
    } : {
      display_title: '', metadata_query_title: undefined, visibility: 'draft', sort_order: 0, category_ids: [], sync_task_id: undefined, custom_poster_url: '', links_text: '',
    })
    setItemModalOpen(true)
  }

  const submitItem = async (values: ItemFormValues) => {
    const payload = {
      display_title: values.display_title,
      metadata_query_title: values.metadata_query_title || null,
      visibility: values.visibility,
      sort_order: values.sort_order || 0,
      category_ids: values.category_ids || [],
      sync_task_id: values.sync_task_id || null,
      custom_poster_url: values.custom_poster_url || null,
    }
    try {
      const item = editingItem ? await updateMediaWallItem(editingItem.id, payload) : await createMediaWallItem({ ...payload, links: parseLinks(values.links_text) })
      if (editingItem) {
        const newLinks = parseLinks(values.links_text).filter((link) => !editingItem.links.some((existing) => existing.url === link.url))
        for (const link of newLinks) await addMediaWallLink(item.id, link)
      }
      message.success(editingItem ? '影视条目已更新' : '影视条目已创建')
      setItemModalOpen(false)
      await loadData()
    } catch (error: unknown) {
      message.error(getRequestErrorMessage(error, '保存影视条目失败'))
    }
  }

  const openCategoryModal = (category?: MediaWallCategory) => {
    setEditingCategory(category || null)
    categoryForm.setFieldsValue(category || { name: '', slug: '', sort_order: 0, is_enabled: true })
    setCategoryModalOpen(true)
  }

  const submitCategory = async (values: CategoryFormValues) => {
    try {
      if (editingCategory) await updateMediaWallCategory(editingCategory.id, values)
      else await createMediaWallCategory(values)
      message.success('分类已保存')
      setCategoryModalOpen(false)
      await loadData()
    } catch (error: unknown) {
      message.error(getRequestErrorMessage(error, '保存分类失败'))
    }
  }

  const handleDeleteItems = async (itemIds: number[]) => {
    const normalizedIds = [...new Set(itemIds.map(Number).filter((itemId) => itemId > 0))]
    if (normalizedIds.length === 0) return
    try {
      if (normalizedIds.length === 1) {
        await deleteMediaWallItem(normalizedIds[0])
      } else {
        await deleteMediaWallItems(normalizedIds)
      }
      setSelectedItemKeys((current) => current.filter((itemId) => !normalizedIds.includes(itemId)))
      message.success(`已删除 ${normalizedIds.length} 个影视条目`)
      await loadData(itemCategoryFilter)
    } catch (error: unknown) {
      message.error(getRequestErrorMessage(error, '删除影视条目失败'))
    }
  }

  const openSourceModal = (source?: MediaWallSource) => {
    setEditingSource(source || null)
    sourceForm.setFieldsValue(source || { name: '', source_url: '', source_type: 'source-list', is_enabled: true, priority: 100, timeout_seconds: 8 })
    setSourceModalOpen(true)
  }

  const submitSource = async (values: SourceFormValues) => {
    try {
      if (editingSource) await updateMediaWallSource(editingSource.id, values)
      else await createMediaWallSource(values)
      message.success('采集源已保存')
      setSourceModalOpen(false)
      await loadData()
    } catch (error: unknown) {
      message.error(getRequestErrorMessage(error, '保存采集源失败'))
    }
  }

  const uploadProps: UploadProps = {
    accept: '.txt,.xlsx,.xlsm',
    showUploadList: false,
    beforeUpload: async (file) => {
      try {
        setImportPreview(await previewMediaWallImport(file))
        message.success('文件解析完成，请确认预览内容')
      } catch (error: unknown) {
        message.error(getRequestErrorMessage(error, '文件解析失败'))
      }
      return false
    },
  }

  const itemColumns = [
    { title: '影视名称', dataIndex: 'display_title', render: (value: string, item: MediaWallItem) => <div><strong>{value}</strong><div className="media-wall-admin-subtitle">{item.progress.label}</div></div> },
    { title: '分类', dataIndex: 'categories', render: (value: MediaWallCategory[]) => <Space wrap>{value.map((category) => <Tag key={category.id}>{category.name}</Tag>)}</Space> },
    { title: '链接', dataIndex: 'link_count', width: 80, render: (value: number) => `${value} 个` },
    { title: '状态', dataIndex: 'visibility', width: 90, render: (value: string) => <Tag color={value === 'public' ? 'green' : value === 'hidden' ? 'default' : 'gold'}>{value === 'public' ? '公开' : value === 'hidden' ? '隐藏' : '草稿'}</Tag> },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, item: MediaWallItem) => (
        <Space>
          <Button type="text" icon={<EditOutlined />} onClick={() => openItemModal(item)}>编辑</Button>
          <Popconfirm
            title="确认删除这个影视条目吗？"
            description="删除后会同时移除分类关联和网盘入口，影视墙将不再显示。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => void handleDeleteItems([item.id])}
          >
            <Button type="text" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const categoryColumns = [
    { title: '分类', dataIndex: 'name' },
    { title: '路径', dataIndex: 'slug' },
    { title: '排序', dataIndex: 'sort_order' },
    { title: '状态', dataIndex: 'is_enabled', render: (value: boolean) => value ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
    { title: '操作', key: 'action', render: (_: unknown, category: MediaWallCategory) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openCategoryModal(category)}>编辑</Button><Button type="text" danger onClick={() => void disableMediaWallCategory(category.id).then(() => loadData())}>停用</Button></Space> },
  ]

  const sourceColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '地址', dataIndex: 'source_url', ellipsis: true },
    { title: '优先级', dataIndex: 'priority' },
    { title: '状态', dataIndex: 'is_enabled', render: (value: boolean) => value ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
    { title: '最近错误', dataIndex: 'last_error_message', ellipsis: true, render: (value?: string | null) => value || '无' },
    { title: '操作', key: 'action', render: (_: unknown, source: MediaWallSource) => <Space><Button type="text" icon={<EditOutlined />} onClick={() => openSourceModal(source)}>编辑</Button><Button type="text" icon={<SafetyOutlined />} onClick={() => void testMediaWallSource(source.id).then((result) => { message[result.ok ? 'success' : 'error'](result.ok ? `测试成功，发现 ${result.endpoint_count} 个接口` : result.error || '采集源测试失败'); void loadData() })}>测试</Button></Space> },
  ]

  return (
    <div className="media-wall-admin-panel">
      <Tabs
        className="media-wall-admin-tabs"
        tabBarExtraContent={<Button icon={<ReloadOutlined />} onClick={() => void loadData()} loading={loading}>刷新</Button>}
        items={[
          {
            key: 'items',
            label: '影视条目',
            children: (
              <Card
                className="resource-ops-panel-card media-wall-admin-card"
                extra={
                  <Space wrap>
                    <Select
                      allowClear
                      placeholder="按分类筛选"
                      value={itemCategoryFilter}
                      options={categoryFilterOptions}
                      onChange={(value) => {
                        setItemCategoryFilter(value)
                        setSelectedItemKeys([])
                        void loadData(value)
                      }}
                      style={{ minWidth: 160 }}
                    />
                    <Popconfirm
                      title={`确认删除已选的 ${selectedItemKeys.length} 个影视条目吗？`}
                      description="删除后会同时移除分类关联和网盘入口，影视墙将不再显示。"
                      okText="批量删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      disabled={selectedItemKeys.length === 0}
                      onConfirm={() => void handleDeleteItems(selectedItemKeys)}
                    >
                      <Button danger icon={<DeleteOutlined />} disabled={selectedItemKeys.length === 0}>
                        批量删除{selectedItemKeys.length > 0 ? ` (${selectedItemKeys.length})` : ''}
                      </Button>
                    </Popconfirm>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => openItemModal()}>添加影视</Button>
                  </Space>
                }
              >
                <Table
                  rowKey="id"
                  loading={loading}
                  columns={itemColumns}
                  dataSource={items}
                  rowSelection={{ selectedRowKeys: selectedItemKeys, onChange: (keys) => setSelectedItemKeys(keys.map(Number)) }}
                  pagination={{ pageSize: 10 }}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无影视条目" /> }}
                />
              </Card>
            ),
          },
          { key: 'categories', label: '分类管理', children: <Card className="resource-ops-panel-card media-wall-admin-card" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openCategoryModal()}>添加分类</Button>}><Table rowKey="id" loading={loading} columns={categoryColumns} dataSource={categories} pagination={false} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无分类" /> }} /></Card> },
          { key: 'sources', label: '采集源', children: <Card className="resource-ops-panel-card media-wall-admin-card" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openSourceModal()}>添加采集源</Button>}><Table rowKey="id" loading={loading} columns={sourceColumns} dataSource={sources} pagination={false} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无采集源" /> }} /></Card> },
          { key: 'import', label: '批量导入', children: <Card className="resource-ops-panel-card media-wall-admin-card"><Upload {...uploadProps}><Button icon={<UploadOutlined />}>选择 TXT / XLSX 文件</Button></Upload>{importPreview ? <div className="media-wall-import-preview"><Alert type="info" showIcon message={`解析 ${importPreview.total_records} 条影视，${importPreview.total_links} 个链接，${importPreview.invalid_count} 行异常`} /><div className="media-wall-import-toolbar"><Select mode="multiple" allowClear placeholder="导入到分类" value={importCategoryIds} options={categoryOptions} onChange={setImportCategoryIds} /><Select value={importVisibility} options={[{ label: '导入为草稿', value: 'draft' }, { label: '直接公开', value: 'public' }]} onChange={setImportVisibility} /><Button type="primary" onClick={() => void confirmMediaWallImport(importPreview.id, { category_ids: importCategoryIds, visibility: importVisibility }).then(() => { message.success('导入已确认'); setImportPreview(null); void loadData() }).catch((error: unknown) => message.error(getRequestErrorMessage(error, '确认导入失败')))}>确认导入</Button></div><Table rowKey="display_title" size="small" pagination={{ pageSize: 8 }} dataSource={importPreview.records} columns={[{ title: '影视名称', dataIndex: 'display_title' }, { title: '链接', dataIndex: 'links', render: (links: Array<{ platform: string }>) => links.map((link) => <Tag key={link.platform}>{link.platform}</Tag>) }]} /></div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择文件后先预览，再确认写入影视墙" />}</Card> },
        ]}
      />

      <Modal open={itemModalOpen} title={editingItem ? '编辑影视条目' : '添加影视条目'} okText="保存" cancelText="取消" onOk={() => itemForm.submit()} onCancel={() => setItemModalOpen(false)} width={720} destroyOnClose>
        <Form form={itemForm} layout="vertical" onFinish={(values) => void submitItem(values)}>
          <div className="media-wall-form-grid"><Form.Item name="display_title" label="前台显示名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="metadata_query_title" label="资料查询名称"><Input placeholder="默认使用显示名称" /></Form.Item></div>
          <div className="media-wall-form-grid"><Form.Item name="visibility" label="公开状态"><Select options={[{ label: '草稿', value: 'draft' }, { label: '公开', value: 'public' }, { label: '隐藏', value: 'hidden' }]} /></Form.Item><Form.Item name="sort_order" label="排序"><InputNumber className="media-wall-full-width" /></Form.Item></div>
          <div className="media-wall-form-grid"><Form.Item name="category_ids" label="分类"><Select mode="multiple" options={categoryOptions} /></Form.Item><Form.Item name="sync_task_id" label="绑定追更任务"><Select allowClear showSearch optionFilterProp="label" options={syncTaskOptions} /></Form.Item></div>
          <Form.Item name="custom_poster_url" label="人工海报地址"><Input placeholder="可选，优先于采集源海报" /></Form.Item>
          <Form.Item name="links_text" label="网盘链接"><Input.TextArea rows={4} placeholder="每行一个链接；可用 Tab 或 | 添加备注" /></Form.Item>
        </Form>
      </Modal>
      <Modal open={categoryModalOpen} title={editingCategory ? '编辑分类' : '添加分类'} okText="保存" cancelText="取消" onOk={() => categoryForm.submit()} onCancel={() => setCategoryModalOpen(false)} destroyOnClose>
        <Form form={categoryForm} layout="vertical" onFinish={(values) => void submitCategory(values)}><Form.Item name="name" label="分类名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="slug" label="访问路径"><Input placeholder="可选，自动生成" /></Form.Item><div className="media-wall-form-grid"><Form.Item name="sort_order" label="排序"><InputNumber className="media-wall-full-width" /></Form.Item><Form.Item name="is_enabled" label="分类启用" valuePropName="checked"><Switch /></Form.Item></div></Form>
      </Modal>
      <Modal open={sourceModalOpen} title={editingSource ? '编辑采集源' : '添加采集源'} okText="保存" cancelText="取消" onOk={() => sourceForm.submit()} onCancel={() => setSourceModalOpen(false)} destroyOnClose>
        <Form form={sourceForm} layout="vertical" onFinish={(values) => void submitSource(values)}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="source_url" label="源地址" rules={[{ required: true, type: 'url' }]}><Input /></Form.Item><div className="media-wall-form-grid"><Form.Item name="source_type" label="类型"><Select options={[{ label: 'LibreTV / SourceList', value: 'source-list' }, { label: 'TVBox', value: 'tvbox' }, { label: 'Apple CMS API', value: 'apple-cms' }]} /></Form.Item><Form.Item name="priority" label="优先级"><InputNumber className="media-wall-full-width" min={0} /></Form.Item></div><div className="media-wall-form-grid"><Form.Item name="timeout_seconds" label="超时秒数"><InputNumber className="media-wall-full-width" min={2} max={20} /></Form.Item><Form.Item name="is_enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></div></Form>
      </Modal>
    </div>
  )
}

export default MediaWallAdminPanel
