import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { PublicSystemConfigResponse, SystemConfigResponse } from '@/types/admin'
import { sanitizeHtml } from '@/utils/safeHtml'
import { extractSiteFooterConfig, useSiteFooterConfig } from '@/utils/siteFooter'
import './SiteFooter.css'

type SiteFooterConfigOverride = Partial<PublicSystemConfigResponse & SystemConfigResponse> | null | undefined

interface SiteFooterProps {
  config?: SiteFooterConfigOverride
  preview?: boolean
}

const SiteFooter = ({ config, preview = false }: SiteFooterProps) => {
  const liveFooterConfig = useSiteFooterConfig()
  const footerConfig = config ? extractSiteFooterConfig(config) : liveFooterConfig

  const sections = useMemo(
    () =>
      footerConfig.footer_builder_sections.map((section) => ({
        ...section,
        sanitizedHtml: sanitizeHtml(section.html),
      })),
    [footerConfig.footer_builder_sections]
  )

  const bottomHtml = useMemo(
    () => sanitizeHtml(footerConfig.footer_builder_bottom_html),
    [footerConfig.footer_builder_bottom_html]
  )

  if (!footerConfig.footer_builder_enabled && !preview) {
    return null
  }

  const hasVisibleContent = sections.some((section) => section.title || section.sanitizedHtml.trim()) || bottomHtml.trim()

  if (!hasVisibleContent && !preview) {
    return null
  }

  return (
    <footer className={`site-footer ${preview ? 'site-footer--preview' : ''}`}>
      <div className="site-footer__inner">
        <div className="site-footer__rail" />

        {hasVisibleContent ? (
          <>
            {sections.length ? (
              <div className="site-footer__grid">
                {sections.map((section) => (
                  <section
                    key={section.id}
                    className="site-footer__column"
                    style={{ '--footer-span': String(section.span) } as CSSProperties}
                  >
                    {section.title ? <h3 className="site-footer__title">{section.title}</h3> : null}
                    {section.sanitizedHtml.trim() ? (
                      <div
                        className="site-footer__html"
                        dangerouslySetInnerHTML={{ __html: section.sanitizedHtml }}
                      />
                    ) : preview ? (
                      <div className="site-footer__empty">此栏目还没有内容</div>
                    ) : null}
                  </section>
                ))}
              </div>
            ) : null}

            {bottomHtml.trim() ? (
              <div className="site-footer__bottom" dangerouslySetInnerHTML={{ __html: bottomHtml }} />
            ) : null}
          </>
        ) : (
          <div className="site-footer__placeholder">添加栏目或底栏 HTML 后，这里会实时展示最终页脚。</div>
        )}
      </div>
    </footer>
  )
}

export default SiteFooter
