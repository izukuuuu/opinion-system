import { computed, ref } from 'vue'

const STORAGE_KEY = 'opinion-system-backend-base'
const DEFAULT_BACKEND_BASE = normaliseBase(import.meta.env.VITE_API_BASE_URL) || 'http://127.0.0.1:8000'

const backendBase = ref(DEFAULT_BACKEND_BASE)

if (typeof window !== 'undefined') {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const normalised = normaliseBase(stored)
      backendBase.value = normalised || DEFAULT_BACKEND_BASE
    } else {
      window.localStorage.setItem(STORAGE_KEY, backendBase.value)
    }
  } catch {
    // localStorage 不可用时继续使用默认值
  }
}

const apiBase = computed(() => `${backendBase.value}/api`)

export const useApiBase = () => {
  const ensureApiBase = async () => apiBase.value

  const setBackendBase = (value) => {
    const normalised = normaliseBase(value) || DEFAULT_BACKEND_BASE
    backendBase.value = normalised
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(STORAGE_KEY, normalised)
      } catch {
        // ignore storage errors
      }
    }
  }

  const resetBackendBase = () => {
    setBackendBase(DEFAULT_BACKEND_BASE)
  }

  const callApi = async (path, options = {}) => {
    const url = buildUrl(path)
    const { headers = {}, ...rest } = options
    const finalHeaders = { ...headers }
    if (!(rest.body instanceof FormData) && !finalHeaders['Content-Type']) {
      finalHeaders['Content-Type'] = 'application/json'
    }
    const response = await fetch(url, { ...rest, headers: finalHeaders })
    if (!response.ok) {
      const message = await safeReadBody(response)
      throw new Error(message || `请求失败: ${response.status}`)
    }
    return parseJson(response)
  }

  return {
    backendBase,
    apiBase,
    ensureApiBase,
    setBackendBase,
    resetBackendBase,
    callApi,
  }
}

function normaliseBase(value) {
  if (typeof value !== 'string') return ''
  let base = value.trim()
  if (!base) return ''
  if (!/^https?:\/\//i.test(base)) {
    base = `http://${base}`
  }
  base = base.replace(/\/+$/, '')
  base = base.replace(/\/api$/i, '')
  base = base.replace(/\/api\/$/i, '')
  return base || ''
}

function buildUrl(path) {
  if (!path) return backendBase.value
  if (/^https?:\/\//i.test(path)) return path
  if (path.startsWith('/')) {
    return `${backendBase.value}${path}`
  }
  return `${backendBase.value}/${path}`
}

async function safeReadBody(response) {
  try {
    const text = await response.text()
    return text
  } catch {
    return ''
  }
}

async function parseJson(response) {
  const contentType = response.headers.get('Content-Type') || ''
  if (!contentType.includes('application/json')) {
    return response.text()
  }
  return response.json()
}
