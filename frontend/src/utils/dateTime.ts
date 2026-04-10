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
