import { computed, reactive, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'
import {
  buildChartOption,
  buildRawText,
  extractRows,
  isHorizontalBarFunction,
  sortRowsDescending
} from '../utils/chartBuilder'

const analysisFunctions = [
  {
    id: 'attitude',
    label: '情感分析',
    description: '分析内容的情感倾向分布，识别正面、负面和中性情绪。'
  },
  {
    id: 'classification',
    label: '话题分类',
    description: '对内容进行分类统计，了解不同话题的分布情况。'
  },
  {
    id: 'geography',
    label: '地域分析',
    description: '分析内容的地域分布特征，识别主要传播区域。'
  },
  {
    id: 'keywords',
    label: '关键词分析',
    description: '提取并统计高频关键词，了解核心关注点。'
  },
  {
    id: 'publishers',
    label: '发布者分析',
    description: '分析主要发布者分布，识别活跃的媒体和账号。'
  },
  {
    id: 'trends',
    label: '趋势洞察',
    description: '分析时间维度的声量变化，识别传播趋势和峰值。'
  },
  {
    id: 'volume',
    label: '声量概览',
    description: '统计各渠道的声量分布，评估传播渠道的影响力。'
  }
]

const MAX_HISTORY = 12

const sanitizeLabel = (label) => {
  if (!label) return ''
  const match = String(label).match(/^[\u4e00-\u9fa5·\s]+/)
  if (match) {
    const value = match[0].trim()
    if (value) return value
  }
  return String(label).trim()
}

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

const fetchLogs = ref([])
const analyzeLogs = ref([])
const viewLogs = ref([])

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

const analysisSections = computed(() => {
  const payload = analysisData.value?.functions
  if (!payload) return []
  return payload.map((func) => {
    const meta = analysisFunctions.find((item) => item.id === func.name) || {
      label: func.name,
      description: ''
    }
    const displayLabel = sanitizeLabel(meta.label) || meta.label || func.name
    const targets = func.targets
      .map((target) => {
        const rows = extractRows(target.data)
        const shouldSortDescending = isHorizontalBarFunction(func.name)
        const displayRows = shouldSortDescending ? sortRowsDescending(rows) : rows
        const targetTitle = `${displayLabel} · ${target.target}`
        return {
          target: target.target,
          title: targetTitle,
          subtitle: '',
          option: buildChartOption(func.name, displayRows, targetTitle),
          hasData: rows.length > 0,
          rows: displayRows.slice(0, 12),
          rawText: buildRawText(target.data)
        }
      })
      .sort((a, b) => {
        // 将"总体"放在前面
        if (a.target === '总体') return -1
        if (b.target === '总体') return 1
        return 0
      })
    return {
      name: func.name,
      label: meta.label,
      description: meta.description,
      targets
    }
  })
})

let initialized = false

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
    loadState,
    fetchLogs,
    analyzeLogs,
    viewLogs,
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
    const response = await callApi('/api/query', { method: 'POST', body: JSON.stringify({}) })
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
  const records = response?.records || response?.data?.records || response?.data || []
  const defaults = {
    topic: response?.topic || topic,
    topic_identifier: response?.topic_identifier || topic
  }
  return normaliseHistoryRecords(records, defaults)
}

const fetchHistoryViaArchives = async (topic) => {
  const encodedTopic = encodeURIComponent(topic)
  const response = await callApi(`/api/projects/${encodedTopic}/archives?layers=analyze`, { method: 'GET' })
  const entries = response?.archives?.analyze || []
  const defaults = {
    topic: response?.display_name || response?.project || topic,
    topic_identifier: response?.topic || topic
  }
  return normaliseHistoryRecords(entries, defaults, { folderKey: 'date' })
}

const normaliseHistoryRecords = (records, defaults = {}, options = {}) => {
  if (!Array.isArray(records) || !records.length) return []
  const folderKey = options.folderKey || 'folder'
  return records
    .map((record) => normaliseSingleHistoryRecord(record, defaults, folderKey))
    .filter((entry) => entry && entry.start)
    .slice(0, MAX_HISTORY)
}

const normaliseSingleHistoryRecord = (record, defaults = {}, folderKey = 'folder') => {
  if (!record) return null
  const topic = String(record.topic || defaults.topic || '').trim()
  const topicIdentifier = String(record.topic_identifier || defaults.topic_identifier || topic).trim()
  const folderRaw = String(record[folderKey] || record.folder || record.date || '').trim()
  const startRaw = String(record.start || '').trim()
  const endRaw = String(record.end || '').trim()
  const { start, end } = deriveRangeFromFolder(folderRaw, startRaw, endRaw)
  if (!topic || !start) return null
  const folder = folderRaw || (start === end ? start : `${start}_${end}`)
  const id = record.id || `${topicIdentifier || topic}:${folder}`
  return {
    id,
    topic,
    topic_identifier: topicIdentifier || topic,
    start,
    end,
    folder,
    updated_at: record.updated_at || record.lastRun || record.last_run || ''
  }
}

const deriveRangeFromFolder = (folderValue, startValue, endValue) => {
  let rangeStart = (startValue || '').trim()
  let rangeEnd = (endValue || '').trim()
  const folder = (folderValue || '').trim()
  if (!rangeStart && folder) {
    if (folder.includes('_')) {
      const [first, second] = folder.split('_', 2)
      rangeStart = first.trim()
      rangeEnd = (second || first).trim()
    } else {
      rangeStart = folder
    }
  }
  if (!rangeEnd) {
    rangeEnd = rangeStart
  }
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

const invokeAnalyze = async (functions) => {
  const { topic, start, end } = normalizeRange(analyzeForm)
  if (!topic || !start || !end) {
    appendLog(analyzeLogs, { label: '参数校验', message: 'Topic / Start / End 为必填', status: 'error' })
    return
  }

  const fetchReady = await ensureFetchReadyForRange({ topic, start, end })
  if (!fetchReady) {
    appendLog(analyzeLogs, { label: '数据准备', message: '未能完成数据拉取，已停止本次分析。', status: 'error' })
    return
  }

  analyzeState.running = true
  let hasSuccess = false
  try {
    for (const func of functions) {
      const meta = analysisFunctions.find((item) => item.id === func)
      const label = meta?.label || func
      const logId = appendLog(analyzeLogs, {
        label,
        message: '排队中，等待执行…',
        status: 'queued'
      })
      try {
        updateLogEntry(analyzeLogs, logId, {
          status: 'running',
          message: '正在运行…',
          time: currentTimeString()
        })
        await callApi('/api/analyze', {
          method: 'POST',
          body: JSON.stringify({
            topic,
            start,
            end,
            function: func
          })
        })
        updateLogEntry(analyzeLogs, logId, {
          status: 'ok',
          message: '分析完成，可前往“查看分析”刷新结果。',
          time: currentTimeString()
        })
        hasSuccess = true
      } catch (error) {
        updateLogEntry(analyzeLogs, logId, {
          message: error instanceof Error ? error.message : String(error),
          status: 'error',
          time: currentTimeString()
        })
      }
    }
  } finally {
    analyzeState.running = false
  }
  if (hasSuccess) {
    recordAnalysisRun({ topic, start, end })
    await loadHistory(topic)
  }
}

const runSelectedFunctions = async () => {
  if (!selectedFunctions.value.length) {
    appendLog(analyzeLogs, { label: '提示', message: '请至少选择一个函数', status: 'error' })
    return
  }
  await invokeAnalyze([...selectedFunctions.value])
}

const runSingleFunction = async (funcId) => {
  await invokeAnalyze([funcId])
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
