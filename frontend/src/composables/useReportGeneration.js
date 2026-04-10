import { computed, effectScope, reactive, ref, watch } from 'vue'
import { useEventSource } from '@vueuse/core'
import { useApiBase } from './useApiBase'
import { normaliseRecord, splitFolderRange as sharedSplitFolderRange } from './useArchiveHistory'
import { buildAnalysisSections } from '../utils/analysisSections'
import { createReportRunLifecycleActor, buildLifecycleSnapshotInput } from '../machines/reportRunMachine'
import { useReportRunStore } from '../stores/reportRun'

const MAX_HISTORY = 24
const TASK_STORAGE_PREFIX = 'opinion-system:report-task'
const TASK_POLL_INTERVAL = 2000
const { callApi, ensureApiBase } = useApiBase()

const topicsState = reactive({ loading: false, error: '', options: [] })
const reportForm = reactive({ topic: '', start: '', end: '', mode: 'fast' })
const availableRange = reactive({
  loading: false,
  error: '',
  notice: '',
  hasAnalyzeHistory: false,
  topic: '',
  start: '',
  end: ''
})
const reportState = reactive({ loading: false, regenerating: false, error: '', lastLoaded: '' })
const fullReportState = reactive({ loading: false, regenerating: false, error: '', lastLoaded: '' })
const analysisState = reactive({ loading: false, error: '', lastLoaded: '', topic: '', start: '', end: '' })
const progressState = reactive({
  loading: false,
  polling: false,
  error: '',
  topic: '',
  start: '',
  end: '',
  stage: '',
  status: 'pending',
  message: '',
  updatedAt: ''
})
const historyState = reactive({ loading: false, error: '', topic: '' })
let taskState = null

const reportHistory = ref([])
const selectedHistoryId = ref('')
const reportData = ref(null)
const fullReportData = ref(null)
const analysisData = ref(null)
const progressLogs = ref([])
const topicOptions = computed(() => topicsState.options)
const analysisSections = computed(() => buildAnalysisSections(analysisData.value?.functions))
const analysisAiSummary = computed(() => analysisData.value?.ai_summary || null)
const taskEvents = computed(() => taskState?.events || [])
const activeTask = computed(() => (taskState?.id ? {
  id: taskState.id,
  threadId: taskState.threadId,
  status: taskState.status,
  phase: taskState.phase,
  percentage: taskState.percentage,
  message: taskState.message,
  trust: taskState.trust,
  artifacts: taskState.artifacts,
  subagents: taskState.subagents,
  agents: taskState.agents,
  todos: taskState.todos,
  approvals: taskState.approvals,
  runState: taskState.runState,
  orchestratorState: taskState.orchestratorState,
  currentOperation: taskState.currentOperation,
  lastDiagnostic: taskState.lastDiagnostic,
  structuredResultDigest: taskState.structuredResultDigest,
  events: taskState.events
} : null))
const taskStageList = [
  { id: 'prepare', label: '准备数据' },
  { id: 'analyze', label: '基础分析' },
  { id: 'explain', label: '总体解读' },
  { id: 'interpret', label: '综合研判' },
  { id: 'write', label: '报告编排' },
  { id: 'review', label: '润色定稿' },
  { id: 'persist', label: '写入结果' }
]

let initialized = false
let rangeRequestId = 0
let historyRequestId = 0
let progressRequestId = 0
let progressPollTimer = null
let taskPollTimer = null
let taskReconnectTimer = null
let taskLifecycleActor = null
let taskStreamController = null
let taskRuntimeScope = null
let suppressTopicWatcher = false

function ensureTaskRuntime() {
  if (!taskState) {
    taskState = useReportRunStore()
  }
  if (!taskLifecycleActor) {
    taskLifecycleActor = createReportRunLifecycleActor()
    taskLifecycleActor.subscribe((snapshot) => {
      taskState.setLifecycleState(String(snapshot.value || 'idle'))
      taskState.setConnectionMode(snapshot.context?.connectionMode || 'idle')
    })
  }
  if (!taskStreamController) {
    taskRuntimeScope = effectScope(true)
    taskStreamController = taskRuntimeScope.run(() => createTaskStreamController())
  }
  syncRunLifecycle()
}

