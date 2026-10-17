import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

const SERVER_TZ_PATTERN = /(Z|[+-]\d{2}:\d{2})$/i
const DEFAULT_DISPLAY_TIMEZONE = 'Asia/Shanghai'

export const parseServerDateTime = (
  value?: string | null,
  targetTimezone: string = DEFAULT_DISPLAY_TIMEZONE,
  naiveAsLocal: boolean = false
) => {
  if (!value) {
    return null
  }
  const normalized = value.trim()
  if (!normalized) {
    return null
  }
  const parsed = SERVER_TZ_PATTERN.test(normalized)
    ? dayjs(normalized)
    : naiveAsLocal
      ? dayjs.tz(normalized, targetTimezone)
      : dayjs.utc(normalized)
  if (!parsed.isValid()) {
    return null
  }
  return parsed.tz(targetTimezone)
}

export const formatServerDateTime = (
  value?: string | null,
  format: string = 'YYYY-MM-DD HH:mm',
  targetTimezone: string = DEFAULT_DISPLAY_TIMEZONE,
  naiveAsLocal: boolean = false
) => {
  const parsed = parseServerDateTime(value, targetTimezone, naiveAsLocal)
  if (!parsed) {
    return '-'
  }
  return parsed.format(format)
}

export const formatRelativeServerDateTime = (
  value?: string | null,
  targetTimezone: string = DEFAULT_DISPLAY_TIMEZONE
) => {
  const parsed = parseServerDateTime(value, targetTimezone)
  if (!parsed) {
    return ''
  }

  const now = dayjs().tz(targetTimezone)
  const elapsedSeconds = Math.max(0, now.diff(parsed, 'second'))
  if (elapsedSeconds < 60) {
    return '刚刚'
  }

  const elapsedMinutes = Math.floor(elapsedSeconds / 60)
  if (elapsedMinutes < 60) {
    return `${elapsedMinutes}分钟前`
  }

  const elapsedHours = Math.floor(elapsedMinutes / 60)
  if (elapsedHours < 24) {
    return `${elapsedHours}小时前`
  }

  const elapsedDays = Math.floor(elapsedHours / 24)
  if (elapsedDays < 7) {
    return `${elapsedDays}天前`
  }

  return parsed.year() === now.year() ? parsed.format('M月D日') : parsed.format('YYYY年M月D日')
}
