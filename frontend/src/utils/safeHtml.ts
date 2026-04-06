const ALLOWED_TAGS = new Set([
  'a',
  'abbr',
  'b',
  'blockquote',
  'br',
  'code',
  'del',
  'div',
  'em',
  'figcaption',
  'figure',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'i',
  'img',
  'li',
  'ol',
  'p',
  'pre',
  'small',
  'span',
  'strong',
  'sub',
  'sup',
  'table',
  'tbody',
  'td',
  'th',
  'thead',
  'tr',
  'u',
  'ul',
])

const ALLOWED_ATTRS = new Set([
  'alt',
  'class',
  'height',
  'href',
  'rel',
  'src',
  'style',
  'target',
  'title',
  'width',
])

const URL_ATTRS = new Set(['href', 'src'])

const isAllowedUrl = (value: string) => {
  const normalized = value.trim().toLowerCase()
  return (
    normalized.startsWith('http://') ||
    normalized.startsWith('https://') ||
    normalized.startsWith('mailto:') ||
    normalized.startsWith('tel:') ||
    normalized.startsWith('/') ||
    normalized.startsWith('./') ||
    normalized.startsWith('../') ||
    normalized.startsWith('#') ||
    normalized.startsWith('data:image/')
  )
}

const sanitizeElement = (element: Element) => {
  const tagName = element.tagName.toLowerCase()

  if (!ALLOWED_TAGS.has(tagName)) {
    const shouldRemoveWithChildren = new Set(['script', 'style', 'iframe', 'object', 'embed', 'form', 'meta', 'link'])
    if (shouldRemoveWithChildren.has(tagName)) {
      element.remove()
      return
    }

    const parent = element.parentNode
    if (!parent) {
      element.remove()
      return
    }

    while (element.firstChild) {
      parent.insertBefore(element.firstChild, element)
    }
    parent.removeChild(element)
    return
  }

  for (const attr of Array.from(element.attributes)) {
    const attrName = attr.name.toLowerCase()
    const attrValue = attr.value

    if (attrName.startsWith('on') || !ALLOWED_ATTRS.has(attrName)) {
      element.removeAttribute(attr.name)
      continue
    }

    if (URL_ATTRS.has(attrName) && attrValue && !isAllowedUrl(attrValue)) {
      element.removeAttribute(attr.name)
      continue
    }
  }

  if (tagName === 'a') {
    const target = element.getAttribute('target')
    if (target === '_blank' && !element.getAttribute('rel')) {
      element.setAttribute('rel', 'noopener noreferrer nofollow')
    }
  }
}

export const sanitizeHtml = (html: string) => {
  if (!html.trim() || typeof window === 'undefined') {
    return html
  }

  const parser = new window.DOMParser()
  const documentNode = parser.parseFromString(`<div>${html}</div>`, 'text/html')
  const wrapper = documentNode.body.firstElementChild

  if (!wrapper) {
    return ''
  }

  const elements = Array.from(wrapper.querySelectorAll('*'))
  for (const element of elements) {
    sanitizeElement(element)
  }

  for (const child of Array.from(wrapper.children)) {
    sanitizeElement(child)
  }

  return wrapper.innerHTML
}