function syncRunLifecycle(connectionOverride = taskState?.connectionMode || 'idle') {
  if (!taskLifecycleActor || !taskState) return
  taskLifecycleActor.send({
    type: 'SNAPSHOT',
    ...buildLifecycleSnapshotInput(taskState, connectionOverride)
  })
}

function sendLifecycleEvent(type, connectionMode = taskState?.connectionMode || 'idle') {
  if (!taskLifecycleActor || !taskState) return
  taskLifecycleActor.send({ type })
  syncRunLifecycle(connectionMode)
}

function createTaskStreamController() {
  const streamUrl = ref(undefined)
  const streamEvents = [
    'task.created',
    'phase.started',
    'phase.progress',
    'agent.started',
    'agent.memo',
    'tool.called',
    'tool.result',
    'artifact.ready',
    'task.completed',
    'task.failed',
    'task.cancelled',
    'todo.updated',
    'subagent.started',
    'subagent.completed',
    'approval.required',
    'approval.resolved',
    'artifact.updated',
    'trust.updated',
    'done',
    'heartbeat'
  ]
  const source = useEventSource(streamUrl, streamEvents, {
    immediate: false,
    autoConnect: false,
    serializer: {
      read(raw) {
        try {
          return JSON.parse(raw)
        } catch {
          return raw
        }
      }
    }
  })

  watch(source.status, (status) => {
    if (!taskState) return
    if (status === 'OPEN') {
      clearTaskReconnectTimer()
      stopTaskPolling()
      sendLifecycleEvent('STREAM_OPENED', 'streaming')
      return
    }
    if (status === 'CONNECTING') {
      taskState.setConnectionMode('idle')
    }
  })

  watch([source.event, source.data], async ([eventName, payload]) => {
    if (!taskState || !eventName) return
    if (eventName === 'heartbeat') return
    if (eventName === 'done') {
      closeTaskStreamOnly()
      await loadReportTask(taskState.id, { silent: true })
      return
    }
    if (payload && typeof payload === 'object') {
      taskState.mergeEvents([payload])
    }
    if (taskState.id) {
      await loadReportTask(taskState.id, { silent: true })
    }
  })

  watch(source.error, () => {
    if (!taskState || !taskState.id) return
    closeTaskStreamOnly()
    sendLifecycleEvent('STREAM_RECONNECTING', 'reconnecting')
    if (typeof window !== 'undefined' && !['completed', 'failed', 'cancelled'].includes(taskState.status)) {
      taskReconnectTimer = window.setTimeout(() => {
        const endpoint = buildTaskStreamEndpoint(taskState.id)
        if (!endpoint) {
          taskState.setConnectionMode('polling_fallback')
          sendLifecycleEvent('STREAM_POLLING', 'polling_fallback')
          scheduleTaskPolling()
          return
        }
        streamUrl.value = endpoint
        source.open()
      }, 1500)
    }
  })

  return {
    open(url) {
      clearTaskReconnectTimer()
      stopTaskPolling()
      streamUrl.value = url
      source.open()
    },
    close() {
      closeTaskStreamOnly()
    }
  }

  function closeTaskStreamOnly() {
    source.close()
    sendLifecycleEvent('STREAM_CLOSED', taskState?.connectionMode || 'idle')
  }
}

export const useReportGeneration = () => {
  ensureTaskRuntime()
  if (!initialized) {
    initialized = true
    initializeStore()
  }
  return {
    topicsState,
    topicOptions,
    reportForm,
    availableRange,
    reportState,
    fullReportState,
    analysisState,
    progressState,
    historyState,
    taskState,
    reportHistory,
    selectedHistoryId,
    reportData,
    fullReportData,
    analysisData,
    analysisSections,
    analysisAiSummary,
    progressLogs,
    taskEvents,
    activeTask,
    taskStageList,
    changeTopic,
    loadTopics,
    loadAvailableRange,
    loadProgress,
    loadHistory,
    loadReport,
    loadFullReport,
    regenerateReport,
    createReportTask,
    loadReportTask,
    openReportTaskStream,
    closeReportTaskStream,
    cancelReportTask,
    retryReportTask,
    resolveReportApproval,
    resumeLastReportTask,
    applyHistorySelection
  }
}

