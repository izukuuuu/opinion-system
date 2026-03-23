import { reactive, ref } from 'vue'
import { useApiBase } from './useApiBase'

const DEFAULT_BERTOPIC_MODEL = 'moka-ai/m3e-base'

const DEFAULT_EMBEDDING_MODEL_OPTIONS = Object.freeze([
  {
    value: DEFAULT_BERTOPIC_MODEL,
    label: '推荐 (8GB GPU / 中文) - moka-ai/m3e-base'
  },
  {
    value: 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
    label: '兼容优先 (多语言) - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
  },
  {
    value: 'sentence-transformers/all-MiniLM-L6-v2',
    label: '快速 (英文优先) - sentence-transformers/all-MiniLM-L6-v2'
  },
  {
    value: 'sentence-transformers/all-mpnet-base-v2',
    label: '高质量语义 - sentence-transformers/all-mpnet-base-v2'
  },
  {
    value: 'shibing624/text2vec-base-chinese',
    label: '中文优化 - shibing624/text2vec-base-chinese'
  },
  {
    value: 'moka-ai/m3e-base',
    label: '中文通用 - moka-ai/m3e-base'
  },
  {
    value: 'BAAI/bge-large-zh-v1.5',
    label: '高精度中文 (8GB GPU 建议小批次) - BAAI/bge-large-zh-v1.5'
  }
])

const MODEL_LABEL_MAP = Object.freeze(
  DEFAULT_EMBEDDING_MODEL_OPTIONS.reduce((acc, option) => {
    acc[option.value] = option.label
    return acc
  }, {})
)

const buildDefaultEmbeddingConfig = () => ({
  model_name: DEFAULT_BERTOPIC_MODEL,
  device: 'auto',
  batch_size: 32
})

const normalizeModelName = (value) => String(value || '').trim()

const dedupeModelOptions = (names = []) => {
  const seen = new Set()
  const options = []

  names.forEach((raw) => {
    const value = normalizeModelName(raw)
    if (!value || seen.has(value)) return
    seen.add(value)
    options.push({
      value,
      label: MODEL_LABEL_MAP[value] || value
    })
  })

  return options
}

const ensureCurrentModelOption = (options, currentModel) => {
  const modelName = normalizeModelName(currentModel)
  if (!modelName) return options
  if (options.some((item) => item.value === modelName)) return options
  return [
    { value: modelName, label: `当前配置 - ${modelName}` },
    ...options
  ]
}

export const useBertopicConfig = () => {
  const { callApi } = useApiBase()

  const configForm = reactive({
    embedding: buildDefaultEmbeddingConfig()
  })

  const configState = reactive({
    loading: false,
    error: ''
  })

  const stopwordsForm = reactive({
    path: '',
    content: '',
    line_count: 0
  })

  const stopwordsState = reactive({
    loading: false,
    saving: false,
    error: ''
  })

  const embeddingModelState = reactive({
    loading: false,
    error: ''
  })

  const embeddingModelOptions = ref([...DEFAULT_EMBEDDING_MODEL_OPTIONS])

  const syncModelOptionsWithCurrentModel = () => {
    embeddingModelOptions.value = ensureCurrentModelOption(
      dedupeModelOptions(embeddingModelOptions.value.map((item) => item.value)),
      configForm.embedding.model_name
    )
  }

  const loadEmbeddingModels = async () => {
    embeddingModelState.loading = true
    embeddingModelState.error = ''

    try {
      const response = await callApi('/api/rag/embedding/models', {
        method: 'GET'
      })
      const remoteModels = Array.isArray(response?.data?.huggingface)
        ? response.data.huggingface
        : []

      const mergedNames = [
        ...remoteModels,
        ...DEFAULT_EMBEDDING_MODEL_OPTIONS.map((item) => item.value)
      ]
      embeddingModelOptions.value = ensureCurrentModelOption(
        dedupeModelOptions(mergedNames),
        configForm.embedding.model_name
      )
      return response
    } catch (error) {
      embeddingModelState.error = error instanceof Error ? error.message : '加载模型列表失败'
      embeddingModelOptions.value = ensureCurrentModelOption(
        dedupeModelOptions(DEFAULT_EMBEDDING_MODEL_OPTIONS.map((item) => item.value)),
        configForm.embedding.model_name
      )
      return null
    } finally {
      embeddingModelState.loading = false
    }
  }

  const loadConfig = async () => {
    configState.loading = true
    configState.error = ''

    try {
      const response = await callApi('/api/topic/config', {
        method: 'GET'
      })

      if (response?.data?.embedding) {
        Object.assign(configForm.embedding, response.data.embedding)
      }
      syncModelOptionsWithCurrentModel()
      return response
    } catch (error) {
      configState.error = error instanceof Error ? error.message : '加载配置失败'
      console.error('Failed to load BERTopic config:', error)
      throw error
    } finally {
      configState.loading = false
    }
  }

  const saveConfig = async () => {
    configState.loading = true
    configState.error = ''

    try {
      const response = await callApi('/api/topic/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(configForm)
      })

      if (response?.data?.embedding) {
        Object.assign(configForm.embedding, response.data.embedding)
      }
      syncModelOptionsWithCurrentModel()
      return response
    } catch (error) {
      configState.error = error instanceof Error ? error.message : '保存配置失败'
      console.error('Failed to save BERTopic config:', error)
      throw error
    } finally {
      configState.loading = false
    }
  }

  const resetConfigForm = () => {
    Object.assign(configForm.embedding, buildDefaultEmbeddingConfig())
    syncModelOptionsWithCurrentModel()
  }

  const loadStopwords = async () => {
    stopwordsState.loading = true
    stopwordsState.error = ''

    try {
      const response = await callApi('/api/topic/config/stopwords', {
        method: 'GET'
      })
      const data = response?.data || {}
      stopwordsForm.path = String(data.path || '')
      stopwordsForm.content = String(data.content || '')
      stopwordsForm.line_count = Number(data.line_count || 0)
      return response
    } catch (error) {
      stopwordsState.error = error instanceof Error ? error.message : '加载停用词失败'
      console.error('Failed to load BERTopic stopwords:', error)
      throw error
    } finally {
      stopwordsState.loading = false
    }
  }

  const saveStopwords = async () => {
    stopwordsState.saving = true
    stopwordsState.error = ''

    try {
      const response = await callApi('/api/topic/config/stopwords', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          content: stopwordsForm.content
        })
      })

      const data = response?.data || {}
      stopwordsForm.path = String(data.path || '')
      stopwordsForm.content = String(data.content || '')
      stopwordsForm.line_count = Number(data.line_count || 0)
      return response
    } catch (error) {
      stopwordsState.error = error instanceof Error ? error.message : '保存停用词失败'
      console.error('Failed to save BERTopic stopwords:', error)
      throw error
    } finally {
      stopwordsState.saving = false
    }
  }

  const resetStopwordsForm = () => {
    stopwordsForm.path = ''
    stopwordsForm.content = ''
    stopwordsForm.line_count = 0
  }

  return {
    configForm,
    configState,
    stopwordsForm,
    stopwordsState,
    embeddingModelState,
    embeddingModelOptions,
    loadConfig,
    saveConfig,
    resetConfigForm,
    loadEmbeddingModels,
    loadStopwords,
    saveStopwords,
    resetStopwordsForm
  }
}
