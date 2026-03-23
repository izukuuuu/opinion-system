import { computed, reactive, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'
import {
  normaliseArchiveRecords,
  normaliseRecord,
  splitFolderRange as sharedSplitFolderRange,
  normalizeArchiveResponse
} from './useArchiveHistory'

const MAX_HISTORY = 24
const { callApi } = useApiBase()

const topicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const reportForm = reactive({
  topic: '',
  start: '',
  end: ''
})

const availableRange = reactive({
  loading: false,
  error: '',
  topic: '',
  start: '',
  end: ''
})

const reportState = reactive({
  loading: false,
  regenerating: false,
  error: '',
  lastLoaded: ''
})

const historyState = reactive({
  loading: false,
  error: '',
  topic: ''
})

const reportHistory = ref([])
const selectedHistoryId = ref('')
const reportData = ref(null)

const topicOptions = computed(() => topicsState.options)

let initialized = false
let rangeRequestId = 0
let historyRequestId = 0
let suppressTopicWatcher = false

export const useReportGeneration = () => {
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
    historyState,
    reportHistory,
    selectedHistoryId,
    reportData,
    changeTopic,
    loadTopics,
    loadAvailableRange,
    loadHistory,
    loadReport,
    regenerateReport,
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
        reportHistory.value = []
        selectedHistoryId.value = ''
        reportData.value = null
        return
      }
      if (trimmed === String(previous || '').trim()) {
        return
      }
      reportData.value = null
      reportForm.start = ''
      reportForm.end = ''
      selectedHistoryId.value = ''
      await refreshTopicContext(trimmed)
    }
  )
}

const ensureTopicSelection = () => {
  if (!topicOptions.value.length) return
  const current = String(reportForm.topic || '').trim()
  if (current && topicOptions.value.includes(current)) {
    return false
  }
  reportForm.topic = topicOptions.value[0]
  return true
}

const changeTopic = (value) => {
  reportForm.topic = String(value || '').trim()
}

const resetRangeState = () => {
  rangeRequestId += 1
  availableRange.loading = false
  availableRange.error = ''
  availableRange.topic = ''
  availableRange.start = ''
  availableRange.end = ''
}

const applyRangeToForm = () => {
  if (!availableRange.start) return
  const start = availableRange.start
  const end = availableRange.end || start
  reportForm.start = start
  reportForm.end = end
}

const loadAvailableRange = async (topicOverride = '', { force = false } = {}) => {
  const topic = String(topicOverride || reportForm.topic || '').trim()
  if (!topic) {
    resetRangeState()
    return
  }

  if (
    !force &&
    topic === availableRange.topic &&
    availableRange.start &&
    !availableRange.loading &&
    !availableRange.error
  ) {
    return
  }

  const requestId = ++rangeRequestId
  availableRange.loading = true
  availableRange.error = ''
  availableRange.topic = topic
  availableRange.start = ''
  availableRange.end = ''

  try {
    const params = new URLSearchParams({ topic })
    const response = await callApi(`/api/fetch/availability?${params.toString()}`, { method: 'GET' })
    if (requestId !== rangeRequestId) return
    const range = response?.data?.range || {}
    availableRange.start = String(range.start || '').trim()
    availableRange.end = String(range.end || '').trim() || availableRange.start
  } catch (error) {
    if (requestId !== rangeRequestId) return
    availableRange.error = error instanceof Error ? error.message : String(error)
    availableRange.start = ''
    availableRange.end = ''
  } finally {
    if (requestId === rangeRequestId) {
      availableRange.loading = false
    }
  }
}

const loadTopics = async () => {
  const previousTopic = String(reportForm.topic || '').trim()
  topicsState.loading = true
  topicsState.error = ''
  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: false })
    })
    const databases = response?.data?.databases || []
    topicsState.options = databases
      .map((db) => String(db?.name || '').trim())
      .filter((name, index, arr) => name && arr.indexOf(name) === index)
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
  } finally {
    topicsState.loading = false
  }
}

// Delegate to the shared implementations from useArchiveHistory.js
const splitFolderRange = sharedSplitFolderRange
const normaliseHistoryRecord = (record, defaults = {}) => normaliseRecord(record, defaults)

const loadHistory = async (topicOverride = '') => {
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
    const records = response?.records || response?.data?.records || []
    const defaults = {
      topic: String(response?.topic || topic).trim(),
      topic_identifier: String(response?.topic_identifier || topic).trim()
    }
    const normalized = records
      .map((record) => normaliseHistoryRecord(record, defaults))
      .filter(Boolean)
      .slice(0, MAX_HISTORY)

    reportHistory.value = normalized

    if (!normalized.length) {
      selectedHistoryId.value = ''
      historyState.error = '暂无报告记录，请先生成报告。'
      return
    }

    const previousSelectedId = selectedHistoryId.value
    const exists = normalized.some((record) => record.id === selectedHistoryId.value)
    if (!exists) {
      selectedHistoryId.value = normalized[0].id
    }
    const shouldSyncForm =
      topic === String(reportForm.topic || '').trim() &&
      (
        !String(reportForm.start || '').trim() ||
        !String(reportForm.end || reportForm.start || '').trim() ||
        previousSelectedId !== selectedHistoryId.value
      )
    if (shouldSyncForm) {
      syncFormWithSelectedHistory()
    }
  } catch (error) {
    if (requestId !== historyRequestId) return
    historyState.error = error instanceof Error ? error.message : String(error)
    reportHistory.value = []
    selectedHistoryId.value = ''
  } finally {
    if (requestId === historyRequestId) {
      historyState.loading = false
    }
  }
}