function initializeStore() {
  loadTopics()
  watch(topicOptions, ensureTopicSelection, { immediate: true })
  watch(
    () => reportForm.topic,
    async (topic, previous) => {
      if (suppressTopicWatcher) return
      const trimmed = String(topic || '').trim()
      if (!trimmed) {
        resetRangeState()
        resetFullReportState()
        resetAnalysisState()
        resetProgressState()
        resetTaskState()
        reportHistory.value = []
        selectedHistoryId.value = ''
        reportData.value = null
        return
      }
      if (trimmed === String(previous || '').trim()) return
      reportData.value = null
      fullReportData.value = null
      analysisData.value = null
      reportForm.start = ''
      reportForm.end = ''
      selectedHistoryId.value = ''
      await refreshTopicContext(trimmed)
    }
  )
}

function ensureTopicSelection() {
  if (!topicOptions.value.length) return false
  const current = String(reportForm.topic || '').trim()
  if (current && topicOptions.value.includes(current)) return false
  reportForm.topic = topicOptions.value[0]
  return true
}

function changeTopic(value) {
  reportForm.topic = String(value || '').trim()
}

function currentTimeString() {
  return new Date().toLocaleString('zh-CN', { hour12: false })
}

function normalizeRange(range) {
  const topic = String(range?.topic || reportForm.topic || '').trim()
  const start = String(range?.start || reportForm.start || '').trim()
  const end = String(range?.end || reportForm.end || '').trim() || start
  const mode = String(range?.mode || reportForm.mode || 'fast').trim() || 'fast'
  return { topic, start, end, mode }
}

function hasCompleteRange(range) {
  const normalized = normalizeRange(range)
  return Boolean(normalized.topic && normalized.start && normalized.end)
}

function resetRangeState() {
  rangeRequestId += 1
  availableRange.loading = false
  availableRange.error = ''
  availableRange.notice = ''
  availableRange.hasAnalyzeHistory = false
  availableRange.topic = ''
  availableRange.start = ''
  availableRange.end = ''
}

function resetAnalysisState() {
  analysisState.loading = false
  analysisState.error = ''
  analysisState.lastLoaded = ''
  analysisState.topic = ''
  analysisState.start = ''
  analysisState.end = ''
  analysisData.value = null
}

function resetFullReportState() {
  fullReportState.loading = false
  fullReportState.regenerating = false
  fullReportState.error = ''
  fullReportState.lastLoaded = ''
  fullReportData.value = null
}

function resetProgressState() {
  progressRequestId += 1
  progressState.loading = false
  progressState.polling = false
  progressState.error = ''
  progressState.topic = ''
  progressState.start = ''
  progressState.end = ''
  progressState.stage = ''
  progressState.status = 'pending'
  progressState.message = ''
  progressState.updatedAt = ''
  progressLogs.value = []
  if (progressPollTimer && typeof window !== 'undefined') {
    window.clearTimeout(progressPollTimer)
  }
  progressPollTimer = null
}

function resetTaskState() {
  closeReportTaskStream()
  stopTaskPolling()
  taskState.reset()
  syncRunLifecycle('idle')
}

function applyRangeToForm() {
  if (!availableRange.start) return
  reportForm.start = availableRange.start
  reportForm.end = availableRange.end || availableRange.start
}

async function loadAvailableRange(topicOverride = '', { force = false } = {}) {
  const topic = String(topicOverride || reportForm.topic || '').trim()
  if (!topic) {
    resetRangeState()
    return
  }
  if (!force && topic === availableRange.topic && availableRange.start && !availableRange.loading && !availableRange.error) {
    return
  }
  const requestId = ++rangeRequestId
  availableRange.loading = true
  availableRange.error = ''
  availableRange.notice = ''
  availableRange.hasAnalyzeHistory = false
  availableRange.topic = topic
  availableRange.start = ''
  availableRange.end = ''
  try {
    const params = new URLSearchParams({ topic })
    const response = await callApi(`/api/report/availability?${params.toString()}`, { method: 'GET' })
    if (requestId !== rangeRequestId) return
    const data = response?.data || {}
    const range = data?.range || {}
    availableRange.start = String(range.start || '').trim()
    availableRange.end = String(range.end || '').trim() || availableRange.start
    availableRange.notice = String(data?.message || '').trim()
    availableRange.hasAnalyzeHistory = Boolean(data?.has_analyze_history)
  } catch (error) {
    if (requestId !== rangeRequestId) return
    availableRange.error = error instanceof Error ? error.message : String(error)
  } finally {
    if (requestId === rangeRequestId) {
      availableRange.loading = false
    }
  }
}

