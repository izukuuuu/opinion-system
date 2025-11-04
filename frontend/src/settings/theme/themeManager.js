import { defaultThemeValues, managedThemeVariables } from './defaultPalette'

const STORAGE_KEY = 'opinion-system.theme.overrides'

const isBrowser = typeof window !== 'undefined' && typeof document !== 'undefined'

export function loadThemeOverrides() {
  if (!isBrowser) {
    return {}
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (!stored) return {}
    const parsed = JSON.parse(stored)
    if (parsed && typeof parsed === 'object') {
      return Object.fromEntries(
        Object.entries(parsed)
          .filter(([key, value]) => managedThemeVariables.includes(key) && typeof value === 'string')
          .map(([key, value]) => [key, value.trim()])
      )
    }
    return {}
  } catch (error) {
    console.warn('读取主题颜色配置失败，将使用默认值。', error)
    return {}
  }
}

export function saveThemeOverrides(overrides) {
  if (!isBrowser) return
  try {
    const sanitized = Object.fromEntries(
      Object.entries(overrides || {})
        .filter(([variable, value]) => managedThemeVariables.includes(variable) && typeof value === 'string')
        .map(([variable, value]) => [variable, value.trim()])
    )
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitized))
  } catch (error) {
    console.warn('无法保存主题颜色配置。', error)
  }
}

export function applyTheme(overrides = {}) {
  if (!isBrowser) return

  const root = document.documentElement

  managedThemeVariables.forEach((variable) => {
    root.style.removeProperty(variable)
  })

  Object.entries(overrides).forEach(([variable, value]) => {
    if (!managedThemeVariables.includes(variable)) return
    if (typeof value !== 'string') return
    const trimmed = value.trim()
    if (!trimmed) return
    root.style.setProperty(variable, trimmed)
  })
}

export function initializeTheme() {
  if (!isBrowser) return
  const overrides = loadThemeOverrides()
  applyTheme(overrides)
}

export function getCurrentThemeValues() {
  if (!isBrowser) {
    return { ...defaultThemeValues }
  }

  const styles = window.getComputedStyle(document.documentElement)
  return managedThemeVariables.reduce((result, variable) => {
    const value = styles.getPropertyValue(variable)
    result[variable] = value ? value.trim() : defaultThemeValues[variable]
    return result
  }, {})
}

export function updateThemeVariable(variable, value, { persist = true } = {}) {
  if (!managedThemeVariables.includes(variable)) {
    throw new Error(`未知的主题变量：${variable}`)
  }
  if (!isBrowser) return

  const overrides = loadThemeOverrides()
  if (typeof value === 'string' && value.trim() !== '') {
    overrides[variable] = value.trim()
  } else {
    delete overrides[variable]
  }

  applyTheme(overrides)
  if (persist) {
    saveThemeOverrides(overrides)
  }
  return overrides
}

export function resetThemeToDefaults() {
  if (!isBrowser) return { ...defaultThemeValues }
  window.localStorage.removeItem(STORAGE_KEY)
  applyTheme({})
  return getCurrentThemeValues()
}

export function exportThemeConfig({ includeDefaults = false } = {}) {
  const overrides = loadThemeOverrides()
  if (includeDefaults) {
    return {
      exportedAt: new Date().toISOString(),
      overrides,
      defaults: defaultThemeValues
    }
  }
  return {
    exportedAt: new Date().toISOString(),
    overrides
  }
}

export function importThemeConfig(config) {
  if (!isBrowser) return {}

  let overrides = {}
  if (config && typeof config === 'object') {
    overrides = config.overrides || config
  }

  if (!overrides || typeof overrides !== 'object') {
    throw new Error('无效的主题配置文件。')
  }

  const sanitized = Object.fromEntries(
    Object.entries(overrides)
      .filter(([variable, value]) => managedThemeVariables.includes(variable) && typeof value === 'string')
      .map(([variable, value]) => [variable, value.trim()])
  )

  applyTheme(sanitized)
  saveThemeOverrides(sanitized)
  return sanitized
}
