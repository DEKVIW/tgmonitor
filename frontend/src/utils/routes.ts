const env = (import.meta as any).env || {}

const DEFAULT_LOGIN_PATH = '/login'
const RESERVED_LOGIN_PATHS = new Set(['/', '/dashboard', '/statistics', '/analytics', '/resource-ops', '/backups', '/admin'])

const normalizePath = (rawPath: string | undefined, fallback: string): string => {
  const trimmed = rawPath?.trim()
  if (!trimmed) {
    return fallback
  }

  const withLeadingSlash = trimmed.startsWith('/') ? trimmed : `/${trimmed}`
  const collapsedSlashes = withLeadingSlash.replace(/\/{2,}/g, '/')
  const normalized = collapsedSlashes.length > 1
    ? collapsedSlashes.replace(/\/+$/, '')
    : collapsedSlashes

  return normalized === '/' ? fallback : normalized
}

const configuredLoginPath = normalizePath(env.VITE_LOGIN_PATH, DEFAULT_LOGIN_PATH)

export const LOGIN_PATH = RESERVED_LOGIN_PATHS.has(configuredLoginPath)
  ? DEFAULT_LOGIN_PATH
  : configuredLoginPath

export const LOGIN_LINUXDO_CALLBACK_PATH = `${LOGIN_PATH}/linuxdo/callback`

const stripTrailingSlash = (path: string): string => {
  return path.length > 1 ? path.replace(/\/+$/, '') : path
}

export const isPathMatch = (pathname: string, targetPath: string): boolean => {
  return stripTrailingSlash(pathname) === stripTrailingSlash(targetPath)
}