async function loadTopics() {
  const previousTopic = String(reportForm.topic || '').trim()
  topicsState.loading = true
  topicsState.error = ''
  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: false })
    })
    const databases = response?.data?.databases || []
    topicsState.options = databases.map((db) => String(db?.name || '').trim()).filter((name, index, arr) => name && arr.indexOf(name) === index)
    const topicChanged = ensureTopicSelection()
    const currentTopic = String(reportForm.topic || '').trim()
    if (!topicChanged && currentTopic && currentTopic === previousTopic) {
      await refreshTopicContext(currentTopic)
    }
  } catch (error) {
    topicsState.error = error instanceof Error ? error.message : '加载专题失败'
    topicsState.options = []
    reportForm.topic = ''
    resetRangeState()
    resetFullReportState()
    resetAnalysisState()
    resetProgressState()
    resetTaskState()
  } finally {
    topicsState.loading = false
  }
}

const splitFolderRange = sharedSplitFolderRange
const normaliseHistoryRecord = (record, defaults = {}) => normaliseRecord(record, defaults)

async function loadHistory(topicOverride = '') {
  const topic = String(topicOverride || reportForm.topic || '').trim()
  if (!topic) {
    historyState.loading = false
    historyState.error = ''
    historyState.topic = ''
    reportHistory.value = []
    selectedHistoryId.value = ''
    return
  }
  const requestId = ++historyRequestId
  historyState.loading = true
  historyState.error = ''
  historyState.topic = topic
  try {
    const params = new URLSearchParams({ topic })
    const response = await callApi(`/api/report/history?${params.toString()}`, { method: 'GET' })
    if (requestId !== historyRequestId) return
    const records = response?.records || []
    const defaults = {
      topic: String(response?.topic || topic).trim(),
      topic_identifier: String(response?.topic_identifier || topic).trim()
    }
    const normalized = records.map((record) => normaliseHistoryRecord(record, defaults)).filter(Boolean).slice(0, MAX_HISTORY)
    reportHistory.value = normalized
    if (!normalized.length) {
      selectedHistoryId.value = ''
      historyState.error = '暂无报告记录，请先生成报告。'
      return
    }
    const previousSelectedId = selectedHistoryId.value
    const exists = normalized.some((record) => record.id === selectedHistoryId.value)
    if (!exists) selectedHistoryId.value = normalized[0].id
    const shouldSyncForm = topic === String(reportForm.topic || '').trim() && (!String(reportForm.start || '').trim() || previousSelectedId !== selectedHistoryId.value)
    if (shouldSyncForm) syncFormWithSelectedHistory()
  } catch (error) {
    if (requestId !== historyRequestId) return
    historyState.error = error instanceof Error ? error.message : String(error)
    reportHistory.value = []
    selectedHistoryId.value = ''
  } finally {
    if (requestId === historyRequestId) historyState.loading = false
  }
}

function getSelectedHistoryRecord() {
  if (!reportHistory.value.length) return null
  return reportHistory.value.find((item) => item.id === selectedHistoryId.value) || reportHistory.value[0] || null
}

function syncFormWithSelectedHistory() {
  const selected = getSelectedHistoryRecord()
  if (!selected) return false
  reportForm.start = selected.start
  reportForm.end = selected.end
  return true
}

async function hydrateRangeFromCurrentTopic() {
  const topic = String(reportForm.topic || '').trim()
  if (!topic) return normalizeRange(reportForm)
  if (!reportHistory.value.length || historyState.topic !== topic) {
    await loadHistory(topic)
  }
  let hydrated = syncFormWithSelectedHistory()
  if (!hydrated && (availableRange.topic !== topic || !availableRange.start)) {
    await loadAvailableRange(topic)
  }
  if (!hydrated) applyRangeToForm()
  return normalizeRange(reportForm)
}

