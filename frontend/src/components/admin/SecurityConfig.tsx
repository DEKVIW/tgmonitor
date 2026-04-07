import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Alert,
  Button,
  Card,
  Input,
  InputNumber,
  Select,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  CloudOutlined,
  GlobalOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SearchOutlined,
  SyncOutlined,
} from '@ant-design/icons'

import { getSecurityConfig, syncDomainAccessChallenge, updateSecurityConfig } from '@/api/security'
import HintTooltip from '@/components/common/HintTooltip'
import type {
  DomainChallengeAction,
  DomainChallengeExpressionMode,
  DomainChallengeSyncStatus,
  SearchChallengeScope,
  SecurityConfigResponse,
  SecurityConfigUpdate,
} from '@/types/security'
import { applyPublicSecurityConfig } from '@/utils/securityConfig'
import './SecurityConfig.css'

const { Text, Title } = Typography
const { Password, TextArea } = Input

const createLabel = (title: string, hint: string) => (
  <div className="security-config-field-label">
    <Text strong>{title}</Text>
    <HintTooltip content={hint} />
  </div>
)

const createSectionTitle = (title: string, hint: string, extra?: ReactNode) => (
  <div className="security-config-section-heading">
    <div className="security-config-section-heading-main">
      <span className="security-config-section-title">{title}</span>
      <HintTooltip content={hint} />
    </div>
    {extra}
  </div>
)

type SecurityDraft = SecurityConfigUpdate &
  Pick<
    SecurityConfigResponse,
    | 'turnstile_secret_configured'
    | 'cloudflare_api_token_configured'
    | 'domain_access_recommended_expression'
    | 'domain_access_rule_id'
    | 'domain_access_ruleset_id'
    | 'domain_access_last_synced_at'
    | 'domain_access_last_sync_status'
    | 'domain_access_last_sync_message'
  >

type OverviewTone = 'success' | 'accent' | 'neutral' | 'warning'

type OverviewCard = {
  key: string
  icon: ReactNode
  title: string
  status: string
  live: boolean
  chips: Array<{ label: string; tone: OverviewTone }>
}

const buildDraftFromResponse = (config: SecurityConfigResponse): SecurityDraft => ({
  turnstile_site_key: config.turnstile_site_key,
  turnstile_secret: '',
  clear_turnstile_secret: false,
  login_challenge_enabled: config.login_challenge_enabled,
  search_challenge_enabled: config.search_challenge_enabled,
  search_challenge_scope: config.search_challenge_scope,
  search_challenge_clearance_ttl_seconds: config.search_challenge_clearance_ttl_seconds,
  cloudflare_zone_id: config.cloudflare_zone_id,
  cloudflare_api_token: '',
  clear_cloudflare_api_token: false,
  domain_access_challenge_enabled: config.domain_access_challenge_enabled,
  domain_access_challenge_action: config.domain_access_challenge_action,
  domain_access_challenge_expression_mode: config.domain_access_challenge_expression_mode,
  domain_access_challenge_expression_custom: config.domain_access_challenge_expression_custom,
  turnstile_secret_configured: config.turnstile_secret_configured,
  cloudflare_api_token_configured: config.cloudflare_api_token_configured,
  domain_access_recommended_expression: config.domain_access_recommended_expression,
  domain_access_rule_id: config.domain_access_rule_id,
  domain_access_ruleset_id: config.domain_access_ruleset_id,
  domain_access_last_synced_at: config.domain_access_last_synced_at,
  domain_access_last_sync_status: config.domain_access_last_sync_status,
  domain_access_last_sync_message: config.domain_access_last_sync_message,
})

const toUpdatePayload = (draft: SecurityDraft): SecurityConfigUpdate => ({
  turnstile_site_key: draft.turnstile_site_key,
  turnstile_secret: draft.turnstile_secret,
  clear_turnstile_secret: draft.clear_turnstile_secret,
  login_challenge_enabled: draft.login_challenge_enabled,
  search_challenge_enabled: draft.search_challenge_enabled,
  search_challenge_scope: draft.search_challenge_scope,
  search_challenge_clearance_ttl_seconds: draft.search_challenge_clearance_ttl_seconds,
  cloudflare_zone_id: draft.cloudflare_zone_id,
  cloudflare_api_token: draft.cloudflare_api_token,
  clear_cloudflare_api_token: draft.clear_cloudflare_api_token,
  domain_access_challenge_enabled: draft.domain_access_challenge_enabled,
  domain_access_challenge_action: draft.domain_access_challenge_action,
  domain_access_challenge_expression_mode: draft.domain_access_challenge_expression_mode,
  domain_access_challenge_expression_custom: draft.domain_access_challenge_expression_custom,
})

