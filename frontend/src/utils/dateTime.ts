import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)

const SERVER_TZ_PATTERN = /(Z|[+-]\d{2}:\d{2})$/i

export const parseServerDateTime = (value?: string | null) => {
  if (!value) {
    return null
  }
  const parsed = SERVER_TZ_PATTERN.test(value) ? dayjs(value) : dayjs.utc(value).local()
  return parsed.isValid() ? parsed : null
}

export const formatServerDateTime = (value?: string | null, format: string = 'YYYY-MM-DD HH:mm') => {
  const parsed = parseServerDateTime(value)
  if (!parsed) {
    return '-'
  }
  return parsed.format(format)
}
