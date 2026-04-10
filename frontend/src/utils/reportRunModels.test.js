import { describe, expect, it } from 'vitest'
import { buildDebugEvent, buildRunConsoleViewModel } from './reportRunModels'

describe('reportRunModels', () => {
  it('builds a failure debug event with next step guidance', () => {
    const model = buildDebugEvent({
      event_id: 11,
      type: 'task.failed',
      ts: '2026-04-10T10:00:00Z',
      payload: {
        closure_stage: 'structured_validation_failed',
        current_operation: 'validating structured result',
        failed_actor: 'report_coordinator'
      }
    })

    expect(model.title).toContain('校验')
    expect(model.nextStep).toContain('缺了哪部分结果')
    expect(model.detailLines[0]).toContain('停在')
  })

  it('maps task snapshot into a single-run console view model', () => {
    const vm = buildRunConsoleViewModel({
      id: 'rp-1',
      topic: '专题 A',
      start: '2026-04-01',
      end: '2026-04-07',
      mode: 'research',
      status: 'running',
      phase: 'interpret',
      message: '正在汇总证据',
      approvals: [],
      artifacts: { report_ready: true },
      structuredResultDigest: { summary: '已有摘要', counts: { evidence: 6, citations: 4 } },
      subagents: [
        { id: 'retrieval_router', status: 'done' },
        { id: 'evidence_organizer', status: 'running' }
      ],
      events: [
        { event_id: 1, type: 'phase.started', ts: '2026-04-10T10:00:00Z' },
        { event_id: 2, type: 'artifact.ready', ts: '2026-04-10T10:01:00Z', message: '结构化结果已生成' }
      ]
    })

    expect(vm.hasTask).toBe(true)
    expect(vm.runSummary.title).toBe('专题 A')
    expect(vm.runSummary.progress).toBeGreaterThan(0)
    expect(vm.inspector.digestSummary).toBe('已有摘要')
    expect(vm.timelineEvents).toHaveLength(2)
    expect(vm.agentDrawer[0].displayName).toBe('检索路由')
  })
})
