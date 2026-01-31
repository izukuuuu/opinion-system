import { reactive } from 'vue'
import { useApiBase } from './useApiBase'

const { callApi } = useApiBase()

// Form states
const searchForm = reactive({
  query: '',
  topic: '',
  top_k: 10,
  threshold: 0.0,
  rag_type: 'tagrag'
})

const configForm = reactive({
  embedding: {
    model_name: 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
    model_type: 'huggingface',
    batch_size: 32,
    normalize: true,
    device: 'auto',
    api_key: '',
    cache_dir: ''
  },
  chunking: {
    strategy: 'size',
    chunk_size: 512,
    chunk_overlap: 50,
    separator: '\n\n',
    respect_sentence_boundary: true,
    strip_whitespace: true
  },
  retrieval: {
    top_k: 10,
    threshold: 0.0,
    search_type: 'vector',
    include_metadata: true,
    score_type: 'cosine',
    rerank: false,
    enable_query_expansion: true,
    enable_llm_summary: true,
    llm_summary_mode: 'strict'
  },
  storage: {
    storage_type: 'file',
    path: './data/rag',
    index_type: 'flat',
    metric: 'cosine',
    persist_index: true
  },
  processing: {
    lowercase: false,
    remove_urls: true,
    remove_emails: true,
    remove_extra_whitespace: true,
    remove_special_chars: false,
    normalize_unicode: true
  },
  api_keys: {
    openai: '',
    cohere: '',
    huggingface: ''
  }
})

// Config state
const configState = reactive({
  loading: false,
  error: ''
})

// Topics state
const topicsState = reactive({
  loading: false,
  error: '',
  tagragTopics: [],
  routerTopics: []
})

// Retrieval results state
const resultsState = reactive({
  loading: false,
  error: '',
  results: [],
  total: 0
})

// Export simplified RAG composable
export const useRAGSimple = () => {
  // Load configuration
  const loadConfig = async () => {
    configState.loading = true
    configState.error = ''

    try {
      const response = await callApi('/api/rag/config', {
        method: 'GET'
      })

      if (response?.data) {
        Object.assign(configForm, response.data)
      }
      return response
    } catch (error) {
      configState.error = error.message || '加载配置失败'
      console.error('Failed to load RAG config:', error)
      throw error
    } finally {
      configState.loading = false
    }
  }

  // Save configuration
  const saveConfig = async () => {
    configState.loading = true
    configState.error = ''

    try {
      const response = await callApi('/api/rag/config', {
        method: 'POST',
        body: JSON.stringify(configForm)
      })
      return response
    } catch (error) {
      configState.error = error.message || '保存配置失败'
      console.error('Failed to save RAG config:', error)
      throw error
    } finally {
      configState.loading = false
    }
  }

  // Load topics
  const loadTopics = async () => {
    topicsState.loading = true
    topicsState.error = ''

    try {
      const response = await callApi('/api/rag/topics', {
        method: 'GET'
      })

      if (response?.data) {
        topicsState.tagragTopics = response.data.tagrag_topics || []
        topicsState.routerTopics = response.data.router_topics || []
      } else {
        // Fallback to empty arrays
        topicsState.tagragTopics = []
        topicsState.routerTopics = []
      }
    } catch (error) {
      topicsState.error = error.message || '加载专题列表失败'
      // Fallback to empty arrays on error
      topicsState.tagragTopics = []
      topicsState.routerTopics = []
      throw error
    } finally {
      topicsState.loading = false
    }
  }

  // Retrieve documents
  const retrieve = async (type = 'tagrag', params = {}) => {
    resultsState.loading = true
    resultsState.error = ''
    resultsState.results = []
    resultsState.total = 0

    try {
      const response = await callApi('/api/rag/test', {
        method: 'POST',
        body: JSON.stringify({
          query: params.query || searchForm.query,
          type: type
        })
      })

      resultsState.results = response?.data?.results || []
      resultsState.total = response?.data?.total || 0

      return response
    } catch (error) {
      resultsState.error = error.message || '检索失败'
      throw error
    } finally {
      resultsState.loading = false
    }
  }

  // Convenience methods
  const retrieveTagRAG = (params = {}) => retrieve('tagrag', params)
  const retrieveRouterRAG = (params = {}) => retrieve('routerrag', params)
  const retrieveUniversal = (params = {}) => retrieve('universal', params)

  // Reset forms
  const resetSearchForm = () => {
    Object.assign(searchForm, {
      query: '',
      topic: '',
      top_k: 10,
      threshold: 0.0,
      rag_type: 'tagrag'
    })
  }

  const resetConfigForm = () => {
    Object.assign(configForm, {
      embedding: {
        model_name: 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
        model_type: 'huggingface',
        batch_size: 32,
        normalize: true,
        device: 'auto',
        api_key: '',
        cache_dir: ''
      },
      chunking: {
        strategy: 'size',
        chunk_size: 512,
        chunk_overlap: 50,
        separator: '\n\n',
        respect_sentence_boundary: true,
        strip_whitespace: true
      },
      retrieval: {
        top_k: 10,
        threshold: 0.0,
        search_type: 'vector',
        include_metadata: true,
        score_type: 'cosine',
        rerank: false,
        enable_query_expansion: true,
        enable_llm_summary: true,
        llm_summary_mode: 'strict'
      },
      storage: {
        storage_type: 'file',
        path: './data/rag',
        index_type: 'flat',
        metric: 'cosine',
        persist_index: true
      },
      processing: {
        lowercase: false,
        remove_urls: true,
        remove_emails: true,
        remove_extra_whitespace: true,
        remove_special_chars: false,
        normalize_unicode: true
      },
      api_keys: {
        openai: '',
        cohere: '',
        huggingface: ''
      }
    })
  }

  return {
    // States
    configState,
    topicsState,
    resultsState,
    searchForm,
    configForm,

    // Methods
    loadConfig,
    saveConfig,
    loadTopics,
    retrieve,
    retrieveTagRAG,
    retrieveRouterRAG,
    retrieveUniversal,
    resetSearchForm,
    resetConfigForm
  }
}