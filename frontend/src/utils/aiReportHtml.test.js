// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'

import { buildStandaloneAiReportHtml } from './aiReportHtml'

describe('aiReportHtml', () => {
  it('renders standalone html from markdown payload and ignores report_document content', () => {
    const html = buildStandaloneAiReportHtml(
      {
        title: '正式报告',
        subtitle: '副标题',
        rangeText: '2025-01-01 → 2025-01-31',
        markdown: '# 正式报告\n\n## 深层动因\n\n传播结构出现明显分化。',
        report_document: {
          sections: [{ title: '章节判断' }]
        },
        meta: {
          scene_label: '政策行业场景',
          template_name: 'policy_dynamics'
        }
      },
      { lastLoaded: '2026-04-10 12:00:00' }
    )

    expect(html).toContain('正式报告')
    expect(html).toContain('深层动因')
    expect(html).toContain('href="#深层动因"')
    expect(html).toContain('政策行业场景')
    expect(html).not.toContain('章节判断')
  })
})
