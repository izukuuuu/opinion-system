import { reactive, ref, computed, watch } from 'vue'
import { useApiBase } from './useApiBase'
import { useActiveProject } from './useActiveProject'

const { callApi } = useApiBase()
const { activeProjectName } = useActiveProject()

// RAG Topics State (mirrors useBasicAnalysis topicsState)
const ragTopicsState = reactive({
  loading: false,
  error: '',
  options: [],  // union of all topics
  tagrag: [],
  router: []
})

const ragTopicOptions = computed(() => ragTopicsState.options)
const tagragTopicOptions = computed(() => ragTopicsState.tagrag)
const routerTopicOptions = computed(() => ragTopicsState.router)

const remoteTopicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const remoteTopicOptions = computed(() => remoteTopicsState.options)

// Search form (mirrors analyzeForm)
const ragSearchForm = reactive({
  topic: '',
  query: '',
  rag_type: 'routerrag',  // Add rag_type field
  top_k: 10,
  threshold: 0.0
})

// Retrieval State
const ragRetrievalState = reactive({
  loading: false,
  error: '',
  results: [],
  total: 0,
  summary: ''
})

const ragBuildState = reactive({
  loading: false,
  error: '',
  status: '',
  percent: 0,
  message: ''
})

const ragBuildForm = reactive({
  topic: ''
})

const ragCacheState = reactive({
  visible: false,
  running: false,
  percent: 0,
  message: '',
  topic: '',
  type: ''
})

let ragCacheTimer = null
let ragCacheHideTimer = null
let ragCacheRefreshQueued = false

const stopRagCachePolling = () => {
  if (ragCacheTimer) {
    clearInterval(ragCacheTimer)
    ragCacheTimer = null
  }
}

const scheduleHideCacheToast = () => {
  if (ragCacheHideTimer) {
    clearTimeout(ragCacheHideTimer)
  }
  ragCacheHideTimer = setTimeout(() => {
    ragCacheState.visible = false
  }, 4000)
}

const updateCacheState = (payload = {}) => {
  ragCacheState.percent = Number(payload.percent || payload.percentage || 0)
  ragCacheState.message = payload.message || ''
  ragCacheState.running = payload.status === 'running'
  if (payload.topic) ragCacheState.topic = payload.topic
  if (payload.type) ragCacheState.type = payload.type

  if (ragCacheState.running) {
    ragCacheState.visible = true
    if (ragCacheHideTimer) clearTimeout(ragCacheHideTimer)
  } else if (payload.status === 'done' || payload.status === 'error') {
    ragCacheState.visible = true
    scheduleHideCacheToast()
  }
}

const pollRagCacheStatus = async (type, topic) => {
  stopRagCachePolling()
  if (!activeProjectName.value || !topic) return

  const params = new URLSearchParams({
    project: activeProjectName.value,
    type,
    topic
  })

  const fetchStatus = async () => {
    const response = await callApi(`/api/rag/cache/status?${params.toString()}`, { method: 'GET' })
    const status = response?.data || {}
    if (status.status === 'idle') {
      stopRagCachePolling()
      ragCacheState.visible = false
      return
    }
    updateCacheState({ ...status, type, topic })
    if (status.status === 'done' || status.status === 'error') {
      stopRagCachePolling()
      if (status.status === 'done' && !ragCacheRefreshQueued) {
        ragCacheRefreshQueued = true
        setTimeout(async () => {
          await loadRAGTopics()
          ragCacheRefreshQueued = false
        }, 600)
      }
    }
  }

  await fetchStatus()
  ragCacheTimer = setInterval(fetchStatus, 2000)
}

