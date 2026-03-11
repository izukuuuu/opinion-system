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

const DEFAULT_BERTOPIC_RUN_PARAMS = Object.freeze({
  vectorizer: {
    ngram_min: 1,
    ngram_max: 2,
    min_df: 2,
    max_df: 0.8
  },
  umap: {
    n_neighbors: 15,
    n_components: 5,
    min_dist: 0.0,
    metric: 'cosine',
    random_state: 42
  },
  hdbscan: {
    min_cluster_size: 10,
    min_samples: 5,
    metric: 'euclidean',
    cluster_selection_method: 'eom'
  },
  bertopic: {
    top_n_words: 10,
    calculate_probabilities: false,
    verbose: true
  }
})

const createDefaultRunParams = () => JSON.parse(JSON.stringify(DEFAULT_BERTOPIC_RUN_PARAMS))

const form = reactive({
  topic: '',
  project: '',
  startDate: '',
  endDate: '',
  runParams: createDefaultRunParams()
})

const MIN_BERTOPIC_PROMPT_TOPICS = 3
const MAX_BERTOPIC_PROMPT_TOPICS = 50
const DEFAULT_BERTOPIC_PROMPT_TARGET_TOPICS = 8
const DEFAULT_DROP_RULE_PROMPT = `
【无关主题丢弃规则（必须执行）】
请先判断每个候选主题是否与专题“{FOCUS_TOPIC}”相关。

判定标准（满足任一可判为无关）：
1. 关键词与专题核心语义没有直接关联；
2. 主要讨论对象偏离专题目标（例如泛娱乐、泛生活、广告噪声）；
3. 无法给出与专题有因果或场景关联的解释。

输出要求（每个聚类条目都必须包含）：
- drop: true/false
- drop_reason: 当 drop=true 时，写明剔除原因；当 drop=false 时可为空字符串

注意：
- 被判定为无关的条目必须单独标记 drop=true，不要混入正常主题；
- 不要省略字段，不要输出额外解释文字。
`.trim()

const DEFAULT_GLOBAL_FILTERS = ['明星八卦', '广告推广', '抽奖转发', '求职招聘']
const DEFAULT_PROJECT_FILTERS = []

const normalizeFilterLabelList = (items, fallback = []) => {
  if (!Array.isArray(items)) {
    return JSON.parse(JSON.stringify(fallback))
  }
  const seen = new Set()
  const result = []
  items.forEach((item) => {
    const value = String(item || '').trim()
    if (!value || seen.has(value)) return
    seen.add(value)
    result.push(value)
  })
  return result
}

const normalizeProjectFilters = (items) => {
  if (!Array.isArray(items)) return []
  const result = []
  items.forEach((item) => {
    if (!item || typeof item !== 'object') return
    const category = String(item.category || '').trim()
    const description = String(item.description || '').trim()
    if (!category && !description) return
    result.push({ category, description })
  })
  return result
}

const bertopicPromptState = reactive({
  loading: false,
  saving: false,
  error: '',
  message: '',
  exists: false,
  path: '',
  maxTopics: DEFAULT_BERTOPIC_PROMPT_TARGET_TOPICS,
  dropRulePrompt: DEFAULT_DROP_RULE_PROMPT,
  defaultDropRulePrompt: DEFAULT_DROP_RULE_PROMPT,
  reclusterSystemPrompt: '',
  reclusterUserPrompt: '',
  keywordSystemPrompt: '',
  keywordUserPrompt: '',
  reclusterDimension: '',
  mustSeparateRules: [],
  mustMergeRules: [],
  coreDropRules: [],
  globalFilters: JSON.parse(JSON.stringify(DEFAULT_GLOBAL_FILTERS)),
  projectFilters: JSON.parse(JSON.stringify(DEFAULT_PROJECT_FILTERS))
})

const bertopicPromptBaseline = ref(null)

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

const clampPromptTopicCount = (value) => {
  const parsed = Number.parseInt(String(value ?? ''), 10)
  if (!Number.isFinite(parsed)) return DEFAULT_BERTOPIC_PROMPT_TARGET_TOPICS
  return Math.max(MIN_BERTOPIC_PROMPT_TOPICS, Math.min(MAX_BERTOPIC_PROMPT_TOPICS, parsed))
}

const hasPromptDraftChanges = computed(() => {
  const baseline = bertopicPromptBaseline.value
  if (!baseline) return false
  const current = capturePromptSnapshot()
  return JSON.stringify(current) !== JSON.stringify(baseline)
})