const getSelectedHistoryRecord = () => {
  if (!reportHistory.value.length) return null
  return reportHistory.value.find((item) => item.id === selectedHistoryId.value) || reportHistory.value[0] || null
}

const syncFormWithSelectedHistory = () => {
  const selected = getSelectedHistoryRecord()
  if (!selected) return false
  reportForm.start = selected.start
  reportForm.end = selected.end
  return true
}

const normalizeRange = (range) => {
  const topic = String(range?.topic || reportForm.topic || '').trim()
  const start = String(range?.start || reportForm.start || '').trim()
  const end = String(range?.end || reportForm.end || '').trim() || start
  return { topic, start, end }
}

const hasCompleteRange = (range) => {
  const normalized = normalizeRange(range)
  return Boolean(normalized.topic && normalized.start && normalized.end)
}

const hydrateRangeFromCurrentTopic = async () => {
  const topic = String(reportForm.topic || '').trim()
  if (!topic) return normalizeRange(reportForm)

  if (!reportHistory.value.length || historyState.topic !== topic) {
    await loadHistory(topic)
  }

  let hydrated = syncFormWithSelectedHistory()
  if (!hydrated && (availableRange.topic !== topic || !availableRange.start)) {
    await loadAvailableRange(topic)
  }
  if (!hydrated) {
    applyRangeToForm()
  }

  return normalizeRange(reportForm)
}

const currentTimeString = () => new Date().toLocaleString('zh-CN', { hour12: false })

const loadReport = async (rangeOverride = null) => {
  const resolvedRange = rangeOverride ? normalizeRange(rangeOverride) : await hydrateRangeFromCurrentTopic()
  const { topic, start, end } = resolvedRange
  if (!topic || !start || !end) {
    reportState.error = 'Topic / Start / End 为必填'
    return null
  }

  reportState.loading = true
  reportState.error = ''
  try {
    const params = new URLSearchParams({ topic, start, end })
    const response = await callApi(`/api/report?${params.toString()}`, { method: 'GET' })
    const payload = response?.data || null
    if (!payload || typeof payload !== 'object') {
      throw new Error('报告接口返回为空')
    }
    reportData.value = payload
    reportState.lastLoaded = currentTimeString()
    reportForm.topic = topic
    reportForm.start = start
    reportForm.end = end
    await loadHistory(topic)
    const matched = reportHistory.value.find((item) => item.start === start && item.end === end)
    if (matched) {
      selectedHistoryId.value = matched.id
    }
    return payload
  } catch (error) {
    reportData.value = null
    reportState.error = error instanceof Error ? error.message : String(error)
    return null
  } finally {
    reportState.loading = false
  }
}

const regenerateReport = async () => {
  const { topic, start, end } = hasCompleteRange(reportForm)
    ? normalizeRange(reportForm)
    : await hydrateRangeFromCurrentTopic()
  if (!topic || !start || !end) {
    reportState.error = 'Topic / Start / End 为必填'
    return null
  }

  reportState.regenerating = true
  reportState.error = ''
  try {
    const response = await callApi('/api/report/regenerate', {
      method: 'POST',
      body: JSON.stringify({
        topic,
        start,
        end
      })
    })
    const payload = response?.data || null
    if (!payload || typeof payload !== 'object') {
      throw new Error('报告重生成接口返回为空')
    }
    reportData.value = payload
    reportState.lastLoaded = currentTimeString()
    await loadHistory(topic)
    const matched = reportHistory.value.find((item) => item.start === start && item.end === end)
    if (matched) {
      selectedHistoryId.value = matched.id
    }
    return payload
  } catch (error) {
    reportState.error = error instanceof Error ? error.message : String(error)
    return null
  } finally {
    reportState.regenerating = false
  }
}

const applyHistorySelection = async (historyId, { shouldLoad = true } = {}) => {
  const record = reportHistory.value.find((item) => item.id === historyId)
  if (!record) return
  selectedHistoryId.value = record.id
  suppressTopicWatcher = true
  reportForm.start = record.start
  reportForm.end = record.end
  suppressTopicWatcher = false
  if (shouldLoad) {
    await loadReport({
      topic: reportForm.topic,
      start: record.start,
      end: record.end
    })
  }
}

const refreshTopicContext = async (topic) => {
  await loadAvailableRange(topic)
  await loadHistory(topic)
  const synced = syncFormWithSelectedHistory()
  if (!synced) {
    applyRangeToForm()
  }
}
