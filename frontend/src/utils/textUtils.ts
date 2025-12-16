/**
 * 文本处理工具函数
 */

/**
 * 去除重复的前缀
 * 如"描述：描述：描述内容"、"描述描述内容"都只保留一个
 */
export const cleanPrefix = (text: string): string => {
  const prefixes = [
    "描述：", "描述", "名称：", "名称", "资源描述：", "资源描述",
    "简介：", "简介", "剧情简介：", "剧情简介", "内容简介：", "内容简介"
  ]
  let cleaned = text.trim()
  for (const prefix of prefixes) {
    while (cleaned.startsWith(prefix)) {
      cleaned = cleaned.slice(prefix.length).trimStart()
    }
  }
  return cleaned
}

/**
 * 格式化时间显示
 */
export const formatTime = (timestamp: string): string => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const days = Math.floor(diff / 86400000)

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const msgDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  if (minutes < 1) {
    return "🔥刚刚"
  } else if (minutes < 60) {
    return `🔥${minutes}分钟前`
  } else if (msgDate.getTime() === today.getTime()) {
    return `⏰今天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
  } else if (msgDate.getTime() === yesterday.getTime()) {
    return `📅昨天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
  } else if (days < 7) {
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    return `📆${weekdays[date.getDay()]} ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
  } else if (date.getFullYear() === now.getFullYear()) {
    return `📋${date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })} ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
  } else {
    return `📋${date.toLocaleString('zh-CN')}`
  }
}

