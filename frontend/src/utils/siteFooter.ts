import { useEffect, useState } from 'react'
import type { FooterBuilderSection, PublicSystemConfigResponse, SystemConfigResponse } from '@/types/admin'

type SiteFooterPayload = Partial<PublicSystemConfigResponse & SystemConfigResponse> | null | undefined

export interface SiteFooterState {
  footer_builder_enabled: boolean
  footer_builder_sections: FooterBuilderSection[]
  footer_builder_bottom_html: string
}

const DEFAULT_SITE_FOOTER: SiteFooterState = {
  footer_builder_enabled: false,
  footer_builder_sections: [],
  footer_builder_bottom_html: '',
}

const SITE_FOOTER_EVENT = 'tg-site-footer-updated'

const normalizeText = (value: unknown) => String(value ?? '').trim()

const normalizeFooterSections = (sections: unknown): FooterBuilderSection[] => {
  if (!Array.isArray(sections)) {
    return []
  }

  return sections
    .filter((item): item is Partial<FooterBuilderSection> => typeof item === 'object' && item !== null)
    .map((item, index) => {
      const spanValue = Number(item.span ?? 3)
      const span = Number.isFinite(spanValue) ? Math.max(1, Math.min(12, Math.round(spanValue))) : 3

      return {
        id: normalizeText(item.id) || `footer-section-${index + 1}`,
        title: normalizeText(item.title),
        html: String(item.html ?? ''),
        span,
      }
    })
}

export const extractSiteFooterConfig = (payload?: SiteFooterPayload): SiteFooterState => ({
  footer_builder_enabled:
    typeof payload?.footer_builder_enabled === 'boolean'
      ? payload.footer_builder_enabled
      : DEFAULT_SITE_FOOTER.footer_builder_enabled,
  footer_builder_sections: normalizeFooterSections(payload?.footer_builder_sections),
  footer_builder_bottom_html: String(payload?.footer_builder_bottom_html ?? ''),
})

let siteFooterSnapshot: SiteFooterState = DEFAULT_SITE_FOOTER

export const getSiteFooterSnapshot = () => siteFooterSnapshot

export const applySiteFooterConfig = (payload?: SiteFooterPayload): SiteFooterState => {
  siteFooterSnapshot = extractSiteFooterConfig(payload)

  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<SiteFooterState>(SITE_FOOTER_EVENT, {
        detail: siteFooterSnapshot,
      })
    )
  }

  return siteFooterSnapshot
}

export const useSiteFooterConfig = () => {
  const [footerConfig, setFooterConfig] = useState<SiteFooterState>(getSiteFooterSnapshot())

  useEffect(() => {
    const handleFooterUpdated = (event: Event) => {
      const detail = (event as CustomEvent<SiteFooterState>).detail
      if (detail) {
        setFooterConfig(detail)
      }
    }

    window.addEventListener(SITE_FOOTER_EVENT, handleFooterUpdated)

    return () => {
      window.removeEventListener(SITE_FOOTER_EVENT, handleFooterUpdated)
    }
  }, [])

  return footerConfig
}
