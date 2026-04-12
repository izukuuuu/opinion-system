import { buildFigureContractMap, renderStaticFigureMarkup } from './reportFigures'

const DEFAULT_DOCUMENT = { hero: {}, sections: [], appendix: { blocks: [] } }

const escapeHtml = (value) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const jsonForScript = (value) => JSON.stringify(value ?? {}).replace(/</g, '\\u003c')

const mapById = (items, key) => {
  const map = new Map()
  for (const item of Array.isArray(items) ? items : []) {
    const id = String(item?.[key] || '').trim()
    if (id) map.set(id, item)
  }
  return map
}

const citationAnchorId = (citationId) => `citation-${String(citationId || '').trim()}`

const calloutToneClass = (tone) => {
  if (tone === 'danger') return 'callout callout-danger'
  if (tone === 'warning') return 'callout callout-warning'
  return 'callout callout-info'
}

const joinMeta = (parts) => parts.filter(Boolean).map(escapeHtml).join(' · ')

function renderCitationRefs(citationIds, citationMap) {
  const citations = (Array.isArray(citationIds) ? citationIds : []).map((id) => citationMap.get(String(id || '').trim())).filter(Boolean)
  if (!citations.length) return '<p class="empty-text">当前区块没有可展示的引用。</p>'
  return citations.map((item) => `
    <article id="${escapeHtml(citationAnchorId(item.citation_id))}" class="citation-card">
      <div class="citation-head">
        <div class="stack-sm">
          <div class="inline-row">
            <span class="pill pill-brand">${escapeHtml(item.citation_id)}</span>
            <p class="citation-title">${escapeHtml(item.title || '未命名来源')}</p>
          </div>
          <p class="meta-text">${joinMeta([item.platform, item.published_at, item.source_type]) || '来源信息未完整标注'}</p>
        </div>
        ${item.url ? `<a class="link-pill" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">打开来源</a>` : ''}
      </div>
      ${item.snippet ? `<p class="body-text">${escapeHtml(item.snippet)}</p>` : ''}
    </article>
  `).join('')
}

function renderSectionBlock(block, context) {
  if (!block || typeof block !== 'object') return ''
  const {
    figureMap,
    evidenceMap,
    timelineMap,
    subjectMap,
    stanceRows,
    riskMap,
    actionMap,
    citationMap
  } = context

  if (block.type === 'narrative') {
    const citations = Array.isArray(block.citation_ids) && block.citation_ids.length
      ? `<div class="citation-pills">${block.citation_ids.map((id) => `<a class="pill-link" href="#${escapeHtml(citationAnchorId(id))}">${escapeHtml(id)}</a>`).join('')}</div>`
      : ''
    return `
      <section class="content-card">
        ${block.title ? `<p class="eyebrow">${escapeHtml(block.title)}</p>` : ''}
        <p class="body-text">${escapeHtml(block.content || '当前区块暂无正文内容。')}</p>
        ${citations}
      </section>
    `
  }

  if (block.type === 'bullets') {
    const items = Array.isArray(block.items) ? block.items : []
    return `
      <section class="content-card">
        ${block.title ? `<p class="eyebrow">${escapeHtml(block.title)}</p>` : ''}
        ${items.length
          ? `<ul class="bullet-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
          : '<p class="empty-text">当前区块暂无要点。</p>'}
      </section>
    `
  }

  if (block.type === 'figure_ref') {
    const figure = figureMap.get(String(block.figure_id || '').trim())
    return figure ? renderStaticFigureMarkup(figure) : '<p class="empty-card">当前区块没有可展示的图表。</p>'
  }

  if (block.type === 'evidence_list') {
    const evidence = (Array.isArray(block.evidence_ids) ? block.evidence_ids : []).map((id) => evidenceMap.get(String(id || '').trim())).filter(Boolean)
    return `
      <section class="content-card">
        <p class="eyebrow">${escapeHtml(block.title || '关键证据')}</p>
        ${evidence.length ? evidence.map((item) => `
          <article class="nested-card">
            <p class="item-title">${escapeHtml(item.finding)}</p>
            ${item.source_summary ? `<p class="body-muted">${escapeHtml(item.source_summary)}</p>` : ''}
            <div class="pill-row">
              ${[item.subject, item.stance, item.time_label, item.confidence].filter(Boolean).map((badge) => `<span class="pill">${escapeHtml(badge)}</span>`).join('')}
            </div>
          </article>
        `).join('') : '<p class="empty-text">当前区块没有可展示的证据。</p>'}
      </section>
    `
  }

  if (block.type === 'timeline_list') {
    const events = (Array.isArray(block.event_ids) ? block.event_ids : []).map((id) => timelineMap.get(String(id || '').trim())).filter(Boolean)
    return `
      <section class="content-card">
        <p class="eyebrow">${escapeHtml(block.title || '关键节点')}</p>
        ${events.length ? events.map((item) => `
          <article class="nested-card">
            <div class="item-head">
              <div class="stack-xs">
                <p class="item-title">${escapeHtml(item.title)}</p>
                ${item.date ? `<p class="meta-text">${escapeHtml(item.date)}</p>` : ''}
              </div>
              <div class="pill-row">
                ${[item.trigger, item.impact].filter(Boolean).map((badge) => `<span class="pill">${escapeHtml(badge)}</span>`).join('')}
              </div>
            </div>
            ${item.description ? `<p class="body-muted">${escapeHtml(item.description)}</p>` : ''}
          </article>
        `).join('') : '<p class="empty-text">当前区块没有可展示的时间线。</p>'}
      </section>
    `
  }

  if (block.type === 'subject_cards') {
    const subjects = (Array.isArray(block.subject_ids) ? block.subject_ids : []).map((id) => subjectMap.get(String(id || '').trim())).filter(Boolean)
    return `
      <section class="content-card">
        <p class="eyebrow">${escapeHtml(block.title || '主体列表')}</p>
        ${subjects.length ? `<div class="two-col-grid">${subjects.map((item) => `
          <article class="nested-card">
            <div class="item-head">
              <div class="stack-xs">
                <p class="item-title">${escapeHtml(item.name)}</p>
                ${item.summary ? `<p class="meta-text">${escapeHtml(item.summary)}</p>` : ''}
              </div>
              <div class="pill-row">
                ${[item.category, item.role].filter(Boolean).map((badge) => `<span class="pill">${escapeHtml(badge)}</span>`).join('')}
              </div>
            </div>
          </article>
        `).join('')}</div>` : '<p class="empty-text">当前区块没有可展示的主体。</p>'}
      </section>
    `
  }

  if (block.type === 'stance_matrix') {
    const names = new Set((Array.isArray(block.subject_names) ? block.subject_names : []).map((item) => String(item || '').trim()).filter(Boolean))
    const rows = names.size
      ? stanceRows.filter((item) => names.has(String(item?.subject || '').trim()))
      : stanceRows
    return `
      <section class="content-card">
        <p class="eyebrow">${escapeHtml(block.title || '立场矩阵')}</p>
        ${rows.length ? `
          <div class="table-shell">
            <table>
              <thead>
                <tr><th>主体</th><th>立场</th><th>说明</th></tr>
              </thead>
              <tbody>
                ${rows.map((item) => `
                  <tr>
                    <td>${escapeHtml(item.subject || '--')}</td>
                    <td>${escapeHtml(item.stance || '--')}</td>
                    <td>${escapeHtml(item.summary || '--')}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        ` : '<p class="empty-text">当前区块没有可展示的立场矩阵。</p>'}
      </section>
    `
  }

  if (block.type === 'risk_list') {
    const risks = (Array.isArray(block.risk_ids) ? block.risk_ids : []).map((id) => riskMap.get(String(id || '').trim())).filter(Boolean)
    return `
      <section class="content-card">
        <p class="eyebrow">${escapeHtml(block.title || '风险判断')}</p>
        ${risks.length ? risks.map((item) => `
          <article class="nested-card">
            <div class="item-head">
              <div class="stack-xs">
                <p class="item-title">${escapeHtml(item.label)}</p>
                ${item.summary ? `<p class="body-muted">${escapeHtml(item.summary)}</p>` : ''}
              </div>
              <span class="pill pill-warning">${escapeHtml(item.level || 'medium')}</span>
            </div>
          </article>
        `).join('') : '<p class="empty-text">当前区块没有可展示的风险。</p>'}
      </section>
    `
  }

  if (block.type === 'action_list') {
    const actions = (Array.isArray(block.action_ids) ? block.action_ids : []).map((id) => actionMap.get(String(id || '').trim())).filter(Boolean)
    return `
      <section class="content-card">
        <p class="eyebrow">${escapeHtml(block.title || '建议动作')}</p>
        ${actions.length ? actions.map((item) => `
          <article class="nested-card">
            <div class="item-head">
              <div class="stack-xs">
                <p class="item-title">${escapeHtml(item.action)}</p>
                ${item.rationale ? `<p class="body-muted">${escapeHtml(item.rationale)}</p>` : ''}
              </div>
              <span class="pill pill-brand">${escapeHtml(item.priority || 'medium')}</span>
            </div>
          </article>
        `).join('') : '<p class="empty-text">当前区块没有可展示的建议动作。</p>'}
      </section>
    `
  }

  if (block.type === 'citation_refs') {
    return `
      <section class="stack-md">
        <div class="stack-xs">
          <p class="eyebrow">${escapeHtml(block.title || '引用索引')}</p>
          <p class="body-muted">可直接核对来源标题、时间和摘录。</p>
        </div>
        ${renderCitationRefs(block.citation_ids, citationMap)}
      </section>
    `
  }

  if (block.type === 'callout') {
    return `
      <section class="${calloutToneClass(block.tone)}">
        ${block.title ? `<p class="eyebrow">${escapeHtml(block.title)}</p>` : ''}
        <p class="body-text">${escapeHtml(block.content || '当前提示区块没有内容。')}</p>
      </section>
    `
  }

  return ''
}

export function buildStandaloneReportHtml(payload, { lastLoaded = '' } = {}) {
  const source = payload && typeof payload === 'object' ? payload : {}
  const reportData = source.report_data && typeof source.report_data === 'object' ? source.report_data : source
  const document = source.report_document && typeof source.report_document === 'object' ? source.report_document : DEFAULT_DOCUMENT
  const reportIr = source.report_ir && typeof source.report_ir === 'object' ? source.report_ir : {}
  const artifactManifest = source.artifact_manifest && typeof source.artifact_manifest === 'object' ? source.artifact_manifest : {}
  const figureMap = buildFigureContractMap(reportIr, artifactManifest)
  const evidenceMap = mapById(reportData.key_evidence, 'evidence_id')
  const timelineMap = mapById(reportData.timeline, 'event_id')
  const subjectMap = mapById(reportData.subjects, 'subject_id')
  const riskMap = mapById(reportData.risk_judgement, 'risk_id')
  const actionMap = mapById(reportData.suggested_actions, 'action_id')
  const citationMap = mapById(reportData.citations, 'citation_id')
  const stanceRows = Array.isArray(reportData.stance_matrix) ? reportData.stance_matrix : []

  const hero = document.hero && typeof document.hero === 'object' ? document.hero : {}
  const sections = Array.isArray(document.sections) ? document.sections : []
  const appendix = document.appendix && typeof document.appendix === 'object' ? document.appendix : { blocks: [] }
  const title = source.title || hero.title || reportData?.task?.topic_label || '正式文稿'
  const subtitle = source.subtitle || hero.subtitle || source.rangeText || ''

  const body = `
    <section class="hero">
      <div class="stack-md">
        <div class="stack-xs">
          <p class="eyebrow">统一结构化报告</p>
          <h1>${escapeHtml(hero.title || title)}</h1>
          <p class="hero-subtitle">${escapeHtml(hero.subtitle || subtitle)}</p>
        </div>
        <section class="hero-summary">
          <p class="eyebrow">结论摘要</p>
          <p class="body-text">${escapeHtml(hero.summary || '当前结果没有独立摘要。')}</p>
          ${Array.isArray(hero.risks) && hero.risks.length ? `<div class="pill-row">${hero.risks.map((item) => `<span class="pill pill-warning">${escapeHtml(item)}</span>`).join('')}</div>` : ''}
        </section>
        ${Array.isArray(hero.metrics) && hero.metrics.length ? `
          <div class="metrics-grid">
            ${hero.metrics.map((metric) => `
              <article class="metric-card">
                <p class="eyebrow">${escapeHtml(metric.label)}</p>
                <p class="metric-value">${escapeHtml(metric.value || '--')}</p>
                ${metric.detail ? `<p class="meta-text">${escapeHtml(metric.detail)}</p>` : ''}
              </article>
            `).join('')}
          </div>
        ` : ''}
      </div>
    </section>
    ${sections.map((section) => `
      <section id="${escapeHtml(section.section_id)}" class="report-section">
        <header class="section-head">
          ${section.kicker ? `<p class="eyebrow">${escapeHtml(section.kicker)}</p>` : ''}
          <h2>${escapeHtml(section.title || '未命名章节')}</h2>
          ${section.summary ? `<p class="body-muted">${escapeHtml(section.summary)}</p>` : ''}
        </header>
        <div class="section-body">
          ${(Array.isArray(section.blocks) ? section.blocks : []).map((block) =>
            renderSectionBlock(block, {
              figureMap,
              evidenceMap,
              timelineMap,
              subjectMap,
              stanceRows,
              riskMap,
              actionMap,
              citationMap
            })
          ).join('')}
        </div>
      </section>
    `).join('')}
    ${Array.isArray(appendix.blocks) && appendix.blocks.length ? `
      <section class="report-section">
        <header class="section-head">
          <p class="eyebrow">附录</p>
          <h2>${escapeHtml(appendix.title || '引用与校验')}</h2>
        </header>
        <div class="section-body">
          ${appendix.blocks.map((block) =>
            renderSectionBlock(block, {
              figureMap,
              evidenceMap,
              timelineMap,
              subjectMap,
              stanceRows,
              riskMap,
              actionMap,
              citationMap
            })
          ).join('')}
        </div>
      </section>
    ` : ''}
  `

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f7fb;
      --surface: #ffffff;
      --surface-soft: #f8fafc;
      --line: #dbe5f0;
      --text: #102033;
      --muted: #526173;
      --brand: #0f6cbd;
      --brand-soft: #e7f1fb;
      --warning: #a15c00;
      --warning-soft: #fff4de;
      --danger: #9f1239;
      --danger-soft: #fee2e2;
      --shadow: 0 20px 40px rgba(15, 32, 51, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 40px 20px;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(15,108,189,0.08), transparent 28%),
        linear-gradient(180deg, #f7fbff 0%, var(--bg) 100%);
      color: var(--text);
    }
    .page {
      max-width: 1180px;
      margin: 0 auto;
      display: grid;
      gap: 24px;
    }
    .shell {
      background: rgba(255,255,255,0.92);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(219,229,240,0.95);
      border-radius: 28px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }
    .head {
      padding: 28px 32px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(231,241,251,0.9) 0%, rgba(255,255,255,0.92) 100%);
    }
    .head h1 { margin: 0; font-size: 28px; line-height: 1.2; }
    .head p { margin: 8px 0 0; color: var(--muted); }
    .content { padding: 28px; display: grid; gap: 24px; }
    .hero, .report-section, .content-card, .chart-card, .nested-card, .citation-card, .callout {
      border: 1px solid var(--line);
      border-radius: 24px;
      background: var(--surface);
    }
    .hero, .report-section { padding: 24px; }
    .hero-summary, .content-card { padding: 20px; background: linear-gradient(180deg, rgba(248,250,252,0.95), rgba(255,255,255,0.95)); }
    .nested-card, .citation-card { padding: 16px; background: var(--surface); }
    .callout { padding: 18px 20px; }
    .callout-info { background: rgba(231,241,251,0.7); }
    .callout-warning { background: var(--warning-soft); color: var(--warning); }
    .callout-danger { background: var(--danger-soft); color: var(--danger); }
    .metrics-grid, .two-col-grid { display: grid; gap: 16px; }
    .metrics-grid { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
    .two-col-grid { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
    .metric-card {
      padding: 18px;
      border-radius: 20px;
      border: 1px solid var(--line);
      background: var(--surface-soft);
    }
    .metric-value { margin: 10px 0 0; font-size: 30px; font-weight: 700; }
    .hero h1, .report-section h2 { margin: 0; line-height: 1.2; }
    .hero h1 { font-size: 34px; }
    .report-section h2 { font-size: 24px; }
    .hero-subtitle { margin: 0; color: var(--muted); font-size: 15px; }
    .section-head, .stack-md, .section-body, .stack-sm, .stack-xs { display: grid; }
    .section-head, .stack-md, .section-body { gap: 16px; }
    .stack-sm { gap: 10px; }
    .stack-xs { gap: 6px; }
    .eyebrow {
      margin: 0;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-weight: 700;
      color: var(--muted);
    }
    .body-text, .body-muted, .meta-text, .chart-title, .item-title, .citation-title {
      margin: 0;
      line-height: 1.85;
    }
    .body-text { font-size: 15px; }
    .body-muted, .meta-text { color: var(--muted); font-size: 14px; }
    .item-title, .chart-title, .citation-title, .block-title { font-size: 16px; font-weight: 700; margin: 0; }
    .item-head, .citation-head, .inline-row {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .pill-row, .citation-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    .pill, .pill-link, .link-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 28px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--muted);
      font-size: 12px;
      text-decoration: none;
    }
    .pill-brand { background: var(--brand-soft); border-color: transparent; color: var(--brand); }
    .pill-warning { background: var(--warning-soft); border-color: transparent; color: var(--warning); }
    .pill-link:hover, .link-pill:hover { border-color: rgba(15,108,189,0.3); color: var(--brand); }
    .bullet-list {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 10px;
    }
    .bullet-list li {
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: var(--surface);
      line-height: 1.8;
    }
    .chart-empty, .empty-card, .empty-text, .export-figure-card {
      padding: 16px;
      border-radius: 18px;
      border: 1px dashed var(--line);
      color: var(--muted);
      background: rgba(248,250,252,0.7);
    }
    .table-shell {
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--surface);
    }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    thead { background: var(--surface-soft); color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; font-size: 12px; }
    th, td { padding: 12px 14px; text-align: left; vertical-align: top; }
    tbody tr + tr td { border-top: 1px solid var(--line); }
    @media (max-width: 720px) {
      body { padding: 18px 10px; }
      .head, .content, .hero, .report-section { padding: 20px; }
      .hero h1 { font-size: 28px; }
      .report-section h2 { font-size: 22px; }
      .chart-canvas { height: 260px; }
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="shell">
      <header class="head">
        <h1>${escapeHtml(title)}</h1>
        <p>${escapeHtml(subtitle)}</p>
        ${lastLoaded ? `<p>导出时间：${escapeHtml(lastLoaded)}</p>` : ''}
      </header>
      <main class="content">
        ${body}
      </main>
    </div>
  </div>
</body>
</html>`
}