// Functions
const loadRAGTopics = async () => {
  ragTopicsState.loading = true
  ragTopicsState.error = ''

  try {
    const params = new URLSearchParams()
    if (activeProjectName.value) {
      params.set('project', activeProjectName.value)
    }
    const url = params.toString() ? `/api/rag/topics?${params.toString()}` : '/api/rag/topics'
    const response = await callApi(url, { method: 'GET' })

    const tagragTopics = response?.data?.tagrag_topics || []
    const routerTopics = response?.data?.router_topics || []
    ragTopicsState.tagrag = tagragTopics
      .map((item) => String(item || '').trim())
      .filter((name, index, arr) => name && arr.indexOf(name) === index)
    ragTopicsState.router = routerTopics
      .map((item) => String(item || '').trim())
      .filter((name, index, arr) => name && arr.indexOf(name) === index)
    ragTopicsState.options = [...ragTopicsState.tagrag, ...ragTopicsState.router]
      .filter((name, index, arr) => name && arr.indexOf(name) === index)

    if (ragSearchForm.topic && !ragTopicsState.options.includes(ragSearchForm.topic)) {
      ragSearchForm.topic = ''
    }


    return response
  } catch (error) {
    ragTopicsState.error = error.message || '加载RAG专题列表失败'
    throw error
  } finally {
    ragTopicsState.loading = false
  }
}

const loadRemoteTopics = async () => {
  remoteTopicsState.loading = true
  remoteTopicsState.error = ''

  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: false })
    })
    const databases = response?.data?.databases ?? []
    remoteTopicsState.options = databases
      .map((db) => String(db?.name || '').trim())
      .filter((name, index, arr) => name && arr.indexOf(name) === index)
    if (!remoteTopicsState.options.includes(ragBuildForm.topic)) {
      ragBuildForm.topic = remoteTopicsState.options[0] || ''
    }
    return response
  } catch (error) {
    remoteTopicsState.error = error.message || '加载远程专题失败'
    remoteTopicsState.options = []
    ragBuildForm.topic = ''
    throw error
  } finally {
    remoteTopicsState.loading = false
  }
}

const buildRagTopic = async (params = {}) => {
  ragBuildState.loading = true
  ragBuildState.error = ''
  const buildTopic = params.topic || ragBuildForm.topic
  const buildType = params.type || 'tagrag'

  if (!buildTopic) {
    ragBuildState.loading = false
    ragBuildState.error = '请选择要生成的专题'
    return null
  }
  if (!activeProjectName.value) {
    ragBuildState.loading = false
    ragBuildState.error = '请先在左侧选择项目'
    return null
  }

  try {
    const response = await callApi('/api/rag/build', {
      method: 'POST',
      body: JSON.stringify({
        topic: buildTopic,
        project: activeProjectName.value,
        type: buildType
      })
    })
    const status = response?.data || {}
    ragBuildState.status = status.status || ''
    ragBuildState.percent = Number(status.percent || 0)
    ragBuildState.message = status.message || ''
    updateCacheState({ ...status, type: buildType, topic: buildTopic })
    await pollRagCacheStatus(buildType, buildTopic)
    return response
  } catch (error) {
    ragBuildState.error = error.message || '准备检索专题失败'
    throw error
  } finally {
    ragBuildState.loading = false
  }
}

const retrieveTagRAG = async (params = {}) => {
  ragRetrievalState.loading = true
  ragRetrievalState.error = ''
  ragRetrievalState.results = []
  ragRetrievalState.total = 0

  try {
    const response = await callApi('/api/rag/tagrag/retrieve', {
      method: 'POST',
      body: JSON.stringify({
        query: params.query || ragSearchForm.query,
        topic: params.topic || ragSearchForm.topic,
        project: params.project || activeProjectName.value || undefined,
        top_k: params.top_k || ragSearchForm.top_k,
        threshold: params.threshold || ragSearchForm.threshold
      })
    })

    ragRetrievalState.results = response?.data?.results || []
    ragRetrievalState.total = response?.data?.total || 0
    ragRetrievalState.summary = response?.data?.summary || ''

    if (response?.status === 'building') {
      ragRetrievalState.error = response?.message || '正在准备检索资料，请稍后再试'
      updateCacheState({ ...response.data, type: 'tagrag', topic: params.topic || ragSearchForm.topic })
      await pollRagCacheStatus('tagrag', params.topic || ragSearchForm.topic)
    }

    return response
  } catch (error) {
    ragRetrievalState.error = error.message || 'TagRAG检索失败'
    throw error
  } finally {
    ragRetrievalState.loading = false
  }
}

