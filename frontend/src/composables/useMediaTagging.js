import { computed, reactive, ref, watch } from 'vue'
import {
  normaliseArchiveRecords,
  normalizeArchiveResponse
} from './useArchiveHistory'
import { useApiBase } from './useApiBase'

const MEDIA_TASK_POLL_INTERVAL = 2000
const MEDIA_ACTIVE_STATUSES = new Set(['queued', 'running'])

const { callApi } = useApiBase()

const topicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const runForm = reactive({
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

const runState = reactive({
  running: false
})

const taskState = reactive({
  loading: false,
  error: '',
  notice: ''
})

const workerState = reactive({
  pid: 0,
  status: 'stopped',
  running: false,
  active_count: 0,
  current_task_id: '',
  last_heartbeat: '',
  started_at: '',
  updated_at: ''
})

const tasks = ref([])

const historyState = reactive({
  loading: false,
  error: '',
  topic: ''
})

const historyRecords = ref([])
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

const resultsState = reactive({
  loading: false,
  error: '',
  saving: false,
  saveError: '',
  saveNotice: '',
  registryLoading: false,
  registrySaving: false,
  registryError: '',
  registryNotice: ''
})

const filters = reactive({
  search: '',
  label: 'all'
})

const mediaResult = ref(null)
const registryItems = ref([])
const pendingLabelMap = ref({})

const topicOptions = computed(() => topicsState.options)
const resultSummary = computed(() => mediaResult.value?.summary || null)
const currentRange = computed(() => mediaResult.value?.range || null)
const rawCandidates = computed(() =>
  Array.isArray(mediaResult.value?.candidates) ? mediaResult.value.candidates : []
)

const mergedCandidates = computed(() =>
  rawCandidates.value.map((candidate) => {
    const key = candidateKey(candidate.publisher_name)
    const draft = pendingLabelMap.value[key]
    if (!draft) return candidate
    return {
      ...candidate,
      current_label: draft.current_label,
      _dirty: true
    }
  })
)

const candidateStats = computed(() => {
  const total = mergedCandidates.value.length
  const official = mergedCandidates.value.filter((item) => item.current_label === 'official_media').length
  const local = mergedCandidates.value.filter((item) => item.current_label === 'local_media').length
  return {
    total,
    official,
    local,
    unlabeled: Math.max(total - official - local, 0)
  }
})

const filteredCandidates = computed(() => {
  const searchText = String(filters.search || '').trim().toLowerCase()
  const labelFilter = String(filters.label || 'all').trim()
  return [...mergedCandidates.value]
    .filter((candidate) => {
      if (labelFilter === 'official_media' && candidate.current_label !== 'official_media') return false
      if (labelFilter === 'local_media' && candidate.current_label !== 'local_media') return false
      if (labelFilter === 'unlabeled' && candidate.current_label) return false
      if (!searchText) return true
      const haystacks = [
        candidate.publisher_name,
        candidate.matched_registry_name,
        ...(Array.isArray(candidate.platforms) ? candidate.platforms : [])
      ]
      return haystacks.some((item) => String(item || '').toLowerCase().includes(searchText))
    })
    .sort((left, right) => {
      const countDiff = Number(right.publish_count || 0) - Number(left.publish_count || 0)
      if (countDiff !== 0) return countDiff
      return String(right.latest_published_at || '').localeCompare(String(left.latest_published_at || ''))
    })
})

const pendingUpdates = computed(() =>
  Object.values(pendingLabelMap.value).filter(
    (item) => item && typeof item === 'object' && item.publisher_name
  )
)

const hasPendingChanges = computed(() => pendingUpdates.value.length > 0)

const filteredRegistryItems = computed(() => {
  const searchText = String(filters.search || '').trim().toLowerCase()
  const labelFilter = String(filters.label || 'all').trim()
  return [...registryItems.value]
    .filter((item) => {
      if (labelFilter === 'official_media' && item.media_level !== 'official_media') return false
      if (labelFilter === 'local_media' && item.media_level !== 'local_media') return false
      if (labelFilter === 'unlabeled' && item.media_level) return false
      if (!searchText) return true
      const haystacks = [
        item.name,
        ...(Array.isArray(item.aliases) ? item.aliases : []),
        item.notes
      ]
      return haystacks.some((entry) => String(entry || '').toLowerCase().includes(searchText))
    })
    .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')))
})

let initialized = false
let availabilityRequestId = 0
let taskPollTimer = null
let submissionCount = 0

export const useMediaTagging = () => {
  if (!initialized) {
    initialized = true
    initializeStore()
  }

  return {
    topicsState,
    topicOptions,
    runForm,
    availableRange,
    runState,
    taskState,
    workerState,
    tasks,
    historyState,
    historyRecords,
    selectedHistoryId,
    viewSelection,
    viewManualForm,
    resultsState,
    mediaResult,
    registryItems,
    filters,
    resultSummary,
    currentRange,
    filteredCandidates,
    filteredRegistryItems,
    candidateStats,
    hasPendingChanges,
    pendingUpdates,
    changeTopic,
    loadTopics,
    loadAvailableRange,
    runMediaTagging,
    loadTasks,
    loadHistory,
    applyHistorySelection,
    loadResults,
    loadResultsFromManual,
    loadRegistry,
    stageCandidateLabel,
    applyLabelToFilteredCandidates,
    discardCandidateChanges,
    clearAllCandidateChanges,
    saveCandidateUpdates,
    saveRegistryItem
  }
}

function initializeStore() {
  loadTopics()

  watch(topicOptions, ensureTopicSelection, { immediate: true })

  watch(
    () => runForm.topic,
    (value) => {
      const topic = String(value || '').trim()
      if (!topic) {
        clearAvailableRange()
        tasks.value = []
        resetWorkerState()
        return
      }
      viewSelection.topic = viewSelection.topic || topic
      viewManualForm.topic = topic
      loadAvailableRange()
    },
    { immediate: true }
  )

  watch(
    () => [runForm.topic, runForm.start, runForm.end],
    ([topic, start, end]) => {
      const range = normalizeRange({ topic, start, end })
      if (!range.topic || !range.start || !range.end) {
        tasks.value = []
        resetWorkerState()
        stopTaskPolling()
        syncRunState()
        return
      }
      loadTasks(range, { silent: true })
    },
    { immediate: true }
  )

  watch(
    historyRecords,
    (value) => {
      if (!value.length) {
        selectedHistoryId.value = ''
        return
      }
      const exists = value.some((item) => item.id === selectedHistoryId.value)
      if (!exists) {
        selectedHistoryId.value = value[0].id
      }
    },
    { deep: true }
  )

  watch(
    () => viewSelection.topic,
    (topic) => {
      const trimmed = String(topic || '').trim()
      viewManualForm.topic = trimmed
      if (!trimmed) {
        historyRecords.value = []
        historyState.topic = ''
        historyState.error = ''
        return
      }
      loadHistory(trimmed)
    },
    { immediate: true }
  )

  watch(
    selectedHistoryId,
    (historyId) => {
      if (!historyId) return
      applyHistorySelection(historyId, { shouldLoad: true })
    }
  )

  watch(
    tasks,
    () => {
      syncRunState()
    },
    { deep: true }
  )
}

function candidateKey(value) {
  return String(value || '').trim().toLowerCase()
}

function normalizeRange(form) {
  const topic = String(form?.topic || '').trim()
  const start = String(form?.start || '').trim()
  const end = String(form?.end || '').trim() || start
  return { topic, start, end }
}

function normalizeTask(task) {
  const payload = task && typeof task === 'object' ? task : {}
  const status = String(payload.status || '').trim().toLowerCase() || 'queued'
  return {
    id: String(payload.id || '').trim(),
    label: '媒体识别与打标',
    status,
    phase: String(payload.phase || '').trim() || status,
    percentage: Math.max(0, Math.min(100, Number(payload.percentage || 0))),
    message: String(payload.message || '').trim(),
    currentTarget: [
      String(payload.start_date || '').trim(),
      String(payload.end_date || '').trim() || String(payload.start_date || '').trim()
    ]
      .filter(Boolean)
      .join(' → '),
    updatedAt: formatDateTime(payload.updated_at),
    createdAt: String(payload.created_at || '').trim(),
    sentimentTotal: 0,
    sentimentProcessed: 0,
    sentimentClassified: 0,
    raw: payload
  }
}

function ensureTopicSelection() {
  if (!topicOptions.value.length) return
  if (!runForm.topic || !topicOptions.value.includes(runForm.topic)) {
    runForm.topic = topicOptions.value[0]
  }
  if (!viewSelection.topic) {
    viewSelection.topic = runForm.topic
  }
  if (!viewManualForm.topic) {
    viewManualForm.topic = runForm.topic
  }
}

function resetAvailableRange() {
  availableRange.start = ''
  availableRange.end = ''
}

function clearAvailableRange() {
  availabilityRequestId += 1
  availableRange.loading = false
  availableRange.error = ''
  resetAvailableRange()
}

function applyAvailableRangeToForms() {
  const start = availableRange.start || ''
  const end = availableRange.end || start || ''
  runForm.start = start
  runForm.end = end
}

function resetWorkerState() {
  workerState.pid = 0
  workerState.status = 'stopped'
  workerState.running = false
  workerState.active_count = 0
  workerState.current_task_id = ''
  workerState.last_heartbeat = ''
  workerState.started_at = ''
  workerState.updated_at = ''
}

function applyWorkerState(payload) {
  const worker = payload && typeof payload === 'object' ? payload : {}
  workerState.pid = Number(worker.pid || 0)
  workerState.status = String(worker.status || '').trim() || 'stopped'
  workerState.running = Boolean(worker.running)
  workerState.active_count = Number(worker.active_count || 0)
  workerState.current_task_id = String(worker.current_task_id || '').trim()
  workerState.last_heartbeat = String(worker.last_heartbeat || '').trim()
  workerState.started_at = String(worker.started_at || '').trim()
  workerState.updated_at = String(worker.updated_at || '').trim()
}

function formatDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function syncRunState() {
  runState.running =
    submissionCount > 0 ||
    tasks.value.some((task) => MEDIA_ACTIVE_STATUSES.has(String(task.status || '').trim().toLowerCase()))
}

function stopTaskPolling() {
  if (typeof window !== 'undefined' && taskPollTimer) {
    window.clearTimeout(taskPollTimer)
  }
  taskPollTimer = null
}

function scheduleTaskPolling() {
  if (typeof window === 'undefined' || taskPollTimer) return
  if (!tasks.value.some((task) => MEDIA_ACTIVE_STATUSES.has(String(task.status || '').trim().toLowerCase()))) {
    return
  }
  taskPollTimer = window.setTimeout(async () => {
    taskPollTimer = null
    await loadTasks(null, { silent: true })
  }, MEDIA_TASK_POLL_INTERVAL)
}

function applyTaskSnapshot(payload) {
  const data = payload && typeof payload === 'object' ? payload : {}
  const list = Array.isArray(data.tasks) ? data.tasks.map(normalizeTask) : []
  tasks.value = list.sort((left, right) => String(right.createdAt || '').localeCompare(String(left.createdAt || '')))
  applyWorkerState(data.worker)
  syncRunState()
}

async function loadTopics() {
  topicsState.loading = true
  topicsState.error = ''
  const previousTopic = runForm.topic
  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: false })
    })
    const databases = Array.isArray(response?.data?.databases) ? response.data.databases : []
    topicsState.options = databases
      .map((item) => String(item?.name || '').trim())
      .filter((name, index, array) => name && array.indexOf(name) === index)
    ensureTopicSelection()
    if (!previousTopic && runForm.topic) {
      await loadAvailableRange()
    }
  } catch (error) {
    topicsState.error = error instanceof Error ? error.message : '专题列表读取失败'
    topicsState.options = []
  } finally {
    topicsState.loading = false
  }
}