function normaliseProgressLogs(steps) {
  return (Array.isArray(steps) ? steps : []).map((step, index) => ({
    id: String(step?.id || `report-progress-${index}`),
    label: String(step?.label || `步骤 ${index + 1}`),
    message: String(step?.message || '').trim(),
    status: String(step?.status || 'pending').trim() || 'pending',
    progress: typeof step?.progress === 'number' ? step.progress : Number(step?.progress || 0),
    time: String(step?.time || '').trim()
  }))
}

function applyProgressPayload(data, fallbackRange = {}) {
  const range = normalizeRange(fallbackRange)
  const summary = data?.summary || {}
  const state = data?.state || {}
  progressLogs.value = normaliseProgressLogs(data?.steps)
  progressState.topic = String(data?.topic || range.topic).trim()
  progressState.start = String(data?.range?.start || range.start).trim()
  progressState.end = String(data?.range?.end || range.end).trim() || progressState.start
  progressState.stage = String(state?.stage || '').trim()
  progressState.status = String(summary?.status || state?.status || 'pending').trim() || 'pending'
  progressState.message = String(summary?.message || state?.message || '').trim()
  progressState.updatedAt = String(state?.updated_at || '').trim()
}

async function loadProgress(rangeOverride = null, { silent = false } = {}) {
  const resolvedRange = normalizeRange(rangeOverride || reportForm)
  if (!hasCompleteRange(resolvedRange)) {
    if (!silent) resetProgressState()
    return null
  }
  const requestId = ++progressRequestId
  if (!silent) progressState.loading = true
  progressState.error = ''
  try {
    const params = new URLSearchParams({ topic: resolvedRange.topic, start: resolvedRange.start, end: resolvedRange.end })
    const response = await callApi(`/api/report/progress?${params.toString()}`, { method: 'GET' })
    if (requestId !== progressRequestId) return null
    const data = response?.data || {}
    applyProgressPayload(data, resolvedRange)
    return data
  } catch (error) {
    if (requestId !== progressRequestId) return null
    progressState.error = error instanceof Error ? error.message : String(error)
    if (!silent) progressLogs.value = []
    return null
  } finally {
    if (requestId === progressRequestId && !silent) progressState.loading = false
  }
}

async function loadAnalyzeResults(rangeOverride = null, { silent = false } = {}) {
  const resolvedRange = normalizeRange(rangeOverride || reportForm)
  if (!hasCompleteRange(resolvedRange)) {
    if (!silent) resetAnalysisState()
    return null
  }
  if (!silent) analysisState.loading = true
  analysisState.error = ''
  try {
    const params = new URLSearchParams({ topic: resolvedRange.topic, start: resolvedRange.start, end: resolvedRange.end })
    const response = await callApi(`/api/analyze/results?${params.toString()}`, { method: 'GET' })
    analysisData.value = response || null
    analysisState.topic = resolvedRange.topic
    analysisState.start = resolvedRange.start
    analysisState.end = resolvedRange.end
    analysisState.lastLoaded = currentTimeString()
    return response || null
  } catch (error) {
    analysisData.value = null
    analysisState.topic = resolvedRange.topic
    analysisState.start = resolvedRange.start
    analysisState.end = resolvedRange.end
    analysisState.error = error instanceof Error ? error.message : String(error)
    return null
  } finally {
    if (!silent) analysisState.loading = false
  }
}

