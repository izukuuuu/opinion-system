const PLAN_STEP_DESCRIPTIONS = {
  scope: '确认专题、时间范围、模式和可直接复用的已有结果。',
  research: '并行推进检索、证据、时间线、立场和传播分析。',
  synthesis: '总控代理汇总并行结果，整理结构化报告对象。',
  writing: '输出结构化结论，并整理正式文稿草稿。',
  validation: '检查证据覆盖、结论边界和表达风险。',
  persist: '处理人工确认，并写入最终结果。'
}

export const RESEARCH_SUBAGENT_IDS = ['retrieval_router', 'archive_evidence_organizer', 'evidence_organizer', 'timeline_analyst', 'stance_conflict', 'propagation_analyst']
export const SUBAGENT_DISPLAY_ORDER = ['report_coordinator', ...RESEARCH_SUBAGENT_IDS, 'writer', 'validator']

const TODO_PROGRESS_WEIGHT = {
  scope: 12,
  research: 28,
  synthesis: 20,
  writing: 16,
  validation: 12,
  persist: 12
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Math.round(Number(value || 0))))
}

export function sanitizeRuntimeMessage(value) {
  const text = String(value || '').trim()
  if (!text) return ''
  return text.replace(/\s*\|\s*diagnostic=.*$/s, '').trim()
}

export function formatTimestamp(value) {
  const text = String(value || '').trim()
  if (!text) return '刚刚'
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${month}.${day} ${hours}:${minutes}`
}

export function modeLabel(mode) {
  return String(mode || '').trim() === 'research' ? '深入模式' : '快速模式'
}

export function phaseLabel(phase) {
  const mapping = {
    prepare: '范围确认',
    analyze: '基础分析',
    explain: '总体解读',
    interpret: '并行调研',
    write: '文稿生成',
    review: '质量校验',
    persist: '结果存储'
  }
  return mapping[String(phase || '').trim()] || '等待中'
}

export function statusLabel(status) {
  const mapping = {
    idle: '未开始',
    queued: '准备中',
    running: '进行中',
    waiting_approval: '等待介入',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return mapping[String(status || '').trim()] || '处理中'
}

export function toPrimaryStatus(status) {
  const normalized = String(status || '').trim()
  if (['completed', 'done'].includes(normalized)) return 'completed'
  if (['failed', 'cancelled'].includes(normalized)) return 'failed'
  if (['running', 'queued', 'waiting_approval'].includes(normalized)) return 'running'
  return 'pending'
}

export function todoStatusLabel(status) {
  const normalized = String(status || '').trim()
  if (normalized === 'completed') return '完成'
  if (normalized === 'running') return '进行中'
  if (normalized === 'failed') return '失败'
  return '等待'
}

export function subagentLabel(id) {
  const mapping = {
    retrieval_router: '检索路由',
    archive_evidence_organizer: '证据整理',
    agenda_frame_builder: '议题框架',
    evidence_organizer: '证据整理',
    timeline_analyst: '时间线与因果',
    stance_conflict: '主体与立场',
    claim_actor_conflict: '冲突构建',
    propagation_analyst: '传播结构',
    decision_utility_judge: '效用裁决',
    report_coordinator: '总控汇总',
    writer: '文稿生成',
    validator: '质量校验',
    load_context: '加载上下文',
    planner_agent: '章节规划',
    existing_analysis_workers_subgraph: '分析子图',
    ir_merge: 'IR 合并',
    trace_binder: 'Trace 绑定',
    section_realizer_agent: '受限成稿',
    section_realizer_worker: '章节成稿 Worker',
    section_realizer_finalize: '章节成稿汇总',
    unit_validator: '单元校验',
    repair_patch_planner: '修复规划',
    repairer_agent: '定点修复',
    repair_worker: '修复 Worker',
    repair_finalize: '修复汇总',
    compile_blocked: '编译门禁',
    markdown_compiler: '正式编译',
    artifact_renderer: '产物渲染'
  }
  return mapping[String(id || '').trim()] || String(id || '处理节点')
}

function normalizePrimaryTodoStatus(status) {
  const normalized = String(status || '').trim()
  if (normalized === 'completed') return 'completed'
  if (normalized === 'running') return 'running'
  if (normalized === 'failed') return 'failed'
  return 'pending'
}

function displayAgentLabel(agent) {
  const id = String(agent || '').trim()
  if (!id) return ''
  if (id === 'approval') return '人工确认'
  if (id === 'report_coordinator') return '总控代理'
  return subagentLabel(id)
}

function shortThreadLabel(threadId) {
  const text = String(threadId || '').trim()
  if (!text) return '--'
  if (text.length <= 28) return text
  return `${text.slice(0, 18)}...${text.slice(-6)}`
}

function shortLocatorLabel(value) {
  const text = String(value || '').trim()
  if (!text) return '--'
  if (text.length <= 42) return text
  return `${text.slice(0, 24)}...${text.slice(-12)}`
}

function runtimeModeLabel(mode) {
  const mapping = {
    'deep-report-coordinator': '深度分析主控',
    'deep-report-subagent': '深度分析子任务',
    'deep-report-root-graph': '分析主流程',
    'deep-report-compile': '报告编译',
    'report-agent-deep': '深度代理',
    'report-agent-plain': '兼容代理',
    'report-api': 'API 入口'
  }
  return mapping[String(mode || '').trim()] || String(mode || '').trim() || '未标注'
}

function latestApprovalRecord(approvals = []) {
  return [...(Array.isArray(approvals) ? approvals : [])].reverse().find((item) => item && typeof item === 'object') || null
}

function resolveRuntimeDiagnostics(taskState = {}, approvals = []) {
  const runState = taskState.runState && typeof taskState.runState === 'object' ? taskState.runState : {}
  const orchestratorDiagnostics = taskState.orchestratorState?.runtime_diagnostics && typeof taskState.orchestratorState.runtime_diagnostics === 'object'
    ? taskState.orchestratorState.runtime_diagnostics
    : {}
  const latestApproval = latestApprovalRecord(approvals)
  const toolArgs = latestApproval?.action?.tool_args && typeof latestApproval.action.tool_args === 'object'
    ? latestApproval.action.tool_args
    : {}
  const interruptPayload = latestApproval?.action?.graph_interrupt && typeof latestApproval.action.graph_interrupt === 'object'
    ? latestApproval.action.graph_interrupt
    : {}
  const currentThreadId = String(taskState.threadId || runState.thread_id || orchestratorDiagnostics.thread_id || '').trim()
  const checkpointBackend = String(runState.checkpoint_backend || orchestratorDiagnostics.checkpoint_backend || toolArgs.checkpoint_backend || '').trim()
  const checkpointLocator = String(runState.checkpoint_locator || orchestratorDiagnostics.checkpoint_locator || toolArgs.checkpoint_locator || toolArgs.checkpoint_path || '').trim()
  const runtimeMode = String(runState.runtime_mode || orchestratorDiagnostics.runtime_mode || '').trim()
  const latestInterruptId = String(latestApproval?.interrupt_id || interruptPayload.interrupt_id || '').trim()
  const langsmithEnabled = Boolean(runState.langsmith_enabled ?? orchestratorDiagnostics.langsmith_enabled)
  const langsmithProject = String(runState.langsmith_project || orchestratorDiagnostics.langsmith_project || '').trim()
  const environment = String(runState.environment || orchestratorDiagnostics.environment || '').trim()
  return {
    threadId: currentThreadId,
    threadLabel: shortThreadLabel(currentThreadId),
    checkpointBackend,
    checkpointBackendLabel: checkpointBackend ? checkpointBackend.toUpperCase() : '--',
    checkpointLocator,
    checkpointLocatorLabel: shortLocatorLabel(checkpointLocator),
    latestInterruptId,
    latestInterruptLabel: latestInterruptId || '--',
    runtimeMode,
    runtimeModeLabel: runtimeModeLabel(runtimeMode),
    langsmithEnabled,
    langsmithProject,
    tracingLabel: langsmithEnabled ? `已开启 (${langsmithProject || '默认'})` : '未开启',
    environment: environment || '--'
  }
}

function utilityDecisionLabel(decision, approvals = []) {
  const normalized = String(decision || '').trim()
  const hasPendingApproval = approvals.some((item) => String(item?.status || '').trim() !== 'resolved')
  if (hasPendingApproval || normalized === 'require_semantic_review') return '需审批'
  if (normalized === 'fallback_recompile') return '待补全'
  if (normalized === 'pass') return '已通过'
  return '处理中'
}

function approvalDecisionLabel(decision, reviewPayload = null) {
  const normalized = String(decision || '').trim()
  if (normalized === 'approve') {
    const hasComment = reviewPayload?.comment || reviewPayload?.annotations?.length
    return hasComment ? '已批注通过' : '已通过'
  }
  if (normalized === 'rewrite') return '已要求重写'
  if (normalized === 'reject') return '已拒绝'
  return '待处理'
}

function buildRouteSummary(routerFacets = [], dispatchTargets = []) {
  if (!routerFacets.length && !dispatchTargets.length) return '当前还没有分派计划。'
  const dimensions = []
  if (routerFacets.some((item) => String(item?.platform || '').trim())) dimensions.push('平台')
  if (routerFacets.some((item) => String(item?.event_stage || '').trim())) dimensions.push('事件阶段')
  if (routerFacets.some((item) => String(item?.task_goal || item?.output_goal || '').trim())) dimensions.push('任务目标')
  if (routerFacets.some((item) => String(item?.time_start || item?.time_end || item?.date_window || '').trim())) dimensions.push('时间窗')
  if (routerFacets.some((item) => String(item?.risk_sensitivity || '').trim())) dimensions.push('风险等级')
  if (dimensions.length) return `已按${dimensions.join('、')}生成分派计划。`
  if (dispatchTargets.length) return '已生成当前轮次的分派计划。'
  return '当前还没有分派计划。'
}

function normalizeArtifactKey(key) {
  const normalized = String(key || '').trim()
  return normalized === 'report_ir' ? 'ir' : normalized
}

function artifactDisplayMeta(key) {
  const normalized = normalizeArtifactKey(key)
  const mapping = {
    structured_projection: { label: '语义报告', description: '结构化的分析结果。' },
    ir: { label: '分析中枢', description: '核心证据与结论的汇总。' },
    conflict_map: { label: '争议图谱', description: '各方的立场和争议点。' },
    mechanism_summary: { label: '传播分析', description: '舆情传播路径和触发因素。' },
    utility_assessment: { label: '质量评估', description: '判断是否满足生成报告的条件。' },
    draft_bundle: { label: '草稿素材', description: '按章节整理的草稿内容。' },
    draft_bundle_v2: { label: '草稿素材', description: '结构化的章节草稿。' },
    validation_result: { label: '校验结果', description: '内容检查和问题记录。' },
    repair_plan: { label: '修复计划', description: '针对问题内容的修复方案。' },
    graph_state: { label: '运行记录', description: '当前进度和调整次数。' },
    approval_records: { label: '确认记录', description: '人工审核的确认情况。' },
    full_markdown: { label: '正式报告', description: '最终的分析报告文稿。' }
  }
  return mapping[normalized] || { label: normalized || '产物', description: '当前产物。' }
}

function toolDisplayName(toolName) {
  const mapping = {
    task: '委派子任务',
    write_todos: '更新执行计划',
    normalize_task: '冻结任务边界',
    get_corpus_coverage: '诊断语料覆盖',
    retrieve_evidence_cards: '整理证据卡',
    build_event_timeline: '生成时间线',
    compute_report_metrics: '生成指标对象',
    extract_actor_positions: '提取主体立场',
    build_agenda_frame_map: '构建议题框架',
    build_claim_actor_conflict: '构建冲突图谱',
    build_mechanism_summary: '生成传播机制',
    detect_risk_signals: '识别风险信号',
    judge_decision_utility: '裁决决策可用性',
    verify_claim_v2: '校验关键断言',
    build_section_packet: '组装章节材料包',
    read_file: '读取文件',
    write_file: '写入文件',
    edit_file: '修改文件',
    ls: '查看目录',
    grep: '搜索内容',
    query_documents: '检索资料',
    build_timeline: '整理时间线',
    build_entity_graph: '分析主体关系',
    run_volume_analysis: '分析传播规模',
    save_structured_report: '保存结构化结果',
    write_final_report: '写入正式文稿',
    overwrite_report_cache: '更新结果缓存',
    graph_interrupt: '语义边界确认'
  }
  return mapping[String(toolName || '').trim()] || String(toolName || '执行动作')
}

const LOW_SIGNAL_TOOL_NAMES = new Set(['read_file', 'write_file', 'edit_file', 'ls', 'grep'])

function isLowSignalToolName(toolName) {
  return LOW_SIGNAL_TOOL_NAMES.has(String(toolName || '').trim())
}

function extractJsonField(text, field) {
  const escaped = String(field || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = String(text || '').match(new RegExp(`"${escaped}"\\s*:\\s*"([^"]*)"`, 'i'))
  return match ? String(match[1] || '').trim() : ''
}

