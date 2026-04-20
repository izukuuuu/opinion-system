import { createApp } from 'vue'

function normalizeRow(row) {
  return row && typeof row === 'object' ? row : {}
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

let chartFigureComponentPromise = null

function loadChartFigureComponent() {
  if (!chartFigureComponentPromise) {
    chartFigureComponentPromise = import('../components/report/ChartFigure.vue').then((module) => module.default)
  }
  return chartFigureComponentPromise
}

export function buildFigureContractMap(reportIr = {}, artifactManifest = {}) {
  const figures = Array.isArray(reportIr?.figures) ? reportIr.figures : []
  const artifacts = Array.isArray(artifactManifest?.figures) ? artifactManifest.figures : []
  const artifactMap = new Map(
    artifacts
      .map((item) => [String(item?.figure_id || '').trim(), item])
      .filter(([id]) => id)
  )
  const map = new Map()
  figures.forEach((figure) => {
    const figureId = String(figure?.figure_id || '').trim()
    if (!figureId) return
    const artifact = artifactMap.get(figureId) || {}
    const dataset = artifact?.dataset && typeof artifact.dataset === 'object' ? artifact.dataset : {}
    const optionArtifact = artifact?.option && typeof artifact.option === 'object' ? artifact.option : {}
    const rows = Array.isArray(dataset?.rows) ? dataset.rows.map(normalizeRow) : []
    const previewRows = Array.isArray(dataset?.preview_rows) ? dataset.preview_rows.map(normalizeRow) : rows.slice(0, 12)
    map.set(figureId, {
      figure_id: figureId,
      caption: String(artifact?.caption || figure?.caption || '').trim() || '图表',
      chartType: String(artifact?.chart_spec?.chart_type || figure?.chart_type || '').trim(),
      option: optionArtifact?.option && typeof optionArtifact.option === 'object' ? optionArtifact.option : {},
      allRows: rows,
      previewRows,
      hasData: Boolean(rows.length && Object.keys(optionArtifact?.option || {}).length),
      emptyMessage: String(artifact?.chart_spec?.blocked_reason || '暂无可视化数据').trim() || '暂无可视化数据',
      renderStatus: String(artifact?.render_status || figure?.render_status || '').trim() || 'ready'
    })
  })
  return map
}

export function replaceFigureDirectives(markdown = '') {
  return String(markdown || '').replace(/::figure\{ref="([^"]+)"\}/g, (_, figureId) => {
    const safeId = String(figureId || '').trim()
    return safeId ? `<div class="report-figure-placeholder" data-report-figure="${escapeHtml(safeId)}"></div>` : ''
  })
}

export function renderStaticFigureMarkup(contract) {
  if (!contract) return ''
  const rows = Array.isArray(contract.previewRows) ? contract.previewRows : []
  const preview = rows.length
    ? `<ul class="report-figure-static__rows">${rows
        .slice(0, 8)
        .map((row) => `<li>${escapeHtml(row?.name || row?.label || row?.source || '未命名')}：${escapeHtml(row?.value ?? row?.target ?? '--')}</li>`)
        .join('')}</ul>`
    : `<p class="report-figure-static__empty">${escapeHtml(contract.emptyMessage || '当前图表暂无可展示数据。')}</p>`
  return `
    <figure class="report-figure-static" data-report-figure="${escapeHtml(contract.figure_id)}">
      <div class="report-figure-static__canvas">图表导出预览</div>
      ${preview}
      <figcaption class="report-figure-static__caption">${escapeHtml(contract.caption)}</figcaption>
    </figure>
  `
}

export function replaceFigureDirectivesWithStaticMarkup(markdown = '', contractMap = new Map()) {
  return String(markdown || '').replace(/::figure\{ref="([^"]+)"\}/g, (_, figureId) => {
    const contract = contractMap.get(String(figureId || '').trim())
    return contract ? renderStaticFigureMarkup(contract) : ''
  })
}

export async function hydrateFigurePlaceholders(root, contractMap = new Map()) {
  if (!root || typeof root.querySelectorAll !== 'function') return
  const ChartFigure = await loadChartFigureComponent()
  const placeholders = root.querySelectorAll('[data-report-figure]')
  placeholders.forEach((node) => {
    const figureId = String(node.getAttribute('data-report-figure') || '').trim()
    const contract = contractMap.get(figureId)
    if (!contract) return
    if (node.__figureApp) {
      node.__figureApp.unmount()
      node.__figureApp = null
    }
    const app = createApp(ChartFigure, { contract })
    app.mount(node)
    node.__figureApp = app
  })
}

export function destroyFigurePlaceholders(root) {
  if (!root || typeof root.querySelectorAll !== 'function') return
  root.querySelectorAll('[data-report-figure]').forEach((node) => {
    if (node.__figureApp) {
      node.__figureApp.unmount()
      node.__figureApp = null
    }
  })
}