const retrieveRouterRAG = async (params = {}) => {
  ragRetrievalState.loading = true
  ragRetrievalState.error = ''
  ragRetrievalState.results = []
  ragRetrievalState.total = 0

  try {
    const response = await callApi('/api/rag/routerrag/retrieve', {
      method: 'POST',
      body: JSON.stringify({
        query: params.query || ragSearchForm.query,
        topic: params.topic || ragSearchForm.topic,
        mode: params.mode || (() => {
          const type = ragSearchForm.rag_type
          if (type === 'routerrag') return 'normalrag'
          if (type === 'hybrid') return 'mixed'
          return type
        })(),
        project: params.project || activeProjectName.value || undefined,
        top_k: params.top_k || ragSearchForm.top_k,
        threshold: params.threshold || ragSearchForm.threshold
      })
    })

    ragRetrievalState.results = response?.data?.results || []
    ragRetrievalState.total = response?.data?.total || 0
    ragRetrievalState.summary = response?.data?.summary || ''

    if (response?.status === 'building') {
      ragRetrievalState.error = response?.message || '正在准备检索资料，请稍后再试'
      updateCacheState({ ...response.data, type: 'routerrag', topic: params.topic || ragSearchForm.topic })
      await pollRagCacheStatus('routerrag', params.topic || ragSearchForm.topic)
    }

    return response
  } catch (error) {
    ragRetrievalState.error = error.message || 'RouterRAG检索失败'
    throw error
  } finally {
    ragRetrievalState.loading = false
  }
}

const retrieveUniversalRAG = async (params = {}) => {
  ragRetrievalState.loading = true
  ragRetrievalState.error = ''
  ragRetrievalState.results = []
  ragRetrievalState.total = 0

  try {
    const response = await callApi('/api/rag/universal/retrieve', {
      method: 'POST',
      body: JSON.stringify({
        query: params.query || ragSearchForm.query,
        topic: params.topic || ragSearchForm.topic,
        rag_type: params.rag_type || 'tagrag',
        project: params.project || activeProjectName.value || undefined,
        top_k: params.top_k || ragSearchForm.top_k,
        threshold: params.threshold || ragSearchForm.threshold
      })
    })

    ragRetrievalState.results = response?.data?.results || []
    ragRetrievalState.total = response?.data?.total || 0
    ragRetrievalState.summary = response?.data?.summary || ''

    if (response?.status === 'building') {
      ragRetrievalState.error = response?.message || '正在准备检索资料，请稍后再试'
      const ragType = params.rag_type || 'tagrag'
      updateCacheState({ ...response.data, type: ragType, topic: params.topic || ragSearchForm.topic })
      await pollRagCacheStatus(ragType, params.topic || ragSearchForm.topic)
    }

    return response
  } catch (error) {
    ragRetrievalState.error = error.message || '检索失败'
    throw error
  } finally {
    ragRetrievalState.loading = false
  }
}

watch(activeProjectName, async (name) => {
  ragSearchForm.topic = ''
  ragTopicsState.options = []
  ragTopicsState.error = ''
  ragBuildForm.topic = ''
  if (name) {
    await loadRAGTopics()
    await loadRemoteTopics()
  }
})

export const useRAGTopics = () => {
  return {
    // States
    ragTopicsState,
    ragTopicOptions,
    tagragTopicOptions,
    routerTopicOptions,
    remoteTopicsState,
    remoteTopicOptions,
    ragSearchForm,
    ragRetrievalState,
    ragCacheState,
    ragBuildState,
    ragBuildForm,

    // Methods
    loadRAGTopics,
    loadRemoteTopics,
    buildRagTopic,
    retrieveTagRAG,
    retrieveRouterRAG,
    retrieveUniversalRAG
  }
}
