import { useEffect } from 'react'
import { getPublicConfig } from '@/api/admin'
import type { SystemConfigResponse } from '@/types/admin'
import { configureAnalytics } from '@/utils/analytics'
import { applySiteBranding } from '@/utils/siteBranding'

const AnalyticsBootstrap = () => {
  useEffect(() => {
    let cancelled = false

    const loadPublicConfig = async () => {
      try {
        const config = await getPublicConfig()
        if (!cancelled) {
          configureAnalytics(config)
          applySiteBranding(config)
        }
      } catch {
        if (!cancelled) {
          configureAnalytics(null)
          applySiteBranding(null)
        }
      }
    }

    const handleConfigUpdated = (event: Event) => {
      const detail = (event as CustomEvent<SystemConfigResponse>).detail
      configureAnalytics(detail)
      applySiteBranding(detail)
    }

    void loadPublicConfig()
    window.addEventListener('tg-system-config-updated', handleConfigUpdated)

    return () => {
      cancelled = true
      window.removeEventListener('tg-system-config-updated', handleConfigUpdated)
    }
  }, [])

  return null
}

export default AnalyticsBootstrap
