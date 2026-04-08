import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  BarChartOutlined,
  DeleteOutlined,
  DeploymentUnitOutlined,
  GlobalOutlined,
  LayoutOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { getSystemConfig, updateSystemConfig } from '@/api/admin'
import HintTooltip from '@/components/common/HintTooltip'
import SiteFooter from '@/components/layout/SiteFooter'
import type { FooterBuilderSection, SystemConfigResponse, SystemConfigUpdate } from '@/types/admin'
import './SystemConfigModern.css'

const { Text, Title } = Typography
const { TextArea } = Input

const SECTION_ITEMS = [
  { id: 'system-config-brand', label: '站点信息' },
  { id: 'system-config-footer', label: '页脚布局' },
  { id: 'system-config-access', label: '访问控制' },
  { id: 'system-config-analytics', label: '流量分析' },
  { id: 'system-config-ads', label: '广告位' },
  { id: 'system-config-link-check', label: '链接检测' },
  { id: 'system-config-monitor', label: '监控运行' },
  { id: 'system-config-timing', label: '生效节奏' },
]

const scrollToSection = (id: string) => {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const createFooterSectionId = () => `footer-section-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

const createEmptyFooterSection = (): FooterBuilderSection => ({
  id: createFooterSectionId(),
  title: '',
  html: '',
  span: 3,
})

const hasFooterSectionContent = (section: FooterBuilderSection) =>
  section.title.trim() || section.html.trim()

const normalizeFooterSectionsForEditor = (sections: FooterBuilderSection[]) =>
  sections.filter(hasFooterSectionContent)

const createLabel = (title: string, hint: string) => (
  <div className="system-config-modern-field-label">
    <Text strong>{title}</Text>
    <HintTooltip content={hint} />
  </div>
)

const createSectionTitle = (title: string, hint: string, extra?: ReactNode) => (
  <div className="system-config-modern-section-heading">
    <div className="system-config-modern-section-heading-main">
      <span className="system-config-modern-section-title-text">{title}</span>
      <HintTooltip content={hint} />
    </div>
    {extra}
  </div>
)

type OverviewChipTone = 'accent' | 'success' | 'neutral' | 'warning'

type OverviewChip = {
  label: string
  tone: OverviewChipTone
}

type OverviewItem = {
  key: string
  icon: ReactNode
  title: string
  status: string
  live: boolean
  meta: OverviewChip[]
}

const SystemConfigModern = () => {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [config, setConfig] = useState<SystemConfigResponse | null>(null)
  const [draft, setDraft] = useState<SystemConfigUpdate | null>(null)

  useEffect(() => {
    void loadConfig()
  }, [])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await getSystemConfig()
      const normalizedData = {
        ...data,
        footer_builder_sections: normalizeFooterSectionsForEditor(data.footer_builder_sections),
      }
      setConfig(normalizedData)
      setDraft(normalizedData)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载系统配置失败')
    } finally {
      setLoading(false)
    }
  }

  const updateDraft = <K extends keyof SystemConfigUpdate>(key: K, value: SystemConfigUpdate[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const isDirty = useMemo(() => {
    if (!config || !draft) {
      return false
    }
    return JSON.stringify(config) !== JSON.stringify(draft)
  }, [config, draft])

  const hasConcurrencyError =
    !!draft && draft.link_check_default_max_concurrent > draft.link_check_max_allowed_concurrent
  const hasUmamiConfigError =
    !!draft && draft.umami_enabled && (!draft.umami_script_url.trim() || !draft.umami_website_id.trim())
  const saveDisabled = !isDirty || hasConcurrencyError || hasUmamiConfigError

  const handleReset = () => {
    if (!config) {
      return
    }
    setDraft({
      ...config,
      footer_builder_sections: normalizeFooterSectionsForEditor(config.footer_builder_sections),
    })
  }

  const handleSave = async () => {
    if (!draft) {
      return
    }
    if (hasConcurrencyError) {
      message.error('链接检测默认并发不能大于系统允许的最大并发')
      return
    }
    if (hasUmamiConfigError) {
      message.error('启用 Umami 时必须填写脚本地址和 Website ID')
      return
    }

    setSaving(true)
    try {
      const normalizedDraft = {
        ...draft,
        footer_builder_sections: normalizeFooterSectionsForEditor(draft.footer_builder_sections),
      }
      const updated = await updateSystemConfig(normalizedDraft)
      const normalizedUpdated = {
        ...updated,
        footer_builder_sections: normalizeFooterSectionsForEditor(updated.footer_builder_sections),
      }
      setConfig(normalizedUpdated)
      setDraft(normalizedUpdated)
      window.dispatchEvent(new CustomEvent<SystemConfigResponse>('tg-system-config-updated', { detail: normalizedUpdated }))
      message.success('系统配置已保存')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新系统配置失败')
    } finally {
      setSaving(false)
    }
  }

  if (!draft || !config) {
    return <Card loading={loading}>加载中...</Card>
  }

  const updateFooterSection = (
    sectionId: string,
    key: keyof FooterBuilderSection,
    value: FooterBuilderSection[keyof FooterBuilderSection]
  ) => {
    updateDraft(
      'footer_builder_sections',
      draft.footer_builder_sections.map((section) =>
        section.id === sectionId ? { ...section, [key]: value } : section
      )
    )
  }

  const addFooterSection = () => {
    updateDraft('footer_builder_sections', [...draft.footer_builder_sections, createEmptyFooterSection()])
  }

  const removeFooterSection = (sectionId: string) => {
    updateDraft(
      'footer_builder_sections',
      draft.footer_builder_sections.filter((section) => section.id !== sectionId)
    )
  }

  const moveFooterSection = (sectionId: string, direction: -1 | 1) => {
    const currentIndex = draft.footer_builder_sections.findIndex((section) => section.id === sectionId)
    if (currentIndex < 0) {
      return
    }

    const targetIndex = currentIndex + direction
    if (targetIndex < 0 || targetIndex >= draft.footer_builder_sections.length) {
      return
    }

    const nextSections = [...draft.footer_builder_sections]
    const [current] = nextSections.splice(currentIndex, 1)
    nextSections.splice(targetIndex, 0, current)
    updateDraft('footer_builder_sections', nextSections)
  }

  const overviewItems: OverviewItem[] = [
    {
      key: 'branding',
      icon: <GlobalOutlined />,
      title: '站点',
      status: draft.site_name.trim() || '未命名',
      live: Boolean(draft.site_name.trim()),
      meta: [
        { label: draft.site_favicon_url ? 'favicon' : '无 favicon', tone: draft.site_favicon_url ? 'success' : 'neutral' },
        { label: draft.brand_icon.trim() ? '标题图标' : '无图标', tone: draft.brand_icon.trim() ? 'accent' : 'neutral' },
      ],
    },
    {
      key: 'public',
      icon: <TeamOutlined />,
      title: '游客',
      status: draft.public_dashboard_enabled ? '已开放' : '已关闭',
      live: draft.public_dashboard_enabled,
      meta: [
        { label: draft.public_dashboard_enabled ? '游客可见' : '仅登录', tone: draft.public_dashboard_enabled ? 'accent' : 'neutral' },
        { label: draft.public_ads_enabled ? '广告开启' : '广告关闭', tone: draft.public_ads_enabled ? 'success' : 'neutral' },
      ],
    },
    {
      key: 'footer',
      icon: <LayoutOutlined />,
      title: '页脚',
      status: draft.footer_builder_enabled ? `${draft.footer_builder_sections.length} 栏` : '已关闭',
      live: draft.footer_builder_enabled,
      meta: [
        { label: draft.footer_builder_enabled ? 'HTML 布局' : '未启用', tone: draft.footer_builder_enabled ? 'accent' : 'neutral' },
        { label: draft.footer_builder_bottom_html.trim() ? '含底栏' : '仅栏目', tone: draft.footer_builder_bottom_html.trim() ? 'success' : 'neutral' },
      ],
    },
    {
      key: 'analytics',
      icon: <BarChartOutlined />,
      title: '流量',
      status: draft.umami_enabled ? 'Umami' : '未启用',
      live: draft.umami_enabled,
      meta: [
        { label: draft.umami_script_url.trim() ? '脚本' : '缺脚本', tone: draft.umami_script_url.trim() ? 'success' : 'neutral' },
        { label: draft.umami_website_id.trim() ? 'Website ID' : '缺 ID', tone: draft.umami_website_id.trim() ? 'success' : 'warning' },
        { label: draft.umami_share_url.trim() ? '看板' : '无看板', tone: draft.umami_share_url.trim() ? 'accent' : 'neutral' },
      ],
    },
    {
      key: 'link-check',
      icon: <LinkOutlined />,
      title: '检测',
      status: `${draft.link_check_default_max_concurrent}/${draft.link_check_max_allowed_concurrent}`,
      live: !hasConcurrencyError,
      meta: [
        { label: `${draft.link_check_max_allowed_links} 链接`, tone: 'accent' },
        { label: `${draft.link_check_poll_interval_seconds}s 轮询`, tone: 'neutral' },
      ],
    },
    {
      key: 'monitor',
      icon: <DeploymentUnitOutlined />,
      title: '监控',
      status: `${draft.monitor_channel_refresh_interval_seconds} 秒`,
      live: true,
      meta: [
        { label: `${draft.monitor_db_write_max_retries} 次重试`, tone: 'accent' },
        { label: `${draft.monitor_db_write_retry_delay_seconds}s 间隔`, tone: 'neutral' },
      ],
    },
  ]

  return (
    <div className="system-config-modern-page">
      <section className="system-config-modern-hero">
        <div className="system-config-modern-heading">
          <Title level={4} className="system-config-modern-title">
            系统配置
          </Title>
          <div className="system-config-modern-status-row">
            <Tag color={isDirty ? 'gold' : 'success'}>{isDirty ? '有未保存修改' : '配置已同步'}</Tag>
            <Tag color={draft.umami_enabled ? 'cyan' : 'default'}>{draft.umami_enabled ? 'Umami 已启用' : 'Umami 未启用'}</Tag>
            <Tag color={draft.public_dashboard_enabled ? 'processing' : 'default'}>
              {draft.public_dashboard_enabled ? '游客模式开启' : '游客模式关闭'}
            </Tag>
          </div>
        </div>

        <div className="system-config-modern-actions" role="group" aria-label="系统配置操作">
          <Button icon={<ReloadOutlined />} onClick={() => void loadConfig()} loading={loading || saving}>
            重新加载
          </Button>
          <Button onClick={handleReset} disabled={!isDirty || saving}>
            撤销修改
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={() => void handleSave()}
            loading={saving}
            disabled={saveDisabled}
          >
            保存配置
          </Button>
        </div>
      </section>

      <section className="system-config-modern-overview-grid">
        {overviewItems.map((item) => (
          <article
            className={`system-config-modern-overview-card ${item.live ? 'is-live' : 'is-idle'}`}
            key={item.key}
          >
            <div className="system-config-modern-overview-icon-shell">
              <div className="system-config-modern-overview-icon">{item.icon}</div>
            </div>
            <div className="system-config-modern-overview-content">
              <div className="system-config-modern-overview-title-row">
                <span className={`system-config-modern-overview-dot ${item.live ? 'is-live' : 'is-idle'}`} />
                <div className="system-config-modern-overview-title">{item.title}</div>
              </div>
              <div className="system-config-modern-overview-status-row">
                <div className="system-config-modern-overview-status">{item.status}</div>
              </div>
              <div className="system-config-modern-overview-meta-row">
                {item.meta.map((chip) => (
                  <span
                    className={`system-config-modern-overview-meta is-${chip.tone}`}
                    key={`${item.key}-${chip.label}`}
                  >
                    {chip.label}
                  </span>
                ))}
              </div>
            </div>
          </article>
        ))}
      </section>

      <nav className="system-config-modern-quick-nav" aria-label="快速定位配置区块">
        {SECTION_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className="system-config-modern-quick-nav-button"
            onClick={() => scrollToSection(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="system-config-modern-sections">
        <section id="system-config-brand" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle('站点信息', '配置站点名称、浏览器标题、描述、关键词、图标与 favicon，保存后刷新页面即可看到新的品牌形象。')}
          >
            <div className="system-config-modern-field-grid">
              <div className="system-config-modern-field-card">
                {createLabel('站点名称', '用于前台页头、游客页和登录页的品牌名称。')}
                <Input
                  value={draft.site_name}
                  onChange={(event) => updateDraft('site_name', event.target.value)}
                  placeholder="TG频道监控"
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('站点标题', '用于浏览器标签页标题，也会作为默认 SEO 标题。')}
                <Input
                  value={draft.site_title}
                  onChange={(event) => updateDraft('site_title', event.target.value)}
                  placeholder="TG频道监控"
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('标题图标', '显示在站点名称前，适合使用单个 emoji 或极短字符。')}
                <Input
                  value={draft.brand_icon}
                  onChange={(event) => updateDraft('brand_icon', event.target.value)}
                  placeholder="📱"
                  maxLength={32}
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('Favicon', '浏览器地址栏和标签页使用的小图标，支持站内相对路径或完整 URL。')}
                <Input
                  value={draft.site_favicon_url}
                  onChange={(event) => updateDraft('site_favicon_url', event.target.value)}
                  placeholder="/favicon.svg"
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card system-config-modern-field-card--wide">
                {createLabel('站点描述', '写给搜索引擎和分享卡片的简介文案，也会用于 meta description。')}
                <TextArea
                  rows={3}
                  value={draft.site_description}
                  onChange={(event) => updateDraft('site_description', event.target.value)}
                  placeholder="Telegram 频道网盘资源监控与检索"
                  className="system-config-modern-textarea"
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card system-config-modern-field-card--wide">
                {createLabel('关键词', '用于 SEO 的关键词集合，建议使用逗号分隔。')}
                <TextArea
                  rows={3}
                  value={draft.site_keywords}
                  onChange={(event) => updateDraft('site_keywords', event.target.value)}
                  placeholder="telegram,网盘,频道监控,资源搜索"
                  className="system-config-modern-textarea"
                  disabled={saving}
                />
              </div>
            </div>
          </Card>
        </section>

        <section id="system-config-footer" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle(
              '页脚布局',
              '按栏目方式配置前台页脚。每栏可自定义标题、HTML 内容和宽度占比，底栏也支持独立 HTML。'
            )}
          >
            <div className="system-config-modern-footer-builder">
              <div className="system-config-modern-footer-builder-main">
                <div className="system-config-modern-footer-builder-toolbar">
                  <div className="system-config-modern-toggle-card system-config-modern-toggle-card--compact">
                    <div className="system-config-modern-toggle-copy">
                      {createLabel('启用页脚', '关闭后前台不渲染页脚；已编辑的栏目内容会继续保留在配置里。')}
                    </div>
                    <Switch
                      checked={draft.footer_builder_enabled}
                      onChange={(checked) => updateDraft('footer_builder_enabled', checked)}
                      disabled={saving}
                    />
                  </div>

                  <Button type="primary" icon={<PlusOutlined />} onClick={addFooterSection} disabled={saving}>
                    新增栏目
                  </Button>
                </div>

                {draft.footer_builder_sections.length ? (
                  <div className="system-config-modern-footer-section-list">
                    {draft.footer_builder_sections.map((section, index) => (
                      <article className="system-config-modern-footer-section-card" key={section.id}>
                        <div className="system-config-modern-footer-section-head">
                          <div className="system-config-modern-footer-section-meta">
                            <Tag color="processing">栏目 {index + 1}</Tag>
                            <span>{section.span}/12</span>
                          </div>
                          <div className="system-config-modern-footer-section-actions">
                            <Button
                              type="text"
                              size="small"
                              icon={<ArrowUpOutlined />}
                              onClick={() => moveFooterSection(section.id, -1)}
                              disabled={saving || index === 0}
                            />
                            <Button
                              type="text"
                              size="small"
                              icon={<ArrowDownOutlined />}
                              onClick={() => moveFooterSection(section.id, 1)}
                              disabled={saving || index === draft.footer_builder_sections.length - 1}
                            />
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={() => removeFooterSection(section.id)}
                              disabled={saving}
                            />
                          </div>
                        </div>

                        <div className="system-config-modern-footer-section-grid">
                          <div className="system-config-modern-footer-section-field">
                            {createLabel('标题', '支持留空。留空时该栏目只显示 HTML 内容。')}
                            <Input
                              value={section.title}
                              onChange={(event) => updateFooterSection(section.id, 'title', event.target.value)}
                              placeholder="例如：友情链接"
                              disabled={saving}
                            />
                          </div>

                          <div className="system-config-modern-footer-section-field">
                            {createLabel('宽度占比', '桌面端按 12 栅格布局；移动端会自动改成单列堆叠。')}
                            <InputNumber
                              min={1}
                              max={12}
                              value={section.span}
                              onChange={(value) => updateFooterSection(section.id, 'span', Number(value || 3))}
                              addonAfter="/12"
                              disabled={saving}
                            />
                          </div>
                        </div>

                        <div className="system-config-modern-footer-section-field">
                          {createLabel('HTML 内容', '支持完整 HTML，也支持 {{current_year}}、{{site_name}} 这类变量。')}
                          <TextArea
                            rows={6}
                            value={section.html}
                            onChange={(event) => updateFooterSection(section.id, 'html', event.target.value)}
                            placeholder='<p><a href="https://example.com">示例链接</a></p>'
                            className="system-config-modern-textarea"
                            disabled={saving}
                          />
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="system-config-modern-footer-empty">
                    <Empty description="还没有页脚栏目，点击“新增栏目”开始配置" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </div>
                )}

                <div className="system-config-modern-field-card system-config-modern-field-card--wide">
                  {createLabel('底栏 HTML', '显示在栏目区下方，支持 HTML，也支持 {{current_year}}、{{site_name}} 变量。')}
                  <TextArea
                    rows={5}
                    value={draft.footer_builder_bottom_html}
                    onChange={(event) => updateDraft('footer_builder_bottom_html', event.target.value)}
                    placeholder='<p>Copyright © 2026 示例站点</p>'
                    className="system-config-modern-textarea"
                    disabled={saving}
                  />
                </div>
              </div>

              <aside className="system-config-modern-footer-preview-panel">
                <div className="system-config-modern-footer-preview-head">
                  <div className="system-config-modern-footer-preview-title">
                    <Text strong>实时预览</Text>
                    <HintTooltip content="预览区域使用和前台一致的页脚渲染组件，移动端会自动改成纵向堆叠。" />
                  </div>
                  <Tag color={draft.footer_builder_enabled ? 'success' : 'default'}>
                    {draft.footer_builder_enabled ? '已启用' : '未启用'}
                  </Tag>
                </div>
                <div className="system-config-modern-footer-preview">
                  <SiteFooter config={draft} preview />
                </div>
              </aside>
            </div>
          </Card>
        </section>

        <section id="system-config-access" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle('访问控制', '控制未登录访客是否可以直接查看公开消息流。')}
          >
            <div className="system-config-modern-toggle-card">
              <div className="system-config-modern-toggle-copy">
                {createLabel('允许未登录用户访问消息列表', '开启后，游客可直接访问首页消息流和公开统计页；后台管理依然需要登录。')}
              </div>
              <Switch
                checked={draft.public_dashboard_enabled}
                onChange={(checked) => updateDraft('public_dashboard_enabled', checked)}
                disabled={saving}
              />
            </div>
          </Card>
        </section>

        <section id="system-config-analytics" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle('流量分析', '配置 Umami 追踪脚本、Website ID 与可选的分享看板链接。', <Tag color="cyan">Umami</Tag>)}
          >
            <div className="system-config-modern-toggle-card">
              <div className="system-config-modern-toggle-copy">
                {createLabel('启用站点流量统计', '保存后前台会注入 Umami 脚本，页面访问与业务事件会开始上报到 Umami。')}
              </div>
              <Switch checked={draft.umami_enabled} onChange={(checked) => updateDraft('umami_enabled', checked)} disabled={saving} />
            </div>

            <div className="system-config-modern-field-grid">
              <div className="system-config-modern-field-card">
                {createLabel('脚本地址', '通常为 Umami 的 script.js 地址，例如官方云的 https://cloud.umami.is/script.js。')}
                <Input
                  value={draft.umami_script_url}
                  onChange={(event) => updateDraft('umami_script_url', event.target.value)}
                  placeholder="https://analytics.example.com/script.js"
                  status={draft.umami_enabled && !draft.umami_script_url.trim() ? 'error' : undefined}
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('Website ID', 'Umami 后台为每个网站生成的唯一标识，用于区分不同站点的数据。')}
                <Input
                  value={draft.umami_website_id}
                  onChange={(event) => updateDraft('umami_website_id', event.target.value)}
                  placeholder="9d2d1f8f-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  status={draft.umami_enabled && !draft.umami_website_id.trim() ? 'error' : undefined}
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('Host URL', '可选，用于代理 Umami 上报地址或使用自定义采集入口。')}
                <Input
                  value={draft.umami_host_url}
                  onChange={(event) => updateDraft('umami_host_url', event.target.value)}
                  placeholder="https://analytics.example.com"
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('分享看板链接', '配置后“数据分析”页可直接打开或嵌入 Umami 分享看板。')}
                <Input
                  value={draft.umami_share_url}
                  onChange={(event) => updateDraft('umami_share_url', event.target.value)}
                  placeholder="https://analytics.example.com/share/xxxx"
                  disabled={saving}
                />
              </div>
            </div>

            {hasUmamiConfigError && (
              <Alert
                className="system-config-modern-inline-alert"
                type="error"
                showIcon
                message="Umami 配置不完整"
                description="启用站点流量统计时，至少需要填写脚本地址和 Website ID。"
              />
            )}
          </Card>
        </section>

        <section id="system-config-ads" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle('广告位', '管理游客消息页顶部广告和信息流插播广告。', <Tag color="processing">游客页</Tag>)}
          >
            <div className="system-config-modern-field-grid">
              <div className="system-config-modern-field-card system-config-modern-field-card--wide">
                <div className="system-config-modern-inline-row">
                  <div className="system-config-modern-toggle-copy">
                    {createLabel('启用游客页广告', '开启后，广告只在游客消息页出现，不影响后台与登录用户界面。')}
                  </div>
                  <Switch
                    checked={draft.public_ads_enabled}
                    onChange={(checked) => updateDraft('public_ads_enabled', checked)}
                    disabled={saving}
                  />
                </div>
              </div>

              <div className="system-config-modern-ad-card">
                <div className="system-config-modern-ad-card-head">
                  <div className="system-config-modern-ad-card-head-copy">
                    {createLabel('顶部广告', '显示在消息总数提示下方，适合横幅类素材。')}
                  </div>
                  <span className="system-config-modern-ad-card-badge">横幅位</span>
                </div>
                <div className="system-config-modern-ad-code-group">
                  {createLabel('桌面端 HTML', '桌面端优先使用的广告 HTML 代码，留空时会回退到移动端代码。')}
                  <TextArea
                    rows={5}
                    value={draft.public_feed_top_ad_html_desktop}
                    onChange={(event) => updateDraft('public_feed_top_ad_html_desktop', event.target.value)}
                    placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                    className="system-config-modern-textarea"
                    allowClear
                    disabled={saving}
                  />
                </div>
                <div className="system-config-modern-ad-code-group">
                  {createLabel('移动端 HTML', '移动端优先使用的广告 HTML 代码，留空时会回退到桌面端代码。')}
                  <TextArea
                    rows={4}
                    value={draft.public_feed_top_ad_html_mobile}
                    onChange={(event) => updateDraft('public_feed_top_ad_html_mobile', event.target.value)}
                    placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                    className="system-config-modern-textarea"
                    allowClear
                    disabled={saving}
                  />
                </div>
              </div>

              <div className="system-config-modern-ad-card">
                <div className="system-config-modern-ad-card-head">
                  <div className="system-config-modern-ad-card-head-copy">
                    {createLabel('信息流插播广告', '插入在消息卡片之间，适合中矩形或紧凑型素材。')}
                  </div>
                  <div className="system-config-modern-ad-inline-setting">
                    <span className="system-config-modern-ad-inline-copy">每</span>
                    <InputNumber
                      className="system-config-modern-ad-inline-input"
                      min={2}
                      max={999}
                      value={draft.public_feed_inline_every_n}
                      onChange={(value) => {
                        if (typeof value !== 'number' || Number.isNaN(value)) {
                          return
                        }
                        updateDraft('public_feed_inline_every_n', value)
                      }}
                      disabled={saving}
                    />
                    <span className="system-config-modern-ad-inline-copy">条插入 1 条</span>
                    <HintTooltip content="每展示 N 条消息后插入 1 条广告。数值越小，广告出现越频繁。" />
                  </div>
                </div>
                <div className="system-config-modern-ad-code-group">
                  {createLabel('桌面端 HTML', '桌面端插播广告代码。')}
                  <TextArea
                    rows={5}
                    value={draft.public_feed_inline_ad_html_desktop}
                    onChange={(event) => updateDraft('public_feed_inline_ad_html_desktop', event.target.value)}
                    placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                    className="system-config-modern-textarea"
                    allowClear
                    disabled={saving}
                  />
                </div>
                <div className="system-config-modern-ad-code-group">
                  {createLabel('移动端 HTML', '移动端插播广告代码。')}
                  <TextArea
                    rows={4}
                    value={draft.public_feed_inline_ad_html_mobile}
                    onChange={(event) => updateDraft('public_feed_inline_ad_html_mobile', event.target.value)}
                    placeholder='<a href="..."><img src="..." alt="ad" /></a>'
                    className="system-config-modern-textarea"
                    allowClear
                    disabled={saving}
                  />
                </div>
              </div>
            </div>
          </Card>
        </section>

        <section id="system-config-link-check" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle('链接检测', '控制链接检测任务的默认并发、最大并发、最大链接数与轮询频率。', <Tag color="success">新任务立即生效</Tag>)}
          >
            <div className="system-config-modern-field-grid">
              <div className="system-config-modern-field-card">
                {createLabel('默认并发数', '创建链接检测任务时自动带入的并发值。')}
                <InputNumber
                  min={1}
                  max={10}
                  value={draft.link_check_default_max_concurrent}
                  onChange={(value) => updateDraft('link_check_default_max_concurrent', Number(value || 1))}
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('允许最大并发', '后端安全阈值，超过后端会直接拒绝任务。')}
                <InputNumber
                  min={1}
                  max={10}
                  value={draft.link_check_max_allowed_concurrent}
                  onChange={(value) => updateDraft('link_check_max_allowed_concurrent', Number(value || 1))}
                  status={hasConcurrencyError ? 'error' : ''}
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('允许最大链接数', '单次任务可处理的最大链接量，用于保护系统资源。')}
                <InputNumber
                  min={100}
                  max={5000}
                  step={100}
                  value={draft.link_check_max_allowed_links}
                  onChange={(value) => updateDraft('link_check_max_allowed_links', Number(value || 100))}
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('任务轮询间隔', '后台页面轮询检测任务状态的频率，单位秒。')}
                <InputNumber
                  min={1}
                  max={30}
                  value={draft.link_check_poll_interval_seconds}
                  onChange={(value) => updateDraft('link_check_poll_interval_seconds', Number(value || 1))}
                  addonAfter="秒"
                  disabled={saving}
                />
              </div>
            </div>

            {hasConcurrencyError && (
              <Alert
                className="system-config-modern-inline-alert"
                type="error"
                showIcon
                message="并发配置不合法"
                description="链接检测默认并发不能大于系统允许的最大并发。"
              />
            )}
          </Card>
        </section>

        <section id="system-config-monitor" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle('监控运行', '配置监控服务读取频道映射与消息写库重试的运行参数。', <Tag color="warning">保存后自动读取</Tag>)}
          >
            <div className="system-config-modern-field-grid">
              <div className="system-config-modern-field-card">
                {createLabel('频道刷新周期', '监控服务刷新频道映射与频道信息的间隔。')}
                <InputNumber
                  min={10}
                  max={3600}
                  value={draft.monitor_channel_refresh_interval_seconds}
                  onChange={(value) => updateDraft('monitor_channel_refresh_interval_seconds', Number(value || 10))}
                  addonAfter="秒"
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('数据库写入重试次数', '监控消息入库失败后的最大重试次数。')}
                <InputNumber
                  min={1}
                  max={10}
                  value={draft.monitor_db_write_max_retries}
                  onChange={(value) => updateDraft('monitor_db_write_max_retries', Number(value || 1))}
                  disabled={saving}
                />
              </div>

              <div className="system-config-modern-field-card">
                {createLabel('数据库写入重试间隔', '单次写库失败后，下一次重试前等待多久。')}
                <InputNumber
                  min={0.1}
                  max={30}
                  step={0.1}
                  value={draft.monitor_db_write_retry_delay_seconds}
                  onChange={(value) => updateDraft('monitor_db_write_retry_delay_seconds', Number(value || 0.1))}
                  addonAfter="秒"
                  disabled={saving}
                />
              </div>
            </div>
          </Card>
        </section>

        <section id="system-config-timing" className="system-config-modern-section-shell">
          <Card
            className="system-config-modern-section-card"
            title={createSectionTitle('生效节奏', '快速判断哪些设置保存后立即生效，哪些设置会在监控下一轮读取。')}
          >
            <div className="system-config-modern-timing-grid">
              <article className="system-config-modern-timing-card">
                <div className="system-config-modern-timing-head">
                  <Tag color="success">即时生效</Tag>
                  <HintTooltip content="站点名称、站点标题、图标、游客访问、广告位、Umami 配置与链接检测阈值保存后即可被前台或新任务读取。" />
                </div>
                <div className="system-config-modern-timing-body">站点品牌、游客访问、广告位、Umami、链接检测阈值</div>
              </article>

              <article className="system-config-modern-timing-card">
                <div className="system-config-modern-timing-head">
                  <Tag color="processing">下一轮读取</Tag>
                  <HintTooltip content="频道刷新周期、数据库写入重试次数与重试间隔由监控进程直接从数据库读取，无需重启 tg-monitor。" />
                </div>
                <div className="system-config-modern-timing-body">监控刷新节奏、写库重试次数、写库重试间隔</div>
              </article>
            </div>
          </Card>
        </section>
      </div>
    </div>
  )
}

export default SystemConfigModern


