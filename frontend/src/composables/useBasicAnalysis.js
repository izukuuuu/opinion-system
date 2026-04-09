import { computed, reactive, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'
import {
  normaliseArchiveRecords,
  normaliseRecord,
  splitFolderRange,
  normalizeArchiveResponse
} from './useArchiveHistory'
import { analysisFunctions, buildAnalysisSections } from '../utils/analysisSections'

const MAX_HISTORY = 12
const ANALYZE_TASK_POLL_INTERVAL = 2000
const ANALYZE_TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])
const ANALYZE_ACTIVE_STATUSES = new Set(['queued', 'running'])
const ANALYZE_FUNCTION_ORDER = new Map(analysisFunctions.map((item, index) => [item.id, index]))

const { callApi } = useApiBase()

const topicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const topicOptions = computed(() => topicsState.options)

const fetchForm = reactive({
  topic: '',
  start: '',
  end: ''
})

const analyzeForm = reactive({
  topic: '',
  start: '',
  end: ''
})

const availableRange = reactive({
  loading: false,
  error: '',
  start: '',
  end: ''
})
let availabilityRequestId = 0

const fetchState = reactive({ loading: false })
const analyzeState = reactive({ running: false })
const loadState = reactive({ loading: false })
const analyzeTaskState = reactive({
  loading: false,
  error: '',
  notice: ''
})
const analyzeWorkerState = reactive({
  pid: 0,
  status: 'stopped',
  running: false,
  active_count: 0,
  current_task_id: '',
  last_heartbeat: '',
  started_at: '',
  updated_at: ''
})

const fetchLogs = ref([])
const analyzeLogs = ref([])
const viewLogs = ref([])
const analyzeTasks = ref([])

const selectedFunctions = ref(analysisFunctions.map((f) => f.id))

const analysisData = ref(null)
const lastLoaded = ref('')

const historyState = reactive({
  loading: false,
  error: '',
  topic: ''
})

const analysisHistory = ref([])
const selectedHistoryId = ref('')

const viewSelection = reactive({
  topic: '',
  start: '',
  end: ''
})

const viewManualForm = reactive({
  topic: '',
  start: '',
  end: ''
})

const analysisSummary = computed(() => {
  if (!analysisData.value?.topic) return null
  return {
    topic: analysisData.value.topic,
    range: analysisData.value.range,
    functionCount: analysisData.value.functions?.length || 0
  }
})

const analysisAiSummary = computed(() => analysisData.value?.ai_summary || null)

const analysisSections = computed(() => buildAnalysisSections(analysisData.value?.functions))

let initialized = false
let analyzeTaskPollTimer = null
let analyzeSubmissionCount = 0

export const useBasicAnalysis = () => {
  if (!initialized) {
    initialized = true
    initializeStore()
  }

  return {
    analysisFunctions,
    topicsState,
    topicOptions,
    fetchForm,
    analyzeForm,
    availableRange,
    fetchState,
    analyzeState,
    analyzeTaskState,
    analyzeWorkerState,
    loadState,
    fetchLogs,
    analyzeLogs,
    viewLogs,
    analyzeTasks,
    selectedFunctions,
    analysisData,
    lastLoaded,
    historyState,
    analysisHistory,
    selectedHistoryId,
    viewSelection,
    viewManualForm,
  analysisSummary,
  analysisAiSummary,
  analysisSections,
  changeTopic,
  loadTopics,
  resetFetchForm,
  runFetch,
  runSelectedFunctions,
  runSingleFunction,
  deleteAnalysisSection,
  rebuildAiSummary,
    loadAnalyzeTasks,
    selectAll,
    clearSelection,
    loadHistory,
    loadResults,
    loadResultsFromManual,
    applyHistorySelection
  }
}

