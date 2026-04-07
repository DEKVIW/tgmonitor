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

const resolveFooterTemplate = (template: string, variables: Record<string, string>) =>
  template.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, rawKey: string) => variables[rawKey] ?? '')

const SiteFooter = ({ config, preview = false }: SiteFooterProps) => {
  const liveFooterConfig = useSiteFooterConfig()
  const footerConfig = config ? extractSiteFooterConfig(config) : liveFooterConfig
  const templateVariables = useMemo(
    () => ({
      current_year: String(new Date().getFullYear()),
      site_name: footerConfig.site_name,
    }),
    [footerConfig.site_name]
  )

  const sections = useMemo(
    () =>
      footerConfig.footer_builder_sections.map((section) => ({
        ...section,
        resolvedTitle: resolveFooterTemplate(section.title, templateVariables),
        sanitizedHtml: sanitizeHtml(resolveFooterTemplate(section.html, templateVariables)),
      })),
    [footerConfig.footer_builder_sections, templateVariables]
  )

  const visibleSections = useMemo(
    () => sections.filter((section) => section.resolvedTitle || section.sanitizedHtml.trim()),
    [sections]
  )

  const bottomHtml = useMemo(
    () => sanitizeHtml(resolveFooterTemplate(footerConfig.footer_builder_bottom_html, templateVariables)),
    [footerConfig.footer_builder_bottom_html, templateVariables]
  )

  if (!footerConfig.footer_builder_enabled && !preview) {
    return null
  }

  const hasVisibleContent = visibleSections.length > 0 || bottomHtml.trim()

  if (!hasVisibleContent && !preview) {
    return null
  }

  return (
    <footer className={`site-footer ${preview ? 'site-footer--preview' : ''}`}>
      <div className="site-footer__inner">
        <div className="site-footer__rail" />

        {hasVisibleContent ? (
          <>
            {visibleSections.length ? (
              <div className="site-footer__grid">
                {visibleSections.map((section) => (
                  <section
                    key={section.id}
                    className="site-footer__column"
                    style={{ '--footer-span': String(section.span) } as CSSProperties}
                  >
                    {section.resolvedTitle ? <h3 className="site-footer__title">{section.resolvedTitle}</h3> : null}
                    {section.sanitizedHtml.trim() ? (
                      <div
                        className="site-footer__html"
                        dangerouslySetInnerHTML={{ __html: section.sanitizedHtml }}
                      />
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
