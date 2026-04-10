import { reactive, ref } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() })
}))

const mockState = reactive({
  loading: false,
  creating: false,
  error: '',
  id: 'rp-1',
  threadId: 'thread-1',
  topic: '专题 A',
  start: '2026-04-01',
  end: '2026-04-07',
  mode: 'research',
  status: 'running',
  phase: 'interpret',
  percentage: 42,
  message: '正在调研',
  artifacts: {},
  structuredResultDigest: {},
  approvals: [],
  subagents: [{ id: 'retrieval_router', status: 'running', message: '检索中' }],
  events: [{ event_id: 1, type: 'phase.started', ts: '2026-04-10T10:00:00Z', message: '开始并行调研' }]
})

vi.mock('../../composables/useReportGeneration', () => ({
  useReportGeneration: () => ({
    topicsState: reactive({ loading: false, error: '', options: ['专题 A'] }),
    topicOptions: ref(['专题 A']),
    reportForm: reactive({ topic: '专题 A', start: '2026-04-01', end: '2026-04-07', mode: 'research' }),
    availableRange: reactive({ loading: false, error: '', notice: '', start: '2026-04-01', end: '2026-04-07' }),
    reportState: reactive({ error: '' }),
    historyState: reactive({ loading: false, error: '' }),
    taskState: mockState,
    reportHistory: ref([]),
    selectedHistoryId: ref(''),
    activeTask: ref(mockState),
    loadTopics: vi.fn(),
    loadHistory: vi.fn(),
    createReportTask: vi.fn(),
    loadReportTask: vi.fn(),
    cancelReportTask: vi.fn(),
    retryReportTask: vi.fn(),
    resolveReportApproval: vi.fn(),
    applyHistorySelection: vi.fn()
  })
}))

import ReportGenerationRun from './ReportGenerationRun.vue'

describe('ReportGenerationRun', () => {
  it('renders the single-run console without a permanent agents column', () => {
    const wrapper = shallowMount(ReportGenerationRun, {
      global: {
        stubs: { AppSelect: true, Transition: false }
      }
    })

    expect(wrapper.text()).toContain('Main Timeline')
    expect(wrapper.text()).toContain('Inspector')
    expect(wrapper.text()).not.toContain('执行节点明细')
  })
})
