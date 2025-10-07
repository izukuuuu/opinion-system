import { ref } from 'vue'

const API_BASE_FALLBACK = 'http://127.0.0.1:8000'

const backendBase = ref(API_BASE_FALLBACK)
const configLoaded = ref(false)
let configPromise = null

const loadConfig = async () => {
  try {
    const response = await fetch(`${backendBase.value}/api/config`)
    if (!response.ok) throw new Error(`配置获取失败: ${response.status}`)
    const config = await response.json()
    if (config.backend?.base_url) {
      backendBase.value = config.backend.base_url
    } else if (config.backend?.host && config.backend?.port) {
      backendBase.value = `http://${config.backend.host}:${config.backend.port}`
    }
  } catch (error) {
    console.warn('加载配置失败，使用默认后端地址', error)
  } finally {
    configLoaded.value = true
    configPromise = null
  }
}

const ensureConfig = async () => {
  if (configLoaded.value) return
  if (!configPromise) {
    configPromise = loadConfig()
  }
  await configPromise
}

const callApi = async (path, options = {}) => {
  await ensureConfig()
  const response = await fetch(`${backendBase.value}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!response.ok) {
    let message = ''
    try {
      const payload = await response.clone().json()
      if (payload) {
        if (typeof payload.message === 'string') message = payload.message
        else if (typeof payload.error === 'string') message = payload.error
        else if (typeof payload === 'string') message = payload
      }
    } catch (parseError) {
      message = await response.text()
    }
    if (!message) {
      message = `请求失败: ${response.status}`
    }
    throw new Error(message)
  }
  const result = await response.json()
  if (result?.status === 'error') {
    throw new Error(result.message || '请求失败')
  }
  return result
}

export const useBackendClient = () => ({ backendBase, ensureConfig, callApi })