const capturePromptSnapshot = () => ({
  maxTopics: clampPromptTopicCount(bertopicPromptState.maxTopics),
  dropRulePrompt: String(bertopicPromptState.dropRulePrompt || '').trim(),
  reclusterSystemPrompt: String(bertopicPromptState.reclusterSystemPrompt || '').trim(),
  reclusterUserPrompt: String(bertopicPromptState.reclusterUserPrompt || '').trim(),
  keywordSystemPrompt: String(bertopicPromptState.keywordSystemPrompt || '').trim(),
  keywordUserPrompt: String(bertopicPromptState.keywordUserPrompt || '').trim(),
  reclusterDimension: String(bertopicPromptState.reclusterDimension || '').trim(),
  mustSeparateRules: JSON.parse(JSON.stringify(bertopicPromptState.mustSeparateRules || [])),
  mustMergeRules: JSON.parse(JSON.stringify(bertopicPromptState.mustMergeRules || [])),
  coreDropRules: JSON.parse(JSON.stringify(bertopicPromptState.coreDropRules || [])),
  globalFilters: JSON.parse(JSON.stringify(bertopicPromptState.globalFilters || [])),
  projectFilters: JSON.parse(JSON.stringify(bertopicPromptState.projectFilters || []))
})

const setPromptStateFromPayload = (payload) => {
  const data = payload || {}
  bertopicPromptState.exists = Boolean(data.exists)
  bertopicPromptState.path = data.path || ''
  bertopicPromptState.maxTopics = clampPromptTopicCount(
    data.max_topics ?? data.target_topics ?? data.maxTopics
  )
  bertopicPromptState.defaultDropRulePrompt = data.default_drop_rule_prompt || data.defaultDropRulePrompt || DEFAULT_DROP_RULE_PROMPT

  bertopicPromptState.dropRulePrompt = data.drop_rule_prompt || data.dropRulePrompt || bertopicPromptState.defaultDropRulePrompt
  bertopicPromptState.reclusterSystemPrompt = data.recluster_system_prompt || data.reclusterSystemPrompt || ''
  bertopicPromptState.reclusterUserPrompt = data.recluster_user_prompt || data.reclusterUserPrompt || ''

  bertopicPromptState.keywordSystemPrompt = data.keyword_system_prompt || data.keywordSystemPrompt || ''
  bertopicPromptState.keywordUserPrompt = data.keyword_user_prompt || data.keywordUserPrompt || ''

  bertopicPromptState.reclusterDimension = data.recluster_dimension || data.reclusterDimension || ''
  bertopicPromptState.mustSeparateRules = normalizeFilterLabelList(
    data.custom_topic_seed_rules ??
    data.customTopicSeedRules ??
    data.must_separate_rules ??
    data.mustSeparateRules
  )
  bertopicPromptState.mustMergeRules = normalizeFilterLabelList(
    data.must_merge_rules ?? data.mustMergeRules
  )
  bertopicPromptState.coreDropRules = normalizeFilterLabelList(
    data.core_drop_rules ?? data.coreDropRules
  )

  const resolvedGlobalFilters = data.global_filters ?? data.globalFilters
  bertopicPromptState.globalFilters = normalizeFilterLabelList(
    resolvedGlobalFilters,
    DEFAULT_GLOBAL_FILTERS
  )

  const resolvedProjectFilters =
    data.project_filters ??
    data.projectFilters ??
    data.custom_filters ??
    data.customFilters
  bertopicPromptState.projectFilters = normalizeProjectFilters(resolvedProjectFilters)
  bertopicPromptBaseline.value = capturePromptSnapshot()
}

const clearPromptState = () => {
  bertopicPromptState.exists = false
  bertopicPromptState.path = ''
  bertopicPromptState.maxTopics = DEFAULT_BERTOPIC_PROMPT_TARGET_TOPICS
  bertopicPromptState.dropRulePrompt = DEFAULT_DROP_RULE_PROMPT
  bertopicPromptState.defaultDropRulePrompt = DEFAULT_DROP_RULE_PROMPT
  bertopicPromptState.reclusterSystemPrompt = ''
  bertopicPromptState.reclusterUserPrompt = ''
  bertopicPromptState.keywordSystemPrompt = ''
  bertopicPromptState.keywordUserPrompt = ''
  bertopicPromptState.reclusterDimension = ''
  bertopicPromptState.mustSeparateRules = []
  bertopicPromptState.mustMergeRules = []
  bertopicPromptState.coreDropRules = []
  bertopicPromptState.globalFilters = JSON.parse(JSON.stringify(DEFAULT_GLOBAL_FILTERS))
  bertopicPromptState.projectFilters = JSON.parse(JSON.stringify(DEFAULT_PROJECT_FILTERS))
  bertopicPromptState.error = ''
  bertopicPromptState.message = ''
  bertopicPromptState.loading = false
  bertopicPromptState.saving = false
  bertopicPromptBaseline.value = null
}

