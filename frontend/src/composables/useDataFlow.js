import { reactive, ref, computed } from 'vue'
import { useApiBase } from './useApiBase'

const { callApi } = useApiBase()

// Standardized data flow states
const createDataFlowState = (name) => ({
  // Remote data state
  remote: reactive({
    loading: false,
    error: '',
    data: null,
    lastFetched: null
  }),

  // Local cache state
  cache: reactive({
    loading: false,
    error: '',
    data: null,
    lastUpdated: null
  }),

  // Processing state
  processing: reactive({
    loading: false,
    error: '',
    result: null,
    progress: 0,
    status: ''
  }),

  // Name for logging
  name
})

// Standard API endpoints
const API_ENDPOINTS = {
  QUERY: '/api/query',
  FETCH: '/api/fetch',
  ANALYZE: '/api/analyze',
  RAG: {
    CONFIG: '/api/rag/config',
    TOPICS: '/api/rag/topics',
    TAGRAG_RETRIEVE: '/api/rag/tagrag/retrieve',
    ROUTERRAG_RETRIEVE: '/api/rag/routerrag/retrieve',
    UNIVERSAL_RETRIEVE: '/api/rag/universal/retrieve',
    EXPORT: '/api/rag/export'
  }
}

// Standard data flow manager
export const useDataFlow = (moduleName, options = {}) => {
  const state = createDataFlowState(moduleName)

  // Configuration
  const config = {
    autoRefresh: options.autoRefresh || false,
    refreshInterval: options.refreshInterval || 300000, // 5 minutes
    cacheKey: options.cacheKey || `dataflow_${moduleName}`,
    ...options
  }

  // Remote data fetching
  const fetchRemote = async (params = {}) => {
    state.remote.loading = true
    state.remote.error = ''

    try {
      const response = await callApi(API_ENDPOINTS.QUERY, {
        method: 'POST',
        body: JSON.stringify(params)
      })

      state.remote.data = response?.data || null
      state.remote.lastFetched = new Date().toISOString()

      // Cache the response
      if (typeof window !== 'undefined') {
        try {
          localStorage.setItem(config.cacheKey, JSON.stringify({
            data: state.remote.data,
            timestamp: state.remote.lastFetched
          }))
        } catch (e) {
          console.warn('Failed to cache data:', e)
        }
      }

      return response
    } catch (error) {
      state.remote.error = error.message || `Failed to fetch ${moduleName} data`
      throw error
    } finally {
      state.remote.loading = false
    }
  }

  // Load data from cache
  const loadFromCache = () => {
    if (typeof window === 'undefined') return null

    try {
      const cached = localStorage.getItem(config.cacheKey)
      if (cached) {
        const { data, timestamp } = JSON.parse(cached)

        // Check if cache is still valid
        const cacheAge = new Date() - new Date(timestamp)
        if (cacheAge < config.refreshInterval) {
          state.cache.data = data
          state.cache.lastUpdated = timestamp
          return data
        }
      }
    } catch (e) {
      console.warn('Failed to load from cache:', e)
    }

    return null
  }

  // Fetch remote data to local cache
  const fetchToLocal = async (params = {}) => {
    state.cache.loading = true
    state.cache.error = ''

    try {
      // First fetch remote data
      await fetchRemote(params)

      // Then fetch to local
      const fetchParams = {
        topic: params.topic,
        start: params.start,
        end: params.end,
        ...params.fetchOptions
      }

      const response = await callApi(API_ENDPOINTS.FETCH, {
        method: 'POST',
        body: JSON.stringify(fetchParams)
      })

      state.cache.data = response?.data || null
      state.cache.lastUpdated = new Date().toISOString()

      return response
    } catch (error) {
      state.cache.error = error.message || `Failed to fetch ${moduleName} to local`
      throw error
    } finally {
      state.cache.loading = false
    }
  }

  // Run analysis on data
  const analyze = async (functions = [], params = {}) => {
    state.processing.loading = true
    state.processing.error = ''
    state.processing.progress = 0
    state.processing.status = 'Initializing...'

    try {
      const response = await callApi(API_ENDPOINTS.ANALYZE, {
        method: 'POST',
        body: JSON.stringify({
          functions,
          topic: params.topic,
          start: params.start,
          end: params.end,
          ...params.analyzeOptions
        })
      })

      state.processing.result = response?.data || null
      state.processing.status = 'Completed'
      state.processing.progress = 100

      return response
    } catch (error) {
      state.processing.error = error.message || `Failed to analyze ${moduleName}`
      state.processing.status = 'Failed'
      throw error
    } finally {
      state.processing.loading = false
    }
  }

  // Combined flow: fetch -> local -> analyze
  const runFullFlow = async (params = {}) => {
    // 1. Check cache first
    const cachedData = loadFromCache()
    if (cachedData && !params.forceRefresh) {
      console.log(`Using cached data for ${moduleName}`)
    }

    // 2. Fetch to local if needed
    if (params.fetchToLocal || !cachedData || params.forceRefresh) {
      await fetchToLocal(params)
    }

    // 3. Run analysis if functions provided
    if (params.functions && params.functions.length > 0) {
      return await analyze(params.functions, params)
    }

    return { data: state.cache.data }
  }

  // Clear cache
  const clearCache = () => {
    if (typeof window !== 'undefined') {
      try {
        localStorage.removeItem(config.cacheKey)
      } catch (e) {
        console.warn('Failed to clear cache:', e)
      }
    }

    state.cache.data = null
    state.cache.lastUpdated = null
  }

  // Get cached data
  const getCachedData = computed(() => state.cache.data || state.remote.data)

  // Is data available
  const hasData = computed(() => {
    return !!(state.cache.data || state.remote.data)
  })

  // Is loading
  const isLoading = computed(() => {
    return state.remote.loading || state.cache.loading || state.processing.loading
  })

  // Get any error
  const getError = computed(() => {
    return state.remote.error || state.cache.error || state.processing.error
  })

  return {
    // States
    state,

    // Data
    getCachedData,
    hasData,
    isLoading,
    getError,

    // Methods
    fetchRemote,
    fetchToLocal,
    analyze,
    runFullFlow,
    loadFromCache,
    clearCache
  }
}