async function loadAvailableRange() {
  const topic = String(runForm.topic || '').trim()
  if (!topic) {
    clearAvailableRange()
    return
  }
  const requestId = ++availabilityRequestId
  availableRange.loading = true
  availableRange.error = ''
  resetAvailableRange()
  try {
    const params = new URLSearchParams({ topic })
    const response = await callApi(`/api/fetch/availability?${params.toString()}`, {
      method: 'GET'
    })
    if (requestId !== availabilityRequestId) return
    const range = response?.data?.range || {}
    availableRange.start = String(range.start || '').trim()
    availableRange.end = String(range.end || '').trim()
    applyAvailableRangeToForms()
  } catch (error) {
    if (requestId !== availabilityRequestId) return
    availableRange.error = error instanceof Error ? error.message : '可用范围读取失败'
    resetAvailableRange()
    runForm.start = ''
    runForm.end = ''
  } finally {
    if (requestId === availabilityRequestId) {
      availableRange.loading = false
    }
  }
}

function changeTopic(value) {
  const topic = String(value || '').trim()
  runForm.topic = topic
  viewSelection.topic = topic
  viewManualForm.topic = topic
}

async function loadTasks(rangeOverride = null, { silent = false } = {}) {
  const range = normalizeRange(rangeOverride || runForm)
  if (!range.topic || !range.start || !range.end) {
    tasks.value = []
    resetWorkerState()
    stopTaskPolling()
    syncRunState()
    return
  }

  if (!silent) {
    taskState.loading = true
    taskState.error = ''
  }

  try {
    const params = new URLSearchParams({
      topic: range.topic,
      start: range.start,
      end: range.end,
      limit: '50'
    })
    const response = await callApi(`/api/media-tags/tasks?${params.toString()}`, {
      method: 'GET'
    })
    applyTaskSnapshot(response?.data || {})
    const hasActive = tasks.value.some((task) => MEDIA_ACTIVE_STATUSES.has(task.status))
    if (!hasActive && tasks.value.some((task) => task.status === 'completed')) {
      await loadHistory(range.topic)
    }
    stopTaskPolling()
    scheduleTaskPolling()
  } catch (error) {
    taskState.error = error instanceof Error ? error.message : '任务状态读取失败'
    tasks.value = []
    resetWorkerState()
    stopTaskPolling()
  } finally {
    if (!silent) {
      taskState.loading = false
    }
    syncRunState()
  }
}