const sanitizeRunParamsForPayload = (params = {}) => {
  const source = params || {}
  const vectorizer = source.vectorizer || {}
  const umap = source.umap || {}
  const hdbscan = source.hdbscan || {}
  const bertopic = source.bertopic || {}

  return {
    vectorizer: {
      ngram_min: Number.parseInt(String(vectorizer.ngram_min ?? 1), 10),
      ngram_max: Number.parseInt(String(vectorizer.ngram_max ?? 2), 10),
      min_df: Number(vectorizer.min_df ?? 2),
      max_df: Number(vectorizer.max_df ?? 0.8)
    },
    umap: {
      n_neighbors: Number.parseInt(String(umap.n_neighbors ?? 15), 10),
      n_components: Number.parseInt(String(umap.n_components ?? 5), 10),
      min_dist: Number(umap.min_dist ?? 0),
      metric: String(umap.metric || 'cosine').trim() || 'cosine',
      random_state: Number.parseInt(String(umap.random_state ?? 42), 10)
    },
    hdbscan: {
      min_cluster_size: Number.parseInt(String(hdbscan.min_cluster_size ?? 10), 10),
      min_samples: Number.parseInt(String(hdbscan.min_samples ?? 5), 10),
      metric: String(hdbscan.metric || 'euclidean').trim() || 'euclidean',
      cluster_selection_method: String(hdbscan.cluster_selection_method || 'eom').trim() || 'eom'
    },
    bertopic: {
      top_n_words: Number.parseInt(String(bertopic.top_n_words ?? 10), 10),
      calculate_probabilities: Boolean(bertopic.calculate_probabilities),
      verbose: Boolean(bertopic.verbose)
    }
  }
}

