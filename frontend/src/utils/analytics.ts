import type { PublicSystemConfigResponse, SystemConfigResponse } from '@/types/admin'

type AnalyticsSourceConfig = Pick<
  PublicSystemConfigResponse,
  'umami_enabled' | 'umami_script_url' | 'umami_website_id' | 'umami_host_url'
> &
  Partial<Pick<SystemConfigResponse, 'umami_share_url'>>

type AnalyticsEventPrimitive = string | number | boolean
export type AnalyticsEventData = Record<string, AnalyticsEventPrimitive | null | undefined>

interface UmamiTracker {
  track: (eventName: string, data?: Record<string, AnalyticsEventPrimitive>) => void
}

interface QueuedAnalyticsEvent {
  name: string
  data?: Record<string, AnalyticsEventPrimitive>
}

interface AnalyticsRuntimeConfig {
  enabled: boolean
  scriptUrl: string
  websiteId: string
  hostUrl: string
}

declare global {
  interface Window {
    umami?: UmamiTracker
    __tgUmamiQueue?: QueuedAnalyticsEvent[]
  }
}

const UMAMI_SCRIPT_ID = 'tg-umami-script'

let currentRuntimeConfig: AnalyticsRuntimeConfig = {
  enabled: false,
  scriptUrl: '',
  websiteId: '',
  hostUrl: '',
}
let currentConfigKey = ''

const normalizeRuntimeConfig = (config?: Partial<AnalyticsSourceConfig> | null): AnalyticsRuntimeConfig => ({
  enabled: Boolean(config?.umami_enabled),
  scriptUrl: String(config?.umami_script_url || '').trim(),
  websiteId: String(config?.umami_website_id || '').trim(),
  hostUrl: String(config?.umami_host_url || '').trim(),
})

const isRuntimeConfigReady = (config: AnalyticsRuntimeConfig) =>
  config.enabled && !!config.scriptUrl && !!config.websiteId

const sanitizeEventData = (data?: AnalyticsEventData): Record<string, AnalyticsEventPrimitive> | undefined => {
  if (!data) {
    return undefined
  }

  const entries = Object.entries(data)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => {
      if (typeof value === 'string') {
        const normalized = value.replace(/\s+/g, ' ').trim()
        return [key, normalized.slice(0, 180)] as const
      }
      return [key, value] as const
    })

  if (entries.length === 0) {
    return undefined
  }

  return Object.fromEntries(entries)
}

const flushQueuedEvents = () => {
  if (typeof window === 'undefined' || !window.umami?.track) {
    return
  }

  const queue = window.__tgUmamiQueue || []
  while (queue.length > 0) {
    const nextEvent = queue.shift()
    if (!nextEvent) {
      continue
    }
    window.umami.track(nextEvent.name, nextEvent.data)
  }
}

const bindScriptLoad = (script: HTMLScriptElement) => {
  if (script.dataset.tgAnalyticsBound === 'true') {
    return
  }

  script.addEventListener('load', flushQueuedEvents)
  script.dataset.tgAnalyticsBound = 'true'
}

export const configureAnalytics = (config?: Partial<AnalyticsSourceConfig> | null) => {
  if (typeof document === 'undefined') {
    return
  }

  currentRuntimeConfig = normalizeRuntimeConfig(config)

  if (!isRuntimeConfigReady(currentRuntimeConfig)) {
    currentConfigKey = ''
    const existingScript = document.getElementById(UMAMI_SCRIPT_ID)
    existingScript?.remove()
    return
  }

  const nextConfigKey = JSON.stringify(currentRuntimeConfig)
  const existingScript = document.getElementById(UMAMI_SCRIPT_ID) as HTMLScriptElement | null
  if (existingScript && currentConfigKey === nextConfigKey) {
    bindScriptLoad(existingScript)
    flushQueuedEvents()
    return
  }

  existingScript?.remove()

  const script = document.createElement('script')
  script.id = UMAMI_SCRIPT_ID
  script.async = true
  script.defer = true
  script.src = currentRuntimeConfig.scriptUrl
  script.setAttribute('data-website-id', currentRuntimeConfig.websiteId)
  if (currentRuntimeConfig.hostUrl) {
    script.setAttribute('data-host-url', currentRuntimeConfig.hostUrl)
  }

  bindScriptLoad(script)
  document.head.appendChild(script)
  currentConfigKey = nextConfigKey
}

export const isAnalyticsEnabled = () => isRuntimeConfigReady(currentRuntimeConfig)

export const trackEvent = (name: string, data?: AnalyticsEventData) => {
  if (typeof window === 'undefined' || !isAnalyticsEnabled()) {
    return
  }

  const normalizedData = sanitizeEventData(data)
  if (window.umami?.track) {
    window.umami.track(name, normalizedData)
    return
  }

  const queue = window.__tgUmamiQueue || []
  queue.push({ name, data: normalizedData })
  window.__tgUmamiQueue = queue
}

