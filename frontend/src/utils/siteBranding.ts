import { useEffect, useState } from 'react'
import type { PublicSystemConfigResponse, SystemConfigResponse } from '@/types/admin'

type SiteBrandingPayload = Partial<PublicSystemConfigResponse> | Partial<SystemConfigResponse> | null | undefined

export interface SiteBrandingState {
  site_name: string
  site_title: string
  site_description: string
  site_keywords: string
  brand_icon: string
  site_favicon_url: string
}

const SITE_BRANDING_STORAGE_KEY = 'tg-site-branding-cache'

const DEFAULT_SITE_BRANDING: SiteBrandingState = {
  site_name: '',
  site_title: '',
  site_description: '',
  site_keywords: '',
  brand_icon: '',
  site_favicon_url: '/favicon.svg',
}

const isBrowser = typeof window !== 'undefined'

const readSiteBrandingCache = (): SiteBrandingState | null => {
  if (!isBrowser) {
    return null
  }

  try {
    const rawValue = window.localStorage.getItem(SITE_BRANDING_STORAGE_KEY)
    if (!rawValue) {
      return null
    }
    return extractSiteBranding(JSON.parse(rawValue))
  } catch {
    return null
  }
}

const persistSiteBrandingCache = (branding: SiteBrandingState) => {
  if (!isBrowser) {
    return
  }

  try {
    window.localStorage.setItem(SITE_BRANDING_STORAGE_KEY, JSON.stringify(branding))
  } catch {
    // ignore storage errors
  }
}

let siteBrandingSnapshot: SiteBrandingState = readSiteBrandingCache() || DEFAULT_SITE_BRANDING

const SITE_BRANDING_EVENT = 'tg-site-branding-updated'

const ensureMetaTag = (name: string) => {
  let tag = document.querySelector(`meta[name="${name}"]`) as HTMLMetaElement | null
  if (!tag) {
    tag = document.createElement('meta')
    tag.setAttribute('name', name)
    document.head.appendChild(tag)
  }
  return tag
}

const ensureFaviconLink = () => {
  let tag = document.querySelector('link[rel="icon"]') as HTMLLinkElement | null
  if (!tag) {
    tag = document.createElement('link')
    tag.setAttribute('rel', 'icon')
    document.head.appendChild(tag)
  }
  return tag
}

export const extractSiteBranding = (payload?: SiteBrandingPayload): SiteBrandingState => ({
  site_name: payload?.site_name?.trim() || DEFAULT_SITE_BRANDING.site_name,
  site_title: payload?.site_title?.trim() || DEFAULT_SITE_BRANDING.site_title,
  site_description: payload?.site_description?.trim() || DEFAULT_SITE_BRANDING.site_description,
  site_keywords: payload?.site_keywords?.trim() || DEFAULT_SITE_BRANDING.site_keywords,
  brand_icon: payload?.brand_icon?.trim() ?? DEFAULT_SITE_BRANDING.brand_icon,
  site_favicon_url: payload?.site_favicon_url?.trim() || DEFAULT_SITE_BRANDING.site_favicon_url,
})

export const getSiteBrandingSnapshot = () => siteBrandingSnapshot

export const hasCachedSiteBranding = () => Boolean(readSiteBrandingCache())

export const applySiteBranding = (payload?: SiteBrandingPayload): SiteBrandingState => {
  siteBrandingSnapshot = extractSiteBranding(payload)
  persistSiteBrandingCache(siteBrandingSnapshot)

  if (typeof document !== 'undefined') {
    document.title = siteBrandingSnapshot.site_title
    ensureMetaTag('description').setAttribute('content', siteBrandingSnapshot.site_description)
    ensureMetaTag('keywords').setAttribute('content', siteBrandingSnapshot.site_keywords)
    ensureFaviconLink().setAttribute('href', siteBrandingSnapshot.site_favicon_url)
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<SiteBrandingState>(SITE_BRANDING_EVENT, {
        detail: siteBrandingSnapshot,
      })
    )
  }

  return siteBrandingSnapshot
}

export const useSiteBranding = () => {
  const [branding, setBranding] = useState<SiteBrandingState>(getSiteBrandingSnapshot())

  useEffect(() => {
    const handleBrandingUpdated = (event: Event) => {
      const detail = (event as CustomEvent<SiteBrandingState>).detail
      if (detail) {
        setBranding(detail)
      }
    }

    window.addEventListener(SITE_BRANDING_EVENT, handleBrandingUpdated)

    return () => {
      window.removeEventListener(SITE_BRANDING_EVENT, handleBrandingUpdated)
    }
  }, [])

  return branding
}

export const formatBrandTitle = (branding: SiteBrandingState) => {
  const icon = branding.brand_icon.trim()
  return icon ? `${icon} ${branding.site_name}` : branding.site_name
}