const syncStatusColorMap: Record<DomainChallengeSyncStatus, string> = {
  never: 'default',
  success: 'success',
  error: 'error',
}

const SecurityConfig = () => {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [config, setConfig] = useState<SecurityConfigResponse | null>(null)
  const [draft, setDraft] = useState<SecurityDraft | null>(null)

  useEffect(() => {
    void loadConfig()
  }, [])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await getSecurityConfig()
      setConfig(data)
      setDraft(buildDraftFromResponse(data))
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载安全配置失败')
    } finally {
      setLoading(false)
    }
  }

  const updateDraft = <K extends keyof SecurityDraft>(key: K, value: SecurityDraft[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const baselinePayload = useMemo(
    () => (config ? JSON.stringify(toUpdatePayload(buildDraftFromResponse(config))) : ''),
    [config]
  )
  const currentPayload = useMemo(() => (draft ? JSON.stringify(toUpdatePayload(draft)) : ''), [draft])
  const isDirty = Boolean(config && draft && baselinePayload !== currentPayload)

  const turnstileReadyPreview = Boolean(
    draft &&
      draft.turnstile_site_key.trim() &&
      ((draft.turnstile_secret_configured && !draft.clear_turnstile_secret) || draft.turnstile_secret.trim())
  )
  const cloudflareReadyPreview = Boolean(
    draft &&
      draft.cloudflare_zone_id.trim() &&
      ((draft.cloudflare_api_token_configured && !draft.clear_cloudflare_api_token) || draft.cloudflare_api_token.trim())
  )

  const persistDraft = async (showSuccess = true) => {
    if (!draft) {
      return null
    }

    setSaving(true)
    try {
      const updated = await updateSecurityConfig(toUpdatePayload(draft))
      setConfig(updated)
      setDraft(buildDraftFromResponse(updated))
      applyPublicSecurityConfig(updated)
      if (showSuccess) {
        message.success('安全配置已保存')
      }
      return updated
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存安全配置失败')
      return null
    } finally {
      setSaving(false)
    }
  }

  const handleSync = async () => {
    if (!draft) {
      return
    }

    if (isDirty) {
      const saved = await persistDraft(false)
      if (!saved) {
        return
      }
    }

    setSyncing(true)
    try {
      const result = await syncDomainAccessChallenge()
      setConfig(result.config)
      setDraft(buildDraftFromResponse(result.config))
      applyPublicSecurityConfig(result.config)
      if (result.success) {
        message.success(result.message)
      } else {
        message.warning(result.message)
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '同步域名访问质询规则失败')
    } finally {
      setSyncing(false)
    }
  }

  if (!draft || !config) {
    return <Card loading={loading}>加载中...</Card>
  }

  const overviewCards: OverviewCard[] = [
    {
      key: 'turnstile',
      icon: <CloudOutlined />,
      title: 'Turnstile',
      status: turnstileReadyPreview ? '已就绪' : '待配置',
      live: turnstileReadyPreview,
      chips: [
        { label: draft.turnstile_site_key.trim() ? 'Site Key' : 'Site Key 空', tone: draft.turnstile_site_key.trim() ? 'success' : 'warning' },
        {
          label:
            draft.turnstile_secret_configured && !draft.clear_turnstile_secret
              ? 'Secret 已配置'
              : draft.turnstile_secret.trim()
                ? 'Secret 待保存'
                : 'Secret 空',
          tone:
            draft.turnstile_secret_configured && !draft.clear_turnstile_secret
              ? 'success'
              : draft.turnstile_secret.trim()
                ? 'accent'
                : 'warning',
        },
      ],
    },
    {
      key: 'login',
      icon: <SafetyCertificateOutlined />,
      title: '登录质询',
      status: draft.login_challenge_enabled ? '已启用' : '未启用',
      live: draft.login_challenge_enabled && turnstileReadyPreview,
      chips: [
        { label: turnstileReadyPreview ? '前端可渲染' : '缺少密钥', tone: turnstileReadyPreview ? 'success' : 'warning' },
        { label: '登录页', tone: 'accent' },
      ],
    },
    {
      key: 'search',
      icon: <SearchOutlined />,
      title: '搜索质询',
      status: draft.search_challenge_enabled ? '已启用' : '未启用',
      live: draft.search_challenge_enabled && turnstileReadyPreview,
      chips: [
        { label: draft.search_challenge_scope === 'all_users' ? '全用户' : '仅游客', tone: 'accent' },
        { label: `${draft.search_challenge_clearance_ttl_seconds / 60} 分钟`, tone: 'neutral' },
      ],
    },
    {
      key: 'domain',
      icon: <GlobalOutlined />,
      title: '域名访问',
      status: draft.domain_access_challenge_enabled ? '规则开启' : '规则关闭',
      live: draft.domain_access_challenge_enabled && cloudflareReadyPreview,
      chips: [
        { label: cloudflareReadyPreview ? 'Cloudflare 就绪' : 'Zone / Token 缺失', tone: cloudflareReadyPreview ? 'success' : 'warning' },
        { label: draft.domain_access_challenge_action, tone: 'accent' },
        { label: draft.domain_access_last_sync_status === 'success' ? '已同步' : '待同步', tone: draft.domain_access_last_sync_status === 'success' ? 'success' : 'neutral' },
      ],
    },
  ]

  return (
    <div className="security-config-page">
      <section className="security-config-hero">
        <div className="security-config-hero-copy">
          <Title level={4} className="security-config-title">
            安全防护
          </Title>
          <div className="security-config-status-row">
            <Tag color={isDirty ? 'gold' : 'success'}>{isDirty ? '有未保存修改' : '配置已同步'}</Tag>
            <Tag color={turnstileReadyPreview ? 'cyan' : 'default'}>{turnstileReadyPreview ? 'Turnstile 就绪' : 'Turnstile 未就绪'}</Tag>
            <Tag color={draft.domain_access_last_sync_status === 'success' ? 'success' : 'default'}>
              {draft.domain_access_last_sync_status === 'success' ? 'Cloudflare 已同步' : 'Cloudflare 未同步'}
            </Tag>
          </div>
        </div>

        <div className="security-config-actions" role="group" aria-label="安全配置操作">
          <Button icon={<ReloadOutlined />} onClick={() => void loadConfig()} loading={loading || saving || syncing}>
            重新加载
          </Button>
          <Button onClick={() => setDraft(buildDraftFromResponse(config))} disabled={!isDirty || saving || syncing}>
            撤销修改
          </Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={() => void persistDraft()} loading={saving} disabled={syncing}>
            保存配置
          </Button>
          <Button icon={<SyncOutlined />} onClick={() => void handleSync()} loading={syncing} disabled={saving}>
            同步域名规则
          </Button>
        </div>
      </section>

      <section className="security-config-overview-grid">
        {overviewCards.map((card) => (
          <article
            key={card.key}
            className={`security-config-overview-card ${card.live ? 'is-live' : 'is-idle'}`}
          >
            <div className="security-config-overview-head">
              <div className="security-config-overview-title-row">
                <span className={`security-config-overview-dot ${card.live ? 'is-live' : 'is-idle'}`} />
                <span className="security-config-overview-title-text">{card.title}</span>
              </div>
              <span className="security-config-overview-icon">{card.icon}</span>
            </div>
            <div className="security-config-overview-status">{card.status}</div>
            <div className="security-config-overview-chip-row">
              {card.chips.map((chip) => (
                <span key={`${card.key}-${chip.label}`} className={`security-config-overview-chip is-${chip.tone}`}>
                  {chip.label}
                </span>
              ))}
            </div>
          </article>
        ))}
      </section>

      <div className="security-config-sections">
        <section className="security-config-section">
          <Card
            className="security-config-card"
            title={createSectionTitle('Cloudflare 接入', '配置 Turnstile 与 Cloudflare Zone 凭据。密钥不会明文回显，留空代表保持原值。')}
          >
            <div className="security-config-field-grid">
              <div className="security-config-field-card">
                {createLabel('Turnstile Site Key', '前端渲染 Turnstile 组件时使用的公开站点密钥。')}
                <Input
                  value={draft.turnstile_site_key}
                  onChange={(event) => updateDraft('turnstile_site_key', event.target.value)}
                  placeholder="0x4AAAA..."
                  disabled={saving || syncing}
                />
              </div>

              <div className="security-config-field-card">
                {createLabel('Turnstile Secret Key', '后端调用 Siteverify 校验登录与搜索质询时使用的私钥。')}
                <Password
                  value={draft.turnstile_secret}
                  onChange={(event) => {
                    updateDraft('turnstile_secret', event.target.value)
                    if (draft.clear_turnstile_secret) {
                      updateDraft('clear_turnstile_secret', false)
                    }
                  }}
                  placeholder={
                    draft.turnstile_secret_configured && !draft.clear_turnstile_secret ? '已配置，留空保持不变' : '请输入 Secret Key'
                  }
                  disabled={saving || syncing}
                />
                <div className="security-config-inline-actions">
                  {draft.turnstile_secret_configured && !draft.clear_turnstile_secret ? (
                    <Tag color="success">已配置</Tag>
                  ) : null}
                  {draft.turnstile_secret_configured ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => {
                        updateDraft('turnstile_secret', '')
                        updateDraft('clear_turnstile_secret', true)
                      }}
                      disabled={saving || syncing}
                    >
                      清空
                    </Button>
                  ) : null}
                </div>
              </div>

              <div className="security-config-field-card">
                {createLabel('Cloudflare Zone ID', '同步域名访问质询规则时使用的 Zone ID。')}
                <Input
                  value={draft.cloudflare_zone_id}
                  onChange={(event) => updateDraft('cloudflare_zone_id', event.target.value)}
                  placeholder="023e105f4ecef8ad9ca31a8372d0c353"
                  disabled={saving || syncing}
                />
              </div>

              <div className="security-config-field-card">
                {createLabel('Cloudflare API Token', '用于读写 Zone 自定义规则。建议只授予当前站点所需的最小权限。')}
                <Password
                  value={draft.cloudflare_api_token}
                  onChange={(event) => {
                    updateDraft('cloudflare_api_token', event.target.value)
                    if (draft.clear_cloudflare_api_token) {
                      updateDraft('clear_cloudflare_api_token', false)
                    }
                  }}
                  placeholder={
                    draft.cloudflare_api_token_configured && !draft.clear_cloudflare_api_token ? '已配置，留空保持不变' : '请输入 API Token'
                  }
                  disabled={saving || syncing}
                />
                <div className="security-config-inline-actions">
                  {draft.cloudflare_api_token_configured && !draft.clear_cloudflare_api_token ? (
                    <Tag color="success">已配置</Tag>
                  ) : null}
                  {draft.cloudflare_api_token_configured ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => {
                        updateDraft('cloudflare_api_token', '')
                        updateDraft('clear_cloudflare_api_token', true)
                      }}
                      disabled={saving || syncing}
                    >
                      清空
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          </Card>
        </section>

        <section className="security-config-section">
          <Card
            className="security-config-card"
            title={createSectionTitle('登录质询', '启用后，登录页会先渲染 Turnstile，人机验证通过后才允许提交用户名和密码。')}
          >
            <div className="security-config-toggle-row">
              <div className="security-config-toggle-copy">
                {createLabel('启用登录页人机验证', '适合直接拦截撞库、弱口令爆破和批量登录脚本。')}
              </div>
              <Switch
                checked={draft.login_challenge_enabled}
                onChange={(checked) => updateDraft('login_challenge_enabled', checked)}
                disabled={saving || syncing}
              />
            </div>
          </Card>
        </section>

        <section className="security-config-section">
          <Card
            className="security-config-card"
            title={createSectionTitle('搜索质询', '搜索请求命中时，前端会先做人机验证，后端也会强制校验，不只是前端限制。')}
          >
            <div className="security-config-field-grid">
              <div className="security-config-field-card">
                <div className="security-config-toggle-row">
                  <div className="security-config-toggle-copy">
                    {createLabel('启用搜索人机验证', '搜索关键词存在时触发，验证通过后会生成一段限时搜索通行令牌。')}
                  </div>
                  <Switch
                    checked={draft.search_challenge_enabled}
                    onChange={(checked) => updateDraft('search_challenge_enabled', checked)}
                    disabled={saving || syncing}
                  />
                </div>
              </div>

              <div className="security-config-field-card">
                {createLabel('适用范围', '可只对游客要求验证，也可对所有登录和未登录用户都要求验证。')}
                <Select<SearchChallengeScope>
                  value={draft.search_challenge_scope}
                  onChange={(value) => updateDraft('search_challenge_scope', value)}
                  disabled={saving || syncing}
                  options={[
                    { value: 'guest_only', label: '仅游客' },
                    { value: 'all_users', label: '所有用户' },
                  ]}
                />
              </div>

              <div className="security-config-field-card">
                {createLabel('搜索通行时长', '搜索验证通过后的有效时长，单位分钟。时间越长，用户越省事；时间越短，风控越严格。')}
                <InputNumber
                  min={5}
                  max={1440}
                  value={Math.round(draft.search_challenge_clearance_ttl_seconds / 60)}
                  onChange={(value) =>
                    updateDraft(
                      'search_challenge_clearance_ttl_seconds',
                      Math.max(300, Math.min(86400, Number(value || 5) * 60))
                    )
                  }
                  addonAfter="分钟"
                  disabled={saving || syncing}
                />
              </div>
            </div>
          </Card>
        </section>

        <section className="security-config-section">
          <Card
            className="security-config-card"
            title={createSectionTitle(
              '域名访问质询',
              '这一块会把规则同步到 Cloudflare WAF，自定义规则生效后，访问站点页面时会由 Cloudflare 接管质询。'
            )}
          >
            <div className="security-config-field-grid">
              <div className="security-config-field-card security-config-field-card--wide">
                <div className="security-config-toggle-row">
                  <div className="security-config-toggle-copy">
                    {createLabel('启用域名访问质询', '保存后不会立刻生效，点击“同步域名规则”后才会把当前配置推送到 Cloudflare。')}
                  </div>
                  <Switch
                    checked={draft.domain_access_challenge_enabled}
                    onChange={(checked) => updateDraft('domain_access_challenge_enabled', checked)}
                    disabled={saving || syncing}
                  />
                </div>
              </div>

              <div className="security-config-field-card">
                {createLabel('质询动作', '推荐优先使用 Managed Challenge，由 Cloudflare 自动选择最合适的质询强度。')}
                <Select<DomainChallengeAction>
                  value={draft.domain_access_challenge_action}
                  onChange={(value) => updateDraft('domain_access_challenge_action', value)}
                  disabled={saving || syncing}
                  options={[
                    { value: 'managed_challenge', label: 'Managed Challenge' },
                    { value: 'js_challenge', label: 'JavaScript Challenge' },
                    { value: 'challenge', label: 'Interactive Challenge' },
                  ]}
                />
              </div>

              <div className="security-config-field-card">
                {createLabel('规则表达式', '推荐模式会自动生成适合当前站点的表达式；自定义模式则完全按你填写的表达式同步。')}
                <Select<DomainChallengeExpressionMode>
                  value={draft.domain_access_challenge_expression_mode}
                  onChange={(value) => updateDraft('domain_access_challenge_expression_mode', value)}
                  disabled={saving || syncing}
                  options={[
                    { value: 'recommended', label: '推荐表达式' },
                    { value: 'custom', label: '自定义表达式' },
                  ]}
                />
              </div>

              <div className="security-config-field-card security-config-field-card--wide">
                {createLabel(
                  draft.domain_access_challenge_expression_mode === 'custom' ? '自定义表达式' : '推荐表达式预览',
                  '这里使用的就是最终会同步到 Cloudflare 的表达式。推荐表达式默认避开 /api 和 /cdn-cgi，并跳过带扩展名的静态资源路径。'
                )}
                <TextArea
                  rows={4}
                  value={
                    draft.domain_access_challenge_expression_mode === 'custom'
                      ? draft.domain_access_challenge_expression_custom
                      : draft.domain_access_recommended_expression
                  }
                  onChange={(event) => updateDraft('domain_access_challenge_expression_custom', event.target.value)}
                  disabled={saving || syncing || draft.domain_access_challenge_expression_mode !== 'custom'}
                  className="security-config-textarea"
                />
              </div>
            </div>

            <div className="security-config-sync-grid">
              <article className="security-config-sync-card">
                <div className="security-config-sync-head">
                  <span className="security-config-sync-title">同步状态</span>
                  <Tag color={syncStatusColorMap[draft.domain_access_last_sync_status]}>
                    {draft.domain_access_last_sync_status}
                  </Tag>
                </div>
                <div className="security-config-sync-body">
                  <div>最近同步：{draft.domain_access_last_synced_at || '尚未同步'}</div>
                  <div>规则 ID：{draft.domain_access_rule_id || '未生成'}</div>
                  <div>Ruleset ID：{draft.domain_access_ruleset_id || '未生成'}</div>
                </div>
              </article>

              <article className="security-config-sync-card">
                <div className="security-config-sync-head">
                  <span className="security-config-sync-title">同步备注</span>
                </div>
                <div className="security-config-sync-body">
                  {draft.domain_access_last_sync_message || '保存配置后，点击“同步域名规则”即可推送到 Cloudflare。'}
                </div>
              </article>
            </div>

            {!cloudflareReadyPreview ? (
              <Alert
                className="security-config-inline-alert"
                type="warning"
                showIcon
                message="Cloudflare 凭据还不完整"
                description="同步域名访问质询前，至少需要填写 Zone ID 和 API Token。"
              />
            ) : null}
          </Card>
        </section>
      </div>
    </div>
  )
}

export default SecurityConfig
