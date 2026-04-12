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
  artifactManifest: {},
  reportIrSummary: {},
  structuredResultDigest: {},
  approvals: [],
  runState: {
    runtime_mode: 'deep-report-coordinator',
    checkpoint_backend: 'sqlite',
    checkpoint_locator: 'f:/opinion-system/backend/data/_report/checkpoints/deep-report-coordinator.sqlite',
    langsmith_enabled: true,
    langsmith_project: 'opinion-system-report'
  },
  orchestratorState: {},
  todos: [
    { id: 'scope', label: '范围确认', status: 'completed' },
    { id: 'retrieval', label: '检索路由', status: 'running' }
  ],
  subagents: [{ id: 'retrieval_router', status: 'running', message: '检索中' }],
  events: [
    { event_id: 1, type: 'phase.started', ts: '2026-04-10T10:00:00Z', message: '开始并行调研' },
    { event_id: 2, type: 'todo.updated', ts: '2026-04-11T12:23:00Z', agent: 'report_coordinator', message: '总控代理更新了任务清单（2 项）。', payload: { todos: [{ id: 'scope', label: '范围确认', status: 'completed' }, { id: 'retrieval', label: '检索路由', status: 'running' }] } }
  ]
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
  it('keeps result navigation disabled without thread even if artifacts look ready', async () => {
    mockState.threadId = ''
    mockState.artifactManifest = {
      structured_projection: { status: 'ready' },
      full_markdown: { status: 'ready' }
    }
    const wrapper = shallowMount(ReportGenerationRun, {
      global: {
        stubs: { AppSelect: true, Transition: false }
      }
    })

    const buttons = wrapper.findAll('button')
    const resultButton = buttons.find((item) => item.text().includes('语义报告'))
    const fullButton = buttons.find((item) => item.text().includes('正式文稿'))

    expect(resultButton.attributes('disabled')).toBeDefined()
    expect(fullButton.attributes('disabled')).toBeDefined()

    mockState.threadId = 'thread-1'
    mockState.artifactManifest = {}
  })

  it('renders the narrative sidebar panels in the run console', () => {
    const wrapper = shallowMount(ReportGenerationRun, {
      global: {
        stubs: { AppSelect: true, Transition: false }
      }
    })

    expect(wrapper.text()).toContain('阶段进度')
    expect(wrapper.text()).toContain('运行状态')
    expect(wrapper.text()).toContain('裁决摘要')
    expect(wrapper.text()).toContain('当前产物')
    expect(wrapper.text()).toContain('审批与恢复')
    expect(wrapper.text()).toContain('运行诊断')
    expect(wrapper.text()).toContain('Deep Coordinator')
    expect(wrapper.text()).toContain('SQLITE')
    expect(wrapper.text()).not.toContain('执行节点明细')
  })

  it('does not enable result navigation from topic and date alone', () => {
    mockState.threadId = 'thread-1'
    mockState.artifactManifest = {}
    const wrapper = shallowMount(ReportGenerationRun, {
      global: {
        stubs: { AppSelect: true, Transition: false }
      }
    })

    const buttons = wrapper.findAll('button')
    const resultButton = buttons.find((item) => item.text().includes('语义报告'))
    const fullButton = buttons.find((item) => item.text().includes('正式文稿'))

    expect(resultButton.attributes('disabled')).toBeDefined()
    expect(fullButton.attributes('disabled')).toBeDefined()
  })

  it('surfaces typed approval requirements in the run header', () => {
    mockState.approvals = [{ approval_id: 'approval-1', status: 'pending', tool_name: 'graph_interrupt' }]
    const wrapper = shallowMount(ReportGenerationRun, {
      global: {
        stubs: { AppSelect: true, Transition: false }
      }
    })

    expect(wrapper.text()).toContain('需要介入 (1)')

    mockState.approvals = []
  })

  it('shows the checklist tab inside the debug drawer', async () => {
    const wrapper = shallowMount(ReportGenerationRun, {
      global: {
        stubs: { AppSelect: true, Transition: false }
      }
    })

    const debugButton = wrapper.findAll('button').find((item) => item.text().includes('调试详情'))
    await debugButton.trigger('click')
    const todoTab = wrapper.findAll('button').find((item) => item.text() === '清单')
    await todoTab.trigger('click')

    expect(wrapper.text()).toContain('当前任务清单')
    expect(wrapper.text()).toContain('检索路由')
    expect(wrapper.text()).toContain('总控代理更新了任务清单')
  })
})