async function runMediaTagging() {
  const range = normalizeRange(runForm)
  taskState.error = ''
  taskState.notice = ''

  if (!range.topic || !range.start || !range.end) {
    taskState.error = '请先补全专题和时间范围。'
    return false
  }

  submissionCount += 1
  syncRunState()

  try {
    const response = await callApi('/api/media-tags/run-async', {
      method: 'POST',
      body: JSON.stringify(range)
    })
    const task = response?.task
    if (task) {
      tasks.value = [
        normalizeTask(task),
        ...tasks.value.filter((item) => item.id !== String(task.id || '').trim())
      ]
    }
    viewSelection.topic = range.topic
    viewSelection.start = range.start
    viewSelection.end = range.end
    viewManualForm.topic = range.topic
    viewManualForm.start = range.start
    viewManualForm.end = range.end
    taskState.notice = '后台任务已创建，候选媒体整理完成后会自动出现在历史记录里。'
    await loadTasks(range, { silent: true })
    return true
  } catch (error) {
    taskState.error = error instanceof Error ? error.message : '任务创建失败'
    return false
  } finally {
    submissionCount = Math.max(0, submissionCount - 1)
    syncRunState()
  }
}

async function loadHistory(topic) {
  const trimmed = String(topic || '').trim()
  if (!trimmed) {
    historyRecords.value = []
    historyState.topic = ''
    historyState.error = ''
    return
  }
  historyState.loading = true
  historyState.error = ''
  try {
    const directRecords = await fetchHistoryViaMediaApi(trimmed)
    if (directRecords.length) {
      historyRecords.value = directRecords
      historyState.topic = trimmed
      return
    }
    const archiveRecords = await fetchHistoryViaArchives(trimmed)
    historyRecords.value = archiveRecords
    historyState.topic = trimmed
    if (!archiveRecords.length) {
      historyState.error = '当前专题还没有媒体识别结果，请先运行一次识别。'
    }
  } catch (primaryError) {
    try {
      const archiveRecords = await fetchHistoryViaArchives(trimmed)
      historyRecords.value = archiveRecords
      historyState.topic = trimmed
      if (!archiveRecords.length) {
        historyState.error = '当前专题还没有媒体识别结果，请先运行一次识别。'
      }
    } catch (fallbackError) {
      historyRecords.value = []
      historyState.topic = ''
      historyState.error = fallbackError instanceof Error ? fallbackError.message : String(fallbackError)
    }
  } finally {
    historyState.loading = false
  }
}

