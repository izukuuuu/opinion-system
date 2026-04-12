import { defineStore } from 'pinia'

export function createDefaultReportRunState() {
  return {
    loading: false,
    creating: false,
    streaming: false,
    reconnecting: false,
    usingPollingFallback: false,
    error: '',
    id: '',
    threadId: '',
    reused: false,
    topic: '',
    topicIdentifier: '',
    start: '',
    end: '',
    mode: 'fast',
    status: 'idle',
    phase: '',
    percentage: 0,
    message: '',
    updatedAt: '',
    startedAt: '',
    finishedAt: '',
    workerPid: 0,
    childPid: 0,
    cancelRequested: false,
    trust: {},
    artifacts: {},
    subagents: [],
    agents: [],
    todos: [],
    approvals: [],
    runState: {},
    orchestratorState: {},
    currentActor: '',
    currentOperation: '',
    lastDiagnostic: {},
    structuredResultDigest: {},
    reportIrSummary: {},
    artifactManifest: {},
    events: [],
    lastEventId: 0,
    lifecycleState: 'idle',
    connectionMode: 'idle'
  }
}

function normalizeEventId(item) {
  return Number(item?.event_id || item?.eventId || 0)
}

export const useReportRunStore = defineStore('report-run', {
  state: () => createDefaultReportRunState(),
  actions: {
    reset() {
      Object.assign(this, createDefaultReportRunState())
    },
    setLoading(value) {
      this.loading = Boolean(value)
    },
    setCreating(value) {
      this.creating = Boolean(value)
    },
    setError(value) {
      this.error = String(value || '').trim()
    },
    setConnectionMode(mode) {
      const next = String(mode || 'idle').trim() || 'idle'
      this.connectionMode = next
      this.streaming = next === 'streaming'
      this.reconnecting = next === 'reconnecting'
      this.usingPollingFallback = next === 'polling_fallback'
    },
    setLifecycleState(state) {
      this.lifecycleState = String(state || 'idle').trim() || 'idle'
    },
    mergeEvents(incoming = []) {
      const map = new Map((Array.isArray(this.events) ? this.events : []).map((item) => [normalizeEventId(item), item]))
      for (const item of Array.isArray(incoming) ? incoming : []) {
        const eventId = normalizeEventId(item)
        if (!eventId) continue
        if (String(item?.type || '').trim() === 'heartbeat') continue
        map.set(eventId, {
          ...item,
          event_id: eventId
        })
      }
      const merged = [...map.values()].sort((a, b) => normalizeEventId(a) - normalizeEventId(b))
      this.events = merged.slice(-240)
      this.lastEventId = normalizeEventId(this.events[this.events.length - 1]) || this.lastEventId || 0
    },
    applySnapshot(task, { reused = false } = {}) {
      if (!task || typeof task !== 'object') return
      const nextTaskId = String(task.id || '').trim()
      if (this.id && nextTaskId && this.id !== nextTaskId) {
        this.events = []
        this.lastEventId = 0
      }
      this.id = nextTaskId
      this.threadId = String(task.thread_id || '').trim()
      this.reused = Boolean(reused)
      this.topic = String(task.topic || '').trim()
      this.topicIdentifier = String(task.topic_identifier || '').trim()
      this.start = String(task.start || '').trim()
      this.end = String(task.end || '').trim() || this.start
      this.mode = String(task.mode || 'fast').trim() || 'fast'
      this.status = String(task.status || 'idle').trim() || 'idle'
      this.phase = String(task.phase || '').trim()
      this.percentage = Number(task.percentage || 0)
      this.message = String(task.message || '').trim()
      this.updatedAt = String(task.updated_at || '').trim()
      this.startedAt = String(task.started_at || '').trim()
      this.finishedAt = String(task.finished_at || '').trim()
      this.workerPid = Number(task.worker_pid || 0)
      this.childPid = Number(task.child_pid || 0)
      this.cancelRequested = Boolean(task.cancel_requested)
      this.trust = task.trust && typeof task.trust === 'object' ? task.trust : {}
      this.artifacts = task.artifacts && typeof task.artifacts === 'object' ? task.artifacts : {}
      this.subagents = Array.isArray(task.subagents) ? task.subagents : (Array.isArray(task.agents) ? task.agents : [])
      this.agents = this.subagents
      this.todos = Array.isArray(task.todos) ? task.todos : []
      this.approvals = Array.isArray(task.approvals) ? task.approvals : []
      this.runState = task.run_state && typeof task.run_state === 'object' ? task.run_state : {}
      this.orchestratorState = task.orchestrator_state && typeof task.orchestrator_state === 'object' ? task.orchestrator_state : {}
      this.currentActor = String(task.current_actor || '').trim()
      this.currentOperation = String(task.current_operation || '').trim()
      this.lastDiagnostic = task.last_diagnostic && typeof task.last_diagnostic === 'object' ? task.last_diagnostic : {}
      this.structuredResultDigest = task.structured_result_digest && typeof task.structured_result_digest === 'object'
        ? task.structured_result_digest
        : {}
      this.reportIrSummary = task.report_ir_summary && typeof task.report_ir_summary === 'object'
        ? task.report_ir_summary
        : {}
      this.artifactManifest = task.artifact_manifest && typeof task.artifact_manifest === 'object'
        ? task.artifact_manifest
        : {}
      this.mergeEvents(task.recent_events || [])
    }
  }
})