function initializeStore() {
  loadTopics()

  watch(topicOptions, ensureTopicSelection, { immediate: true })

  watch(
    () => fetchForm.topic,
    (value) => {
      const topicValue = (value || '').trim()
      if (topicValue) {
        analyzeForm.topic = topicValue
        loadAvailableRange()
      } else {
        analyzeForm.topic = ''
        loadAvailableRange()
      }
    },
    { immediate: true }
  )

  watch(
    () => analyzeForm.topic,
    (value) => {
      const topicValue = (value || '').trim()
      if (topicValue && topicValue !== fetchForm.topic) {
        fetchForm.topic = topicValue
      }
    }
  )

  watch(
    () => fetchForm.start,
    (value) => {
      analyzeForm.start = value
      if (!fetchForm.end) {
        analyzeForm.end = value
      }
    }
  )

  watch(
    () => fetchForm.end,
    (value) => {
      analyzeForm.end = value || analyzeForm.start || ''
    }
  )

  watch(
    analysisHistory,
    (value) => {
      if (!value.length) {
        selectedHistoryId.value = ''
        return
      }
      const exists = value.some((entry) => entry.id === selectedHistoryId.value)
      if (!exists) {
        selectedHistoryId.value = value[0].id
      }
    },
    { deep: true }
  )

  watch(
    () => viewSelection.topic,
    (topic) => {
      const trimmed = (topic || '').trim()
      if (trimmed) {
        loadHistory(trimmed)
        viewManualForm.topic = trimmed
      } else {
        analysisHistory.value = []
        historyState.topic = ''
      }
    },
    { immediate: true }
  )

  watch(
    () => [analyzeForm.topic, analyzeForm.start, analyzeForm.end],
    ([topic, start, end]) => {
      const normalizedTopic = String(topic || '').trim()
      const normalizedStart = String(start || '').trim()
      const normalizedEnd = String(end || '').trim() || normalizedStart
      if (!normalizedTopic || !normalizedStart || !normalizedEnd) {
        analyzeTasks.value = []
        resetAnalyzeWorkerState()
        syncAnalyzeRunningState()
        stopAnalyzeTaskPolling()
        return
      }
      loadAnalyzeTasks({ topic: normalizedTopic, start: normalizedStart, end: normalizedEnd }, { silent: true })
    },
    { immediate: true }
  )

  watch(
    analyzeTasks,
    () => {
      syncAnalyzeRunningState()
    },
    { deep: true }
  )
}

const changeTopic = (value) => {
  const next = (value || '').trim()
  fetchForm.topic = next
  analyzeForm.topic = next
  loadAvailableRange()
}

const ensureTopicSelection = () => {
  if (!topicOptions.value.length) return
  if (!fetchForm.topic || !topicOptions.value.includes(fetchForm.topic)) {
    fetchForm.topic = topicOptions.value[0]
  }
  if (!analyzeForm.topic) {
    analyzeForm.topic = fetchForm.topic
  }
  if (!viewSelection.topic) {
    viewSelection.topic = fetchForm.topic
  }
  if (!viewManualForm.topic) {
    viewManualForm.topic = fetchForm.topic
  }
}

const resetAvailableRange = () => {
  availableRange.start = ''
  availableRange.end = ''
}

const clearAvailableRange = () => {
  availabilityRequestId += 1
  resetAvailableRange()
  availableRange.error = ''
  availableRange.loading = false
}

const applyAvailableRangeToForms = () => {
  const startValue = availableRange.start || ''
  const endValue = availableRange.end || startValue || ''
  fetchForm.start = startValue
  fetchForm.end = endValue
  analyzeForm.start = startValue
  analyzeForm.end = endValue
}

const loadAvailableRange = async () => {
  const topic = (fetchForm.topic || '').trim()
  if (!topic) {
    availableRange.loading = false
    clearAvailableRange()
    return
  }
  const requestId = ++availabilityRequestId
  availableRange.loading = true
  availableRange.error = ''
  resetAvailableRange()
  fetchForm.start = ''
  fetchForm.end = ''
  analyzeForm.start = ''
  analyzeForm.end = ''
  try {
    const params = new URLSearchParams({ topic })
    const response = await callApi(`/api/fetch/availability?${params.toString()}`, { method: 'GET' })
    if (requestId !== availabilityRequestId) return
    const range = response?.data?.range ?? {}
    availableRange.start = range.start || ''
    availableRange.end = range.end || ''
    applyAvailableRangeToForms()
  } catch (error) {
    if (requestId !== availabilityRequestId) return
    resetAvailableRange()
    availableRange.error = error instanceof Error ? error.message : String(error)
    fetchForm.start = ''
    fetchForm.end = ''
    analyzeForm.start = ''
    analyzeForm.end = ''
  } finally {
    if (requestId === availabilityRequestId) {
      availableRange.loading = false
    }
  }
}