async function loadReport(rangeOverride = null) {
  const resolvedRange = rangeOverride ? normalizeRange(rangeOverride) : await hydrateRangeFromCurrentTopic()
  if (!hasCompleteRange(resolvedRange)) {
    reportState.error = availableRange.notice || 'Topic / Start / End 为必填'
    return null
  }
  reportState.loading = true
  reportState.error = ''
  analysisState.error = ''
  analysisState.loading = true
  try {
    const params = new URLSearchParams({ topic: resolvedRange.topic, start: resolvedRange.start, end: resolvedRange.end })
    const [reportResponse] = await Promise.all([
      callApi(`/api/report?${params.toString()}`, { method: 'GET' }),
      loadAnalyzeResults(resolvedRange, { silent: true })
    ])
    const payload = reportResponse?.data || null
    if (!payload || typeof payload !== 'object') throw new Error('报告接口返回为空')
    reportData.value = payload
    reportState.lastLoaded = currentTimeString()
    reportForm.topic = resolvedRange.topic
    reportForm.start = resolvedRange.start
    reportForm.end = resolvedRange.end
    await loadHistory(resolvedRange.topic)
    const matched = reportHistory.value.find((item) => item.start === resolvedRange.start && item.end === resolvedRange.end)
    if (matched) selectedHistoryId.value = matched.id
    await loadProgress(resolvedRange, { silent: true })
    return payload
  } catch (error) {
    reportData.value = null
    analysisData.value = null
    const message = error instanceof Error ? error.message : String(error)
    reportState.error = message.includes('未找到分析结果目录')
      ? '当前专题暂无基础分析结果，请前往“运行报告”，系统会先自动补跑基础分析再生成报告。'
      : message
    await loadProgress(resolvedRange, { silent: true })
    return null
  } finally {
    reportState.loading = false
    analysisState.loading = false
  }
}

async function loadFullReport(rangeOverride = null, { regenerate = false } = {}) {
  const resolvedRange = rangeOverride ? normalizeRange(rangeOverride) : await hydrateRangeFromCurrentTopic()
  if (!hasCompleteRange(resolvedRange)) {
    fullReportState.error = availableRange.notice || 'Topic / Start / End 为必填'
    return null
  }
  fullReportState.loading = !regenerate
  fullReportState.regenerating = regenerate
  fullReportState.error = ''
  try {
    const params = new URLSearchParams({
      topic: resolvedRange.topic,
      start: resolvedRange.start,
      end: resolvedRange.end
    })
    if (regenerate) params.set('regenerate', '1')
    const response = await callApi(`/api/report/full?${params.toString()}`, { method: 'GET' })
    const payload = response?.data || null
    if (!payload || typeof payload !== 'object') throw new Error('AI 完整报告接口返回为空')
    fullReportData.value = payload
    fullReportState.lastLoaded = currentTimeString()
    reportForm.topic = resolvedRange.topic
    reportForm.start = resolvedRange.start
    reportForm.end = resolvedRange.end
    await loadHistory(resolvedRange.topic)
    const matched = reportHistory.value.find((item) => item.start === resolvedRange.start && item.end === resolvedRange.end)
    if (matched) selectedHistoryId.value = matched.id
    await loadProgress(resolvedRange, { silent: true })
    return payload
  } catch (error) {
    fullReportData.value = null
    fullReportState.error = error instanceof Error ? error.message : String(error)
    await loadProgress(resolvedRange, { silent: true })
    return null
  } finally {
    fullReportState.loading = false
    fullReportState.regenerating = false
  }
}

async function regenerateReport() {
  return createReportTask()
}

function buildTaskStorageKey(range = reportForm) {
  const normalized = normalizeRange(range)
  return `${TASK_STORAGE_PREFIX}:${normalized.topic}:${normalized.start}:${normalized.end}:${normalized.mode}`
}

function persistTaskKey(task) {
  if (typeof window === 'undefined' || !task?.id) return
  try {
    window.localStorage.setItem(buildTaskStorageKey(task), String(task.id))
    window.localStorage.setItem(`${TASK_STORAGE_PREFIX}:last`, String(task.id))
  } catch {
    // ignore storage errors
  }
}

function readPersistedTaskId(range = reportForm) {
  if (typeof window === 'undefined') return ''
  try {
    return String(window.localStorage.getItem(buildTaskStorageKey(range)) || '').trim()
  } catch {
    return ''
  }
}

function clearTaskReconnectTimer() {
  if (taskReconnectTimer && typeof window !== 'undefined') {
    window.clearTimeout(taskReconnectTimer)
  }
  taskReconnectTimer = null
}

function stopTaskPolling() {
  if (taskPollTimer && typeof window !== 'undefined') {
    window.clearTimeout(taskPollTimer)
  }
  taskPollTimer = null
}

function mergeTaskEvents(incoming = []) {
  taskState.mergeEvents(incoming)
}

