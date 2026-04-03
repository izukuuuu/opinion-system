import { marked } from 'marked'
import DOMPurify from 'dompurify'

const HEADING_PATTERN = /^(#{1,6})\s+(.+)$/

function slugify(text, counts) {
  const base = String(text || '')
    .trim()
    .toLowerCase()
    .replace(/[`*_~[\]()]/g, '')
    .replace(/[^\p{L}\p{N}\s-]/gu, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || 'section'
  const next = (counts.get(base) || 0) + 1
  counts.set(base, next)
  return next === 1 ? base : `${base}-${next}`
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function normalizeAssets(assets) {
  const map = new Map()
  if (!Array.isArray(assets)) return map
  assets.forEach((item) => {
    const key = String(item?.key || '').trim()
    if (!key) return
    map.set(key, {
      key,
      title: String(item?.title || key).trim(),
      dataUrl: String(item?.dataUrl || '').trim(),
      description: String(item?.description || '').trim()
    })
  })
  return map
}

function replaceAssetUrls(markdown, assetMap) {
  return String(markdown || '').replace(/\(report-asset:\/\/([^)]+)\)/g, (full, key) => {
    const asset = assetMap.get(String(key || '').trim())
    if (!asset?.dataUrl) return full
    return `(${asset.dataUrl})`
  })
}

function injectHeadingAnchors(markdown) {
  const counts = new Map()
  return String(markdown || '')
    .split('\n')
    .map((line) => {
      const match = line.match(HEADING_PATTERN)
      if (!match) return line
      const level = match[1].length
      const text = String(match[2] || '').trim()
      const id = slugify(text, counts)
      return `<h${level} id="${id}" class="ai-report-heading ai-report-heading-${level}">${escapeHtml(text)}</h${level}>`
    })
    .join('\n')
}

export function extractMarkdownToc(markdown = '') {
  const counts = new Map()
  return String(markdown || '')
    .split('\n')
    .map((line) => line.match(HEADING_PATTERN))
    .filter(Boolean)
    .map((match) => {
      const level = match[1].length
      const text = String(match[2] || '').trim()
      return {
        level,
        text,
        id: slugify(text, counts)
      }
    })
    .filter((item) => item.level >= 1 && item.level <= 3)
}

export function renderAiReportMarkdown(markdown = '', { assets = [] } = {}) {
  const assetMap = normalizeAssets(assets)
  const resolved = replaceAssetUrls(markdown, assetMap)
  const prepared = injectHeadingAnchors(resolved)
  const rendered = marked.parse(prepared, {
    breaks: true,
    gfm: true
  })
  return DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target', 'rel', 'class', 'id']
  })
}

export function exportableAiMarkdown(markdown = '', { assets = [] } = {}) {
  return replaceAssetUrls(markdown, normalizeAssets(assets))
}
