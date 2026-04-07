import { useEffect, useRef, useState } from 'react'
import './TurnstileWidget.css'

type TurnstileTheme = 'auto' | 'light' | 'dark'
type TurnstileSize = 'normal' | 'compact' | 'flexible'

interface TurnstileRenderOptions {
  sitekey: string
  action?: string
  theme?: TurnstileTheme
  size?: TurnstileSize
  callback?: (token: string) => void
  'error-callback'?: () => void
  'expired-callback'?: () => void
}

interface TurnstileApi {
  render: (container: HTMLElement, options: TurnstileRenderOptions) => string
  remove?: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

interface TurnstileWidgetProps {
  siteKey: string
  action: string
  theme?: TurnstileTheme
  size?: TurnstileSize
  onVerify: (token: string) => void
  onExpire?: () => void
  onError?: (message: string) => void
}

let turnstileScriptPromise: Promise<void> | null = null

const loadTurnstileScript = () => {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Turnstile is unavailable during server render'))
  }

  if (window.turnstile) {
    return Promise.resolve()
  }

  if (turnstileScriptPromise) {
    return turnstileScriptPromise
  }

  turnstileScriptPromise = new Promise<void>((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>('script[data-turnstile-script="true"]')
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve(), { once: true })
      existingScript.addEventListener('error', () => reject(new Error('Turnstile script failed to load')), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.dataset.turnstileScript = 'true'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Turnstile script failed to load'))
    document.head.appendChild(script)
  })

  return turnstileScriptPromise
}

const TurnstileWidget = ({
  siteKey,
  action,
  theme = 'auto',
  size = 'flexible',
  onVerify,
  onExpire,
  onError,
}: TurnstileWidgetProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const widgetIdRef = useRef<string | null>(null)
  const onVerifyRef = useRef(onVerify)
  const onExpireRef = useRef(onExpire)
  const onErrorRef = useRef(onError)
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    onVerifyRef.current = onVerify
  }, [onVerify])

  useEffect(() => {
    onExpireRef.current = onExpire
  }, [onExpire])

  useEffect(() => {
    onErrorRef.current = onError
  }, [onError])

  useEffect(() => {
    let cancelled = false

    const mountWidget = async () => {
      if (!siteKey || !containerRef.current) {
        setLoading(false)
        return
      }

      setLoading(true)
      setErrorMessage('')

      try {
        await loadTurnstileScript()
        if (cancelled || !containerRef.current || !window.turnstile) {
          return
        }

        containerRef.current.innerHTML = ''
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          theme,
          size,
          callback: (token: string) => {
            setErrorMessage('')
            onVerifyRef.current(token)
          },
          'expired-callback': () => {
            onExpireRef.current?.()
          },
          'error-callback': () => {
            const nextMessage = 'Turnstile 组件加载失败，请稍后重试'
            setErrorMessage(nextMessage)
            onErrorRef.current?.(nextMessage)
          },
        })
        setLoading(false)
      } catch (error) {
        const nextMessage =
          error instanceof Error ? error.message : 'Turnstile 组件加载失败，请检查网络或 Cloudflare 配置'
        setErrorMessage(nextMessage)
        setLoading(false)
        onErrorRef.current?.(nextMessage)
      }
    }

    void mountWidget()

    return () => {
      cancelled = true
      if (widgetIdRef.current && window.turnstile?.remove) {
        window.turnstile.remove(widgetIdRef.current)
      }
      widgetIdRef.current = null
    }
  }, [action, siteKey, size, theme])

  return (
    <div className="turnstile-widget-shell">
      <div ref={containerRef} className="turnstile-widget-container" />
      {loading ? <div className="turnstile-widget-status">正在加载人机验证…</div> : null}
      {errorMessage ? <div className="turnstile-widget-error">{errorMessage}</div> : null}
    </div>
  )
}

export default TurnstileWidget
