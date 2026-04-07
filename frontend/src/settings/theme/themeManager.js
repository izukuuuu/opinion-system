import {
  defaultThemePresetId,
  defaultThemeValues,
  managedThemeVariables,
  themePresets
} from "./defaultPalette"

const STORAGE_KEY = "opinion-system.theme.overrides"

const isBrowser = typeof window !== "undefined" && typeof document !== "undefined"

const themePresetMap = new Map(themePresets.map((preset) => [preset.id, preset]))

function sanitizeOverrides(overrides) {
  if (!overrides || typeof overrides !== "object") {
    return {}
  }

  return Object.fromEntries(
    Object.entries(overrides)
      .filter(([key, value]) => managedThemeVariables.includes(key) && typeof value === "string")
      .map(([key, value]) => [key, value.trim()])
      .filter(([, value]) => Boolean(value))
  )
}

function sanitizePresetId(presetId) {
  return themePresetMap.has(presetId) ? presetId : defaultThemePresetId
}

function parseThemeState(rawValue) {
  if (!rawValue || typeof rawValue !== "object" || Array.isArray(rawValue)) {
    return {
      state: { presetId: defaultThemePresetId, overrides: {} },
      shouldNormalize: false
    }
  }

  if ("presetId" in rawValue || "overrides" in rawValue) {
    return {
      state: {
        presetId: sanitizePresetId(rawValue.presetId),
        overrides: sanitizeOverrides(rawValue.overrides)
      },
      shouldNormalize: rawValue.presetId !== sanitizePresetId(rawValue.presetId)
    }
  }

  return {
    state: {
      presetId: defaultThemePresetId,
      overrides: sanitizeOverrides(rawValue)
    },
    shouldNormalize: true
  }
}

function composeThemeValuesFromState(state) {
  const preset = getThemePresetDefinition(state?.presetId)
  return {
    ...preset.values,
    ...sanitizeOverrides(state?.overrides)
  }
}

function applyThemeValues(values) {
  if (!isBrowser) return

  const root = document.documentElement
  managedThemeVariables.forEach((variable) => {
    root.style.removeProperty(variable)
  })

  Object.entries(values).forEach(([variable, value]) => {
    if (!managedThemeVariables.includes(variable)) return
    if (typeof value !== "string") return
    const trimmed = value.trim()
    if (!trimmed) return
    root.style.setProperty(variable, trimmed)
  })
}

export function getThemePresetDefinition(presetId = defaultThemePresetId) {
  return themePresetMap.get(sanitizePresetId(presetId)) || themePresetMap.get(defaultThemePresetId)
}

export function loadThemeState() {
  if (!isBrowser) {
    return {
      presetId: defaultThemePresetId,
      overrides: {}
    }
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (!stored) {
      return {
        presetId: defaultThemePresetId,
        overrides: {}
      }
    }

    const parsed = JSON.parse(stored)
    const { state, shouldNormalize } = parseThemeState(parsed)
    if (shouldNormalize) {
      saveThemeState(state)
    }
    return state
  } catch (error) {
    console.warn("读取主题颜色配置失败，将使用默认值。", error)
    return {
      presetId: defaultThemePresetId,
      overrides: {}
    }
  }
}

export function loadThemeOverrides() {
  return loadThemeState().overrides
}

export function saveThemeState(state) {
  if (!isBrowser) return

  try {
    const normalized = {
      presetId: sanitizePresetId(state?.presetId),
      overrides: sanitizeOverrides(state?.overrides)
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  } catch (error) {
    console.warn("无法保存主题颜色配置。", error)
  }
}

export function saveThemeOverrides(overrides) {
  const state = loadThemeState()
  saveThemeState({
    presetId: state.presetId,
    overrides
  })
}

export function applyTheme(state = loadThemeState()) {
  if (!isBrowser) return
  applyThemeValues(composeThemeValuesFromState(state))
}

export function initializeTheme() {
  if (!isBrowser) return
  applyTheme(loadThemeState())
}

export function getActiveThemePreset() {
  return getThemePresetDefinition(loadThemeState().presetId)
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
  if (!isBrowser) return {}

  const state = loadThemeState()
  if (typeof value === "string" && value.trim() !== "") {
    state.overrides[variable] = value.trim()
  } else {
    delete state.overrides[variable]
  }

  applyTheme(state)
  if (persist) {
    saveThemeState(state)
  }
  return { ...state.overrides }
}

export function setThemePreset(presetId, { persist = true, clearOverrides = true } = {}) {
  if (!themePresetMap.has(presetId)) {
    throw new Error(`未知的主题预设：${presetId}`)
  }
  if (!isBrowser) {
    return {
      presetId,
      overrides: {}
    }
  }

  const state = loadThemeState()
  state.presetId = presetId
  if (clearOverrides) {
    state.overrides = {}
  }

  applyTheme(state)
  if (persist) {
    saveThemeState(state)
  }
  return state
}

export function resetThemeToDefaults() {
  const defaultState = {
    presetId: defaultThemePresetId,
    overrides: {}
  }

  if (!isBrowser) {
    return { ...defaultThemeValues }
  }

  window.localStorage.removeItem(STORAGE_KEY)
  applyTheme(defaultState)
  return getCurrentThemeValues()
}

export function exportThemeConfig({ includeDefaults = false } = {}) {
  const state = loadThemeState()
  const payload = {
    exportedAt: new Date().toISOString(),
    presetId: state.presetId,
    overrides: state.overrides
  }

  if (includeDefaults) {
    payload.defaults = defaultThemeValues
  }

  return payload
}

export function importThemeConfig(config) {
  if (!isBrowser) {
    return {
      presetId: defaultThemePresetId,
      overrides: {}
    }
  }

  if (!config || typeof config !== "object") {
    throw new Error("无效的主题配置文件。")
  }

  const { state } = parseThemeState(config)
  applyTheme(state)
  saveThemeState(state)
  return state
}
