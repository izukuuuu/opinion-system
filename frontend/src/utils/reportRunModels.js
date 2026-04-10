const PLAN_STEP_DESCRIPTIONS = {
  scope: '确认专题、时间范围、模式和可直接复用的已有结果。',
  research: '并行推进检索、证据、时间线、立场和传播分析。',
  synthesis: '总控代理汇总并行结果，整理结构化报告对象。',
  writing: '输出结构化结论，并整理正式文稿草稿。',
  validation: '检查证据覆盖、结论边界和表达风险。',
  persist: '处理人工确认，并写入最终结果。'
}

export const RESEARCH_SUBAGENT_IDS = ['retrieval_router', 'evidence_organizer', 'timeline_analyst', 'stance_conflict', 'propagation_analyst']
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
    evidence_organizer: '证据整理',
    timeline_analyst: '时间线与因果',
    stance_conflict: '主体与立场',
    propagation_analyst: '传播结构',
    report_coordinator: '总控汇总',
    writer: '文稿生成',
    validator: '质量校验'
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
  if (id === 'report_coordinator') return '总控代理'
  return subagentLabel(id)
}

function toolDisplayName(toolName) {
  const mapping = {
    task: '委派子任务',
    write_todos: '更新执行计划',
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
    overwrite_report_cache: '更新结果缓存'
  }
  return mapping[String(toolName || '').trim()] || String(toolName || '执行动作')
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

function summarizeToolResultPreview(toolName, rawPreview) {
  const text = String(rawPreview || '').trim()
  if (!text) return ''
  if (text.includes(`Error invoking tool '${toolName}'`)) {
    if (toolName === 'save_structured_report') return '结构化保存没有通过校验。'
    if (toolName === 'write_final_report') return '正式文稿写入失败。'
    if (toolName === 'overwrite_report_cache') return '结果缓存更新失败。'
    return `${toolDisplayName(toolName)}失败。`
  }
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
  const hasStructuredResult = Boolean(taskState.artifacts?.report_ready || Object.keys(taskState.structuredResultDigest || {}).length)
  const hasFullReport = Boolean(taskState.artifacts?.full_report_ready)
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
  return [
    {
      key: 'report_ready',
      label: '结构化结果',
      description: '供查看页读取的结构化对象。',
      ready: Boolean(taskState.artifacts?.report_ready)
    },
    {
      key: 'full_report_ready',
      label: '正式文稿',
      description: '供 AI 报告页读取的完整文稿。',
      ready: Boolean(taskState.artifacts?.full_report_ready)
    },
    {
      key: 'report_runtime_artifact',
      label: '运行时草稿',
      description: '审批通过后保存的本次文稿版本。',
      ready: Boolean(taskState.artifacts?.report_runtime_artifact)
    }
  ]
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
    'task.completed': '任务完成',
    'task.failed': '任务失败',
    'task.cancelled': '任务取消',
    heartbeat: '状态同步'
  }
  return mapping[String(type || '').trim()] || '任务事件'
}

function eventPrimaryStatus(type) {
  const normalized = String(type || '').trim()
  if (['task.failed', 'task.cancelled'].includes(normalized)) return 'failed'
  if (['task.completed', 'artifact.ready', 'artifact.updated', 'approval.resolved', 'subagent.completed', 'tool.result'].includes(normalized)) return 'completed'
  if (['approval.required'].includes(normalized)) return 'running'
  if (['phase.started', 'phase.progress', 'agent.started', 'tool.called', 'subagent.started'].includes(normalized)) return 'running'
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
    model.message = actor ? `${actor} 正在执行动作。` : '正在执行动作。'
    return model
  }

  if (type === 'tool.result') {
    model.title = `${toolName} 已返回`
    model.message = summarizeToolResultPreview(payload.tool_name, payload.result_preview)
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
    'artifact.ready',
    'artifact.updated',
    'approval.required',
    'approval.resolved',
    'task.failed',
    'task.completed',
    'task.cancelled'
  ])
  return (Array.isArray(events) ? events : [])
    .filter((item) => item && String(item.type || '').trim() !== 'heartbeat')
    .map(buildDebugEvent)
    .filter((item) => KEY_TYPES.has(item.type))
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
  const debugEvents = (Array.isArray(taskState.events) ? taskState.events : [])
    .filter((item) => String(item?.type || '').trim() !== 'heartbeat')
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
  const digest = taskState.structuredResultDigest && typeof taskState.structuredResultDigest === 'object'
    ? taskState.structuredResultDigest
    : {}
  const digestCounts = digest.counts || {}
  const artifacts = buildArtifactCards(taskState)
  const recentSuccessArtifact = [...artifacts].reverse().find((item) => item.ready) || null
  const latestFailure = debugEvents.find((item) => item.primaryStatus === 'failed') || null
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
          ? '结构化结果和正式文稿都已写好。'
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
      { label: '主体', value: Number(digestCounts.subjects || 0) },
      { label: '证据', value: Number(digestCounts.evidence || 0) },
      { label: '引用', value: Number(digestCounts.citations || 0) }
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
    approvals,
    artifacts
  }
}
