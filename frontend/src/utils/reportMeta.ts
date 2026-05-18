export type ReportMeta = {
  schema: 'report.meta.v1'
  title: string
  meta: Record<string, string>
  headings: Array<{ level: string; text: string }>
  text_stats: {
    char_count: number
    token_count_rough: number
    heading_count: number
    h1_count: number
    h2_count: number
    h3_count: number
  }
}

function normalizeWhitespace(value: string) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

export function extractReportMetaFromHtml(html: string): ReportMeta {
  const parser = new DOMParser()
  const doc = parser.parseFromString(String(html || ''), 'text/html')

  const title = normalizeWhitespace(doc.querySelector('title')?.textContent || '')
  const meta: Record<string, string> = {}
  doc.querySelectorAll('meta[name][content]').forEach((node) => {
    const name = normalizeWhitespace(node.getAttribute('name') || '')
    const content = normalizeWhitespace(node.getAttribute('content') || '')
    if (name && content) meta[name] = content
  })
  doc.querySelectorAll('meta[property][content]').forEach((node) => {
    const name = normalizeWhitespace(node.getAttribute('property') || '')
    const content = normalizeWhitespace(node.getAttribute('content') || '')
    if (name && content && !meta[name]) meta[name] = content
  })

  const headings = Array.from(doc.querySelectorAll('h1,h2,h3'))
    .map((node) => ({
      level: node.tagName.toLowerCase(),
      text: normalizeWhitespace(node.textContent || '')
    }))
    .filter((h) => h.text)

  const fullText = normalizeWhitespace(doc.body?.textContent || '')
  const tokens = fullText.split(/[\s，。；、,.!?]+/).filter(Boolean)

  const text_stats = {
    char_count: fullText.length,
    token_count_rough: tokens.length,
    heading_count: headings.length,
    h1_count: headings.filter((h) => h.level === 'h1').length,
    h2_count: headings.filter((h) => h.level === 'h2').length,
    h3_count: headings.filter((h) => h.level === 'h3').length
  }

  return {
    schema: 'report.meta.v1',
    title,
    meta,
    headings,
    text_stats
  }
}

