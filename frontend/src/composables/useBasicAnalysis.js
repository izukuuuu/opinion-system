import { computed, reactive, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'

const analysisFunctions = [
  {
    id: 'attitude',
    label: '情感分析 attitude',
    description: '统计 Positive / Negative / Neutral 的占比。'
  },
  {
    id: 'classification',
    label: '话题分类 classification',
    description: '基于 classification 字段的数量分布。'
  },
  {
    id: 'geography',
    label: '地域分析 geography',
    description: '按地域字段统计声量，适合地图或水平条形图。'
  },
  {
    id: 'keywords',
    label: '关键词分析 keywords',
    description: '从正文中提取高频关键词并统计词频。'
  },
  {
    id: 'publishers',
    label: '发布者分析 publishers',
    description: '统计 author 列中高频的媒体/账号。'
  },
  {
    id: 'trends',
    label: '趋势分析 trends',
    description: '按日期统计声量趋势。'
  },
  {
    id: 'volume',
    label: '声量分析 volume',
    description: '按渠道统计 JSONL 行数，评估声量占比。'
  }
]

const HORIZONTAL_BAR_FUNCTIONS = ['geography', 'publishers', 'keywords', 'classification']
const MAX_HISTORY = 12

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

const analysisSections = computed(() => {
  const payload = analysisData.value?.functions
  if (!payload) return []
  return payload.map((func) => {
    const meta = analysisFunctions.find((item) => item.id === func.name) || {
      label: func.name,
      description: ''
    }
    const targets = func.targets.map((target) => {
      const rows = extractRows(target.data)
      const hasCustomOption = Boolean(target.data?.echarts)
      const shouldSortDescending = !hasCustomOption && HORIZONTAL_BAR_FUNCTIONS.includes(func.name)
      const displayRows = shouldSortDescending ? sortRowsDescending(rows) : rows
      return {
        target: target.target,
        title: `${meta.label} · ${target.target}`,
        subtitle: `结果文件：${target.file}`,
        option: target.data?.echarts || buildFallbackOption(func.name, displayRows, target.target),
        hasData: rows.length > 0,
        rows: displayRows.slice(0, 12),
        rawText: JSON.stringify(target.data ?? {}, null, 2)
      }
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
    analysisSections,
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

const appendLog = (collection, payload) => {
  const now = new Date().toLocaleTimeString()
  collection.value = [
    { id: `${payload.label}-${Date.now()}`, time: now, ...payload },
    ...collection.value
  ].slice(0, 8)
}

const normalizeRange = (form) => {
  const topic = (form.topic || '').trim()
  const start = (form.start || '').trim()
  const end = (form.end || '').trim() || start
  return { topic, start, end }
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

const runFetch = async () => {
  const { topic, start, end } = normalizeRange(fetchForm)
  if (!topic || !start || !end) {
    appendLog(fetchLogs, { label: '参数校验', message: 'Topic / Start / End 为必填', status: 'error' })
    return
  }

  fetchState.loading = true
  try {
    await callApi('/api/fetch', {
      method: 'POST',
      body: JSON.stringify({
        topic,
        start,
        end
      })
    })
    appendLog(fetchLogs, { label: 'Fetch', message: `已触发 ${topic} ${start}→${end}`, status: 'ok' })
  } catch (error) {
    appendLog(fetchLogs, {
      label: 'Fetch',
      message: error instanceof Error ? error.message : String(error),
      status: 'error'
    })
  } finally {
    fetchState.loading = false
  }
}

const invokeAnalyze = async (functions) => {
  const { topic, start, end } = normalizeRange(analyzeForm)
  if (!topic || !start || !end) {
    appendLog(analyzeLogs, { label: '参数校验', message: 'Topic / Start / End 为必填', status: 'error' })
    return
  }

  analyzeState.running = true
  let hasSuccess = false
  try {
    for (const func of functions) {
      try {
        await callApi('/api/analyze', {
          method: 'POST',
          body: JSON.stringify({
            topic,
            start,
            end,
            function: func
          })
        })
        const meta = analysisFunctions.find((item) => item.id === func)
        appendLog(analyzeLogs, {
          label: meta?.label || func,
          message: '运行成功，结果已写入 analyze 目录',
          status: 'ok'
        })
        hasSuccess = true
      } catch (error) {
        appendLog(analyzeLogs, {
          label: func,
          message: error instanceof Error ? error.message : String(error),
          status: 'error'
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

const extractRows = (payload) => {
  if (!payload) return []
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload.data)) return payload.data
  return []
}

const ensureNumber = (value) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

const sortRowsDescending = (rows) =>
  [...rows].sort((a, b) => ensureNumber(rowValue(b)) - ensureNumber(rowValue(a)))

const rowName = (row) => {
  if (!row) return '-'
  return row.name ?? row.label ?? row.key ?? '未命名'
}

const rowValue = (row) => {
  if (!row) return 0
  return row.value ?? row.count ?? row.total ?? 0
}

const buildBarOption = (title, rows, orientation = 'vertical', categoryLabel = '类别', valueLabel = '数量') => {
  const orderedRows = orientation === 'horizontal' ? sortRowsDescending(rows) : rows
  const categories = orderedRows.map((row) => rowName(row))
  const values = orderedRows.map((row) => ensureNumber(rowValue(row)))
  const isVertical = orientation !== 'horizontal'
  const catAxis = {
    type: 'category',
    data: categories,
    axisLabel: { interval: 0, color: '#303d47' },
    axisLine: { lineStyle: { color: '#d0d5d9' } }
  }
  const valAxis = {
    type: 'value',
    axisLabel: { color: '#303d47' },
    splitLine: { lineStyle: { color: '#e2e9f1' } }
  }
  return {
    color: ['#9ab2cb'],
    title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 30, top: 60, bottom: 60, containLabel: true },
    xAxis: isVertical ? catAxis : valAxis,
    yAxis: isVertical ? valAxis : catAxis,
    dataset: {
      dimensions: [categoryLabel, valueLabel],
      source: orderedRows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) }))
    },
    series: [
      {
        type: 'bar',
        data: values,
        label: { show: true, color: '#303d47' }
      }
    ]
  }
}

const buildLineOption = (title, rows, categoryLabel = '日期', valueLabel = '数量') => {
  const categories = rows.map((row) => rowName(row))
  const values = rows.map((row) => ensureNumber(rowValue(row)))
  return {
    color: ['#7babce'],
    title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, top: 60, bottom: 60, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: categories, axisLabel: { color: '#303d47' } },
    yAxis: { type: 'value', axisLabel: { color: '#303d47' }, splitLine: { lineStyle: { color: '#e2e9f1' } } },
    dataset: {
      dimensions: [categoryLabel, valueLabel],
      source: rows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) }))
    },
    series: [
      {
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.1 },
        data: values
      }
    ]
  }
}

const buildPieOption = (title, rows) => ({
  title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, type: 'scroll', textStyle: { color: '#303d47' } },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      data: rows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) })),
      label: { formatter: '{b}: {d}%' }
    }
  ]
})

const buildFallbackOption = (funcName, rows, targetLabel) => {
  if (!rows.length) return null
  const title = `${funcName} · ${targetLabel}`
  if (funcName === 'trends') return buildLineOption(title, rows)
  if (funcName === 'attitude') return buildPieOption(title, rows)
  const orientation = HORIZONTAL_BAR_FUNCTIONS.includes(funcName) ? 'horizontal' : 'vertical'
  return buildBarOption(title, rows, orientation)
}