function applyTaskSnapshot(task, { reused = false } = {}) {
  if (!task || typeof task !== 'object') return
  taskState.applySnapshot(task, { reused })
  persistTaskKey(taskState)
  syncRunLifecycle(taskState.connectionMode || 'idle')
  applyProgressPayload({
    topic: taskState.topic,
    range: { start: taskState.start, end: taskState.end },
    state: { stage: taskState.phase, status: taskState.status, message: taskState.message, updated_at: taskState.updatedAt },
    summary: {
      status: taskState.status === 'completed'
        ? 'ok'
        : (['queued', 'running', 'waiting_approval'].includes(taskState.status) ? 'running' : 'error'),
      message: taskState.message
    },
    steps: buildProgressStepsFromTask()
  }, taskState)
}

function buildProgressStepsFromTask() {
  const currentIndex = taskStageList.findIndex((item) => item.id === taskState.phase)
  return taskStageList.map((item, index) => ({
    id: item.id,
    label: item.label,
    status: index < currentIndex ? 'ok' : (item.id === taskState.phase ? (taskState.status === 'completed' ? 'ok' : (taskState.status === 'failed' ? 'error' : 'running')) : 'pending'),
    message: item.id === taskState.phase ? taskState.message : '',
    progress: item.id === taskState.phase ? taskState.percentage : (index < currentIndex ? 100 : 0),
    time: taskState.updatedAt
  }))
}

function buildTaskStreamEndpoint(taskId = taskState?.id) {
  const resolvedTaskId = String(taskId || '').trim()
  if (!resolvedTaskId) return ''
  const since = taskState?.lastEventId ? `?since_id=${encodeURIComponent(String(taskState.lastEventId))}` : ''
  return `/api/report/tasks/${encodeURIComponent(resolvedTaskId)}/stream${since}`
}

function closeReportTaskStream() {
  clearTaskReconnectTimer()
  if (taskStreamController) {
    taskStreamController.close()
  }
  taskState.setConnectionMode('idle')
  syncRunLifecycle('idle')
}

function scheduleTaskPolling() {
  stopTaskPolling()
  if (!taskState.id || ['completed', 'failed', 'cancelled'].includes(taskState.status)) return
  if (typeof window === 'undefined') return
  taskPollTimer = window.setTimeout(async () => {
    await loadReportTask(taskState.id, { silent: true })
    scheduleTaskPolling()
  }, TASK_POLL_INTERVAL)
}

async function openReportTaskStream(taskId = taskState.id, { force = false } = {}) {
  const resolvedTaskId = String(taskId || '').trim()
  if (!resolvedTaskId) return
  if (typeof window === 'undefined' || typeof window.EventSource === 'undefined') {
    taskState.setConnectionMode('polling_fallback')
    sendLifecycleEvent('STREAM_POLLING', 'polling_fallback')
    scheduleTaskPolling()
    return
  }
  if (taskState.connectionMode === 'streaming' && !force) return
  closeReportTaskStream()
  stopTaskPolling()
  const apiBase = await ensureApiBase()
  const endpoint = `${apiBase}${buildTaskStreamEndpoint(resolvedTaskId)}`
  taskState.setConnectionMode('idle')
  taskStreamController.open(endpoint)
}

async function loadReportTask(taskId = taskState.id, { silent = false, reused = false } = {}) {
  const resolvedTaskId = String(taskId || '').trim()
  if (!resolvedTaskId) return null
  if (!silent) taskState.setLoading(true)
  taskState.setError('')
  try {
    const response = await callApi(`/api/report/tasks/${encodeURIComponent(resolvedTaskId)}`, { method: 'GET' })
    const task = response?.task || null
    if (task && typeof task === 'object') {
      applyTaskSnapshot(task, { reused })
      if (taskState.status === 'completed' && hasCompleteRange(taskState)) {
        await loadHistory(taskState.topic)
      }
    }
    return task
  } catch (error) {
    taskState.setError(error instanceof Error ? error.message : String(error))
    return null
  } finally {
    if (!silent) taskState.setLoading(false)
  }
}

