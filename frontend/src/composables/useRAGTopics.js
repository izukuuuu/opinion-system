import { reactive, ref, computed } from 'vue'
import { useApiBase } from './useApiBase'
import { useActiveProject } from './useActiveProject'

const { callApi } = useApiBase()
const { activeProjectName } = useActiveProject()

// RAG Topics State (mirrors useBasicAnalysis topicsState)
const ragTopicsState = reactive({
  loading: false,
  error: '',
  options: []  // This will hold available RAG topics
})

const ragTopicOptions = computed(() => ragTopicsState.options)

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
  total: 0
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
    updateCacheState({ ...status, type, topic })
    if (status.status === 'done' || status.status === 'error') {
      stopRagCachePolling()
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

    // Combine TagRAG and RouterRAG topics
    const tagragTopics = response?.data?.tagrag_topics || []
    const routerTopics = response?.data?.router_topics || []

    // All available topics
    ragTopicsState.options = [...tagragTopics, ...routerTopics]

    // If no current selection, select first available topic
    if (!ragSearchForm.topic && ragTopicsState.options.length > 0) {
      ragSearchForm.topic = ragTopicsState.options[0]
    }

    return response
  } catch (error) {
    ragTopicsState.error = error.message || '加载RAG专题列表失败'
    throw error
  } finally {
    ragTopicsState.loading = false
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
        project: params.project || activeProjectName.value || undefined,
        top_k: params.top_k || ragSearchForm.top_k,
        threshold: params.threshold || ragSearchForm.threshold
      })
    })

    ragRetrievalState.results = response?.data?.results || []
    ragRetrievalState.total = response?.data?.total || 0

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

export const useRAGTopics = () => {
  return {
    // States
    ragTopicsState,
    ragTopicOptions,
    ragSearchForm,
    ragRetrievalState,
    ragCacheState,

    // Methods
    loadRAGTopics,
    retrieveTagRAG,
    retrieveRouterRAG,
    retrieveUniversalRAG
  }
}
