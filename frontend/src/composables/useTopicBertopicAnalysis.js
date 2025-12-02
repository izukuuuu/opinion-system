import { reactive, ref } from 'vue'
import { useApiBase } from './useApiBase'

const initialState = () => ({
  running: false,
  error: '',
  result: null
})

const state = reactive(initialState())
const lastPayload = ref(null)
const { callApi } = useApiBase()

const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '')

const normalisePayload = (payload = {}) => {
  const topic = normalizeText(payload.topic)
  const startDate = normalizeText(payload.startDate || payload.start_date)
  const endDate = normalizeText(payload.endDate || payload.end_date)
  const fetchDir = normalizeText(payload.fetchDir || payload.fetch_dir)
  const userdict = normalizeText(payload.userdict || payload.user_dict || payload.userDict)
  const stopwords = normalizeText(payload.stopwords || payload.stop_words || payload.stopWords)

  if (!topic || !startDate) {
    throw new Error('topic 与 startDate 为必填字段')
  }

  const body = {
    topic,
    start_date: startDate
  }
  if (endDate) body.end_date = endDate
  if (fetchDir) body.fetch_dir = fetchDir
  if (userdict) body.userdict = userdict
  if (stopwords) body.stopwords = stopwords
  return body
}

export function useTopicBertopicAnalysis() {
  const resetState = () => {
    Object.assign(state, initialState())
    lastPayload.value = null
  }

  const runBertopicAnalysis = async (payload) => {
    state.error = ''
    state.running = true
    try {
      const body = normalisePayload(payload)
      lastPayload.value = body
      const response = await callApi('/api/analysis/topic/bertopic/run', {
        method: 'POST',
        body: JSON.stringify(body)
      })
      state.result = response
      return response
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error || '请求失败')
      state.error = message
      throw error
    } finally {
      state.running = false
    }
  }

  return {
    state,
    lastPayload,
    runBertopicAnalysis,
    resetState
  }
}

