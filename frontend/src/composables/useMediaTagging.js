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
  options: [],
  topicIdentifiers: {} // name -> identifier mapping
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
  topic_identifier: '',
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
  label: 'all',
  platform: '',
  sortMode: 'suggest_first' // suggest_first | publish_count
})

const mediaResult = ref(null)
const registryItems = ref([])
const selectedItems = ref(new Set())
const selectedRegistryItems = ref(new Set())

const topicOptions = computed(() => topicsState.options)
const resultSummary = computed(() => mediaResult.value?.summary || null)
const currentRange = computed(() => mediaResult.value?.range || null)
const rawCandidates = computed(() =>
  Array.isArray(mediaResult.value?.candidates) ? mediaResult.value.candidates : []
)

const candidateStats = computed(() => {
  const total = rawCandidates.value.length
  const official = rawCandidates.value.filter((item) => item.current_label === 'official_media').length
  const local = rawCandidates.value.filter((item) => item.current_label === 'local_media').length
  const network = rawCandidates.value.filter((item) => item.current_label === 'network_media').length
  const comprehensive = rawCandidates.value.filter((item) => item.current_label === 'comprehensive_media').length
  const hasSuggest = rawCandidates.value.filter((item) => item.suggested_label && !item.current_label).length
  return {
    total,
    official,
    local,
    network,
    comprehensive,
    unlabeled: Math.max(total - official - local - network - comprehensive, 0),
    hasSuggest
  }
})

// 提取所有平台列表
const allPlatforms = computed(() => {
  const platforms = new Set()
  rawCandidates.value.forEach((item) => {
    if (Array.isArray(item.platforms)) {
      item.platforms.forEach((p) => platforms.add(p))
    }
  })
  return Array.from(platforms).sort()
})

const filteredCandidates = computed(() => {
  const searchText = String(filters.search || '').trim().toLowerCase()
  const labelFilter = String(filters.label || 'all').trim()
  const platformFilter = String(filters.platform || '').trim()
  const sortMode = String(filters.sortMode || 'suggest_first').trim()

  let result = [...rawCandidates.value]
    .filter((candidate) => {
      if (labelFilter === 'official_media' && candidate.current_label !== 'official_media') return false
      if (labelFilter === 'local_media' && candidate.current_label !== 'local_media') return false
      if (labelFilter === 'network_media' && candidate.current_label !== 'network_media') return false
      if (labelFilter === 'comprehensive_media' && candidate.current_label !== 'comprehensive_media') return false
      if (labelFilter === 'unlabeled' && candidate.current_label) return false
      if (labelFilter === 'has_suggest' && !candidate.suggested_label) return false
      if (platformFilter && !candidate.platforms?.includes(platformFilter)) return false
      if (!searchText) return true
      const haystacks = [
        candidate.publisher_name,
        candidate.matched_registry_name,
        ...(Array.isArray(candidate.platforms) ? candidate.platforms : [])
      ]
      return haystacks.some((item) => String(item || '').toLowerCase().includes(searchText))
    })

  // 排序：建议优先 or 发布量优先
  if (sortMode === 'suggest_first') {
    result.sort((left, right) => {
      // 有建议且未打标的排前面
      const leftSuggest = left.suggested_label && !left.current_label ? 1 : 0
      const rightSuggest = right.suggested_label && !right.current_label ? 1 : 0
      if (leftSuggest !== rightSuggest) return rightSuggest - leftSuggest
      // 然后按发布量
      const countDiff = Number(right.publish_count || 0) - Number(left.publish_count || 0)
      if (countDiff !== 0) return countDiff
      return String(right.latest_published_at || '').localeCompare(String(left.latest_published_at || ''))
    })
  } else {
    result.sort((left, right) => {
      const countDiff = Number(right.publish_count || 0) - Number(left.publish_count || 0)
      if (countDiff !== 0) return countDiff
      return String(right.latest_published_at || '').localeCompare(String(left.latest_published_at || ''))
    })
  }

  return result
})

