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
      threadId: 'thread-1',
      topic: '专题 A',
      start: '2026-04-01',
      end: '2026-04-07',
      mode: 'research',
      status: 'running',
      phase: 'interpret',
      message: '正在汇总证据',
      approvals: [],
      runState: {
        runtime_mode: 'deep-report-coordinator',
        checkpoint_backend: 'sqlite',
        checkpoint_locator: 'f:/opinion-system/backend/data/_report/checkpoints/deep-report-coordinator.sqlite',
        langsmith_enabled: true,
        langsmith_project: 'opinion-system-report'
      },
      artifacts: {},
      artifactManifest: {
        structured_projection: { status: 'ready', created_at: '2026-04-10T10:01:00Z', policy_version: 'policy.v2' },
        utility_assessment: { status: 'pending' },
        approval_records: { status: 'ready' },
        full_markdown: { status: 'pending' }
      },
      structuredResultDigest: { summary: '已有摘要', counts: { evidence: 6, citations: 4 }, utility_assessment: { decision: 'fallback_recompile' } },
      subagents: [
        { id: 'retrieval_router', status: 'done' },
        { id: 'evidence_organizer', status: 'running' }
      ],
      events: [
        { event_id: 1, type: 'phase.started', ts: '2026-04-10T10:00:00Z' },
        { event_id: 2, type: 'agent.memo', ts: '2026-04-10T10:00:30Z', payload: { router_facets: [{ task_goal: 'overview', platform: 'all' }], dispatch_targets: ['retrieval_router', 'propagation_analyst'] } },
        { event_id: 3, type: 'approval.required', ts: '2026-04-10T10:00:45Z', payload: { approvals: [] } },
        { event_id: 4, type: 'phase.context', ts: '2026-04-10T10:00:50Z', payload: { resume_from: 'approval_resolution' } },
        { event_id: 5, type: 'artifact.ready', ts: '2026-04-10T10:01:00Z', message: '结构化结果已生成' }
      ]
    })

    expect(vm.hasTask).toBe(true)
    expect(vm.runSummary.title).toBe('专题 A')
    expect(vm.runSummary.progress).toBeGreaterThan(0)
    expect(vm.inspector.digestSummary).toBe('已有摘要')
    expect(vm.timelineEvents.length).toBeGreaterThan(1)
    expect(vm.agentDrawer[0].displayName).toBe('检索路由')
    expect(vm.artifacts.find((item) => item.key === 'structured_projection')?.ready).toBe(true)
    expect(vm.artifacts.find((item) => item.key === 'approval_records')?.ready).toBe(true)
    expect(vm.graphObservability.currentActorLabel).toBe('证据整理')
    expect(vm.graphObservability.routerFacets[0]).toContain('overview')
    expect(vm.graphObservability.dispatchTargets).toContain('检索路由')
    expect(vm.graphObservability.routerSummary).toContain('任务目标')
    expect(vm.decisionObservability.utilityDecision).toBe('fallback_recompile')
    expect(vm.decisionObservability.utilityDecisionLabel).toBe('待补全')
    expect(vm.artifactObservability.items.length).toBeGreaterThan(0)
    expect(vm.approvalObservability.compactStatus).toBe('未触发审批')
    expect(vm.runtimeDiagnostics.runtimeModeLabel).toBe('Deep Coordinator')
    expect(vm.runtimeDiagnostics.checkpointBackendLabel).toBe('SQLITE')
    expect(vm.runtimeDiagnostics.tracingLabel).toContain('LangSmith')
  })

  it('keeps intelligence tool events visible while filtering low-signal file io noise', () => {
    const vm = buildRunConsoleViewModel({
      id: 'rp-2',
      topic: '专题 B',
      start: '2026-04-01',
      end: '2026-04-07',
      status: 'running',
      phase: 'interpret',
      events: [
        {
          event_id: 1,
          type: 'tool.result',
          ts: '2026-04-10T10:00:00Z',
          agent: 'evidence_organizer',
          payload: {
            tool_name: 'read_file',
            result_preview: '1\t{}'
          }
        },
        {
          event_id: 2,
          type: 'tool.result',
          ts: '2026-04-10T10:00:10Z',
          agent: 'evidence_organizer',
          payload: {
            tool_name: 'retrieve_evidence_cards',
            result_preview: '{\n  "result": [],\n  "tool_name": "retrieve_evidence_cards"\n}'
          }
        }
      ]
    })

    expect(vm.debugEvents).toHaveLength(1)
    expect(vm.debugEvents[0].title).toContain('整理证据卡')
    expect(vm.debugEvents[0].message).toContain('没有召回到可用证据卡')
    expect(vm.timelineEvents[0].title).toContain('整理证据卡')
  })

  it('prefers intelligence receipts over paired raw tool results', () => {
    const vm = buildRunConsoleViewModel({
      id: 'rp-3',
      topic: '专题 C',
      start: '2026-04-01',
      end: '2026-04-07',
      status: 'running',
      phase: 'review',
      events: [
        {
          event_id: 1,
          type: 'tool.result',
          ts: '2026-04-10T10:00:00Z',
          agent: 'validator',
          payload: {
            tool_name: 'verify_claim_v2',
            tool_call_id: 'call-1',
            result_preview: '{"result":[{"status":"unsupported"}]}'
          }
        },
        {
          event_id: 2,
          type: 'agent.memo',
          ts: '2026-04-10T10:00:01Z',
          agent: 'validator',
          payload: {
            stage_id: 'validation',
            tool_name: 'verify_claim_v2',
            tool_call_id: 'call-1',
            decision_summary: '断言核验完成：supported 1，partially_supported 0，unsupported 1，contradicted 0。',
            next_action: '降低结论强度，并显式保留不确定性边界。',
            counts: {
              checked_count: 2,
              supported_count: 1,
              partially_supported_count: 0,
              unsupported_count: 1,
              contradicted_count: 0
            }
          }
        }
      ]
    })

    expect(vm.debugEvents).toHaveLength(1)
    expect(vm.debugEvents[0].title).toContain('校验关键断言')
    expect(vm.debugEvents[0].message).toContain('unsupported 1')
    expect(vm.debugEvents[0].nextStep).toContain('降低结论强度')
    expect(vm.debugEvents[0].detailLines[0]).toContain('已校验：2')
  })

  it('surfaces contract violations with requested and effective ranges', () => {
    const model = buildDebugEvent({
      event_id: 9,
      type: 'agent.memo',
      ts: '2026-04-12T01:42:00Z',
      agent: 'retrieval_router',
      payload: {
        stage_id: 'scope',
        tool_name: 'normalize_task',
        diagnostic_kind: 'contract_violation',
        decision_summary: '检索子代理改写了任务边界，已按真实任务合同纠正。',
        next_action: '按纠正后的真实任务边界继续进行语料覆盖判断。',
        requested_range: { start: '2025-01-01', end: '2025-06-30' },
        effective_range: { start: '2025-01-15', end: '2025-12-31' },
        contract_topic_identifier: '20260304-091855-2025控烟舆情',
        counts: { matched_count: 0, sampled_count: 0, platform_count: 0 }
      }
    })

    expect(model.title).toContain('任务边界异常')
    expect(model.message).toContain('纠正')
    expect(model.detailLines).toContain('请求区间：2025-01-01 至 2025-06-30')
    expect(model.detailLines).toContain('执行区间：2025-01-15 至 2025-12-31')
    expect(model.detailLines).toContain('任务专题：20260304-091855-2025控烟舆情')
    expect(model.detailLines.some((line) => line.includes('计数：'))).toBe(false)
  })

  it('surfaces overlap fetch diagnostics instead of generic empty corpus', () => {
    const model = buildDebugEvent({
      event_id: 10,
      type: 'agent.memo',
      ts: '2026-04-12T01:42:30Z',
      agent: 'retrieval_router',
      payload: {
        stage_id: 'scope',
        tool_name: 'get_corpus_coverage',
        diagnostic_kind: 'partial_range_coverage',
        decision_summary: '当前请求区间与已有语料部分重叠，已按可用重叠区间继续检索。',
        next_action: '继续整理证据卡，但后续结论需保留区间部分覆盖说明。',
        counts: { matched_count: 3, platform_count: 1, sampled_count: 3 },
        requested_range: { start: '2025-01-01', end: '2025-06-30' },
        effective_range: { start: '2025-01-01', end: '2025-06-30' },
        resolved_fetch_range: { start: '2025-01-15', end: '2025-12-31' },
        effective_topic_identifier: '20260304-091855-2025控烟舆情'
      }
    })

    expect(model.title).toContain('部分覆盖')
    expect(model.message).toContain('部分重叠')
    expect(model.detailLines).toContain('命中归档区间：2025-01-15 至 2025-12-31')
    expect(model.nextStep).toContain('继续整理证据卡')
  })

  it('surfaces clipped retrieval scopes inside the main task contract', () => {
    const model = buildDebugEvent({
      event_id: 11,
      type: 'agent.memo',
      ts: '2026-04-12T02:40:00Z',
      agent: 'retrieval_router',
      payload: {
        stage_id: 'scope',
        tool_name: 'get_corpus_coverage',
        diagnostic_kind: 'scope_clipped_to_contract',
        decision_summary: '自定义时间窗超出了主任务范围，系统已裁剪到 contract 内继续检索。',
        next_action: '继续检索，但请注意当前结果只覆盖裁剪后的时间区间。',
        requested_range: { start: '2025-01-01', end: '2025-03-31' },
        effective_range: { start: '2025-01-15', end: '2025-03-31' },
        contract_topic_identifier: '20260304-091855-2025控烟舆情'
      }
    })

    expect(model.message).toContain('裁剪')
    expect(model.detailLines).toContain('请求区间：2025-01-01 至 2025-03-31')
    expect(model.detailLines).toContain('执行区间：2025-01-15 至 2025-03-31')
  })

  it('surfaces contract binding failures with stable three-column diagnostics', () => {
    const model = buildDebugEvent({
      event_id: 12,
      type: 'agent.memo',
      ts: '2026-04-12T03:10:00Z',
      agent: 'retrieval_router',
      payload: {
        stage_id: 'scope',
        tool_name: 'get_corpus_coverage',
        diagnostic_kind: 'contract_binding_failed',
        decision_summary: 'contract_id 缺失或无法绑定到 registry，系统已阻止继续检索。',
        next_action: '请确认当前任务是否已生成 task_contract，并使用 contract_id 重新调用。',
        contract_value: { topic_identifier: '20260304-091855-2025控烟舆情', start: '2025-01-15', end: '2025-12-31', mode: 'fast' },
        agent_proposed_value: { topic_identifier: 'tobacco_control_2025', start: '2025-01-01', end: '2025-06-30', mode: 'research' },
        effective_value: { topic_identifier: '', start: '', end: '', mode: '' },
        violation_origin: 'payload_adapter',
        repair_action: 'reject_missing_contract',
        skip_reason: 'contract_binding_failed'
      }
    })

    expect(model.title).toContain('合同绑定失败')
    expect(model.detailLines).toContain('合同绑定：20260304-091855-2025控烟舆情 / 2025-01-15 至 2025-12-31 / 模式 fast')
    expect(model.detailLines).toContain('原始提议：tobacco_control_2025 / 2025-01-01 至 2025-06-30 / 模式 research')
    expect(model.detailLines).toContain('异常来源：payload_adapter')
    expect(model.detailLines).toContain('修正动作：reject_missing_contract')
  })

  it('surfaces legacy adapter hits separately from empty corpus', () => {
    const model = buildDebugEvent({
      event_id: 13,
      type: 'agent.memo',
      ts: '2026-04-12T03:15:00Z',
      agent: 'retrieval_router',
      payload: {
        stage_id: 'scope',
        tool_name: 'get_corpus_coverage',
        diagnostic_kind: 'legacy_adapter_hit',
        decision_summary: '当前调用命中了 legacy adapter，系统已映射到新 ABI 后继续执行。',
        next_action: '建议尽快清理旧 JSON 入口，避免兼容层继续承接主链路。',
        contract_value: { topic_identifier: '20260304-091855-2025控烟舆情', start: '2025-01-15', end: '2025-12-31', mode: 'fast' },
        agent_proposed_value: { topic_identifier: '20260304-091855-2025控烟舆情', start: '2025-01-15', end: '2025-12-31', mode: 'fast' },
        effective_value: { topic_identifier: '20260304-091855-2025控烟舆情', start: '2025-01-15', end: '2025-12-31', mode: 'fast' },
        violation_origin: 'payload_adapter',
        repair_action: 'mapped_legacy_fields'
      }
    })

    expect(model.title).toContain('兼容入口')
    expect(model.detailLines).toContain('修正动作：mapped_legacy_fields')
  })

  it('surfaces blocked legacy runtime resume diagnostics', () => {
    const model = buildDebugEvent({
      event_id: 14,
      type: 'phase.context',
      ts: '2026-04-12T03:20:00Z',
      payload: {
        diagnostic_kind: 'legacy_runtime_version',
        runtime_contract_version: 'deep-report-contract.v3',
        task_runtime_contract_version: 'deep-report-contract.v2',
        next_action: '旧任务只允许只读回放或显式重建 contract 后重跑。'
      },
      title: '旧运行时任务已阻止恢复',
      message: '当前任务来自旧 ABI 版本，系统未继续沿新运行时主路径恢复。'
    })

    expect(model.title).toContain('阻止恢复')
    expect(model.detailLines).toContain('当前 ABI：deep-report-contract.v3')
    expect(model.detailLines).toContain('任务 ABI：deep-report-contract.v2')
  })

  it('builds todo observability from the latest checklist update', () => {
    const vm = buildRunConsoleViewModel({
      id: 'rp-4',
      threadId: 'thread-1',
      topic: '专题 D',
      start: '2026-04-01',
      end: '2026-04-07',
      status: 'running',
      phase: 'interpret',
      todos: [
        { id: 'scope', label: '范围确认', status: 'completed' },
        { id: 'retrieval', label: '检索路由', status: 'running' },
        { id: 'writing', label: '文稿生成', status: 'pending' }
      ],
      events: [
        {
          event_id: 1,
          type: 'todo.updated',
          ts: '2026-04-11T12:23:00Z',
          agent: 'report_coordinator',
          message: '总控代理更新了任务清单（3 项）。',
          payload: {
            todos: [
              { id: 'scope', label: '范围确认', status: 'completed' },
              { id: 'retrieval', label: '检索路由', status: 'running' },
              { id: 'writing', label: '文稿生成', status: 'pending' }
            ]
          }
        }
      ]
    })

    expect(vm.todoObservability.totalCount).toBe(3)
    expect(vm.todoObservability.completedCount).toBe(1)
    expect(vm.todoObservability.runningCount).toBe(1)
    expect(vm.todoObservability.updatedBy).toBe('总控代理')
    expect(vm.todoObservability.updatedMessage).toContain('任务清单')
    expect(vm.todoObservability.items[1].label).toBe('检索路由')
    expect(vm.todoObservability.items[1].isCurrent).toBe(true)
  })

  it('surfaces graph validation and compile gate events in the debug console', () => {
    const vm = buildRunConsoleViewModel({
      id: 'rp-graph',
      topic: '专题 Graph',
      start: '2026-04-01',
      end: '2026-04-07',
      status: 'running',
      phase: 'review',
      currentActor: 'unit_validator',
      currentOperation: '验证失败：3 个单元需要修复或人工复核。',
      artifactManifest: {
        draft_bundle_v2: { status: 'ready' },
        validation_result: { status: 'ready' },
        repair_plan: { status: 'ready' },
        graph_state: { status: 'ready' }
      },
      events: [
        {
          event_id: 1,
          type: 'graph.node.started',
          ts: '2026-04-12T04:24:00Z',
          agent: 'trace_binder',
          payload: { current_node: 'trace_binder', visited_nodes: ['load_context', 'planner_agent', 'trace_binder'] }
        },
        {
          event_id: 2,
          type: 'validation.failed',
          ts: '2026-04-12T04:25:00Z',
          agent: 'unit_validator',
          message: '验证失败：3 个单元需要修复或人工复核。',
          payload: {
            current_node: 'unit_validator',
            repair_count: 1,
            validation_result_v2: {
              gate: 'repair',
              repair_count: 1,
              failures: [{ failure_type: 'missing_trace', target_unit_id: 'u_17' }],
              metadata: { failure_count: 3 }
            }
          }
        },
        {
          event_id: 3,
          type: 'compile.blocked',
          ts: '2026-04-12T04:26:00Z',
          agent: 'compile_blocked',
          message: '验证仍未通过，当前停在人工复核前置门禁。',
          payload: {
            current_node: 'compile_blocked',
            validation_result_v2: {
              gate: 'human_review',
              failures: [{ failure_type: 'missing_trace', target_unit_id: 'u_17' }]
            }
          }
        }
      ]
    })

    expect(vm.graphObservability.currentNodeLabel).toBe('编译门禁')
    expect(vm.graphObservability.failureCount).toBe(1)
    expect(vm.graphObservability.compileGate).toBe('human_review')
    expect(vm.artifacts.find((item) => item.key === 'validation_result')?.ready).toBe(true)
    expect(vm.debugEvents[0].title).toContain('正式编译已阻止')
    expect(vm.debugEvents[1].title).toContain('单元验证')
  })
})
