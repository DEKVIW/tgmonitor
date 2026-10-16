import { useState } from 'react'

import { useSiteBranding } from '@/utils/siteBranding'

interface SiteBrandProps {
  className?: string
  onClick?: () => void
}

const SiteBrand = ({ className = '', onClick }: SiteBrandProps) => {
  const branding = useSiteBranding()
  const [imageFailed, setImageFailed] = useState(false)
  const siteName = branding.site_name || 'TG Monitor'
  const fallbackMark = branding.brand_icon.trim() || siteName.slice(0, 1)
  const classes = ['site-brand', onClick ? 'is-interactive' : '', className].filter(Boolean).join(' ')

  return (
    <div
      className={classes}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(event) => {
        if (onClick && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault()
          onClick()
        }
      }}
    >
      {!imageFailed && branding.site_favicon_url ? (
        <img
          className="site-brand-logo"
          src={branding.site_favicon_url}
          alt=""
          aria-hidden="true"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <span className="site-brand-fallback" aria-hidden="true">{fallbackMark}</span>
      )}
      <span className="site-brand-name">{siteName}</span>
    </div>
  )
}

export default SiteBrand
