import { useEffect, useRef } from 'react'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { trackEvent } from '@/utils/analytics'

interface PublicAdSlotProps {
  html: string
  placement: 'top' | 'inline'
}

const PublicAdSlot = ({ html, placement }: PublicAdSlotProps) => {
  const frameRef = useRef<HTMLDivElement | null>(null)
  const isMobile = useMediaQuery('(max-width: 768px)')

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) {
      return
    }

    const anchors = Array.from(frame.querySelectorAll<HTMLAnchorElement>('a[href]'))
    anchors.forEach((anchor, index) => {
      anchor.setAttribute('data-umami-event', 'ad_click')
      anchor.setAttribute('data-umami-event-placement', placement)
      anchor.setAttribute('data-umami-event-slot', placement === 'top' ? 'public_feed_top' : 'public_feed_inline')
      anchor.setAttribute('data-umami-event-device', isMobile ? 'mobile' : 'desktop')
      anchor.setAttribute('data-umami-event-link_index', String(index + 1))

      try {
        const targetUrl = new URL(anchor.href)
        anchor.setAttribute('data-umami-event-target_host', targetUrl.host)
      } catch {
        anchor.setAttribute('data-umami-event-target_host', anchor.href)
      }
    })
  }, [html, isMobile, placement])

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) {
      return
    }

    let tracked = false
    const observer = new IntersectionObserver(
      (entries) => {
        if (tracked) {
          return
        }

        const entry = entries[0]
        if (!entry?.isIntersecting) {
          return
        }

        tracked = true
        trackEvent('ad_impression', {
          placement,
          slot: placement === 'top' ? 'public_feed_top' : 'public_feed_inline',
          device: isMobile ? 'mobile' : 'desktop',
        })
        observer.disconnect()
      },
      { threshold: 0.35 }
    )

    observer.observe(frame)
    return () => observer.disconnect()
  }, [html, isMobile, placement])

  if (!html.trim()) {
    return null
  }

  return (
    <section className={`public-ad-slot public-ad-slot-${placement}`} aria-label="广告">
      <div
        ref={frameRef}
        className={`public-ad-slot-frame public-ad-slot-frame-${placement}`}
        // HTML comes from the admin-managed system config.
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </section>
  )
}

export default PublicAdSlot