const loadTopics = async () => {
  topicsState.loading = true
  topicsState.error = ''
  const previousTopic = fetchForm.topic
  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: false })
    })
    const databases = response?.data?.databases ?? []
    topicsState.options = databases
      .map((db) => String(db?.name || '').trim())
      .filter((name, index, arr) => name && arr.indexOf(name) === index)
    ensureTopicSelection()
    const hasInitialSelection = !previousTopic && (fetchForm.topic || '').trim()
    if (hasInitialSelection || fetchForm.topic === previousTopic) {
      await loadAvailableRange()
    }
  } catch (error) {
    topicsState.error = error instanceof Error ? error.message : '加载远程数据源失败'
    topicsState.options = []
    fetchForm.topic = ''
    analyzeForm.topic = ''
    clearAvailableRange()
  } finally {
    topicsState.loading = false
  }
}

const loadHistory = async (topic) => {
  const trimmed = (topic || '').trim()
  if (!trimmed) {
    analysisHistory.value = []
    historyState.topic = ''
    historyState.error = ''
    return
  }
  historyState.loading = true
  historyState.error = ''
  try {
    const apiRecords = await fetchHistoryViaAnalyzeApi(trimmed)
    if (apiRecords.length) {
      analysisHistory.value = apiRecords
      historyState.topic = trimmed
      return
    }
    const archiveRecords = await fetchHistoryViaArchives(trimmed)
    analysisHistory.value = archiveRecords
    historyState.topic = trimmed
    if (!archiveRecords.length) {
      historyState.error = '当前专题暂无分析存档，请先运行 Analyze。'
    }
  } catch (primaryError) {
    try {
      const archiveRecords = await fetchHistoryViaArchives(trimmed)
      analysisHistory.value = archiveRecords
      historyState.topic = trimmed
      if (!archiveRecords.length) {
        historyState.error = '当前专题暂无分析存档，请先运行 Analyze。'
      }
    } catch (fallbackError) {
      historyState.error = fallbackError instanceof Error ? fallbackError.message : String(fallbackError)
      analysisHistory.value = []
      historyState.topic = ''
    }
  } finally {
    historyState.loading = false
  }
}

const resetFetchForm = () => {
  fetchForm.topic = topicOptions.value[0] || ''
  if (availableRange.start || availableRange.end) {
    applyAvailableRangeToForms()
  } else {
    fetchForm.start = ''
    fetchForm.end = ''
  }
}

const currentTimeString = () => new Date().toLocaleTimeString()

const resolveAnalyzeTaskPayload = (response) => response?.data?.task || response?.task || null

const isAnalyzeTaskActive = (status) => !ANALYZE_TERMINAL_STATUSES.has(String(status || '').trim().toLowerCase())

const resetAnalyzeWorkerState = () => {
  analyzeWorkerState.pid = 0
  analyzeWorkerState.status = 'stopped'
  analyzeWorkerState.running = false
  analyzeWorkerState.active_count = 0
  analyzeWorkerState.current_task_id = ''
  analyzeWorkerState.last_heartbeat = ''
  analyzeWorkerState.started_at = ''
  analyzeWorkerState.updated_at = ''
}

const applyAnalyzeWorkerState = (worker) => {
  const payload = worker && typeof worker === 'object' ? worker : {}
  analyzeWorkerState.pid = Number(payload.pid || 0)
  analyzeWorkerState.status = String(payload.status || '').trim() || 'stopped'
  analyzeWorkerState.running = Boolean(payload.running)
  analyzeWorkerState.active_count = Number(payload.active_count || 0)
  analyzeWorkerState.current_task_id = String(payload.current_task_id || '').trim()
  analyzeWorkerState.last_heartbeat = String(payload.last_heartbeat || '').trim()
  analyzeWorkerState.started_at = String(payload.started_at || '').trim()
  analyzeWorkerState.updated_at = String(payload.updated_at || '').trim()
}

const formatDateTime = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

const normalizeAnalyzeTask = (task) => {
  const payload = task && typeof task === 'object' ? task : {}
  const progress = payload.progress && typeof payload.progress === 'object' ? payload.progress : {}
  const functionId = String(payload.only_function || progress.current_function || '').trim()
  const meta = analysisFunctions.find((item) => item.id === functionId)
  const status = String(payload.status || '').trim().toLowerCase() || 'queued'
  const percentage = Math.max(0, Math.min(100, Number(payload.percentage || 0)))
  return {
    id: String(payload.id || '').trim(),
    functionId,
    label: meta?.label || functionId || '基础分析',
    status,
    phase: String(payload.phase || '').trim() || status,
    percentage,
    message: String(payload.message || '').trim(),
    currentTarget: String(progress.current_target || '').trim(),
    updatedAt: formatDateTime(payload.updated_at),
    createdAt: String(payload.created_at || '').trim(),
    sentimentPhase: String(progress.sentiment_phase || '').trim(),
    sentimentTotal: Number(progress.sentiment_total || 0),
    sentimentProcessed: Number(progress.sentiment_processed || 0),
    sentimentClassified: Number(progress.sentiment_classified || 0),
    raw: payload
  }
}