function sanitizeEventText(value) {
  const text = sanitizeRuntimeMessage(value)
  if (!text) return ''
  if (/^\s*[\[{]/.test(text)) return ''
  return text.replace(/\s+/g, ' ').trim()
}

function sanitizeEventPreview(value) {
  const text = String(value || '').trim()
  if (!text) return ''
  if (/^\s*[\[{]/.test(text)) return ''
  if (text.includes('diagnostic=')) return ''
  return text.replace(/\s+/g, ' ').trim().slice(0, 180)
}

function parseArgsPreview(value) {
  const text = String(value || '').trim()
  if (!text) return {}
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function parseMaybeJsonString(value) {
  if (value && typeof value === 'object') return value
  const text = String(value || '').trim()
  if (!text) return {}
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function toStringList(value) {
  return (Array.isArray(value) ? value : [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
}

function compactRequestTerms(values = []) {
  const ordered = [...new Set((Array.isArray(values) ? values : []).map((item) => String(item || '').trim()).filter(Boolean))]
  return ordered.filter((item, index) => {
    const normalized = item.replace(/\s+/g, '')
    return !ordered.some((other, otherIndex) => {
      if (index === otherIndex) return false
      const otherNormalized = String(other || '').replace(/\s+/g, '')
      return otherNormalized.length > normalized.length && otherNormalized.includes(normalized)
    })
  })
}

function extractRequestTerms(args = {}) {
  const filters = parseMaybeJsonString(args.filters_json)
  const scope = parseMaybeJsonString(args.retrieval_scope_json)
  const normalizedTask = parseMaybeJsonString(args.normalized_task_json)
  const candidates = []

  const explicitQuery = String(filters.query || filters.keyword || filters.search || '').trim()
  if (explicitQuery) candidates.push(explicitQuery)

  candidates.push(...toStringList(filters.keywords))
  candidates.push(...toStringList(scope.keywords))
  candidates.push(...toStringList(scope.entities))
  candidates.push(...toStringList(normalizedTask.keywords))
  candidates.push(...toStringList(normalizedTask.entities))

  const topic = String(
    normalizedTask.topic_label
    || normalizedTask.topic
    || normalizedTask.topic_name
    || scope.topic
    || ''
  ).trim()
  if (topic) candidates.push(topic)

  return compactRequestTerms(candidates).slice(0, 4)
}

function extractRequestPlatforms(args = {}) {
  const filters = parseMaybeJsonString(args.filters_json)
  const scope = parseMaybeJsonString(args.retrieval_scope_json)
  const normalizedTask = parseMaybeJsonString(args.normalized_task_json)
  return [...new Set([
    ...toStringList(filters.platforms),
    ...toStringList(scope.platforms),
    ...toStringList(normalizedTask.platform_scope)
  ])].slice(0, 4)
}

function extractRequestEntities(args = {}) {
  const filters = parseMaybeJsonString(args.filters_json)
  const scope = parseMaybeJsonString(args.retrieval_scope_json)
  const normalizedTask = parseMaybeJsonString(args.normalized_task_json)
  return [...new Set([
    ...toStringList(filters.entities),
    ...toStringList(scope.entities),
    ...toStringList(normalizedTask.entities)
  ])].slice(0, 4)
}

function extractRequestTimeRange(args = {}) {
  const filters = parseMaybeJsonString(args.filters_json)
  const scope = parseMaybeJsonString(args.retrieval_scope_json)
  const normalizedTask = parseMaybeJsonString(args.normalized_task_json)
  const start = String(filters.time_start || scope.start || normalizedTask?.time_range?.start || '').trim()
  const end = String(filters.time_end || scope.end || normalizedTask?.time_range?.end || start || '').trim()
  return formatRangeLabel({ start, end })
}

function summarizeToolCallIntent(args = {}) {
  const intent = String(args.intent || '').trim()
  const mapping = {
    overview: '总览',
    timeline: '时间线',
    actors: '主体立场',
    risk: '风险信号',
    claim_support: '支持性主张',
    claim_counter: '反向主张'
  }
  return mapping[intent] || intent
}

function summarizeToolCallArgs(toolName, argsPreview) {
  const args = parseArgsPreview(argsPreview)
  const lines = []
  const normalizedTool = String(toolName || '').trim()

  if (normalizedTool === 'retrieve_evidence_cards') {
    const intentLabel = summarizeToolCallIntent(args)
    if (intentLabel) lines.push(`本次目标：整理${intentLabel}相关证据卡`)
    const requestTerms = extractRequestTerms(args)
    if (requestTerms.length) lines.push(`请求词：${requestTerms.join('、')}`)
    const platforms = extractRequestPlatforms(args)
    if (platforms.length) lines.push(`平台范围：${platforms.join('、')}`)
    const entities = extractRequestEntities(args)
    if (entities.length) lines.push(`关注主体：${entities.join('、')}`)
    const timeRange = extractRequestTimeRange(args)
    if (timeRange) lines.push(`时间窗：${timeRange}`)
    const sortBy = String(args.sort_by || '').trim()
    if (sortBy) lines.push(`排序方式：${sortBy}`)
    const limit = Number(args.limit || 0)
    if (Number.isFinite(limit) && limit > 0) lines.push(`数量上限：${limit}`)
  } else if (normalizedTool === 'get_corpus_coverage') {
    lines.push('本次目标：确认当前范围内是否存在可用语料')
    const requestTerms = extractRequestTerms(args)
    if (requestTerms.length) lines.push(`请求词：${requestTerms.join('、')}`)
    const platforms = extractRequestPlatforms(args)
    if (platforms.length) lines.push(`平台范围：${platforms.join('、')}`)
    const entities = extractRequestEntities(args)
    if (entities.length) lines.push(`关注主体：${entities.join('、')}`)
    const timeRange = extractRequestTimeRange(args)
    if (timeRange) lines.push(`时间窗：${timeRange}`)
  } else if (normalizedTool === 'normalize_task') {
    lines.push('本次目标：冻结专题、时间范围和执行模式')
  } else if (normalizedTool === 'build_event_timeline') {
    lines.push('本次目标：把已命中的证据整理成可回链时间线')
  } else if (normalizedTool === 'extract_actor_positions') {
    lines.push('本次目标：识别主体与立场关系')
  } else if (normalizedTool === 'build_claim_actor_conflict') {
    lines.push('本次目标：整理主体主张和冲突关系')
  } else if (normalizedTool === 'build_mechanism_summary') {
    lines.push('本次目标：归纳传播路径和放大机制')
  } else if (normalizedTool === 'detect_risk_signals') {
    lines.push('本次目标：识别当前轮次的风险信号')
  } else if (normalizedTool === 'judge_decision_utility') {
    lines.push('本次目标：判断当前结果能否进入写稿')
  }

  return lines
}

function formatReceiptCounts(counts) {
  const payload = counts && typeof counts === 'object' ? counts : {}
  const mapping = {
    matched_count: '命中',
    sampled_count: '采样',
    platform_count: '平台',
    cards_count: '证据卡',
    timeline_count: '时间线节点',
    metric_count: '指标',
    actor_count: '主体',
    actors_count: '主体',
    claims_count: '断言',
    conflicts_count: '冲突边',
    paths_count: '放大路径',
    triggers_count: '触发节点',
    bridge_nodes_count: '桥接节点',
    risks_count: '风险',
    missing_dimensions_count: '缺口维度',
    checked_count: '已校验',
    supported_count: 'supported',
    partially_supported_count: 'partially_supported',
    unsupported_count: 'unsupported',
    contradicted_count: 'contradicted',
    uncertainty_count: '不确定性提示'
  }
  return Object.entries(payload)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .map(([key, value]) => {
      const label = mapping[key] || key
      return `${label}：${Number(value)}`
    })
}

function shouldDisplayReceiptCounts(toolName, counts) {
  if (String(toolName || '').trim() === 'normalize_task') return false
  return formatReceiptCounts(counts).length > 0
}

function formatRangeLabel(range) {
  const payload = range && typeof range === 'object' ? range : {}
  const start = String(payload.start || '').trim()
  const end = String(payload.end || '').trim() || start
  if (!start && !end) return ''
  if (start && end) return `${start} 至 ${end}`
  return start || end
}

function formatExecutionValue(value) {
  const payload = value && typeof value === 'object' ? value : {}
  const topic = String(payload.topic_identifier || '').trim()
  const range = formatRangeLabel({ start: payload.start, end: payload.end })
  const mode = String(payload.mode || '').trim()
  const parts = []
  if (topic) parts.push(topic)
  if (range) parts.push(range)
  if (mode) parts.push(`模式 ${mode}`)
  return parts.join(' / ')
}

function buildReceiptToolCallIdSet(events = []) {
  const ids = new Set()
  for (const item of Array.isArray(events) ? events : []) {
    const payload = item?.payload && typeof item.payload === 'object' ? item.payload : {}
    if (String(item?.type || '').trim() !== 'agent.memo') continue
    if (!String(payload.stage_id || '').trim() || !String(payload.decision_summary || '').trim()) continue
    const toolCallId = String(payload.tool_call_id || '').trim()
    if (toolCallId) ids.add(toolCallId)
  }
  return ids
}

function summarizeToolResultPreview(toolName, rawPreview) {
  const text = String(rawPreview || '').trim()
  if (!text) return ''
  if (text.includes(`Error invoking tool '${toolName}'`)) {
    if (toolName === 'save_structured_report') return '结构化保存没有通过校验。'
    if (toolName === 'write_final_report') return '正式文稿写入失败。'
    if (toolName === 'overwrite_report_cache') return '结果缓存更新失败。'
    return `${toolDisplayName(toolName)}失败。`
  }
  if (toolName === 'normalize_task') return '任务边界已冻结。'
  if (toolName === 'get_corpus_coverage') {
    if (/"contract_mismatch"\s*:\s*true/.test(text)) return '检索范围与真实任务边界不一致。'
    if (/"source_resolution"\s*:\s*"overlap_fetch_range"/.test(text)) return '当前请求区间与已有语料部分重叠。'
    if (/"source_resolution"\s*:\s*"unavailable"/.test(text)) return '当前没有命中的原始语料归档。'
    return /"matched_count"\s*:\s*0/.test(text) ? '当前范围内没有命中文档。' : '已返回覆盖诊断结果。'
  }
  if (toolName === 'retrieve_evidence_cards') return /"result"\s*:\s*\[\s*\]/.test(text) ? '没有召回到可用证据卡。' : '已返回证据卡结果。'
  if (toolName === 'build_event_timeline') return /"result"\s*:\s*\[\s*\]/.test(text) ? '没有形成可回链的时间线节点。' : '已生成时间线节点。'
  if (toolName === 'compute_report_metrics') return '已生成指标对象。'
  if (toolName === 'extract_actor_positions') return /"result"\s*:\s*\[\s*\]/.test(text) ? '当前没有识别到明确主体立场。' : '已提取主体立场关系。'
  if (toolName === 'build_agenda_frame_map') return '已构建议题框架对象。'
  if (toolName === 'build_claim_actor_conflict') return /"claims"\s*:\s*\[\s*\]/.test(text) ? '当前冲突图谱为空。' : '已生成断言冲突图谱。'
  if (toolName === 'build_mechanism_summary') return /"amplification_paths"\s*:\s*\[\s*\]/.test(text) ? '当前传播机制对象为空。' : '已生成传播机制对象。'
  if (toolName === 'detect_risk_signals') return /"result"\s*:\s*\[\s*\]/.test(text) ? '暂未识别到风险信号。' : '已返回风险信号结果。'
  if (toolName === 'judge_decision_utility') {
    const decision = extractJsonField(text, 'decision')
    return decision ? `当前裁决为 ${decision}。` : '已更新决策可用性裁决。'
  }
  if (toolName === 'verify_claim_v2') return '已完成关键断言回链校验。'
  if (toolName === 'build_section_packet') {
    const sectionId = extractJsonField(text, 'section_id')
    return sectionId ? `已组装 ${sectionId} 章节材料包。` : '已组装章节材料包。'
  }
  if (toolName === 'save_structured_report') return '结构化结果已保存。'
  return sanitizeEventPreview(text)
}

function summarizeStateFiles(stateFiles) {
  if (!stateFiles || typeof stateFiles !== 'object') return ''
  const labels = {
    '/workspace/state/retrieval_plan.md': '检索计划',
    '/workspace/state/evidence_bundle.md': '证据整理',
    '/workspace/state/timeline_bundle.md': '时间线',
    '/workspace/state/stance_bundle.md': '立场分析',
    '/workspace/state/propagation_bundle.md': '传播分析',
    '/workspace/base_context.json': '任务上下文'
  }
  const ready = []
  const missing = []
  for (const [path, info] of Object.entries(stateFiles)) {
    if (!info || typeof info !== 'object') continue
    const label = labels[path] || path
    if (info.exists && !info.empty) ready.push(label)
    else missing.push(label)
  }
  if (ready.length && missing.length) return `已拿到 ${ready.join('、')}，缺少 ${missing.join('、')}`
  if (ready.length) return `已拿到 ${ready.join('、')}`
  if (missing.length) return `还缺少 ${missing.join('、')}`
  return ''
}

function failureHeadlineFromStage(stage) {
  if (stage === 'agent_save_missing') return '没有生成可用结论'
  if (stage === 'fallback_synthesis_failed') return '自动整理没有生成可用结果'
  if (stage === 'structured_validation_failed') return '结果已整理，但校验没有通过'
  if (stage === 'tool_round_limit_reached') return '本轮达到调用上限'
  return '任务未能完成'
}

function failureMessageFromStage(stage) {
  if (stage === 'agent_save_missing') return '调研节点已经跑完，但这轮没有整理出最终结构化结果。'
  if (stage === 'fallback_synthesis_failed') return '系统尝试根据中间结果自动整理结论，但没有整理成功。'
  if (stage === 'structured_validation_failed') return '结果对象已经生成，但关键字段还不完整，暂时不能继续写稿。'
  if (stage === 'tool_round_limit_reached') return '本轮调用次数超过当前上限，任务先停在这里。'
  return '这轮任务没有顺利结束。'
}

function nextStepFromStage(stage) {
  if (stage === 'agent_save_missing') return '优先检查结构汇总之后的节点，确认总控是否读取了全部中间结果。'
  if (stage === 'fallback_synthesis_failed') return '先检查证据、时间线、立场、传播几个中间结果是否都已生成。'
  if (stage === 'structured_validation_failed') return '先看节点说明里缺了哪部分结果，再决定是否重跑。'
  if (stage === 'tool_round_limit_reached') return '如果这类任务经常停在半路，可以提高工具回合上限。'
  return ''
}

function buildResearchAgents(taskState) {
  const rawAgents = Array.isArray(taskState.subagents) ? taskState.subagents : []
  const mapped = rawAgents
    .filter((item) => item && item.id)
    .map((item) => ({
      id: String(item.id || '').trim(),
      displayName: subagentLabel(item.id),
      status: normalizePrimaryTodoStatus(item.status === 'done' ? 'completed' : item.status),
      rawStatus: String(item.status || '').trim() || 'idle',
      message: sanitizeRuntimeMessage(item.message),
      startedAt: String(item.started_at || '').trim(),
      updatedAt: String(item.updated_at || '').trim(),
      toolCallCount: Number(item.tool_call_count || 0),
      toolResultCount: Number(item.tool_result_count || 0)
    }))
  return mapped.sort((a, b) => {
    const left = SUBAGENT_DISPLAY_ORDER.indexOf(a.id)
    const right = SUBAGENT_DISPLAY_ORDER.indexOf(b.id)
    const aIndex = left >= 0 ? left : SUBAGENT_DISPLAY_ORDER.length + 1
    const bIndex = right >= 0 ? right : SUBAGENT_DISPLAY_ORDER.length + 1
    if (aIndex !== bIndex) return aIndex - bIndex
    return a.displayName.localeCompare(b.displayName)
  })
}

function deriveStageCards(taskState, agents) {
  const phase = String(taskState.phase || '').trim()
  const status = String(taskState.status || '').trim()
  const approvals = Array.isArray(taskState.approvals) ? taskState.approvals : []
  const pendingApprovals = approvals.filter((item) => String(item?.status || '').trim() !== 'resolved')
  const failed = status === 'failed'
  const hasStructuredResult = Boolean(taskState.id && taskState.threadId && taskState.artifactManifest?.structured_projection?.status === 'ready')
  const hasFullReport = Boolean(taskState.id && taskState.threadId && taskState.artifactManifest?.full_markdown?.status === 'ready')
  const researchAgents = agents.filter((item) => RESEARCH_SUBAGENT_IDS.includes(item.id))
  const researchDone = researchAgents.filter((item) => item.rawStatus === 'done').length
  const researchStarted = researchAgents.filter((item) => item.rawStatus !== 'idle').length
  const states = [
    {
      id: 'scope',
      label: '范围确认',
      description: PLAN_STEP_DESCRIPTIONS.scope,
      status: !taskState.id ? 'pending' : (['prepare', 'analyze', 'explain', 'queued'].includes(phase) || status === 'queued' ? (failed ? 'failed' : 'running') : 'completed'),
      detail: taskState.start ? `${taskState.start} → ${taskState.end || taskState.start}` : '等待范围'
    },
    {
      id: 'research',
      label: '并行调研',
      description: PLAN_STEP_DESCRIPTIONS.research,
      status: phase === 'interpret'
        ? (failed && !hasStructuredResult ? 'failed' : (researchDone >= RESEARCH_SUBAGENT_IDS.length ? 'completed' : 'running'))
        : ((['write', 'review', 'persist', 'completed'].includes(phase) || hasStructuredResult) ? 'completed' : 'pending'),
      detail: researchStarted ? `${researchDone}/${RESEARCH_SUBAGENT_IDS.length} 个节点完成` : '等待并行调研'
    },
    {
      id: 'synthesis',
      label: '结构汇总',
      description: PLAN_STEP_DESCRIPTIONS.synthesis,
      status: hasStructuredResult || ['write', 'review', 'persist', 'completed'].includes(phase)
        ? 'completed'
        : (phase === 'interpret' && researchStarted ? (failed ? 'failed' : 'running') : 'pending'),
      detail: hasStructuredResult ? '结构化结果已生成' : '等待总控汇总'
    },
    {
      id: 'writing',
      label: '文稿生成',
      description: PLAN_STEP_DESCRIPTIONS.writing,
      status: hasFullReport || ['review', 'persist', 'completed'].includes(phase)
        ? 'completed'
        : ((phase === 'write' || agents.some((item) => item.id === 'writer' && item.rawStatus === 'running')) ? (failed ? 'failed' : 'running') : 'pending'),
      detail: hasFullReport ? '正式文稿已生成' : '等待文稿生成'
    },
    {
      id: 'validation',
      label: '质量校验',
      description: PLAN_STEP_DESCRIPTIONS.validation,
      status: ['persist', 'completed'].includes(phase) && !pendingApprovals.length
        ? 'completed'
        : ((phase === 'review' || pendingApprovals.length || agents.some((item) => item.id === 'validator' && item.rawStatus === 'running'))
            ? (failed && phase === 'review' ? 'failed' : 'running')
            : 'pending'),
      detail: pendingApprovals.length ? `待处理 ${pendingApprovals.length} 项` : '等待校验'
    },
    {
      id: 'persist',
      label: '结果存储',
      description: PLAN_STEP_DESCRIPTIONS.persist,
      status: status === 'completed'
        ? 'completed'
        : ((phase === 'persist' || pendingApprovals.length || hasStructuredResult || hasFullReport)
            ? (failed && phase === 'persist' ? 'failed' : 'running')
            : 'pending'),
      detail: status === 'completed' ? '结果已写入' : '等待结果存储'
    }
  ]
  return states.map((item, index) => ({
    ...item,
    order: index + 1,
    statusText: todoStatusLabel(item.status),
    isCurrent: item.status === 'running'
  }))
}

function calculateProgress(taskState, stageCards, agents) {
  if (!taskState.id) return 0
  if (taskState.status === 'completed') return 100
  if (['failed', 'cancelled'].includes(taskState.status)) {
    return clampPercent(Number(taskState.percentage || 0))
  }
  const researchAgents = agents.filter((item) => RESEARCH_SUBAGENT_IDS.includes(item.id))
  const researchDone = researchAgents.filter((item) => item.rawStatus === 'done').length
  const researchRunning = researchAgents.filter((item) => item.rawStatus === 'running').length
  const researchProgress = RESEARCH_SUBAGENT_IDS.length
    ? Math.max(0, Math.min(1, (researchDone + researchRunning * 0.45) / RESEARCH_SUBAGENT_IDS.length))
    : 0
  const runningRatio = (stageId) => {
    if (stageId === 'scope') return 0.55
    if (stageId === 'research') return 0.2 + (researchProgress * 0.75)
    if (stageId === 'synthesis') return 0.72
    if (stageId === 'writing') return 0.65
    if (stageId === 'validation') return 0.72
    if (stageId === 'persist') return 0.68
    return 0.4
  }
  const totalWeight = stageCards.reduce((sum, item) => sum + (TODO_PROGRESS_WEIGHT[item.id] || 0), 0) || 100
  let completeWeight = 0
  for (const item of stageCards) {
    const weight = TODO_PROGRESS_WEIGHT[item.id] || 0
    if (item.status === 'completed') completeWeight += weight
    else if (item.status === 'running') completeWeight += weight * runningRatio(item.id)
  }
  return clampPercent(Math.round((completeWeight / totalWeight) * 100))
}

function buildArtifactCards(taskState) {
  const manifest = taskState.artifactManifest && typeof taskState.artifactManifest === 'object'
    ? taskState.artifactManifest
    : {}
  return [
    {
      key: 'structured_projection',
      label: '语义报告',
      description: '由 Report IR 派生的结构化投影视图。',
      ready: Boolean(taskState.id && taskState.threadId && manifest.structured_projection?.status === 'ready')
    },
    {
      key: 'report_ir',
      label: 'Report IR',
      description: '本次任务的语义中枢与证据编译结果。',
      ready: Boolean(manifest.ir?.status === 'ready')
    },
    {
      key: 'draft_bundle',
      label: '受约束草稿',
      description: '按 section 编译的 draft units，仍保留 trace 绑定。',
      ready: Boolean(manifest.draft_bundle?.status === 'ready')
    },
    {
      key: 'draft_bundle_v2',
      label: '受约束草稿 V2',
      description: '按 DraftUnitV2 编译的结构化草稿单元。',
      ready: Boolean(manifest.draft_bundle_v2?.status === 'ready')
    },
    {
      key: 'validation_result',
      label: '验证结果',
      description: '单元级验证结果、失败类型与 compile gate。',
      ready: Boolean(manifest.validation_result?.status === 'ready')
    },
    {
      key: 'repair_plan',
      label: '修复计划',
      description: '自动 repair loop 生成的 patch plan。',
      ready: Boolean(manifest.repair_plan?.status === 'ready')
    },
    {
      key: 'graph_state',
      label: '图运行快照',
      description: '记录当前节点、repair 次数和 gate 状态。',
      ready: Boolean(manifest.graph_state?.status === 'ready')
    },
    {
      key: 'approval_records',
      label: '审批记录',
      description: '语义审查和人工确认会追加到同一条 lineage。',
      ready: Boolean(manifest.approval_records?.status === 'ready')
    },
    {
      key: 'full_markdown',
      label: '正式文稿',
      description: '由 Report IR 编译得到的正式 Markdown 文稿。',
      ready: Boolean(taskState.id && taskState.threadId && manifest.full_markdown?.status === 'ready')
    }
  ]
}

function summarizeFacet(facet) {
  if (!facet || typeof facet !== 'object') return ''
  const parts = [
    facet.task_goal,
    facet.event_stage,
    facet.platform,
    facet.risk_sensitivity
  ].map((item) => String(item || '').trim()).filter(Boolean)
  if (parts.length) return parts.join(' / ')
  const fallback = [
    facet.actor_scope,
    facet.source_type,
    facet.date_window
  ].map((item) => {
    if (Array.isArray(item)) return item.filter(Boolean).join('、')
    if (item && typeof item === 'object') return Object.values(item).filter(Boolean).join(' → ')
    return String(item || '').trim()
  }).filter(Boolean)
  return fallback.join(' / ')
}

function summarizeApprovalReason(approval) {
  const graphInterrupt = approval?.action?.graph_interrupt
  const graphSummary = String(graphInterrupt?.value?.summary || '').trim()
  if (graphSummary) return graphSummary
  return String(approval?.summary || '').trim()
}

function buildGraphObservability(taskState, timelineEvents) {
  const rawEvents = Array.isArray(taskState.events) ? taskState.events : []
  const latestGraphEvent = [...rawEvents].reverse().find((item) => {
    const type = String(item?.type || '').trim()
    return type.startsWith('graph.') || ['validation.failed', 'repair.loop.started', 'repair.loop.completed', 'compile.blocked', 'compile.started', 'compile.completed', 'interrupt.human_review'].includes(type)
  }) || null
  const routerEvent = [...rawEvents].reverse().find((item) => Array.isArray(item?.payload?.router_facets) || Array.isArray(item?.payload?.dispatch_targets))
  const latestTransition = timelineEvents[0] || null
  const routerFacetPayload = Array.isArray(routerEvent?.payload?.router_facets)
    ? routerEvent.payload.router_facets
    : []
  const routerFacets = routerFacetPayload.map(summarizeFacet).filter(Boolean)
  const dispatchTargets = Array.isArray(routerEvent?.payload?.dispatch_targets)
    ? routerEvent.payload.dispatch_targets.map((item) => displayAgentLabel(item) || String(item || '').trim()).filter(Boolean)
    : []
  const dispatchQuality = routerEvent?.payload?.dispatch_quality_summary && typeof routerEvent.payload.dispatch_quality_summary === 'object'
    ? routerEvent.payload.dispatch_quality_summary
    : {}
  const runningAgent = (Array.isArray(taskState.subagents) ? taskState.subagents : []).find((item) => String(item?.status || '').trim() === 'running')
  const graphPayload = latestGraphEvent?.payload && typeof latestGraphEvent.payload === 'object' ? latestGraphEvent.payload : {}
  const graphNode = String(graphPayload.current_node || latestGraphEvent?.agent || '').trim()
  const validation = graphPayload.validation_result_v2 && typeof graphPayload.validation_result_v2 === 'object'
    ? graphPayload.validation_result_v2
    : {}
  const repairCount = Number(graphPayload.repair_count ?? validation.repair_count ?? 0)
  const failureCount = Number(validation.metadata?.failure_count ?? graphPayload.failure_count ?? (Array.isArray(validation.failures) ? validation.failures.length : 0) ?? 0)
  const compileGate = String(validation.gate || taskState.lastDiagnostic?.gate || '').trim()
  const currentActor = String(
    graphNode
    || taskState.currentActor
    || taskState.orchestratorState?.agent
    || runningAgent?.id
    || (taskState.status === 'waiting_approval' ? 'approval' : 'report_coordinator')
  ).trim()
  const currentOperation = sanitizeRuntimeMessage(taskState.currentOperation || taskState.orchestratorState?.message || taskState.message)
  let currentNodeLabel = displayAgentLabel(currentActor) || phaseLabel(taskState.phase)
  if (taskState.status === 'waiting_approval') currentNodeLabel = '语义边界确认'
  else if (currentActor === 'writer') currentNodeLabel = '正式文稿编译'
  else if (currentActor === 'validator') currentNodeLabel = '语义校验'
  else if (currentActor === 'report_coordinator' && routerFacets.length && String(taskState.phase || '').trim() === 'interpret') currentNodeLabel = '路由与汇总'
  let nextStep = ''
  if (String(taskState.status || '').trim() === 'waiting_approval') nextStep = '等待人工处理后恢复正式写入。'
  else if (String(taskState.status || '').trim() === 'completed') nextStep = '本轮任务已完成，可直接查看语义报告和正式文稿。'
  else if (String(taskState.status || '').trim() === 'failed') nextStep = latestTransition?.nextStep || '先查看失败详情，再决定是否重跑。'
  else nextStep = sanitizeRuntimeMessage(latestGraphEvent?.message) || latestTransition?.nextStep || String(taskState.reportIrSummary?.utility_assessment?.next_action || taskState.structuredResultDigest?.utility_assessment?.next_action || '').trim() || currentOperation || '等待下一步调度。'
  return {
    currentStageLabel: phaseLabel(taskState.phase),
    currentStageMessage: sanitizeRuntimeMessage(taskState.message) || currentOperation || '等待阶段进度。',
    currentNodeLabel,
    currentActorLabel: displayAgentLabel(currentActor) || '协调器',
    nextStep,
    threadLabel: shortThreadLabel(taskState.threadId),
    connectionLabel: taskState.connectionMode === 'streaming'
      ? '实时同步'
      : (taskState.connectionMode === 'polling_fallback' ? '自动刷新' : (taskState.connectionMode === 'reconnecting' ? '重连中' : '待连接')),
    routerSummary: buildRouteSummary(routerFacetPayload, dispatchTargets),
    routerFacets,
    dispatchTargets,
    dispatchCount: Number(dispatchQuality.count || dispatchTargets.length || 0),
    dispatchArtifacts: Array.isArray(dispatchQuality.contributed_artifacts)
      ? dispatchQuality.contributed_artifacts.map((item) => artifactDisplayMeta(item).label || String(item || '').trim()).filter(Boolean)
      : [],
    repairCount,
    failureCount,
    compileGate,
    graphStatus: latestGraphEvent ? eventTypeLabel(latestGraphEvent.type) : ''
  }
}

function buildArtifactObservability(taskState) {
  const manifest = taskState.artifactManifest && typeof taskState.artifactManifest === 'object' ? taskState.artifactManifest : {}
  const approvals = Array.isArray(taskState.approvals) ? taskState.approvals : []
  const fallbackCount = Number(taskState.reportIrSummary?.utility_assessment?.fallback_trace_count || taskState.structuredResultDigest?.fallback_trace_count || 0)
  const approvalState = approvals.some((item) => String(item?.status || '').trim() !== 'resolved')
    ? '待处理'
    : (approvals.length ? approvalDecisionLabel(approvals[approvals.length - 1]?.decision) : '未触发')
  const phaseQueues = {
    interpret: ['conflict_map', 'mechanism_summary', 'utility_assessment', 'ir', 'structured_projection'],
    write: ['draft_bundle_v2', 'validation_result', 'repair_plan', 'graph_state', 'full_markdown'],
    review: ['validation_result', 'repair_plan', 'graph_state', 'approval_records', 'full_markdown'],
    persist: ['approval_records', 'full_markdown']
  }
  const allEntries = Object.entries(manifest)
    .filter(([key]) => !['versions', 'runtime_log'].includes(String(key || '').trim()))
    .map(([key, record]) => ({
      key,
      meta: artifactDisplayMeta(key),
      record: record && typeof record === 'object' ? record : {},
      ready: String(record?.status || '').trim() === 'ready',
      createdAt: new Date(String(record?.created_at || '').trim() || 0).getTime() || 0
    }))
  const latestReady = [...allEntries].filter((item) => item.ready).sort((a, b) => a.createdAt - b.createdAt).pop() || null
  const phaseQueue = phaseQueues[String(taskState.phase || '').trim()] || ['structured_projection', 'ir', 'draft_bundle', 'full_markdown']
  const currentKey = phaseQueue.find((key) => String(manifest[normalizeArtifactKey(key)]?.status || '').trim() !== 'ready')
    || (String(taskState.status || '').trim() === 'completed' ? 'full_markdown' : phaseQueue[phaseQueue.length - 1])
  const items = [latestReady?.key, currentKey, 'full_markdown']
    .map((key) => normalizeArtifactKey(key))
    .filter((key, index, list) => key && list.indexOf(key) === index)
    .map((key) => {
      const record = manifest[key] && typeof manifest[key] === 'object' ? manifest[key] : {}
      const meta = artifactDisplayMeta(key)
      const ready = String(record.status || '').trim() === 'ready'
      let statusText = ready ? (key === 'approval_records' ? '已记录' : '已生成') : '未开始'
      if (!ready && key === normalizeArtifactKey(currentKey)) {
        statusText = String(taskState.status || '').trim() === 'waiting_approval' && key === 'approval_records'
          ? '待确认'
          : (['queued', 'running', 'waiting_approval'].includes(String(taskState.status || '').trim()) ? '生成中' : '未开始')
      }
      if (!ready && key === 'full_markdown' && String(taskState.status || '').trim() === 'completed') statusText = '已生成'
      return {
        key,
        label: meta.label,
        description: meta.description,
        ready,
        isCurrent: key === normalizeArtifactKey(currentKey),
        isOutput: key === 'full_markdown',
        statusText,
        createdAtLabel: formatTimestamp(record.created_at),
        sourceLabel: Array.isArray(record.source_artifact_ids) && record.source_artifact_ids.length
          ? record.source_artifact_ids.join('、')
          : (Array.isArray(record.parent_artifact_ids) && record.parent_artifact_ids.length ? record.parent_artifact_ids.join('、') : '当前主线'),
        reviewState: key === 'approval_records' || key === 'full_markdown' ? approvalState : '',
        fallbackState: fallbackCount > 0 && ['utility_assessment', 'draft_bundle', 'full_markdown'].includes(key) ? `已回退 ${fallbackCount} 次` : ''
      }
    })
  return {
    items,
    upcomingLine: items.some((item) => item.ready) ? '' : '后续将生成：分析中枢 → 草稿素材 → 正式报告'
  }
}

function buildDecisionObservability(taskState, approvals) {
  const utility = taskState.reportIrSummary?.utility_assessment && typeof taskState.reportIrSummary.utility_assessment === 'object'
    ? taskState.reportIrSummary.utility_assessment
    : (taskState.structuredResultDigest?.utility_assessment && typeof taskState.structuredResultDigest.utility_assessment === 'object'
        ? taskState.structuredResultDigest.utility_assessment
        : {})
  const latestApproval = [...approvals].reverse()[0] || null
  const fallbackTrace = Array.isArray(utility.fallback_trace) ? utility.fallback_trace : []
  const missingDimensions = Array.isArray(utility.missing_dimensions) ? utility.missing_dimensions : []
  const rawDecision = String(utility.decision || '').trim() || (taskState.status === 'completed' ? 'pass' : 'pending')
  const hasPendingApproval = approvals.some((item) => String(item?.status || '').trim() !== 'resolved')
  let finalReason = ''
  if (hasPendingApproval) finalReason = summarizeApprovalReason(latestApproval) || '正式报告触发审核，等待人工确认。'
  else if (rawDecision === 'fallback_recompile' && fallbackTrace.length) finalReason = String(fallbackTrace[0]?.reason || '').trim() || '当前判断还不够完整，暂时不能生成报告。'
  else if (missingDimensions.length) finalReason = `当前还缺少 ${missingDimensions.slice(0, 3).join('、')}。`
  else if (rawDecision === 'pass') finalReason = taskState.status === 'completed' ? '当前结果已满足输出条件。' : '当前判断已满足进入下一步的条件。'
  else finalReason = sanitizeRuntimeMessage(taskState.currentOperation || taskState.message) || '当前还没有状态说明。'
  let nextAction = String(utility.next_action || '').trim()
  if (hasPendingApproval) nextAction = '等待人工处理后继续。'
  else if (!nextAction && rawDecision === 'pass') nextAction = taskState.status === 'completed' ? '可直接查看最终结果。' : '继续生成正式报告。'
  else if (!nextAction) nextAction = '等待下一步调度。'
  return {
    utilityDecision: rawDecision,
    utilityDecisionLabel: utilityDecisionLabel(rawDecision, approvals),
    missingDimensions,
    fallbackTrace,
    fallbackSummary: fallbackTrace.length
      ? fallbackTrace.map((item) => String(item?.reason || item?.suggested_pass || item?.dimension || '').trim()).filter(Boolean).slice(0, 2).join('；')
      : '暂无调整记录',
    reviewReason: hasPendingApproval ? '需审核' : (latestApproval ? approvalDecisionLabel(latestApproval.decision) : '未触发审核'),
    approvalDecision: latestApproval?.decision ? approvalDecisionLabel(latestApproval.decision) : '暂未审核',
    finalReason,
    nextAction,
    hasPendingApproval
  }
}

function buildApprovalObservability(taskState, approvals) {
  const rawEvents = Array.isArray(taskState.events) ? taskState.events : []
  const interruptEvent = [...rawEvents].reverse().find((item) => String(item?.type || '').trim() === 'approval.required')
  const resumeEvent = [...rawEvents].reverse().find((item) => item?.payload?.resume_from || String(item?.type || '').trim() === 'approval.resolved')
  const latestApproval = latestApprovalRecord(approvals)
  const hasPending = approvals.some((item) => String(item?.status || '').trim() !== 'resolved')
  const toolArgs = latestApproval?.action?.tool_args && typeof latestApproval.action.tool_args === 'object'
    ? latestApproval.action.tool_args
    : {}
  const reason = hasPending
    ? (summarizeApprovalReason(latestApproval) || sanitizeRuntimeMessage(interruptEvent?.message) || '任务正在等待人工确认。')
    : (resumeEvent?.payload?.resume_from
        ? `已从 ${String(resumeEvent.payload.resume_from || '').trim()} 恢复执行。`
        : (latestApproval ? `${approvalDecisionLabel(latestApproval.decision)}，后续会继续推进。` : '必要时会暂停等待确认。'))
  return {
    compactStatus: hasPending
      ? '等待处理'
      : (latestApproval ? approvalDecisionLabel(latestApproval.decision) : '暂未触发'),
    reason,
    affectedLabel: String(latestApproval?.title || '').trim() || (hasPending ? '正式文稿' : ''),
    resumeLabel: resumeEvent?.payload?.resume_from ? String(resumeEvent.payload.resume_from || '').trim() : '',
    interruptLabel: String(latestApproval?.interrupt_id || latestApproval?.action?.graph_interrupt?.interrupt_id || '').trim(),
    checkpointLabel: String(toolArgs.checkpoint_locator || toolArgs.checkpoint_path || '').trim(),
    actionSummary: hasPending && Array.isArray(latestApproval?.allowed_decisions)
      ? latestApproval.allowed_decisions.map((item) => approvalDecisionLabel(item)).join(' / ')
      : '',
    canOpenPanel: hasPending || approvals.length > 0
  }
}

function buildTodoObservability(taskState) {
  const rawEvents = Array.isArray(taskState.events) ? taskState.events : []
  const latestTodoEvent = [...rawEvents].reverse().find((item) => String(item?.type || '').trim() === 'todo.updated')
  const eventTodos = Array.isArray(latestTodoEvent?.payload?.todos) ? latestTodoEvent.payload.todos : []
  const sourceTodos = Array.isArray(taskState.todos) && taskState.todos.length ? taskState.todos : eventTodos
  const items = sourceTodos
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => {
      const status = normalizePrimaryTodoStatus(item.status)
      return {
        id: String(item.id || `todo-${index + 1}`).trim() || `todo-${index + 1}`,
        order: index + 1,
        label: String(item.label || item.content || `任务 ${index + 1}`).trim() || `任务 ${index + 1}`,
        status,
        statusText: todoStatusLabel(status),
        isCurrent: status === 'running'
      }
    })
  const completedCount = items.filter((item) => item.status === 'completed').length
  const runningCount = items.filter((item) => item.status === 'running').length
  const failedCount = items.filter((item) => item.status === 'failed').length
  const pendingCount = items.filter((item) => item.status === 'pending').length
  let summary = '当前还没有任务清单。'
  if (items.length) {
    if (failedCount) summary = `任务清单共 ${items.length} 项，当前有 ${failedCount} 项执行失败。`
    else if (runningCount) summary = `任务清单共 ${items.length} 项，已完成 ${completedCount} 项，当前正在推进 ${runningCount} 项。`
    else if (completedCount === items.length) summary = `任务清单共 ${items.length} 项，当前已全部完成。`
    else summary = `任务清单共 ${items.length} 项，已完成 ${completedCount} 项，待开始 ${pendingCount} 项。`
  }
  return {
    items,
    totalCount: items.length,
    completedCount,
    runningCount,
    failedCount,
    pendingCount,
    summary,
    updatedAtLabel: formatTimestamp(latestTodoEvent?.ts || latestTodoEvent?.timestamp),
    updatedMessage: sanitizeRuntimeMessage(latestTodoEvent?.message) || '',
    updatedBy: displayAgentLabel(latestTodoEvent?.agent) || ''
  }
}

function eventTypeLabel(type) {
  const mapping = {
    'task.created': '任务创建',
    'phase.started': '阶段开始',
    'phase.progress': '阶段推进',
    'agent.started': '节点启动',
    'agent.memo': '节点说明',
    'tool.called': '工具调用',
    'tool.result': '工具回执',
    'artifact.ready': '产物就绪',
    'artifact.updated': '产物更新',
    'trust.updated': '置信更新',
    'todo.updated': '清单更新',
    'subagent.started': '子代理启动',
    'subagent.completed': '子代理完成',
    'approval.required': '等待确认',
    'approval.resolved': '确认完成',
    'graph.node.started': '图节点启动',
    'graph.node.completed': '图节点完成',
    'graph.node.failed': '图节点失败',
    'validation.failed': '验证失败',
    'repair.loop.started': '修复开始',
    'repair.loop.completed': '修复完成',
    'compile.blocked': '编译阻止',
    'compile.started': '正式编译',
    'compile.completed': '编译完成',
    'interrupt.human_review': '等待人工复核',
    'task.completed': '任务完成',
    'task.failed': '任务失败',
    'task.cancelled': '任务取消',
    heartbeat: '状态同步'
  }
  return mapping[String(type || '').trim()] || '任务事件'
}

function eventPrimaryStatus(type) {
  const normalized = String(type || '').trim()
  if (['task.failed', 'task.cancelled', 'graph.node.failed', 'validation.failed', 'compile.blocked'].includes(normalized)) return 'failed'
  if (['task.completed', 'artifact.ready', 'artifact.updated', 'approval.resolved', 'subagent.completed', 'tool.result', 'graph.node.completed', 'repair.loop.completed', 'compile.completed'].includes(normalized)) return 'completed'
  if (['approval.required', 'interrupt.human_review'].includes(normalized)) return 'running'
  if (['phase.started', 'phase.progress', 'agent.started', 'tool.called', 'subagent.started', 'graph.node.started', 'repair.loop.started', 'compile.started'].includes(normalized)) return 'running'
  return 'pending'
}

export function buildDebugEvent(event = {}) {
  const payload = event?.payload && typeof event.payload === 'object' ? event.payload : {}
  const type = String(event?.type || '').trim()
  const stage = String(payload.closure_stage || '').trim()
  const actor = displayAgentLabel(payload.agent_name || event?.agent || payload.failed_actor)
  const toolName = toolDisplayName(payload.tool_name)
  const model = {
    id: Number(event?.event_id || event?.eventId || 0),
    type,
    label: eventTypeLabel(type),
    timestamp: String(event?.ts || event?.timestamp || '').trim(),
    timestampLabel: formatTimestamp(event?.ts || event?.timestamp),
    primaryStatus: eventPrimaryStatus(type),
    title: '',
    message: '',
    actorLabel: actor,
    detailLines: [],
    nextStep: '',
    raw: event
  }

  if (type === 'task.failed') {
    model.title = failureHeadlineFromStage(stage)
    model.message = failureMessageFromStage(stage)
    model.nextStep = nextStepFromStage(stage)
    const stateFilesSummary = summarizeStateFiles(payload.state_files)
    if (payload.current_operation) model.detailLines.push(`停在：${sanitizeEventText(payload.current_operation)}`)
    if (Array.isArray(payload.subagents_completed) && payload.subagents_completed.length) {
      model.detailLines.push(`已完成节点：${payload.subagents_completed.map((item) => displayAgentLabel(item)).filter(Boolean).join('、')}`)
    }
    if (stateFilesSummary) model.detailLines.push(stateFilesSummary)
    if (payload.validation_error_message) model.detailLines.push(`校验提示：${sanitizeEventText(payload.validation_error_message)}`)
    return model
  }

  if (type === 'agent.memo') {
    const receiptStage = String(payload.stage_id || '').trim()
    const receiptSummary = sanitizeEventText(payload.decision_summary || event?.message)
    const receiptToolName = String(payload.tool_name || '').trim()
    if (receiptStage && receiptSummary) {
      const diagnosticKind = String(payload.diagnostic_kind || '').trim()
      if (diagnosticKind === 'contract_violation') model.title = '任务边界异常已识别'
      else if (diagnosticKind === 'contract_binding_failed') model.title = '合同绑定失败'
      else if (diagnosticKind === 'legacy_adapter_hit') model.title = '命中兼容入口'
      else if (diagnosticKind === 'partial_range_coverage') model.title = '语料区间部分覆盖已识别'
      else if (diagnosticKind === 'scope_clipped_to_contract') model.title = '检索时间窗已裁剪'
      else if (diagnosticKind === 'source_unavailable') model.title = '语料源未命中'
      else model.title = `${toolDisplayName(receiptToolName)} 已形成阶段判断`
      model.message = receiptSummary
      model.nextStep = sanitizeEventText(payload.next_action)
      const countLines = formatReceiptCounts(payload.counts)
      if (shouldDisplayReceiptCounts(receiptToolName, payload.counts)) model.detailLines.push(`计数：${countLines.join('，')}`)
      const contractValue = formatExecutionValue(payload.contract_value)
      const proposedValue = formatExecutionValue(payload.agent_proposed_value)
      const effectiveValue = formatExecutionValue(payload.effective_value)
      if (contractValue) model.detailLines.push(`合同绑定：${contractValue}`)
      if (proposedValue) model.detailLines.push(`原始提议：${proposedValue}`)
      if (effectiveValue) model.detailLines.push(`系统生效：${effectiveValue}`)
      const requestedRange = formatRangeLabel(payload.requested_range)
      const effectiveRange = formatRangeLabel(payload.effective_range)
      const resolvedFetchRange = formatRangeLabel(payload.resolved_fetch_range)
      if (requestedRange) model.detailLines.push(`请求区间：${requestedRange}`)
      if (effectiveRange) model.detailLines.push(`执行区间：${effectiveRange}`)
      if (resolvedFetchRange) model.detailLines.push(`命中归档区间：${resolvedFetchRange}`)
      if (payload.contract_topic_identifier) model.detailLines.push(`任务专题：${sanitizeEventText(payload.contract_topic_identifier)}`)
      if (payload.effective_topic_identifier && payload.effective_topic_identifier !== payload.contract_topic_identifier) {
        model.detailLines.push(`当前执行专题：${sanitizeEventText(payload.effective_topic_identifier)}`)
      }
      if (payload.violation_origin) model.detailLines.push(`异常来源：${sanitizeEventText(payload.violation_origin)}`)
      if (payload.repair_action) model.detailLines.push(`修正动作：${sanitizeEventText(payload.repair_action)}`)
      if (payload.skip_reason) model.detailLines.push(`跳过原因：${sanitizeEventText(payload.skip_reason)}`)
      return model
    }
    model.title = sanitizeEventText(event?.title) || '节点说明'
    model.message = stage ? failureMessageFromStage(stage) : sanitizeEventText(event?.message)
    model.nextStep = nextStepFromStage(stage)
    const stateFilesSummary = summarizeStateFiles(payload.state_files)
    if (payload.current_operation) model.detailLines.push(`当前卡点：${sanitizeEventText(payload.current_operation)}`)
    if (stateFilesSummary) model.detailLines.push(stateFilesSummary)
    return model
  }

  if (type === 'tool.called') {
    model.title = `正在${toolName}`
    model.message = actor ? `${actor} 已发起 ${toolName}。` : `已发起 ${toolName}。`
    model.detailLines.push(...summarizeToolCallArgs(payload.tool_name, payload.args_preview))
    if (Number.isFinite(Number(payload.tool_round_count))) {
      const round = Number(payload.tool_round_count)
      const limit = Number(payload.tool_round_limit || 0)
      if (Number.isFinite(limit) && limit > 0) model.detailLines.push(`调用轮次：第 ${round} / ${limit} 轮`)
      else model.detailLines.push(`调用轮次：第 ${round} 轮`)
    }
    return model
  }

  if (type === 'tool.result') {
    model.title = `${toolName} 已返回`
    model.message = summarizeToolResultPreview(payload.tool_name, payload.result_preview)
    return model
  }

  if (type === 'phase.context' && String(payload.diagnostic_kind || '').trim()) {
    const diagnosticKind = String(payload.diagnostic_kind || '').trim()
    if (diagnosticKind === 'legacy_runtime_version') model.title = '旧运行时任务已阻止恢复'
    else model.title = sanitizeEventText(event?.title) || '阶段诊断'
    model.message = sanitizeEventText(event?.message)
    if (payload.runtime_contract_version) model.detailLines.push(`当前 ABI：${sanitizeEventText(payload.runtime_contract_version)}`)
    if (payload.task_runtime_contract_version) model.detailLines.push(`任务 ABI：${sanitizeEventText(payload.task_runtime_contract_version)}`)
    if (payload.next_action) model.nextStep = sanitizeEventText(payload.next_action)
    return model
  }

  if (type === 'subagent.started') {
    model.title = `${displayAgentLabel(payload.agent_name || event?.agent) || '子代理'} 已开始`
    model.message = '这个分支任务已经启动。'
    const preview = sanitizeEventPreview(payload.task_preview)
    if (preview) model.detailLines.push(preview)
    return model
  }

  if (type === 'subagent.completed') {
    model.title = `${displayAgentLabel(payload.agent_name || event?.agent) || '子代理'} 已完成`
    model.message = '这个分支任务已经返回结果。'
    const preview = sanitizeEventPreview(payload.result_preview)
    if (preview) model.detailLines.push(preview)
    return model
  }

  if (type === 'approval.required') {
    model.title = '等待你介入'
    model.message = '任务已经走到需要人工确认的步骤。'
    return model
  }

  if (type === 'approval.resolved') {
    model.title = '介入结果已同步'
    model.message = '任务会根据你的处理结果继续推进。'
    return model
  }

  if (type === 'graph.node.started' || type === 'graph.node.completed' || type === 'graph.node.failed') {
    const nodeName = String(payload.current_node || event?.agent || '').trim()
    model.actorLabel = displayAgentLabel(nodeName) || model.actorLabel
    model.title = `${displayAgentLabel(nodeName) || '图节点'}${type.endsWith('started') ? ' 已启动' : (type.endsWith('completed') ? ' 已完成' : ' 执行失败')}`
    model.message = sanitizeEventText(event?.message) || '图执行状态已更新。'
    const visitedNodes = Array.isArray(payload.visited_nodes) ? payload.visited_nodes.map((item) => displayAgentLabel(item) || String(item || '').trim()).filter(Boolean) : []
    if (visitedNodes.length) model.detailLines.push(`已访问节点：${visitedNodes.join('、')}`)
    return model
  }

  if (type === 'validation.failed') {
    const validation = payload.validation_result_v2 && typeof payload.validation_result_v2 === 'object' ? payload.validation_result_v2 : {}
    const failures = Array.isArray(validation.failures) ? validation.failures : []
    model.title = '单元验证未通过'
    model.message = sanitizeEventText(event?.message) || `当前有 ${failures.length} 个单元未通过验证。`
    if (validation.gate) model.detailLines.push(`当前 gate：${sanitizeEventText(validation.gate)}`)
    if (Number.isFinite(Number(payload.repair_count))) model.detailLines.push(`修复轮次：第 ${Number(payload.repair_count)} 轮`)
    const firstFailure = failures[0] && typeof failures[0] === 'object' ? failures[0] : null
    if (firstFailure?.failure_type) model.detailLines.push(`首个失败：${sanitizeEventText(firstFailure.failure_type)} / ${sanitizeEventText(firstFailure.target_unit_id)}`)
    return model
  }

  if (type === 'repair.loop.started' || type === 'repair.loop.completed') {
    model.title = type === 'repair.loop.started' ? '开始自动修复' : '自动修复已完成'
    model.message = sanitizeEventText(event?.message) || ''
    if (Number.isFinite(Number(payload.repair_count))) model.detailLines.push(`修复轮次：第 ${Number(payload.repair_count)} 轮`)
    const plan = payload.repair_plan_v2 && typeof payload.repair_plan_v2 === 'object' ? payload.repair_plan_v2 : {}
    const patchCount = Array.isArray(plan.patches) ? plan.patches.length : Number(plan.metadata?.patch_count || 0)
    if (patchCount) model.detailLines.push(`计划补丁：${patchCount}`)
    return model
  }

  if (type === 'compile.blocked') {
    const validation = payload.validation_result_v2 && typeof payload.validation_result_v2 === 'object' ? payload.validation_result_v2 : {}
    model.title = '正式编译已阻止'
    model.message = sanitizeEventText(event?.message) || '当前停在编译前门禁。'
    if (validation.gate) model.detailLines.push(`当前 gate：${sanitizeEventText(validation.gate)}`)
    const failureCount = Array.isArray(validation.failures) ? validation.failures.length : 0
    if (failureCount) model.detailLines.push(`失败单元：${failureCount}`)
    model.nextStep = '先查看失败单元和候选 trace，再决定是否人工复核。'
    return model
  }

  if (type === 'compile.started' || type === 'compile.completed') {
    model.title = type === 'compile.started' ? '正式编译开始' : '正式编译完成'
    model.message = sanitizeEventText(event?.message) || ''
    if (Number.isFinite(Number(payload.validated_unit_count))) model.detailLines.push(`已验证单元：${Number(payload.validated_unit_count)}`)
    if (Number.isFinite(Number(payload.markdown_issue_count))) model.detailLines.push(`Markdown 风险：${Number(payload.markdown_issue_count)}`)
    return model
  }

  if (type === 'interrupt.human_review') {
    const validation = payload.validation_result_v2 && typeof payload.validation_result_v2 === 'object' ? payload.validation_result_v2 : {}
    model.title = '等待人工复核'
    model.message = sanitizeEventText(event?.message) || '自动修复已停止，当前需要人工复核。'
    if (validation.gate) model.detailLines.push(`当前 gate：${sanitizeEventText(validation.gate)}`)
    if (Array.isArray(validation.failures) && validation.failures.length) {
      const item = validation.failures[0]
      model.detailLines.push(`优先检查：${sanitizeEventText(item?.failure_type)} / ${sanitizeEventText(item?.target_unit_id)}`)
    }
    return model
  }

  if (type === 'task.completed') {
    model.title = '任务已完成'
    model.message = '结构化结果和正式文稿已经就绪。'
    return model
  }

  if (type === 'artifact.ready' || type === 'artifact.updated') {
    model.title = sanitizeEventText(event?.title) || '结果已更新'
    model.message = sanitizeEventText(event?.message) || '新的结果内容已经写入。'
    return model
  }

  model.title = sanitizeEventText(event?.title) || eventTypeLabel(type)
  model.message = sanitizeEventText(event?.message)
  return model
}

function buildTimelineEvents(events = []) {
  const KEY_TYPES = new Set([
    'phase.started',
    'phase.progress',
    'agent.memo',
    'subagent.started',
    'subagent.completed',
    'graph.node.started',
    'graph.node.completed',
    'graph.node.failed',
    'validation.failed',
    'repair.loop.started',
    'repair.loop.completed',
    'compile.blocked',
    'compile.started',
    'compile.completed',
    'interrupt.human_review',
    'artifact.ready',
    'artifact.updated',
    'approval.required',
    'approval.resolved',
    'task.failed',
    'task.completed',
    'task.cancelled'
  ])
  const receiptToolCallIds = buildReceiptToolCallIdSet(events)
  return (Array.isArray(events) ? events : [])
    .filter((item) => item && String(item.type || '').trim() !== 'heartbeat')
    .filter((item) => {
      const type = String(item?.type || '').trim()
      if (KEY_TYPES.has(type)) return true
      if (!['tool.called', 'tool.result'].includes(type)) return false
      const payload = item?.payload && typeof item.payload === 'object' ? item.payload : {}
      if (type === 'tool.result' && receiptToolCallIds.has(String(payload.tool_call_id || '').trim())) return false
      return !isLowSignalToolName(payload.tool_name)
    })
    .map(buildDebugEvent)
    .slice(-12)
    .reverse()
}

/**
 * @returns {{
 *   runSummary: object,
 *   stageTimeline: object[],
 *   timelineEvents: object[],
 *   agentDrawer: object[],
 *   debugEvents: object[],
 *   inspector: object,
 *   graphObservability: object,
 *   todoObservability: object,
 *   artifactObservability: object,
 *   decisionObservability: object,
 *   approvalObservability: object,
 *   runtimeDiagnostics: object,
 *   approvals: object[],
 *   artifacts: object[],
 *   hasTask: boolean,
 *   canIntervene: boolean
 * }}
 */
export function buildRunConsoleViewModel(taskState = {}) {
  const agents = buildResearchAgents(taskState)
  const stageTimeline = deriveStageCards(taskState, agents)
  const progress = calculateProgress(taskState, stageTimeline, agents)
  const rawEvents = (Array.isArray(taskState.events) ? taskState.events : [])
    .filter((item) => String(item?.type || '').trim() !== 'heartbeat')
  const receiptToolCallIds = buildReceiptToolCallIdSet(rawEvents)
  const meaningfulRawEvents = rawEvents.filter((item) => {
    const type = String(item?.type || '').trim()
    if (!['tool.called', 'tool.result'].includes(type)) return true
    const payload = item?.payload && typeof item.payload === 'object' ? item.payload : {}
    if (type === 'tool.result' && receiptToolCallIds.has(String(payload.tool_call_id || '').trim())) return false
    return !isLowSignalToolName(payload.tool_name)
  })
  const debugEvents = (meaningfulRawEvents.length ? meaningfulRawEvents : rawEvents)
    .map(buildDebugEvent)
    .slice(-40)
    .reverse()
  const timelineEvents = buildTimelineEvents(taskState.events)
  const approvals = Array.isArray(taskState.approvals) ? taskState.approvals : []
  const pendingApprovals = approvals.filter((item) => String(item?.status || '').trim() !== 'resolved')
  const currentStage = stageTimeline.find((item) => item.status === 'running')
    || stageTimeline.find((item) => item.status === 'failed')
    || stageTimeline.find((item) => item.status === 'pending')
    || stageTimeline[stageTimeline.length - 1]
  const digest = taskState.reportIrSummary && typeof taskState.reportIrSummary === 'object' && Object.keys(taskState.reportIrSummary).length
    ? taskState.reportIrSummary
    : (taskState.structuredResultDigest && typeof taskState.structuredResultDigest === 'object' ? taskState.structuredResultDigest : {})
  const digestCounts = digest.counts || {}
  const artifacts = buildArtifactCards(taskState)
  const recentSuccessArtifact = [...artifacts].reverse().find((item) => item.ready) || null
  const latestFailure = debugEvents.find((item) => item.primaryStatus === 'failed') || null
  const graphObservability = buildGraphObservability(taskState, timelineEvents)
  const todoObservability = buildTodoObservability(taskState)
  const artifactObservability = buildArtifactObservability(taskState)
  const decisionObservability = buildDecisionObservability(taskState, approvals)
  const approvalObservability = buildApprovalObservability(taskState, approvals)
  const runtimeDiagnostics = resolveRuntimeDiagnostics(taskState, approvals)
  const runSummary = {
    title: String(taskState.topic || '').trim() || '当前任务',
    rangeText: taskState.start ? `${taskState.start} → ${taskState.end || taskState.start}` : '待补齐',
    modeText: modeLabel(taskState.mode),
    statusText: statusLabel(taskState.status),
    statusTone: toPrimaryStatus(taskState.status),
    progress,
    headline: !taskState.id
      ? '尚未创建任务'
      : (taskState.status === 'failed'
        ? (latestFailure?.title || '任务没有完成')
        : (sanitizeRuntimeMessage(taskState.message) || '任务正在推进')),
    subline: !taskState.id
      ? '创建任务后，页面会切换为单次 run 控制台。'
      : (taskState.status === 'completed'
          ? '语义报告和正式文稿都已写好。'
          : (taskState.status === 'waiting_approval'
              ? '任务暂停等待你确认后继续。'
              : `当前阶段：${phaseLabel(taskState.phase)}`)),
    connectionText: taskState.connectionMode === 'streaming'
      ? '实时连接'
      : (taskState.connectionMode === 'reconnecting'
          ? '重连中'
          : (taskState.connectionMode === 'polling_fallback' ? '自动刷新' : '待连接'))
  }
  const inspector = {
    currentStage: currentStage || null,
    nextStep: latestFailure?.nextStep || (pendingApprovals.length ? '先处理待确认项，再继续推进结果存储。' : (currentStage?.description || '等待下一步调度。')),
    latestArtifact: recentSuccessArtifact,
    digestSummary: String(digest.summary || '').trim(),
    digestCounts: [
      { label: '时间线', value: Number(digestCounts.timeline || 0) },
      { label: '主体', value: Number(digestCounts.subjects || digestCounts.actors || 0) },
      { label: '断言', value: Number(digestCounts.claims || 0) },
      { label: '证据', value: Number(digestCounts.evidence || 0) },
      { label: '风险', value: Number(digestCounts.risks || 0) }
    ],
    failure: latestFailure
  }
  return {
    hasTask: Boolean(taskState.id),
    canIntervene: Boolean(pendingApprovals.length || latestFailure),
    runSummary,
    stageTimeline,
    timelineEvents,
    agentDrawer: agents,
    debugEvents,
    inspector,
    graphObservability,
    todoObservability,
    artifactObservability,
    decisionObservability,
    approvalObservability,
    runtimeDiagnostics,
    approvals,
    artifacts
  }
}
