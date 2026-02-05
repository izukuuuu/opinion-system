import { computed, reactive, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'

const { callApi } = useApiBase()

// 状态管理
const topicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const topicOptions = computed(() => topicsState.options)

const viewSelection = reactive({
  topic: '',
  project: '',
  start: '',
  end: ''
})

const viewManualForm = reactive({
  topic: '',
  start: '',
  end: ''
})

const loadState = reactive({
  loading: false,
  error: ''
})

const analysisData = ref(null)
const lastLoaded = ref('')

// 分析历史
const historyState = reactive({
  loading: false,
  error: '',
  topic: ''
})

const analysisHistory = ref([])
const selectedHistoryId = ref('')

// 历史记录列表
const selectableTopicOptions = computed(() =>
  Array.isArray(topicOptions.value) ? topicOptions.value.slice() : []
)

const selectedRecord = computed(() => {
  return analysisHistory.value.find((item) => item.id === selectedHistoryId.value)
})

// 可用的时间范围
const availableRange = reactive({
  loading: false,
  error: '',
  start: '',
  end: ''
})

// BERTopic特有的数据
const bertopicData = ref(null)
const hasResults = computed(() => Boolean(bertopicData.value))

// 文件映射
const FILE_MAP = {
  summary: "1主题统计结果",
  keywords: "2主题关键词",
  coords: "3文档2D坐标",
  llm_clusters: "4大模型再聚类结果",
  llm_keywords: "5大模型主题关键词"
}

// BERTopic特有的统计
const bertopicStats = computed(() => {
  if (!bertopicData.value || !bertopicData.value.files) return null

  const files = bertopicData.value.files

  // 从summary文件获取原始主题统计
  const summaryFile = files.summary || {}
  const topicStats = summaryFile['主题文档统计'] || {}

  const originalTopics = Object.entries(topicStats).map(([name, info]) => ({
    name: name,
    docCount: info['文档数'] || 0
  }))

  // 从llm_clusters获取LLM聚类统计
  const llmClusters = files.llm_clusters || []
  const llmTopics = Array.isArray(llmClusters) ? llmClusters : Object.values(llmClusters)

  const llmStats = llmTopics.length > 0 ? {
    totalTopics: llmTopics.length,
    totalDocs: llmTopics.reduce((sum, item) => sum + (item['文档数'] || 0), 0),
    maxDocs: Math.max(...llmTopics.map(item => item['文档数'] || 0))
  } : null

  return {
    originalTopics,
    originalStats: {
      count: originalTopics.length,
      totalDocs: originalTopics.reduce((sum, item) => sum + item.docCount, 0),
      maxDocs: originalTopics.length > 0 ? Math.max(...originalTopics.map(t => t.docCount)) : 0
    },
    llmStats,
    hasLLMClusters: llmTopics.length > 0
  }
})

// 加载专题列表
const loadTopics = async (onlyWithData = false) => {
  topicsState.loading = true
  topicsState.error = ''

  try {
    // 首先尝试从远程数据库获取专题列表（像基础分析一样）
    let topics = []
    try {
      const response = await callApi('/api/query', {
        method: 'POST',
        body: JSON.stringify({ include_counts: false })
      })
      const databases = response?.data?.databases ?? []
      topics = databases
        .map((db) => ({
          bucket: db.name,
          name: db.name,
          display_name: db.display_name || db.name,
          source: 'database'
        }))
        .filter((topic) => topic.name && topic.name.trim())
    } catch (dbError) {
      console.warn('Failed to load topics from remote database:', dbError)
      // 如果远程数据库调用失败，回退到BERTopic专用API
      const queryParams = onlyWithData ? '?only_with_data=true' : ''
      const response = await callApi(`/api/topic/bertopic/topics${queryParams}`, {
        method: 'GET'
      })
      topics = response?.data?.topics || response?.topics || []
    }

    // 标准化专题格式
    topicsState.options = topics.map(t => ({
      ...t,
      bucket: t.bucket || t.name,
      name: t.name || t.display_name || t.bucket,
      display_name: t.display_name || t.name || t.bucket
    }))
  } catch (error) {
    topicsState.error = error instanceof Error ? error.message : '加载专题列表失败'
    topicsState.options = []
  } finally {
    topicsState.loading = false
  }
}

// 加载分析历史
const loadHistory = async (topic, projectOverride = '') => {
  historyState.loading = true
  historyState.error = ''

  const trimmed = (topic || '').trim()
  if (!trimmed) {
    analysisHistory.value = []
    historyState.topic = ''
    return
  }

  historyState.topic = trimmed
  const project = (projectOverride || viewSelection.project || '').trim()
  const archiveTopic = project || trimmed

  try {
    // 先从analyze API获取历史
    const params = new URLSearchParams({ topic: trimmed })
    if (project) {
      params.set('project', project)
    }
    const response = await callApi(`/api/analyze/history?${params.toString()}`, {
      method: 'GET'
    })

    if (response?.records?.length) {
      analysisHistory.value = response.records
      historyState.topic = trimmed
      return
    }

    // 如果没有，从archives获取
    const encodedTopic = encodeURIComponent(archiveTopic)
    const archiveResponse = await callApi(`/api/projects/${encodedTopic}/archives?layers=analyze`, {
      method: 'GET'
    })

    const entries = archiveResponse?.archives?.analyze || []
    analysisHistory.value = entries
    historyState.topic = trimmed

    if (!entries.length) {
      historyState.error = '当前专题暂无分析存档'
    }
  } catch (primaryError) {
    try {
      // 降级到archives
      const encodedTopic = encodeURIComponent(archiveTopic)
      const archiveResponse = await callApi(`/api/projects/${encodedTopic}/archives?layers=analyze`, {
        method: 'GET'
      })

      const entries = archiveResponse?.archives?.analyze || []
      analysisHistory.value = entries
      historyState.topic = trimmed

      if (!entries.length) {
        historyState.error = '当前专题暂无分析存档'
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

// 加载结果数据
const loadResults = async (range) => {
  const targetRange = range ? range : viewSelection
  const { topic, start, end } = targetRange
  const project = (targetRange?.project || viewSelection.project || '').trim()

  if (!topic || !start) {
    loadState.error = '请选择专题和时间范围'
    return
  }

  viewSelection.topic = topic
  viewSelection.start = start
  viewSelection.end = end
  loadState.loading = true

  try {
    const params = new URLSearchParams({ topic, start })
    if (project) {
      params.set('project', project)
    }
    if (end) params.set('end', end)

    const response = await callApi(`/api/topic/bertopic/results?${params.toString()}`, {
      method: 'GET'
    })

    // 处理响应数据
    if (response?.status === 'error') {
      loadState.error = response?.message || '加载结果失败'
      bertopicData.value = null
      return
    }

    bertopicData.value = response?.data || response

    if (bertopicData.value?.topic && bertopicData.value.range) {
      lastLoaded.value = new Date().toLocaleString()
      viewManualForm.topic = bertopicData.value.topic
      viewManualForm.start = bertopicData.value.range.start || start
      viewManualForm.end = bertopicData.value.range.end || end
    }
  } catch (error) {
    loadState.error = error instanceof Error ? error.message : String(error)
    bertopicData.value = null
  } finally {
    loadState.loading = false
  }
}

// 从历史记录加载数据
const applyHistorySelection = async (recordId, { shouldLoad = false } = {}) => {
  const entry = analysisHistory.value.find((item) => item.id === recordId)
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

// 手动输入查询
const loadResultsFromManual = async () => {
  const manualRange = {
    topic:
      viewManualForm.topic ||
      viewSelection.topic ||
      topicOptions.value[0] ||
      '',
    start: viewManualForm.start,
    end: viewManualForm.end,
    project: viewSelection.project
  }

  const range = manualRange
  if (!range.topic || !range.start) {
    loadState.error = '请填写专题和开始日期'
    return
  }

  selectedHistoryId.value = ''
  await loadResults(range)
}

const refreshHistory = async () => {
  if (historyState.loading || loadState.loading) return
  const topic = (viewSelection.topic || '').trim()
  if (!topic) return

  await loadHistory(topic)
  if (selectedHistoryId.value) {
    await applyHistorySelection(selectedHistoryId.value, { shouldLoad: true })
  }
}

// 格式化时间戳
const formatTimestamp = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

let initialized = false

function initializeStore() {
  loadTopics()

  // 监听活动项目变化
  watch(
    () => viewSelection.topic,
    (topic) => {
      if (topic) {
        loadHistory(topic, viewSelection.project)
      }
    }
  )
}

export const useTopicBertopicView = () => {
  if (!initialized) {
    initialized = true
    initializeStore()
  }

  return {
    topicsState,
    topicOptions,
    selectableTopicOptions,
    viewSelection,
    viewManualForm,
    loadState,
    analysisData,
    bertopicData,
    hasResults,
    historyState,
    analysisHistory,
    selectedHistoryId,
    selectedRecord,
    availableRange,
    bertopicStats,
    lastLoaded,
    loadTopics,
    loadHistory,
    loadResults,
    loadResultsFromManual,
    refreshHistory,
    applyHistorySelection,
    formatTimestamp
  }
}