const sortAnalyzeTasks = (tasks) =>
  [...tasks].sort((left, right) => {
    const orderDiff =
      (ANALYZE_FUNCTION_ORDER.get(left.functionId) ?? 999) - (ANALYZE_FUNCTION_ORDER.get(right.functionId) ?? 999)
    if (orderDiff !== 0) return orderDiff
    return String(right.createdAt || '').localeCompare(String(left.createdAt || ''))
  })

const syncAnalyzeRunningState = () => {
  analyzeState.running =
    analyzeSubmissionCount > 0 ||
    analyzeTasks.value.some((task) => ANALYZE_ACTIVE_STATUSES.has(String(task.status || '').trim().toLowerCase()))
}

const stopAnalyzeTaskPolling = () => {
  if (typeof window !== 'undefined' && analyzeTaskPollTimer) {
    window.clearTimeout(analyzeTaskPollTimer)
  }
  analyzeTaskPollTimer = null
}

const applyAnalyzeTaskSnapshot = (payload) => {
  const data = payload && typeof payload === 'object' ? payload : {}
  const tasks = Array.isArray(data.tasks) ? data.tasks.map(normalizeAnalyzeTask) : []
  analyzeTasks.value = sortAnalyzeTasks(tasks)
  applyAnalyzeWorkerState(data.worker)
  syncAnalyzeRunningState()
}

const scheduleAnalyzeTaskPolling = () => {
  if (typeof window === 'undefined' || analyzeTaskPollTimer) return
  if (!analyzeTasks.value.some((task) => ANALYZE_ACTIVE_STATUSES.has(task.status))) return
  analyzeTaskPollTimer = window.setTimeout(async () => {
    analyzeTaskPollTimer = null
    await loadAnalyzeTasks(null, { silent: true })
  }, ANALYZE_TASK_POLL_INTERVAL)
}

const loadAnalyzeTasks = async (rangeOverride = null, { silent = false } = {}) => {
  const range = normalizeRange(rangeOverride || analyzeForm)
  const { topic, start, end } = range
  if (!topic || !start || !end) {
    analyzeTasks.value = []
    resetAnalyzeWorkerState()
    stopAnalyzeTaskPolling()
    syncAnalyzeRunningState()
    return
  }

  if (!silent) {
    analyzeTaskState.loading = true
    analyzeTaskState.error = ''
  }

  try {
    const params = new URLSearchParams({
      topic,
      start,
      end,
      latest: 'true',
      limit: '50'
    })
    const response = await callApi(`/api/analyze/tasks?${params.toString()}`, { method: 'GET' })
    applyAnalyzeTaskSnapshot(response?.data || {})
    const hasActiveTasks = analyzeTasks.value.some((task) => ANALYZE_ACTIVE_STATUSES.has(task.status))
    if (!hasActiveTasks && analyzeTasks.value.some((task) => task.status === 'completed')) {
      await loadHistory(topic)
    }
    stopAnalyzeTaskPolling()
    scheduleAnalyzeTaskPolling()
  } catch (error) {
    analyzeTasks.value = []
    resetAnalyzeWorkerState()
    analyzeTaskState.error = error instanceof Error ? error.message : String(error)
    stopAnalyzeTaskPolling()
  } finally {
    if (!silent) {
      analyzeTaskState.loading = false
    }
    syncAnalyzeRunningState()
  }
}

const appendLog = (collection, payload) => {
  const entry = {
    id: payload.id || `${payload.label || 'log'}-${Date.now()}`,
    time: payload.time || currentTimeString(),
    status: payload.status || 'pending',
    ...payload
  }
  collection.value = [entry, ...collection.value].slice(0, 8)
  return entry.id
}

const updateLogEntry = (collection, id, patch = {}) => {
  if (!id) return
  collection.value = collection.value.map((entry) => {
    if (entry.id !== id) return entry
    return {
      ...entry,
      ...patch,
      time: patch.time || entry.time
    }
  })
}

