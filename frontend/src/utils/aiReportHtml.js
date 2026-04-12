import { extractMarkdownToc, renderAiReportMarkdown } from './aiReportMarkdown'

const escapeHtml = (value) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

export function buildStandaloneAiReportHtml(payload, { lastLoaded = '' } = {}) {
  const source = payload && typeof payload === 'object' ? payload : {}
  const markdown = String(source.markdown || '').trim()
  const assets = Array.isArray(source.assets) ? source.assets : []
  const meta = source.meta && typeof source.meta === 'object' ? source.meta : {}
  const toc = extractMarkdownToc(markdown)
  const content = renderAiReportMarkdown(markdown, {
    assets,
    reportIr: source.report_ir || {},
    artifactManifest: source.artifact_manifest || {},
    staticFigures: true
  })
  const title = String(source.title || '正式文稿').trim() || '正式文稿'
  const subtitle = String(source.subtitle || '').trim()
  const metaLines = [
    String(source.rangeText || '').trim(),
    String(meta.scene_label || '').trim(),
    String(meta.template_name || '').trim(),
    lastLoaded ? `导出时间：${lastLoaded}` : ''
  ].filter(Boolean)

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f7fb;
      --surface: rgba(255, 255, 255, 0.96);
      --line: #d9e3ef;
      --text: #122033;
      --muted: #5b6777;
      --brand: #145da0;
      --brand-soft: #e8f1fa;
      --shadow: 0 22px 44px rgba(18, 32, 51, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(20, 93, 160, 0.08), transparent 30%),
        linear-gradient(180deg, #f9fbfe 0%, var(--bg) 100%);
      padding: 32px 18px;
    }
    .shell {
      max-width: 1200px;
      margin: 0 auto;
      display: grid;
      gap: 24px;
    }
    .panel {
      background: var(--surface);
      border: 1px solid rgba(217, 227, 239, 0.96);
      border-radius: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .hero {
      padding: 30px 34px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(232, 241, 250, 0.92) 0%, rgba(255,255,255,0.96) 100%);
    }
    .hero h1 { margin: 0; font-size: 32px; line-height: 1.18; }
    .subtitle { margin: 10px 0 0; color: var(--muted); font-size: 15px; }
    .meta { margin: 14px 0 0; display: flex; flex-wrap: wrap; gap: 8px; }
    .meta span {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      font-size: 12px;
    }
    .layout {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 24px;
      align-items: start;
    }
    .toc {
      position: sticky;
      top: 24px;
      padding: 22px;
    }
    .toc h2 { margin: 0 0 14px; font-size: 14px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); }
    .toc nav { display: grid; gap: 8px; }
    .toc a {
      display: block;
      padding: 10px 12px;
      border-radius: 14px;
      color: var(--text);
      text-decoration: none;
      background: rgba(248, 250, 252, 0.95);
      border: 1px solid transparent;
      font-size: 14px;
    }
    .toc a:hover { border-color: rgba(20, 93, 160, 0.22); background: var(--brand-soft); }
    .report {
      padding: 28px 34px 36px;
    }
    .report .ai-report-heading-1 { font-size: 34px; margin: 0 0 22px; }
    .report .ai-report-heading-2 { font-size: 26px; margin: 34px 0 14px; }
    .report .ai-report-heading-3 { font-size: 20px; margin: 22px 0 10px; }
    .report p, .report li, .report blockquote { line-height: 1.9; font-size: 15px; }
    .report p, .report ul, .report ol, .report table, .report blockquote { margin: 0 0 16px; }
    .report ul, .report ol { padding-left: 22px; }
    .report blockquote {
      padding: 14px 18px;
      border-left: 4px solid rgba(20, 93, 160, 0.4);
      background: rgba(232, 241, 250, 0.55);
      border-radius: 0 18px 18px 0;
      color: var(--muted);
    }
    .report table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid var(--line);
    }
    .report th, .report td {
      padding: 12px 14px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--line);
    }
    .report thead th {
      background: rgba(248, 250, 252, 0.98);
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .report img {
      max-width: 100%;
      display: block;
      border-radius: 20px;
      border: 1px solid var(--line);
      background: #fff;
      margin: 20px auto;
    }
    .report code {
      padding: 2px 6px;
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.06);
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 13px;
    }
    .report .export-figure-card {
      margin: 20px 0;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: rgba(248, 250, 252, 0.96);
      overflow: hidden;
    }
    .report .export-figure-card__header {
      padding: 18px 20px 12px;
      border-bottom: 1px solid var(--line);
    }
    .report .export-figure-card__header h3 {
      margin: 0;
      font-size: 18px;
    }
    .report .export-figure-card__header p {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .report .export-figure-card__body {
      padding: 16px 20px 20px;
    }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .toc { position: static; }
      .hero, .report { padding: 22px; }
      .hero h1, .report .ai-report-heading-1 { font-size: 28px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="panel hero">
      <h1>${escapeHtml(title)}</h1>
      ${subtitle ? `<p class="subtitle">${escapeHtml(subtitle)}</p>` : ''}
      ${metaLines.length ? `<div class="meta">${metaLines.map((item) => `<span>${escapeHtml(item)}</span>`).join('')}</div>` : ''}
    </section>
    <div class="layout">
      <aside class="panel toc">
        <h2>章节导航</h2>
        <nav>
          ${toc.length ? toc.map((item) => `<a href="#${escapeHtml(item.id)}">${escapeHtml(item.text)}</a>`).join('') : '<span>正文未生成目录</span>'}
        </nav>
      </aside>
      <main class="panel report">${content}</main>
    </div>
  </div>
</body>
</html>`
}
