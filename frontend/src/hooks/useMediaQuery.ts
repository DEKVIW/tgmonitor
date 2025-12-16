/**
 * 媒体查询 Hook
 * 用于响应式设计
 */

import { useState, useEffect } from 'react'

/**
 * 检测媒体查询是否匹配
 * @param query 媒体查询字符串，例如 '(max-width: 768px)'
 * @returns 是否匹配
 */
export const useMediaQuery = (query: string): boolean => {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    // 检查是否在浏览器环境
    if (typeof window === 'undefined') {
      return
    }

    const mediaQuery = window.matchMedia(query)
    
    // 设置初始值
    setMatches(mediaQuery.matches)

    // 监听变化
    const handler = (event: MediaQueryListEvent) => {
      setMatches(event.matches)
    }

    // 使用 addEventListener（现代浏览器）
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handler)
      return () => mediaQuery.removeEventListener('change', handler)
    } else {
      // 兼容旧浏览器
      mediaQuery.addListener(handler)
      return () => mediaQuery.removeListener(handler)
    }
  }, [query])

  return matches
}