const normalizeRange = (form) => {
  const topic = (form.topic || '').trim()
  const start = (form.start || '').trim()
  const end = (form.end || '').trim() || start
  return { topic, start, end }
}

const parseDateValue = (value) => {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

const hasValidRange = (form) => {
  const { topic, start, end } = normalizeRange(form)
  return Boolean(topic && start && end)
}

const recordAnalysisRun = ({ topic, start, end }) => {
  const normalized = normalizeRange({ topic, start, end })
  if (!normalized.topic || !normalized.start || !normalized.end) return
  viewSelection.topic = normalized.topic
  viewSelection.start = normalized.start
  viewSelection.end = normalized.end
  viewManualForm.topic = normalized.topic
  viewManualForm.start = normalized.start
  viewManualForm.end = normalized.end
}

const fetchHistoryViaAnalyzeApi = async (topic) => {
  const params = new URLSearchParams({ topic })
  const response = await callApi(`/api/analyze/history?${params.toString()}`, { method: 'GET' })
  const { records, defaults } = normalizeArchiveResponse(response, 'analyze', topic)
  return normaliseArchiveRecords(records, defaults)
}

const fetchHistoryViaArchives = async (topic) => {
  const encodedTopic = encodeURIComponent(topic)
  const response = await callApi(`/api/projects/${encodedTopic}/archives?layers=analyze`, { method: 'GET' })
  const { records, defaults, folderKey } = normalizeArchiveResponse(response, 'analyze', topic)
  return normaliseArchiveRecords(records, defaults, folderKey ? { folderKey } : {})
}

// normaliseHistoryRecords and friends have been moved to useArchiveHistory.js
// These thin wrappers preserve the internal call sites above.
const normaliseHistoryRecords = normaliseArchiveRecords
const normaliseSingleHistoryRecord = normaliseRecord
const deriveRangeFromFolder = (folderValue, startValue, endValue) => {
  let rangeStart = (startValue || '').trim()
  let rangeEnd = (endValue || '').trim()
  const folder = (folderValue || '').trim()
  if (!rangeStart && folder) {
    const result = splitFolderRange(folder)
    rangeStart = result.start
    rangeEnd = result.end
  }
  if (!rangeEnd) rangeEnd = rangeStart
  return { start: rangeStart, end: rangeEnd }
}


const runFetch = async (rangeOverride = null, options = {}) => {
  const range = normalizeRange(rangeOverride || fetchForm)
  const { topic, start, end } = range
  const { logId = null, label = 'Fetch', silent = false } = options

  if (!topic || !start || !end) {
    if (logId) {
      updateLogEntry(fetchLogs, logId, { status: 'error', message: 'Topic / Start / End 为必填', time: currentTimeString() })
    } else {
      appendLog(fetchLogs, { label: '参数校验', message: 'Topic / Start / End 为必填', status: 'error' })
    }
    return false
  }

  const entryId =
    logId ||
    appendLog(fetchLogs, {
      label,
      message: `准备拉取 ${topic} ${start}→${end}`,
      status: 'running'
    })

  if (!silent) {
    fetchState.loading = true
  }

  try {
    updateLogEntry(fetchLogs, entryId, {
      status: 'running',
      message: `正在拉取 ${topic} ${start}→${end}…`,
      time: currentTimeString()
    })

    await callApi('/api/fetch', {
      method: 'POST',
      body: JSON.stringify({
        topic,
        start,
        end
      })
    })

    updateLogEntry(fetchLogs, entryId, {
      status: 'ok',
      message: `已触发 ${topic} ${start}→${end}`,
      time: currentTimeString()
    })
    return true
  } catch (error) {
    updateLogEntry(fetchLogs, entryId, {
      label,
      message: error instanceof Error ? error.message : String(error),
      status: 'error',
      time: currentTimeString()
    })
    return false
  } finally {
    if (!silent) {
      fetchState.loading = false
    }
  }
}

const ensureFetchReadyForRange = async (range) => {
  const target = normalizeRange(range)
  const { topic, start, end } = target
  if (!topic || !start || !end) {
    appendLog(fetchLogs, { label: '数据准备', message: 'Topic / Start / End 为必填', status: 'error' })
    return false
  }

  const logId = appendLog(fetchLogs, {
    label: '数据准备',
    message: `预先拉取 ${topic} ${start}→${end}`,
    status: 'running'
  })

  const availStart = parseDateValue(availableRange.start)
  const availEnd = parseDateValue(availableRange.end)
  const reqStart = parseDateValue(start)
  const reqEnd = parseDateValue(end)
  if (availStart && availEnd && reqStart && reqEnd) {
    const withinRange = reqStart >= availStart && reqEnd <= availEnd
    if (!withinRange) {
      updateLogEntry(fetchLogs, logId, {
        status: 'error',
        message: `当前专题可用区间为 ${availableRange.start}→${availableRange.end}，请调整时间。`,
        time: currentTimeString()
      })
      appendLog(analyzeLogs, {
        label: '数据准备',
        message: `超出可用区间：${availableRange.start}→${availableRange.end}`,
        status: 'error'
      })
      return false
    }
  }

  const success = await runFetch(target, { logId, label: 'Fetch' })
  if (!success) {
    updateLogEntry(fetchLogs, logId, {
      status: 'error',
      message: '预拉取失败，请检查时间范围后重试。',
      time: currentTimeString()
    })
    return false
  }
  updateLogEntry(fetchLogs, logId, {
    status: 'ok',
    message: '预拉取完成，准备执行分析。',
    time: currentTimeString()
  })
  return true
}

const validateAnalyzeRange = (range) => {
  const target = normalizeRange(range)
  const { topic, start, end } = target
  if (!topic || !start || !end) {
    return 'Topic / Start / End 为必填'
  }

  const availStart = parseDateValue(availableRange.start)
  const availEnd = parseDateValue(availableRange.end)
  const reqStart = parseDateValue(start)
  const reqEnd = parseDateValue(end)
  if (availStart && availEnd && reqStart && reqEnd) {
    const withinRange = reqStart >= availStart && reqEnd <= availEnd
    if (!withinRange) {
      return `当前专题可用区间为 ${availableRange.start}→${availableRange.end}，请调整时间。`
    }
  }
  return ''
}

const invokeAnalyze = async (functions, options = {}) => {
  const { force = false } = options
  const { topic, start, end } = normalizeRange(analyzeForm)
  analyzeTaskState.error = ''
  analyzeTaskState.notice = ''

  const validationError = validateAnalyzeRange({ topic, start, end })
  if (validationError) {
    analyzeTaskState.error = validationError
    return
  }

  analyzeSubmissionCount += 1
  syncAnalyzeRunningState()
  let hasSuccess = false
  const failedLabels = []
  try {
    for (const func of functions) {
      const meta = analysisFunctions.find((item) => item.id === func)
      const label = meta?.label || func
      try {
        const response = await callApi('/api/analyze/run-async', {
          method: 'POST',
          body: JSON.stringify({
            topic,
            start,
            end,
            function: func,
            force
          })
        })
        const task = resolveAnalyzeTaskPayload(response)
        if (task && typeof task === 'object') {
          const normalizedTask = normalizeAnalyzeTask(task)
          analyzeTasks.value = sortAnalyzeTasks([
            ...analyzeTasks.value.filter((item) => item.functionId !== normalizedTask.functionId),
            normalizedTask
          ])
        }
        hasSuccess = true
      } catch (error) {
        failedLabels.push(`${label}：${error instanceof Error ? error.message : String(error)}`)
      }
    }
  } finally {
    analyzeSubmissionCount = Math.max(0, analyzeSubmissionCount - 1)
    syncAnalyzeRunningState()
  }

  if (failedLabels.length) {
    analyzeTaskState.error = failedLabels.join('；')
  }

  if (hasSuccess) {
    analyzeTaskState.notice =
      functions.length > 1
        ? `已提交 ${functions.length} 个后台任务，下方会按真实任务状态持续刷新。`
        : '后台任务已创建，下方会持续刷新真实执行状态。'
    recordAnalysisRun({ topic, start, end })
    await Promise.all([
      loadHistory(topic),
      loadAnalyzeTasks({ topic, start, end }, { silent: true })
    ])
  }
}

const runSelectedFunctions = async () => {
  if (!selectedFunctions.value.length) {
    analyzeTaskState.error = '请至少选择一个分析维度。'
    return
  }
  await invokeAnalyze([...selectedFunctions.value])
}

const runSingleFunction = async (funcId) => {
  await invokeAnalyze([funcId], { force: true })
}

const rebuildAiSummary = async () => {
  const { topic, start, end } = normalizeRange(analyzeForm)
  if (!topic || !start || !end) {
    analyzeTaskState.error = 'Topic / Start / End 为必填'
    return false
  }
  analyzeTaskState.error = ''
  analyzeTaskState.notice = '正在重新生成当前范围的 AI 摘要。'

  try {
    await callApi('/api/analyze/ai-summary/rebuild', {
      method: 'POST',
      body: JSON.stringify({ topic, start, end })
    })
    analyzeTaskState.notice = 'AI 摘要已重新生成，可前往“查看分析”刷新结果。'
    return true
  } catch (error) {
    analyzeTaskState.error = error instanceof Error ? error.message : String(error)
    return false
  }
}

const deleteAnalysisSection = async (sectionName, rangeOverride = null) => {
  const normalizedSection = String(sectionName || '').trim()
  if (!normalizedSection) {
    throw new Error('缺少要删除的分析模块')
  }

  const range = normalizeRange(
    rangeOverride || {
      topic: analysisData.value?.topic || viewSelection.topic || viewManualForm.topic || analyzeForm.topic,
      start: analysisData.value?.range?.start || viewSelection.start || viewManualForm.start,
      end: analysisData.value?.range?.end || viewSelection.end || viewManualForm.end
    }
  )

  const { topic, start, end } = range
  if (!topic || !start) {
    throw new Error('缺少专题或时间范围，无法删除分析模块')
  }

  const response = await callApi('/api/analyze/results/function', {
    method: 'DELETE',
    body: JSON.stringify({
      topic,
      start,
      end,
      function: normalizedSection
    })
  })

  const payload = response?.data || {}
  const remainingFunctions = Array.isArray(payload.remaining_functions) ? payload.remaining_functions : []

  if (remainingFunctions.length) {
    await loadResults({ topic, start, end })
  } else {
    analysisData.value = {
      status: 'ok',
      topic,
      range: { start, end: end || start },
      functions: [],
      ai_summary: payload.ai_summary_exists ? (analysisData.value?.ai_summary || null) : null
    }
    lastLoaded.value = new Date().toLocaleString()
  }

  await loadHistory(topic)
  return payload
}

const selectAll = () => {
  selectedFunctions.value = analysisFunctions.map((f) => f.id)
}

const clearSelection = () => {
  selectedFunctions.value = []
}

const loadResults = async (range) => {
  const targetRange = range ? normalizeRange(range) : normalizeRange(viewSelection)
  const { topic, start, end } = targetRange
  if (!topic || !start || !end) {
    appendLog(viewLogs, { label: '查看', message: '请选择历史记录或输入完整区间', status: 'error' })
    return
  }
  viewSelection.topic = topic
  viewSelection.start = start
  viewSelection.end = end
  loadState.loading = true
  try {
    const params = new URLSearchParams({ topic, start, end })
    const response = await callApi(`/api/analyze/results?${params.toString()}`, { method: 'GET' })
    analysisData.value = response
    lastLoaded.value = new Date().toLocaleString()
    viewManualForm.topic = topic
    viewManualForm.start = start
    viewManualForm.end = end
  } catch (error) {
    appendLog(viewLogs, {
      label: '查看',
      message: error instanceof Error ? error.message : String(error),
      status: 'error'
    })
    analysisData.value = null
  } finally {
    loadState.loading = false
  }
}

const loadResultsFromManual = async () => {
  const manualRange = {
    topic:
      viewManualForm.topic ||
      viewSelection.topic ||
      fetchForm.topic ||
      analyzeForm.topic ||
      topicOptions.value[0] ||
      '',
    start: viewManualForm.start,
    end: viewManualForm.end
  }
  const range = normalizeRange(manualRange)
  if (!range.topic || !range.start || !range.end) {
    appendLog(viewLogs, { label: '查看', message: 'Topic / Start / End 为必填', status: 'error' })
    return
  }
  selectedHistoryId.value = ''
  await loadResults(range)
}

const applyHistorySelection = async (historyId, { shouldLoad = false } = {}) => {
  const entry = analysisHistory.value.find((item) => item.id === historyId)
  if (!entry) return
  viewSelection.topic = entry.topic
  viewSelection.start = entry.start
  viewSelection.end = entry.end
  viewManualForm.topic = entry.topic
  viewManualForm.start = entry.start
  viewManualForm.end = entry.end
  if (shouldLoad) {
    await loadResults(entry)
  }
}
