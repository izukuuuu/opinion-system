import { computed, reactive, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'

const { callApi } = useApiBase()

// BERTopic分析的状态管理
const topicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const topicOptions = computed(() => topicsState.options)

const form = reactive({
  topic: '',
  startDate: '',
  endDate: '',
  fetchDir: '',
  userdict: '',
  stopwords: ''
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

const lastResult = ref(null)
const lastPayload = ref(null)

const logs = ref([])

// 分析历史（可选功能）
const historyState = reactive({
  loading: false,
  error: '',
  topic: ''
})

const analysisHistory = ref([])

let initialized = false

export const useTopicBertopicAnalysis = () => {
  if (!initialized) {
    initialized = true
    initializeStore()
  }

  return {
    topicsState,
    topicOptions,
    form,
    availableRange,
    runState,
    lastResult,
    lastPayload,
    logs,
    historyState,
    analysisHistory,
    loadTopics,
    loadAvailableRange,
    resetState,
    runBertopicAnalysis,
    resetForm,
    resetOptionalFields,
    appendLog,
    clearLogs
  }
}

function initializeStore() {
  loadTopics()

  // 监听专题变化，自动加载可用日期范围
  watch(
    () => form.topic,
    (newTopic) => {
      if (newTopic) {
        loadAvailableRange()
      } else {
        clearAvailableRange()
      }
    },
    { immediate: true }
  )
}

const clearAvailableRange = () => {
  availableRange.start = ''
  availableRange.end = ''
  availableRange.error = ''
  availableRange.loading = false
}

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
      const response = await callApi(`/api/analysis/topic/bertopic/topics${queryParams}`, {
        method: 'GET'
      })
      topics = response?.data?.topics || []
    }

    // 标准化专题格式
    topicsState.options = topics.map(t => ({
      ...t,
      bucket: t.bucket || t.name,
      name: t.name || t.display_name || t.bucket,
      display_name: t.display_name || t.name || t.bucket
    }))

    // 如果没有选中的专题，自动选择第一个
    if (!form.topic && topicsState.options.length > 0) {
      form.topic = topicsState.options[0].bucket
    }
  } catch (error) {
    topicsState.error = error instanceof Error ? error.message : '加载专题列表失败'
    topicsState.options = []
  } finally {
    topicsState.loading = false
  }
}

const loadAvailableRange = async () => {
  if (!form.topic) {
    clearAvailableRange()
    return
  }

  availableRange.loading = true
  availableRange.error = ''
  clearAvailableRange()

  try {
    // 使用基础分析相同的API检查数据可用性
    const response = await callApi(
      `/api/fetch/availability?topic=${encodeURIComponent(form.topic)}`,
      { method: 'GET' }
    )

    const data = response?.data
    if (data && data.range) {
      availableRange.start = data.range.start || ''
      availableRange.end = data.range.end || ''

      // 自动填充日期范围
      if (availableRange.start) {
        form.startDate = availableRange.start
        form.endDate = availableRange.end
      }
    }
  } catch (error) {
    // 如果基础API失败，尝试使用BERTopic专用的API
    try {
      const response = await callApi(
        `/api/analysis/topic/bertopic/availability?topic=${encodeURIComponent(form.topic)}`,
        { method: 'GET' }
      )

      const data = response?.data
      if (data) {
        availableRange.start = data.database_range?.start || ''
        availableRange.end = data.database_range?.end || ''

        // 如果本地有缓存，显示缓存信息
        if (data.has_cache && data.local_caches?.length > 0) {
          appendLog({
            label: '缓存',
            message: `发现 ${data.local_caches.length} 个本地缓存`,
            status: 'info'
          })
        }

        // 自动填充日期范围（使用最近的一个缓存或数据库范围）
        if (data.local_caches?.length > 0) {
          const latest = data.local_caches[0]
          form.startDate = latest.start
          form.endDate = latest.end === latest.start ? '' : latest.end
        } else if (availableRange.start) {
          form.startDate = availableRange.start
          form.endDate = availableRange.end
        }
      }
    } catch (fallbackError) {
      availableRange.error = fallbackError instanceof Error ? fallbackError.message : '获取数据范围失败'
    }
  } finally {
    availableRange.loading = false
  }
}