const filteredRegistryItems = computed(() => {
  const searchText = String(filters.search || '').trim().toLowerCase()
  const labelFilter = String(filters.label || 'all').trim()
  return [...registryItems.value]
    .filter((item) => {
      if (labelFilter === 'official_media' && item.media_level !== 'official_media') return false
      if (labelFilter === 'local_media' && item.media_level !== 'local_media') return false
      if (labelFilter === 'network_media' && item.media_level !== 'network_media') return false
      if (labelFilter === 'comprehensive_media' && item.media_level !== 'comprehensive_media') return false
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
    allPlatforms,
    selectedItems,
    isAllSelected,
    selectedCount,
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
    toggleSelectAll,
    toggleSelectItem,
    applyLabelToSelected,
    clearSelection,
    saveCandidateUpdates,
    saveRegistryItem,
    deleteCandidates,
    deleteSelectedCandidates,
    deleteRegistryItem,
    acceptAllSuggestions,
    selectedRegistryItems,
    isAllRegistrySelected,
    selectedRegistryCount,
    toggleSelectAllRegistry,
    toggleSelectRegistryItem,
    clearRegistrySelection,
    mergeRegistryItems
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
    () => viewSelection.topic_identifier || viewSelection.topic,
    (topicIdentifier) => {
      const trimmed = String(topicIdentifier || '').trim()
      viewManualForm.topic = viewSelection.topic || trimmed
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
  const topicInput = String(form?.topic || '').trim()
  const identifierInput = String(form?.topic_identifier || '').trim()
  // 优先使用展示名称（topic），没有时才用内部 identifier，避免时间戳前缀被 URL 编码后触发后端解析失败
  let topic = topicInput || identifierInput
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
    // Build name -> identifier mapping from database records
    const mapping = {}
    databases.forEach((item) => {
      const name = String(item?.name || '').trim()
      const identifier = String(item?.identifier || item?.project_id || name).trim()
      if (name) mapping[name] = identifier
    })
    topicsState.topicIdentifiers = mapping
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
  viewSelection.topic_identifier = entry.topic_identifier || entry.topic
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
  // 优先使用传入的 range，其次用当前结果中的 range，最后用 viewSelection
  const currentLoadedRange = mediaResult.value?.range || currentRange.value
  const range = normalizeRange(rangeOverride || currentLoadedRange || viewSelection)

  if (!range.topic || !range.start || !range.end) {
    resultsState.error = '请选择要查看的专题和时间范围。'
    return
  }

  resultsState.loading = true
  resultsState.error = ''
  selectedItems.value.clear()
  selectedItems.value = new Set()

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
    viewSelection.topic_identifier = response?.topic_identifier || range.topic
    viewSelection.topic = response?.topic || range.topic
    viewSelection.start = range.start
    viewSelection.end = range.end
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

// 构建候选索引，加速查找
const candidateIndex = computed(() => {
  const index = new Map()
  for (const item of rawCandidates.value) {
    const key = candidateKey(item.publisher_name)
    index.set(key, item)
  }
  return index
})

// 本地乐观更新候选标签（不等待API）
function optimisticUpdateLabel(publisherName, label) {
  const key = candidateKey(publisherName)
  const candidate = candidateIndex.value.get(key)
  if (!candidate) return

  // 立即更新本地状态
  candidate.current_label = String(label || '').trim()

  // 触发响应式更新
  mediaResult.value = { ...mediaResult.value }
}

// 后台批量保存标签（不阻塞UI）
async function saveLabelsInBackground(publisherNames, label) {
  const range = normalizeRange({
    topic: viewSelection.topic || viewSelection.topic_identifier || mediaResult.value?.topic || runForm.topic,
    start: currentRange.value?.start || viewSelection.start,
    end: currentRange.value?.end || viewSelection.end
  })

  if (!range.topic || !range.start || !range.end) {
    console.warn('缺少专题或时间范围，无法后台保存')
    return false
  }

  const updates = publisherNames.map((name) => ({
    publisher_name: name,
    current_label: String(label || '').trim()
  }))

  try {
    await callApi('/api/media-tags/results/labels', {
      method: 'POST',
      body: JSON.stringify({
        topic: range.topic,
        start: range.start,
        end: range.end,
        updates
      })
    })
    // 不需要用 API response 替换，乐观更新已经生效
    // 后台静默刷新 registry
    loadRegistry().catch(() => {})
    return true
  } catch (error) {
    console.error('后台保存失败:', error)
    return false
  }
}

async function stageCandidateLabel(publisherName, label) {
  const key = candidateKey(publisherName)
  const original = candidateIndex.value.get(key)
  if (!original) {
    console.warn(`未找到候选媒体：${publisherName}`)
    return false
  }

  const nextLabel = String(label || '').trim()
  if (nextLabel === String(original.current_label || '').trim()) {
    return true
  }

  // 1. 立即乐观更新UI（零延迟）
  optimisticUpdateLabel(publisherName, nextLabel)

  // 2. 后台保存，不阻塞
  await saveLabelsInBackground([publisherName], nextLabel)
  return true
}

// 一键采纳所有建议
function acceptAllSuggestions() {
  const toUpdate = rawCandidates.value.filter((c) => c.suggested_label && !c.current_label)
  if (!toUpdate.length) return

  // 批量乐观更新
  toUpdate.forEach((c) => {
    c.current_label = c.suggested_label
  })
  mediaResult.value = { ...mediaResult.value }

  // 后台批量保存
  const updates = toUpdate.map((c) => ({
    publisher_name: c.publisher_name,
    current_label: c.suggested_label
  }))

  const range = normalizeRange({
    topic: viewSelection.topic || viewSelection.topic_identifier || mediaResult.value?.topic || runForm.topic,
    start: currentRange.value?.start || viewSelection.start,
    end: currentRange.value?.end || viewSelection.end
  })

  if (!range.topic || !range.start || !range.end) {
    console.warn('缺少专题或时间范围，无法保存')
    return
  }

  callApi('/api/media-tags/results/labels', {
    method: 'POST',
    body: JSON.stringify({
      topic: range.topic,
      start: range.start,
      end: range.end,
      updates
    })
  }).then((response) => {
    mediaResult.value = response
    loadRegistry().catch(() => {})
  }).catch((err) => {
    console.error('批量采纳保存失败:', err)
  })
}

async function applyLabelToFilteredCandidates(label) {
  const names = filteredCandidates.value.map((c) => c.publisher_name)
  if (!names.length) return
  await saveCandidateUpdates(names, label)
}

// ── 多选相关函数 ──────────────────────────────────────────────────────
function toggleSelectAll(checked) {
  if (checked) {
    filteredCandidates.value.forEach((c) => {
      selectedItems.value.add(candidateKey(c.publisher_name))
    })
  } else {
    selectedItems.value.clear()
  }
  selectedItems.value = new Set(selectedItems.value)
}

function toggleSelectItem(publisherName, checked) {
  const key = candidateKey(publisherName)
  if (checked) {
    selectedItems.value.add(key)
  } else {
    selectedItems.value.delete(key)
  }
  selectedItems.value = new Set(selectedItems.value)
}

async function applyLabelToSelected(label) {
  const selectedCandidates = filteredCandidates.value
    .filter((c) => selectedItems.value.has(candidateKey(c.publisher_name)))

  if (!selectedCandidates.length) return

  const names = selectedCandidates.map((c) => c.publisher_name)

  // 1. 批量乐观更新
  selectedCandidates.forEach((c) => {
    c.current_label = String(label || '').trim()
  })
  mediaResult.value = { ...mediaResult.value }

  // 2. 清除选择
  clearSelection()

  // 3. 后台保存
  await saveLabelsInBackground(names, label)
}

function clearSelection() {
  selectedItems.value.clear()
  selectedItems.value = new Set(selectedItems.value)
}

const isAllSelected = computed(() =>
  filteredCandidates.value.length > 0 &&
  filteredCandidates.value.every((c) => selectedItems.value.has(candidateKey(c.publisher_name)))
)

const selectedCount = computed(() => selectedItems.value.size)

const isAllRegistrySelected = computed(() =>
  filteredRegistryItems.value.length > 0 &&
  filteredRegistryItems.value.every((item) => selectedRegistryItems.value.has(item.id))
)

const selectedRegistryCount = computed(() => selectedRegistryItems.value.size)

async function saveCandidateUpdates(publisherNames = null, label = null) {
  const range = normalizeRange({
    topic: viewSelection.topic || viewSelection.topic_identifier || mediaResult.value?.topic || runForm.topic,
    start: currentRange.value?.start || viewSelection.start,
    end: currentRange.value?.end || viewSelection.end
  })
  if (!range.topic || !range.start || !range.end) {
    resultsState.saveError = '缺少专题或时间范围，暂时无法保存。'
    return false
  }

  // 直接保存：必须提供 publisherNames 和 label
  if (!Array.isArray(publisherNames) || publisherNames.length === 0) {
    resultsState.saveNotice = '当前没有需要保存的标签变更。'
    return true
  }

  const updates = publisherNames.map((name) => ({
    publisher_name: name,
    current_label: String(label || '').trim()
  }))

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
    resultsState.saveNotice =
      updates.length === 1 ? '标签已保存。' : `已保存 ${updates.length} 条媒体标签。`
    return true
  } catch (error) {
    resultsState.saveError = error instanceof Error ? error.message : '标签保存失败'
    return false
  } finally {
    resultsState.saving = false
  }
}

async function deleteCandidates(publisherNames) {
  const range = normalizeRange({
    topic: viewSelection.topic || viewSelection.topic_identifier || mediaResult.value?.topic || runForm.topic,
    start: currentRange.value?.start || viewSelection.start,
    end: currentRange.value?.end || viewSelection.end
  })
  if (!range.topic || !range.start || !range.end) {
    resultsState.saveError = '缺少专题或时间范围，暂时无法删除。'
    return false
  }

  if (!Array.isArray(publisherNames) || publisherNames.length === 0) {
    return true
  }

  resultsState.saving = true
  resultsState.saveError = ''
  resultsState.saveNotice = ''
  try {
    const response = await callApi('/api/media-tags/results/candidates', {
      method: 'DELETE',
      body: JSON.stringify({
        topic: range.topic,
        start: range.start,
        end: range.end,
        publisher_names: publisherNames
      })
    })
    mediaResult.value = response
    resultsState.saveNotice = `已删除 ${publisherNames.length} 条候选媒体。`
    return true
  } catch (error) {
    resultsState.saveError = error instanceof Error ? error.message : '删除失败'
    return false
  } finally {
    resultsState.saving = false
  }
}

async function deleteSelectedCandidates() {
  const names = filteredCandidates.value
    .filter((c) => selectedItems.value.has(candidateKey(c.publisher_name)))
    .map((c) => c.publisher_name)
  if (!names.length) return false
  const success = await deleteCandidates(names)
  if (success) {
    clearSelection()
  }
  return success
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

async function deleteRegistryItem(itemId) {
  const id = String(itemId || '').trim()
  if (!id) {
    resultsState.registryError = '缺少条目 ID。'
    return false
  }

  resultsState.registrySaving = true
  resultsState.registryError = ''
  resultsState.registryNotice = ''
  try {
    await callApi(`/api/media-tags/registry/${encodeURIComponent(id)}`, {
      method: 'DELETE'
    })
    await loadRegistry()
    resultsState.registryNotice = '字典条目已删除。'
    return true
  } catch (error) {
    resultsState.registryError = error instanceof Error ? error.message : '删除失败'
    return false
  } finally {
    resultsState.registrySaving = false
  }
}

// ── Registry 多选相关函数 ────────────────────────────────────────────────
function toggleSelectAllRegistry(checked) {
  if (checked) {
    filteredRegistryItems.value.forEach((item) => {
      selectedRegistryItems.value.add(item.id)
    })
  } else {
    selectedRegistryItems.value.clear()
  }
  selectedRegistryItems.value = new Set(selectedRegistryItems.value)
}

function toggleSelectRegistryItem(itemId, checked) {
  if (checked) {
    selectedRegistryItems.value.add(itemId)
  } else {
    selectedRegistryItems.value.delete(itemId)
  }
  selectedRegistryItems.value = new Set(selectedRegistryItems.value)
}

function clearRegistrySelection() {
  selectedRegistryItems.value.clear()
  selectedRegistryItems.value = new Set(selectedRegistryItems.value)
}

async function mergeRegistryItems({ canonicalId, canonicalName, mediaLevel, notes }) {
  const selectedIds = Array.from(selectedRegistryItems.value)
  if (selectedIds.length < 2) {
    resultsState.registryError = '请至少选择 2 条条目进行合并。'
    return null
  }

  // 收集所有选中条目的别名
  const allAliases = new Set()
  selectedIds.forEach((id) => {
    const item = registryItems.value.find((r) => r.id === id)
    if (item) {
      if (item.name !== canonicalName) {
        allAliases.add(item.name)
      }
      if (Array.isArray(item.aliases)) {
        item.aliases.forEach((a) => {
          if (a !== canonicalName) allAliases.add(a)
        })
      }
    }
  })

  resultsState.registrySaving = true
  resultsState.registryError = ''
  resultsState.registryNotice = ''

  try {
    // 更新主条目
    const mainItem = registryItems.value.find((r) => r.id === canonicalId)
    const updatedAliases = Array.from(allAliases)
    await callApi(`/api/media-tags/registry/${encodeURIComponent(canonicalId)}`, {
      method: 'PUT',
      body: JSON.stringify({
        id: canonicalId,
        name: canonicalName,
        aliases: updatedAliases,
        media_level: mediaLevel || mainItem?.media_level || '',
        status: 'active',
        notes: notes || mainItem?.notes || ''
      })
    })

    // 删除其他条目
    for (const id of selectedIds) {
      if (id !== canonicalId) {
        await callApi(`/api/media-tags/registry/${encodeURIComponent(id)}`, {
          method: 'DELETE'
        })
      }
    }

    await loadRegistry()
    clearRegistrySelection()
    resultsState.registryNotice = `已合并 ${selectedIds.length} 条条目到「${canonicalName}」。`
    return { name: canonicalName, aliases: updatedAliases }
  } catch (error) {
    resultsState.registryError = error instanceof Error ? error.message : '合并失败'
    return null
  } finally {
    resultsState.registrySaving = false
  }
}
