import { reactive, ref, computed } from 'vue'
import { useApiBase } from './useApiBase'

const { callApi } = useApiBase()

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

// Functions
const loadRAGTopics = async () => {
  ragTopicsState.loading = true
  ragTopicsState.error = ''

  try {
    const response = await callApi('/api/rag/topics', {
      method: 'GET'
    })

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
        top_k: params.top_k || ragSearchForm.top_k,
        threshold: params.threshold || ragSearchForm.threshold
      })
    })

    ragRetrievalState.results = response?.data?.results || []
    ragRetrievalState.total = response?.data?.total || 0

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
        top_k: params.top_k || ragSearchForm.top_k,
        threshold: params.threshold || ragSearchForm.threshold
      })
    })

    ragRetrievalState.results = response?.data?.results || []
    ragRetrievalState.total = response?.data?.total || 0

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
        top_k: params.top_k || ragSearchForm.top_k,
        threshold: params.threshold || ragSearchForm.threshold
      })
    })

    ragRetrievalState.results = response?.data?.results || []
    ragRetrievalState.total = response?.data?.total || 0

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

    // Methods
    loadRAGTopics,
    retrieveTagRAG,
    retrieveRouterRAG,
    retrieveUniversalRAG
  }
}