function fetchHistoryViaMediaApi(topic) {
  const params = new URLSearchParams({ topic })
  return callApi(`/api/media-tags/history?${params.toString()}`, { method: 'GET' }).then((response) => {
    const { records, defaults } = normalizeArchiveResponse(response, 'media_tags', topic)
    return normaliseArchiveRecords(records, defaults)
  })
}

function fetchHistoryViaArchives(topic) {
  const encodedTopic = encodeURIComponent(topic)
  return callApi(`/api/projects/${encodedTopic}/archives?layers=media_tags`, {
    method: 'GET'
  }).then((response) => {
    const { records, defaults, folderKey } = normalizeArchiveResponse(response, 'media_tags', topic)
    return normaliseArchiveRecords(records, defaults, folderKey ? { folderKey } : {})
  })
}

async function applyHistorySelection(historyId, { shouldLoad = false } = {}) {
  const entry = historyRecords.value.find((item) => item.id === historyId)
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

async function loadResults(rangeOverride = null) {
  const range = normalizeRange(rangeOverride || viewSelection)
  if (!range.topic || !range.start || !range.end) {
    resultsState.error = '请选择要查看的专题和时间范围。'
    return
  }
  resultsState.loading = true
  resultsState.error = ''
  resultsState.saveError = ''
  resultsState.saveNotice = ''
  pendingLabelMap.value = {}
  try {
    const params = new URLSearchParams({
      topic: range.topic,
      start: range.start,
      end: range.end
    })
    const response = await callApi(`/api/media-tags/results?${params.toString()}`, {
      method: 'GET'
    })
    mediaResult.value = response
    registryItems.value = Array.isArray(response?.registry) ? response.registry : registryItems.value
    viewSelection.topic = range.topic
    viewSelection.start = range.start
    viewSelection.end = range.end
    viewManualForm.topic = range.topic
    viewManualForm.start = range.start
    viewManualForm.end = range.end
  } catch (error) {
    mediaResult.value = null
    resultsState.error = error instanceof Error ? error.message : '结果读取失败'
  } finally {
    resultsState.loading = false
  }
}

async function loadResultsFromManual() {
  const range = normalizeRange(viewManualForm)
  if (!range.topic || !range.start || !range.end) {
    resultsState.error = '请先补全手动查询的时间范围。'
    return
  }
  selectedHistoryId.value = ''
  await loadResults(range)
}

async function loadRegistry() {
  resultsState.registryLoading = true
  resultsState.registryError = ''
  try {
    const response = await callApi('/api/media-tags/registry', {
      method: 'GET'
    })
    registryItems.value = Array.isArray(response?.data?.items) ? response.data.items : []
  } catch (error) {
    resultsState.registryError = error instanceof Error ? error.message : '共享字典读取失败'
  } finally {
    resultsState.registryLoading = false
  }
}

function stageCandidateLabel(publisherName, label) {
  const key = candidateKey(publisherName)
  const original = rawCandidates.value.find((item) => candidateKey(item.publisher_name) === key)
  if (!original) return
  const nextLabel = String(label || '').trim()
  if (nextLabel === String(original.current_label || '').trim()) {
    delete pendingLabelMap.value[key]
    pendingLabelMap.value = { ...pendingLabelMap.value }
    return
  }
  pendingLabelMap.value = {
    ...pendingLabelMap.value,
    [key]: {
      publisher_name: original.publisher_name,
      current_label: nextLabel
    }
  }
}

function applyLabelToFilteredCandidates(label) {
  filteredCandidates.value.forEach((candidate) => {
    stageCandidateLabel(candidate.publisher_name, label)
  })
}

function discardCandidateChanges(publisherName) {
  const key = candidateKey(publisherName)
  if (!pendingLabelMap.value[key]) return
  const next = { ...pendingLabelMap.value }
  delete next[key]
  pendingLabelMap.value = next
}

function clearAllCandidateChanges() {
  pendingLabelMap.value = {}
}

async function saveCandidateUpdates(publisherNames = null) {
  const range = normalizeRange({
    topic: viewSelection.topic || mediaResult.value?.topic || runForm.topic,
    start: currentRange.value?.start || viewSelection.start,
    end: currentRange.value?.end || viewSelection.end
  })
  if (!range.topic || !range.start || !range.end) {
    resultsState.saveError = '缺少专题或时间范围，暂时无法保存。'
    return false
  }

  const targetSet = Array.isArray(publisherNames)
    ? new Set(publisherNames.map((item) => candidateKey(item)))
    : null
  const updates = pendingUpdates.value.filter((item) =>
    targetSet ? targetSet.has(candidateKey(item.publisher_name)) : true
  )

  if (!updates.length) {
    resultsState.saveNotice = '当前没有需要保存的标签变更。'
    return true
  }

  resultsState.saving = true
  resultsState.saveError = ''
  resultsState.saveNotice = ''
  try {
    const response = await callApi('/api/media-tags/results/labels', {
      method: 'POST',
      body: JSON.stringify({
        topic: range.topic,
        start: range.start,
        end: range.end,
        updates
      })
    })
    mediaResult.value = response
    await loadRegistry()
    if (targetSet) {
      const next = { ...pendingLabelMap.value }
      updates.forEach((item) => {
        delete next[candidateKey(item.publisher_name)]
      })
      pendingLabelMap.value = next
    } else {
      pendingLabelMap.value = {}
    }
    resultsState.saveNotice =
      updates.length === 1 ? '这一条标签已经保存。' : `已保存 ${updates.length} 条媒体标签。`
    return true
  } catch (error) {
    resultsState.saveError = error instanceof Error ? error.message : '标签保存失败'
    return false
  } finally {
    resultsState.saving = false
  }
}

async function saveRegistryItem(payload) {
  const name = String(payload?.name || '').trim()
  if (!name) {
    resultsState.registryError = '请先填写媒体名称。'
    return null
  }

  const itemId =
    String(payload?.id || '').trim() ||
    `mr-manual-${Date.now().toString(36)}`

  resultsState.registrySaving = true
  resultsState.registryError = ''
  resultsState.registryNotice = ''
  try {
    const response = await callApi(`/api/media-tags/registry/${encodeURIComponent(itemId)}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...payload,
        aliases: Array.isArray(payload?.aliases)
          ? payload.aliases
          : String(payload?.aliases || '')
              .split(/[\n,，;；]/)
              .map((item) => item.trim())
              .filter(Boolean)
      })
    })
    await loadRegistry()
    resultsState.registryNotice = '共享媒体字典已更新。'
    return response?.data || null
  } catch (error) {
    resultsState.registryError = error instanceof Error ? error.message : '共享字典保存失败'
    return null
  } finally {
    resultsState.registrySaving = false
  }
}
