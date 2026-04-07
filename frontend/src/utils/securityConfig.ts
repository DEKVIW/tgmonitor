import { useEffect, useState } from 'react'
import type { UserInfo } from '@/types/auth'
import type {
  PublicSecurityConfigResponse,
  SearchChallengeClearance,
  SecurityConfigResponse,
} from '@/types/security'

type PublicSecurityPayload =
  | Partial<PublicSecurityConfigResponse>
  | Partial<SecurityConfigResponse>
  | null
  | undefined

export interface PublicSecurityState extends PublicSecurityConfigResponse {
  loaded: boolean
}

const PUBLIC_SECURITY_STORAGE_KEY = 'tg-public-security-config-cache'
const PUBLIC_SECURITY_EVENT = 'tg-public-security-config-updated'
const SEARCH_CLEARANCE_STORAGE_PREFIX = 'tg-search-challenge-clearance'

const DEFAULT_PUBLIC_SECURITY_STATE: PublicSecurityState = {
  loaded: false,
  turnstile_ready: false,
  turnstile_site_key: '',
  login_challenge_enabled: false,
  search_challenge_enabled: false,
  search_challenge_scope: 'guest_only',
  search_challenge_clearance_ttl_seconds: 1800,
}

const isBrowser = typeof window !== 'undefined'

export const extractPublicSecurityConfig = (payload?: PublicSecurityPayload): PublicSecurityState => ({
  loaded: true,
  turnstile_ready: Boolean(payload?.turnstile_ready),
  turnstile_site_key: payload?.turnstile_site_key?.trim() || '',
  login_challenge_enabled: Boolean(payload?.login_challenge_enabled),
  search_challenge_enabled: Boolean(payload?.search_challenge_enabled),
  search_challenge_scope: payload?.search_challenge_scope === 'all_users' ? 'all_users' : 'guest_only',
  search_challenge_clearance_ttl_seconds: Math.max(
    300,
    Number(payload?.search_challenge_clearance_ttl_seconds || DEFAULT_PUBLIC_SECURITY_STATE.search_challenge_clearance_ttl_seconds)
  ),
})

const readPublicSecurityCache = (): PublicSecurityState | null => {
  if (!isBrowser) {
    return null
  }

  try {
    const rawValue = window.localStorage.getItem(PUBLIC_SECURITY_STORAGE_KEY)
    if (!rawValue) {
      return null
    }
    return {
      ...extractPublicSecurityConfig(JSON.parse(rawValue)),
      loaded: true,
    }
  } catch {
    return null
  }
}

const persistPublicSecurityCache = (value: PublicSecurityState) => {
  if (!isBrowser) {
    return
  }

  try {
    window.localStorage.setItem(PUBLIC_SECURITY_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // ignore storage errors
  }
}

let publicSecuritySnapshot: PublicSecurityState = readPublicSecurityCache() || DEFAULT_PUBLIC_SECURITY_STATE

export const getPublicSecuritySnapshot = () => publicSecuritySnapshot

export const applyPublicSecurityConfig = (payload?: PublicSecurityPayload) => {
  publicSecuritySnapshot = extractPublicSecurityConfig(payload)
  persistPublicSecurityCache(publicSecuritySnapshot)

  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<PublicSecurityState>(PUBLIC_SECURITY_EVENT, {
        detail: publicSecuritySnapshot,
      })
    )
  }

  return publicSecuritySnapshot
}

export const markPublicSecurityConfigLoaded = () => applyPublicSecurityConfig(null)

export const usePublicSecurityConfig = () => {
  const [securityConfig, setSecurityConfig] = useState<PublicSecurityState>(getPublicSecuritySnapshot())

  useEffect(() => {
    const handleUpdated = (event: Event) => {
      const detail = (event as CustomEvent<PublicSecurityState>).detail
      if (detail) {
        setSecurityConfig(detail)
      }
    }

    window.addEventListener(PUBLIC_SECURITY_EVENT, handleUpdated)
    return () => {
      window.removeEventListener(PUBLIC_SECURITY_EVENT, handleUpdated)
    }
  }, [])

  return securityConfig
}

export const buildSearchChallengeAudienceKey = (user?: UserInfo | null) =>
  user?.username ? `user:${user.username}` : 'guest'

const getSearchClearanceStorageKey = (user?: UserInfo | null) =>
  `${SEARCH_CLEARANCE_STORAGE_PREFIX}:${buildSearchChallengeAudienceKey(user)}`

export const readSearchChallengeClearance = (user?: UserInfo | null): SearchChallengeClearance | null => {
  if (!isBrowser) {
    return null
  }

  try {
    const rawValue = window.sessionStorage.getItem(getSearchClearanceStorageKey(user))
    if (!rawValue) {
      return null
    }

    const parsed = JSON.parse(rawValue) as SearchChallengeClearance
    if (!parsed?.clearance_token || !parsed?.expires_at) {
      return null
    }

    if (new Date(parsed.expires_at).getTime() <= Date.now()) {
      window.sessionStorage.removeItem(getSearchClearanceStorageKey(user))
      return null
    }

    return parsed
  } catch {
    return null
  }
}

export const writeSearchChallengeClearance = (user: UserInfo | null | undefined, value: SearchChallengeClearance) => {
  if (!isBrowser) {
    return
  }
  try {
    window.sessionStorage.setItem(getSearchClearanceStorageKey(user), JSON.stringify(value))
  } catch {
    // ignore storage errors
  }
}

export const clearSearchChallengeClearance = (user?: UserInfo | null) => {
  if (!isBrowser) {
    return
  }
  window.sessionStorage.removeItem(getSearchClearanceStorageKey(user))
}

export const isSearchChallengeRequiredForAudience = (
  config: PublicSecurityState,
  user?: UserInfo | null
) => {
  if (!config.turnstile_ready || !config.search_challenge_enabled) {
    return false
  }
  if (!user) {
    return true
  }
  return config.search_challenge_scope === 'all_users'
}
