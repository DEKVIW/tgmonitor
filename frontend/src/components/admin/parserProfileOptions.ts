export const PARSER_PROFILE_OPTIONS = [
  { value: 'auto', label: '自动判断' },
  { value: 'default', label: '默认通用' },
  { value: 'movie_default', label: '影视资源' },
  { value: 'course_list_default', label: '课程清单' },
]

const PARSER_PROFILE_LABELS: Record<string, string> = {
  auto: '自动判断',
  default: '默认通用',
  movie_default: '影视资源',
  course_list_default: '课程清单',
}

const PARSER_PROFILE_COLORS: Record<string, string> = {
  default: 'default',
  movie_default: 'magenta',
  course_list_default: 'cyan',
}

export const getConfiguredParserProfileLabel = (value?: string | null) =>
  value ? PARSER_PROFILE_LABELS[value] || value : PARSER_PROFILE_LABELS.auto

export const getEffectiveParserProfileLabel = (value?: string | null) =>
  PARSER_PROFILE_LABELS[value || 'default'] || value || 'default'

export const getEffectiveParserProfileColor = (value?: string | null) =>
  PARSER_PROFILE_COLORS[value || 'default'] || 'default'
