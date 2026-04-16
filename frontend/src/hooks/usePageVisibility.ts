import { useEffect, useState } from 'react'

export const usePageVisibility = () => {
  const [isVisible, setIsVisible] = useState(() => {
    if (typeof document === 'undefined') {
      return true
    }
    return document.visibilityState !== 'hidden'
  })

  useEffect(() => {
    if (typeof document === 'undefined') {
      return
    }

    const handleVisibilityChange = () => {
      setIsVisible(document.visibilityState !== 'hidden')
    }

    handleVisibilityChange()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  return isVisible
}