export const useTopicBertopicAnalysis = () => {
  if (!initialized) {
    initialized = true
    initializeStore()
  }

  return {
    topicsState,
    topicOptions,
    form,
    bertopicPromptState,
    hasPromptDraftChanges,
    availableRange,
    runState,
    lastResult,
    lastPayload,
    logs,
    historyState,
    analysisHistory,
    loadTopics,
    loadBertopicPrompt,
    saveBertopicPrompt,
    loadAvailableRange,
    resetState,
    runBertopicAnalysis,
    resetForm,
    resetRunParams,
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
        loadBertopicPrompt(newTopic)
      } else {
        clearAvailableRange()
        clearPromptState()
      }
    },
    { immediate: true }
  )

  watch(
    () => form.project,
    () => {
      if (!form.topic) return
      loadAvailableRange()
      loadBertopicPrompt(form.topic)
    }
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
      const response = await callApi(`/api/topic/bertopic/topics${queryParams}`, {
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
  availableRange.start = ''
  availableRange.end = ''

  try {
    // 使用基础分析相同的API检查数据可用性
    const params = new URLSearchParams({ topic: form.topic })
    const project = (form.project || '').trim()
    if (project) {
      params.set('project', project)
    }
    const response = await callApi(`/api/fetch/availability?${params.toString()}`, { method: 'GET' })

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
      const fallbackParams = new URLSearchParams({ topic: form.topic })
      const project = (form.project || '').trim()
      if (project) {
        fallbackParams.set('project', project)
      }
      const response = await callApi(
        `/api/topic/bertopic/availability?${fallbackParams.toString()}`,
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

const loadBertopicPrompt = async (topicOverride = '') => {
  const topic = (topicOverride || form.topic || '').trim()
  if (!topic) {
    clearPromptState()
    return
  }

  bertopicPromptState.loading = true
  bertopicPromptState.error = ''
  bertopicPromptState.message = ''

  try {
    const params = new URLSearchParams({ topic })
    const project = (form.project || '').trim()
    if (project) {
      params.set('project', project)
    }
    const response = await callApi(`/api/topic/bertopic/prompt?${params.toString()}`, { method: 'GET' })
    const data = response?.data || {}
    setPromptStateFromPayload(data)
  } catch (error) {
    bertopicPromptState.error = error instanceof Error ? error.message : '加载 BERTopic 提示词失败'
  } finally {
    bertopicPromptState.loading = false
  }
}

const saveBertopicPrompt = async (options = {}) => {
  const topic = (options.topic || form.topic || '').trim()
  if (!topic) {
    bertopicPromptState.error = '请先选择专题再保存提示词'
    return null
  }

  const snapshot = capturePromptSnapshot()

  bertopicPromptState.saving = true
  bertopicPromptState.error = ''
  bertopicPromptState.message = ''

  try {
    const response = await callApi('/api/topic/bertopic/prompt', {
      method: 'POST',
      body: JSON.stringify({
        topic,
        project: form.project || undefined,
        target_topics: snapshot.maxTopics,
        max_topics: snapshot.maxTopics,
        drop_rule_prompt: snapshot.dropRulePrompt,
        recluster_system_prompt: snapshot.reclusterSystemPrompt,
        recluster_user_prompt: snapshot.reclusterUserPrompt,
        keyword_system_prompt: snapshot.keywordSystemPrompt,
        keyword_user_prompt: snapshot.keywordUserPrompt,
        recluster_dimension: snapshot.reclusterDimension,
        custom_topic_seed_rules: snapshot.mustSeparateRules,
        must_separate_rules: snapshot.mustSeparateRules,
        must_merge_rules: snapshot.mustMergeRules,
        core_drop_rules: snapshot.coreDropRules,
        global_filters: snapshot.globalFilters,
        project_filters: snapshot.projectFilters
      })
    })

    const data = response?.data || {}
    setPromptStateFromPayload(data)
    bertopicPromptState.message = 'BERTopic 提示词已保存'
    return data
  } catch (error) {
    bertopicPromptState.error = error instanceof Error ? error.message : '保存 BERTopic 提示词失败'
    throw error
  } finally {
    bertopicPromptState.saving = false
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
}

const resetRunParams = () => {
  form.runParams = createDefaultRunParams()
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
    // 先拉取远程数据到本地缓存（与基础分析一致）
    const fetchLogId = appendLog({
      label: '数据准备',
      message: `拉取远程数据 ${form.topic} ${form.startDate} → ${form.endDate || form.startDate}`,
      status: 'running'
    })
    try {
      const fetchResponse = await callApi('/api/fetch', {
        method: 'POST',
        body: JSON.stringify({
          topic: form.topic,
          project: form.project || undefined,
          start: form.startDate,
          end: form.endDate || form.startDate
        })
      })
      updateLog(fetchLogId, {
        status: 'ok',
        message: '数据拉取完成，可开始主题分析'
      })

      // 自动优化参数逻辑
      try {
        const fetchedCount = fetchResponse.data?.count || 0
        if (fetchedCount >= 2000) {
          const currentMinCluster = parseInt(form.runParams.hdbscan.min_cluster_size)
          // 仅在当前设置较小（默认值附近）时触发自动调整
          if (currentMinCluster <= 20) {
            let suggested = 0
            if (fetchedCount < 20000) {
              suggested = Math.floor(fetchedCount / 250)
            } else if (fetchedCount < 100000) {
              suggested = Math.max(24, Math.floor(fetchedCount / 3000) + 16)
            } else {
              suggested = Math.max(36, Math.floor(fetchedCount / 10000) + 28)
            }
            suggested = Math.max(suggested, currentMinCluster, 10)
            suggested = Math.min(suggested, 60)

            if (suggested > currentMinCluster) {
              form.runParams.hdbscan.min_cluster_size = suggested
              appendLog({
                label: '参数优化',
                message: `检测到数据量(${fetchedCount}条)较大，已自动调整最小聚类规模: ${currentMinCluster} -> ${suggested}`,
                status: 'info'
              })
            }
          }
        }
      } catch (optError) {
        console.warn('Parameter optimization failed:', optError)
      }

    } catch (fetchError) {
      updateLog(fetchLogId, {
        status: 'error',
        message: fetchError instanceof Error ? fetchError.message : String(fetchError)
      })
      updateLog(logId, {
        status: 'error',
        message: '数据拉取失败，已终止分析'
      })
      return
    }

    // 构建请求参数
    const payload = {
      topic: form.topic,
      project: form.project || undefined,
      start_date: form.startDate,
      end_date: form.endDate || undefined,
      run_params: sanitizeRunParamsForPayload(form.runParams)
    }

    lastPayload.value = payload

    updateLog(logId, {
      status: 'running',
      message: `正在分析 ${form.topic} (${form.startDate} ~ ${form.endDate || form.startDate})...`
    })

    // 调用API
    const response = await callApi('/api/topic/bertopic/run', {
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
