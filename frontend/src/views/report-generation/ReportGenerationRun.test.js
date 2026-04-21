import { defineComponent, reactive, ref } from 'vue'
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
  resumeCapabilities: {},
  parentTaskId: '',
  resumeKind: '',
  resumeSourceTaskId: '',
  resumeSourcePhase: '',
  resumeSourceActor: '',
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
    { event_id: 2, type: 'todo.updated', ts: '2026-04-11T12:23:00Z', agent: 'report_coordinator', message: '总控代理更新了任务清单（2 项）。', payload: { todos: [{ id: 'scope', label: '范围确认', status: 'completed' }, { id: 'retrieval', label: '检索路由', status: 'running' }] } },
    { event_id: 3, type: 'agent.memo', ts: '2026-04-11T12:24:00Z', agent: 'writer', message: 'writer 更新了内部执行计划，但不会覆盖主流程清单。', payload: { stage_id: 'agent_todo', todos: [{ id: 'overview', label: '写入 overview.json', status: 'running' }, { id: 'timeline', label: '写入 timeline.json', status: 'pending' }] } }
  ]
})

const retryReportTask = vi.fn()
const resumeBeforeFailureReportTask = vi.fn()
const resolveReportApproval = vi.fn()

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
    retryReportTask,
    resumeBeforeFailureReportTask,
    resolveReportApproval,
    applyHistorySelection: vi.fn()
  })
}))

import ReportGenerationRun from './ReportGenerationRun.vue'

const TabSwitchStub = defineComponent({
  props: {
    tabs: { type: Array, default: () => [] },
    active: { type: String, default: '' }
  },
  emits: ['change'],
  template: `
    <div>
      <button
        v-for="tab in tabs"
        :key="tab.value"
        type="button"
        @click="$emit('change', tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>
  `
})

const mountOptions = {
  global: {
    stubs: {
      AppSelect: true,
      Transition: false,
      TabSwitch: TabSwitchStub
    }
  }
}

describe('ReportGenerationRun', () => {
  it('allows result navigation from ready historical artifacts even without thread', async () => {
    mockState.threadId = ''
    mockState.artifactManifest = {
      structured_projection: { status: 'ready' },
      full_markdown: { status: 'ready' }
    }
    const wrapper = shallowMount(ReportGenerationRun, mountOptions)

    const buttons = wrapper.findAll('button')
    const resultButton = buttons.find((item) => item.text().includes('语义报告'))
    const fullButton = buttons.find((item) => item.text().includes('正式文稿'))

    expect(resultButton.attributes('disabled')).toBeUndefined()
    expect(fullButton.attributes('disabled')).toBeUndefined()

    mockState.threadId = 'thread-1'
    mockState.artifactManifest = {}
  })

  it('renders the narrative sidebar panels in the run console', () => {
    const wrapper = shallowMount(ReportGenerationRun, mountOptions)

    expect(wrapper.text()).toContain('阶段进度')
    expect(wrapper.text()).toContain('运行状态')
    expect(wrapper.text()).toContain('进展判断')
    expect(wrapper.text()).toContain('生成结果')
    expect(wrapper.text()).toContain('人工确认')
    expect(wrapper.text()).toContain('运行详情')
    expect(wrapper.text()).toContain('深度分析主控')
    expect(wrapper.text()).toContain('SQLITE')
    expect(wrapper.text()).not.toContain('执行节点明细')
  })

  it('does not enable result navigation from topic and date alone', () => {
    mockState.threadId = 'thread-1'
    mockState.artifactManifest = {}
    const wrapper = shallowMount(ReportGenerationRun, mountOptions)

    const buttons = wrapper.findAll('button')
    const resultButton = buttons.find((item) => item.text().includes('语义报告'))
    const fullButton = buttons.find((item) => item.text().includes('正式文稿'))

    expect(resultButton.attributes('disabled')).toBeDefined()
    expect(fullButton.attributes('disabled')).toBeDefined()
  })

  it('surfaces typed approval requirements in the run header', () => {
    mockState.approvals = [{ approval_id: 'approval-1', status: 'pending', tool_name: 'graph_interrupt' }]
    const wrapper = shallowMount(ReportGenerationRun, mountOptions)

    expect(wrapper.text()).toContain('需要介入 (1)')

    mockState.approvals = []
  })

  it('shows the checklist tab inside the debug drawer', async () => {
    const wrapper = shallowMount(ReportGenerationRun, mountOptions)

    const debugButton = wrapper.findAll('button').find((item) => item.text().includes('调试详情'))
    await debugButton.trigger('click')
    const todoTab = wrapper.findAll('button').find((item) => item.text() === '清单')
    await todoTab.trigger('click')

    expect(wrapper.text()).toContain('总控任务清单')
    expect(wrapper.text()).toContain('当前子代理计划')
    expect(wrapper.text()).toContain('检索路由')
    expect(wrapper.text()).toContain('写入 overview.json')
    expect(wrapper.text()).toContain('总控代理更新了任务清单')
    expect(wrapper.text()).toContain('writer 更新了内部执行计划')
  })

  it('shows and triggers resume-before-failure when capability is enabled', async () => {
    mockState.status = 'failed'
    mockState.resumeCapabilities = {
      resume_before_failure: {
        enabled: true,
        restart_phase: 'compile',
        source_phase: 'compile'
      }
    }
    const wrapper = shallowMount(ReportGenerationRun, mountOptions)

    const resumeButton = wrapper.findAll('button').find((item) => item.text().includes('从失败前继续'))
    expect(resumeButton).toBeTruthy()
    await resumeButton.trigger('click')
    expect(resumeBeforeFailureReportTask).toHaveBeenCalled()

    mockState.status = 'running'
    mockState.resumeCapabilities = {}
  })

  it('submits structured rewrite feedback when approval requests revision', async () => {
    mockState.approvals = [{
      approval_id: 'approval-annotation',
      status: 'pending',
      tool_name: 'graph_interrupt',
      action: {
        markdown_preview: '# 预览文稿',
        review_mode: 'annotation',
        review_placeholder: '请输入批注',
        semantic_interrupt: {
          rewrite_round: 1,
          allowed_rewrite_ops: ['delete_untraced', 'rephrase'],
          offending_unit_ids: ['unit-1']
        }
      }
    }]
    const wrapper = shallowMount(ReportGenerationRun, mountOptions)

    const debugButton = wrapper.findAll('button').find((item) => item.text().includes('调试详情'))
    await debugButton.trigger('click')
    const approvalTab = wrapper.findAll('button').find((item) => item.text() === '审批')
    await approvalTab.trigger('click')

    expect(wrapper.text()).toContain('文稿预览')
    expect(wrapper.text()).toContain('重写批注')
    const textarea = wrapper.find('textarea')
    await textarea.setValue('这里补充边界说明')
    const rewriteButton = wrapper.findAll('button').find((item) => item.text().includes('要求重写'))
    await rewriteButton.trigger('click')

    expect(resolveReportApproval).toHaveBeenCalledWith(
      'rp-1',
      'approval-annotation',
      {
        decision: 'rewrite',
        review_payload: {
          comment: '这里补充边界说明',
          rewrite_focus: [],
          must_keep: [],
          must_remove: [],
          tone_target: ''
        }
      }
    )

    mockState.approvals = []
    resolveReportApproval.mockReset()
  })
})