// RAG-specific data flow
export const useRAGDataFlow = () => {
  const ragState = useDataFlow('rag', {
    cacheKey: 'rag_config'
  })

  // RAG-specific methods
  const retrieve = async (type, params) => {
    const endpoints = {
      tagrag: API_ENDPOINTS.RAG.TAGRAG_RETRIEVE,
      routerrag: API_ENDPOINTS.RAG.ROUTERRAG_RETRIEVE,
      universal: API_ENDPOINTS.RAG.UNIVERSAL_RETRIEVE
    }

    const endpoint = endpoints[type]
    if (!endpoint) {
      throw new Error(`Unknown RAG type: ${type}`)
    }

    try {
      const response = await callApi(endpoint, {
        method: 'POST',
        body: JSON.stringify(params)
      })

      return response
    } catch (error) {
      throw error
    }
  }

  const loadConfig = async () => {
    try {
      const response = await callApi(API_ENDPOINTS.RAG.CONFIG, {
        method: 'GET'
      })

      if (response?.data?.config) {
        ragState.state.remote.data = response.data.config
        ragState.state.remote.lastFetched = new Date().toISOString()
      }

      return response
    } catch (error) {
      throw error
    }
  }

  const saveConfig = async (config) => {
    try {
      const response = await callApi(API_ENDPOINTS.RAG.CONFIG, {
        method: 'POST',
        body: JSON.stringify({ config })
      })

      return response
    } catch (error) {
      throw error
    }
  }

  const loadTopics = async () => {
    try {
      const response = await callApi(API_ENDPOINTS.RAG.TOPICS, {
        method: 'GET'
      })

      return response?.data || { tagrag_topics: [], router_topics: [] }
    } catch (error) {
      throw error
    }
  }

  return {
    ...ragState,

    // RAG-specific methods
    retrieve,
    loadConfig,
    saveConfig,
    loadTopics
  }
}

// Export API endpoints for reference
export { API_ENDPOINTS }