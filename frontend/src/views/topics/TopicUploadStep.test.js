import { describe, expect, it } from 'vitest'
import {
  buildNetInsightTaskPayload,
  createNetInsightTaskFormState,
  defaultPlatformsForScope,
  applyNetInsightTaskPlan,
  setNetInsightTaskScope,
} from '../../composables/useNetInsightTaskForm'

describe('TopicUploadStep acquisition task form helpers', () => {
  it('locks submission payload to the current topic', () => {
    const form = createNetInsightTaskFormState()
    form.title = '控烟舆情 数据采集'
    form.project = '不应使用的项目'
    form.brief = '国内控烟舆情'
    form.keywordsText = '控烟\n二手烟'
    form.startDate = '2026-05-01'
    form.endDate = '2026-05-15'

    const payload = buildNetInsightTaskPayload(form, {
      project: '控烟舆情',
      auto_import_project: true,
    })

    expect(payload.project).toBe('控烟舆情')
    expect(payload.auto_import_project).toBe(true)
    expect(payload.keywords).toEqual(['控烟', '二手烟'])
  })

  it('uses explicit platform checkboxes for global scope', () => {
    const form = createNetInsightTaskFormState()

    setNetInsightTaskScope(form, 'global')

    expect(form.platforms).toEqual(defaultPlatformsForScope('global'))
    expect(form.platforms).toContain('微博')
    expect(form.platforms).toContain('Facebook')
    expect(form.platforms).not.toContain('全部')
  })

  it('applies recommendation results without requiring a project selector', () => {
    const form = createNetInsightTaskFormState()
    form.project = '专题A'

    applyNetInsightTaskPlan(form, {
      scope: 'foreign',
      keywords: ['电子烟监管'],
      platforms: ['境外新闻', 'Twitter'],
      start_date: '2026-05-01',
      end_date: '2026-05-15',
    })

    expect(form.project).toBe('专题A')
    expect(form.scope).toBe('foreign')
    expect(form.keywordsText).toBe('电子烟监管')
    expect(form.platforms).toEqual(['境外新闻', 'Twitter'])
  })
})