async function createReportTask(rangeOverride = null) {
  const resolvedRange = hasCompleteRange(rangeOverride || reportForm)
    ? normalizeRange(rangeOverride || reportForm)
    : await hydrateRangeFromCurrentTopic()
  if (!hasCompleteRange(resolvedRange)) {
    reportState.error = availableRange.notice || 'Topic / Start / End 为必填'
    return null
  }
  taskState.setCreating(true)
  taskState.setError('')
  reportState.error = ''
  try {
    const response = await callApi('/api/report/tasks', {
      method: 'POST',
      body: JSON.stringify(resolvedRange)
    })
    const task = response?.task || null
    if (!task || typeof task !== 'object') throw new Error('任务创建接口返回为空')
    applyTaskSnapshot(task, { reused: Boolean(response?.reused) })
    reportForm.topic = resolvedRange.topic
    reportForm.start = resolvedRange.start
    reportForm.end = resolvedRange.end
    reportForm.mode = resolvedRange.mode
    await openReportTaskStream(task.id, { force: true })
    return task
  } catch (error) {
    taskState.setError(error instanceof Error ? error.message : String(error))
    reportState.error = taskState.error
    return null
  } finally {
    taskState.setCreating(false)
  }
}

async function cancelReportTask(taskId = taskState.id) {
  const resolvedTaskId = String(taskId || '').trim()
  if (!resolvedTaskId) return null
  try {
    const response = await callApi(`/api/report/tasks/${encodeURIComponent(resolvedTaskId)}/cancel`, { method: 'POST' })
    const task = response?.task || null
    if (task) applyTaskSnapshot(task)
    return task
  } catch (error) {
    taskState.setError(error instanceof Error ? error.message : String(error))
    return null
  }
}

async function retryReportTask(taskId = taskState.id) {
  const resolvedTaskId = String(taskId || '').trim()
  if (!resolvedTaskId) return null
  try {
    const response = await callApi(`/api/report/tasks/${encodeURIComponent(resolvedTaskId)}/retry`, { method: 'POST' })
    const task = response?.task || null
    if (task) {
      applyTaskSnapshot(task)
      await openReportTaskStream(task.id, { force: true })
    }
    return task
  } catch (error) {
    taskState.setError(error instanceof Error ? error.message : String(error))
    return null
  }
}

async function resolveReportApproval(taskId = taskState.id, approvalId, payload = {}) {
  const resolvedTaskId = String(taskId || '').trim()
  const resolvedApprovalId = String(approvalId || '').trim()
  if (!resolvedTaskId || !resolvedApprovalId) return null
  try {
    const response = await callApi(
      `/api/report/tasks/${encodeURIComponent(resolvedTaskId)}/approvals/${encodeURIComponent(resolvedApprovalId)}`,
      {
        method: 'POST',
        body: JSON.stringify(payload)
      }
    )
    const task = response?.task || null
    if (task) applyTaskSnapshot(task)
    return task
  } catch (error) {
    taskState.setError(error instanceof Error ? error.message : String(error))
    return null
  }
}

async function resumeLastReportTask(rangeOverride = null) {
  const resolvedRange = normalizeRange(rangeOverride || reportForm)
  const taskId = readPersistedTaskId(resolvedRange)
  if (!taskId) return null
  const task = await loadReportTask(taskId, { silent: true })
  if (!task || ['completed', 'failed', 'cancelled'].includes(String(task.status || ''))) return task
  await openReportTaskStream(taskId, { force: true })
  return task
}

async function applyHistorySelection(historyId, { shouldLoad = true } = {}) {
  const record = reportHistory.value.find((item) => item.id === historyId)
  if (!record) return
  selectedHistoryId.value = record.id
  suppressTopicWatcher = true
  reportForm.start = record.start
  reportForm.end = record.end
  suppressTopicWatcher = false
  if (shouldLoad) {
    await loadReport({ topic: reportForm.topic, start: record.start, end: record.end, mode: reportForm.mode })
  }
}

async function refreshTopicContext(topic) {
  await loadAvailableRange(topic)
  await loadHistory(topic)
  const synced = syncFormWithSelectedHistory()
  if (!synced) applyRangeToForm()
  const nextRange = normalizeRange(reportForm)
  if (hasCompleteRange(nextRange)) {
    await loadProgress(nextRange, { silent: true })
    await resumeLastReportTask(nextRange)
  } else {
    resetAnalysisState()
    resetProgressState()
    resetTaskState()
  }
}