const resetState = () => {
  lastResult.value = null
  lastPayload.value = null
  runState.running = false
  clearLogs()
}

const resetForm = () => {
  form.endDate = ''
  form.fetchDir = ''
  form.userdict = ''
  form.stopwords = ''
}

const resetOptionalFields = () => {
  form.fetchDir = ''
  form.userdict = ''
  form.stopwords = ''
}

const currentTimeString = () => new Date().toLocaleTimeString()

const appendLog = (payload) => {
  const entry = {
    id: payload.id || `${payload.label || 'log'}-${Date.now()}`,
    time: payload.time || currentTimeString(),
    status: payload.status || 'pending',
    ...payload
  }
  logs.value = [entry, ...logs.value].slice(0, 20)
  return entry.id
}

const clearLogs = () => {
  logs.value = []
}

const runBertopicAnalysis = async (params) => {
  // 更新表单
  Object.assign(form, params)

  // 验证参数
  if (!form.topic || !form.startDate) {
    appendLog({
      label: '参数验证',
      message: '请填写专题名称和开始日期',
      status: 'error'
    })
    return
  }

  // 检查日期范围是否在可用范围内
  if (availableRange.start && availableRange.end) {
    const reqStart = new Date(form.startDate)
    const reqEnd = new Date(form.endDate || form.startDate)
    const availStart = new Date(availableRange.start)
    const availEnd = new Date(availableRange.end)

    if (reqStart < availStart || reqEnd > availEnd) {
      appendLog({
        label: '数据范围',
        message: `请求日期超出可用范围 ${availableRange.start} ~ ${availableRange.end}`,
        status: 'error'
      })
      return
    }
  }

  runState.running = true

  const logId = appendLog({
    label: 'BERTopic分析',
    message: '准备执行主题分析...',
    status: 'running'
  })

  try {
    // 构建请求参数
    const payload = {
      topic: form.topic,
      start_date: form.startDate,
      end_date: form.endDate || undefined,
      fetch_dir: form.fetchDir || undefined,
      userdict: form.userdict || undefined,
      stopwords: form.stopwords || undefined
    }

    lastPayload.value = payload

    updateLog(logId, {
      status: 'running',
      message: `正在分析 ${form.topic} (${form.startDate} ~ ${form.endDate || form.startDate})...`
    })

    // 调用API
    const response = await callApi('/api/analysis/topic/bertopic/run', {
      method: 'POST',
      body: JSON.stringify(payload)
    })

    if (response.status === 'ok') {
      updateLog(logId, {
        status: 'ok',
        message: 'BERTopic分析完成'
      })

      lastResult.value = response

      // 加载分析历史
      if (form.topic) {
        loadHistory()
      }

      return response
    } else {
      throw new Error(response.message || '分析失败')
    }
  } catch (error) {
    updateLog(logId, {
      status: 'error',
      message: error instanceof Error ? error.message : String(error)
    })
    throw error
  } finally {
    runState.running = false
  }
}

const updateLog = (logId, updates) => {
  const index = logs.value.findIndex(log => log.id === logId)
  if (index !== -1) {
    logs.value[index] = {
      ...logs.value[index],
      ...updates,
      time: updates.time || currentTimeString()
    }
  }
}

// 加载分析历史（可选）
const loadHistory = async () => {
  historyState.loading = true
  historyState.error = ''

  try {
    // 这里可以扩展实现历史记录功能
    // 暂时留空
  } catch (error) {
    historyState.error = error instanceof Error ? error.message : '加载历史记录失败'
  } finally {
    historyState.loading = false
  }
}