<template>
  <section class="theme-editor">
    <header class="theme-editor__header">
      <div class="theme-editor__intro">
        <h2>主题颜色</h2>
        <p>
          调整 <code>colors.css</code> 中的主题色变量，实时预览界面效果。支持导入/导出 JSON 配置，并可针对单个变量恢复默认值。
        </p>
        <p v-if="overrideCount" class="theme-editor__meta">
          已覆盖 <strong>{{ overrideCount }}</strong> 项变量
        </p>
      </div>
      <div class="theme-editor__tools">
        <button type="button" class="ghost-button" @click="triggerImport">
          读取配置
        </button>
        <button type="button" class="ghost-button" @click="handleExport">
          导出配置
        </button>
      </div>
    </header>

    <p v-if="statusMessage" :class="['theme-editor__status', `theme-editor__status--${statusTone}`]">
      {{ statusMessage }}
    </p>

    <div class="theme-editor__groups">
      <article v-for="group in groups" :key="group.id" class="theme-editor__group">
        <header class="theme-editor__group-header">
          <div>
            <h3>{{ group.title }}</h3>
            <p>{{ group.description }}</p>
          </div>
        </header>
        <div class="theme-editor__tokens">
          <div v-for="token in group.tokens" :key="token.variable" class="theme-editor__token">
            <div
              class="theme-editor__preview"
              :class="[{ 'theme-editor__preview--outline': token.variant === 'outline' }]"
              :style="previewStyle(token)"
            >
              <span>{{ displayValue(token) }}</span>
            </div>
            <div class="theme-editor__details">
              <p>{{ token.label }}</p>
              <code>{{ token.variable }}</code>
            </div>
            <div class="theme-editor__controls">
              <label class="theme-editor__color-picker" :title="`设置 ${token.label}`">
                <input
                  type="color"
                  :value="hexValue(token)"
                  @input="(event) => handleColorInput(token, event.target.value)"
                >
              </label>
              <button
                v-if="isOverridden(token.variable)"
                type="button"
                class="ghost-button ghost-button--small"
                @click="restoreDefault(token.variable)"
              >
                恢复默认
              </button>
            </div>
          </div>
        </div>
      </article>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="application/json"
      class="hidden"
      @change="handleImportFile"
    >
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { themeGroups as groups } from '../../../settings/theme/defaultPalette'
import {
  exportThemeConfig,
  getCurrentThemeValues,
  importThemeConfig,
  loadThemeOverrides,
  resetThemeToDefaults,
  updateThemeVariable
} from '../../../settings/theme/themeManager'

const themeValues = ref({})
const overrides = ref({})
const statusMessage = ref('')
const statusTone = ref('neutral')
const fileInput = ref(null)
let statusTimer = null

const overrideCount = computed(() => Object.keys(overrides.value || {}).length)

const setStatus = (message, tone = 'neutral') => {
  statusMessage.value = message
  statusTone.value = tone

  if (statusTimer) {
    window.clearTimeout(statusTimer)
  }

  if (message) {
    statusTimer = window.setTimeout(() => {
      statusMessage.value = ''
    }, 3200)
  }
}

const refresh = () => {
  themeValues.value = getCurrentThemeValues()
  overrides.value = loadThemeOverrides()
}

onMounted(() => {
  refresh()
})

onBeforeUnmount(() => {
  if (statusTimer) {
    window.clearTimeout(statusTimer)
  }
})

const normalizeHex = (value) => {
  if (!value) return '#000000'
  let hex = value.trim().replace('#', '')
  if (hex.length === 3) {
    hex = hex.split('').map((char) => char + char).join('')
  }
  if (hex.length !== 6) {
    return '#000000'
  }
  return `#${hex.toLowerCase()}`
}

const rgbToHex = (rgbString) => {
  const parts = rgbString.trim().split(/\s+/).map((part) => Number(part))
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
    return '#000000'
  }
  const hex = parts.map((part) => {
    const clamped = Math.min(255, Math.max(0, Math.round(part)))
    return clamped.toString(16).padStart(2, '0')
  }).join('')
  return `#${hex}`
}

const hexToRgbString = (hex) => {
  const normalized = normalizeHex(hex).replace('#', '')
  const rgb = [0, 2, 4].map((index) => parseInt(normalized.slice(index, index + 2), 16))
  return rgb.join(' ')
}

const hexValue = (token) => {
  const value = themeValues.value[token.variable] || ''
  if (token.format === 'rgb') {
    return rgbToHex(value || '0 0 0')
  }
  return normalizeHex(value || token.default)
}

const displayValue = (token) => themeValues.value[token.variable] || token.default

const previewTextColor = (token) => {
  if (token.variant === 'outline') {
    return 'var(--color-text-secondary)'
  }
  return token.previewTextColor || 'var(--color-surface)'
}

const previewStyle = (token) => {
  const value = themeValues.value[token.variable] || token.default

  if (token.variant === 'outline') {
    return {
      borderColor: token.format === 'rgb' ? `rgb(${value})` : value,
      color: previewTextColor(token)
    }
  }

  const background = token.format === 'rgb' ? `rgb(${value})` : value
  return {
    backgroundColor: background,
    color: token.previewTextColor || '#ffffff'
  }
}

const isOverridden = (variable) => Boolean(overrides.value && overrides.value[variable])

const handleColorInput = (token, hex) => {
  const value = token.format === 'rgb' ? hexToRgbString(hex) : normalizeHex(hex)
  try {
    overrides.value = updateThemeVariable(token.variable, value)
    themeValues.value[token.variable] = value
    setStatus(`${token.label} 已更新`, 'success')
  } catch (error) {
    console.error(error)
    setStatus(`更新 ${token.label} 失败`, 'danger')
  }
}

const restoreDefault = (variable) => {
  try {
    overrides.value = updateThemeVariable(variable, '')
    refresh()
    setStatus('已恢复默认颜色', 'success')
  } catch (error) {
    console.error(error)
    setStatus('恢复默认颜色失败', 'danger')
  }
}

const triggerImport = () => {
  fileInput.value?.click()
}

const handleImportFile = async (event) => {
  const [file] = event.target.files || []
  event.target.value = ''
  if (!file) return

  try {
    const text = await file.text()
    const parsed = JSON.parse(text)
    importThemeConfig(parsed)
    refresh()
    setStatus('配置已导入并应用', 'success')
  } catch (error) {
    console.error(error)
    setStatus('导入失败，请确认文件格式正确。', 'danger')
  }
}

const handleExport = () => {
  try {
    const payload = exportThemeConfig()
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `theme-config-${new Date().toISOString().replace(/[:.]/g, '-')}.json`
    anchor.click()
    window.URL.revokeObjectURL(url)
    setStatus('配置已导出', 'success')
  } catch (error) {
    console.error(error)
    setStatus('导出失败', 'danger')
  }
}

const resetAll = () => {
  resetThemeToDefaults()
  refresh()
  setStatus('主题已还原为默认配色', 'success')
}

defineExpose({
  refresh,
  resetAll
})
</script>

<style scoped>
.theme-editor {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.theme-editor__header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 1rem 1.5rem;
}

.theme-editor__intro h2 {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.theme-editor__intro p {
  margin: 0.6rem 0 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.theme-editor__meta {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: var(--color-accent-600-hex);
}

.theme-editor__meta strong {
  font-weight: 700;
  color: var(--color-brand-600-hex);
}

.theme-editor__tools {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.ghost-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  border-radius: 9999px;
  border: 1px solid var(--color-border-soft);
  padding: 0.45rem 1.1rem;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background-color: rgba(255, 255, 255, 0.68);
  transition: all 0.15s ease;
}

.ghost-button:hover {
  border-color: rgb(var(--color-brand-200) / 1);
  background-color: rgb(var(--color-brand-100) / 0.45);
  color: var(--color-brand-600-hex);
}

.ghost-button--small {
  padding: 0.35rem 0.8rem;
  font-size: 0.78rem;
}

.theme-editor__status {
  margin: 0;
  padding: 0.65rem 1rem;
  border-radius: 14px;
  font-size: 0.85rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.theme-editor__status--neutral {
  background-color: rgb(var(--color-accent-50) / 1);
  color: var(--color-text-secondary);
}

.theme-editor__status--success {
  background-color: rgb(var(--color-success-100) / 1);
  color: rgb(var(--color-success-600) / 1);
}

.theme-editor__status--danger {
  background-color: rgb(var(--color-danger-100) / 1);
  color: rgb(var(--color-danger-600) / 1);
}

.theme-editor__groups {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.theme-editor__group {
  border-radius: 22px;
  border: 1px solid var(--color-border-soft);
  background-color: var(--color-surface);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.theme-editor__group-header h3 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.theme-editor__group-header p {
  margin: 0.35rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.9rem;
}

.theme-editor__tokens {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.theme-editor__token {
  display: grid;
  grid-template-columns: minmax(0, 180px) minmax(0, 1fr) auto;
  align-items: center;
  gap: 1rem;
  padding: 0.9rem 1.1rem;
  border-radius: 16px;
  background-color: rgba(243, 245, 248, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.theme-editor__preview {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 52px;
  border-radius: 14px;
  font-weight: 600;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border: 1px solid transparent;
}

.theme-editor__preview--outline {
  background-color: var(--color-surface);
}

.theme-editor__details p {
  margin: 0;
  font-weight: 600;
  color: var(--color-text-primary);
}

.theme-editor__details code {
  display: block;
  margin-top: 0.35rem;
  font-size: 0.82rem;
  color: var(--color-text-muted);
  background-color: rgba(255, 255, 255, 0.8);
  padding: 0.25rem 0.5rem;
  border-radius: 10px;
}

.theme-editor__controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.theme-editor__color-picker input {
  width: 42px;
  height: 42px;
  border: none;
  border-radius: 12px;
  background: transparent;
  cursor: pointer;
  padding: 0;
}

@media (max-width: 960px) {
  .theme-editor__token {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-areas:
      'preview preview'
      'details controls';
    gap: 0.75rem;
  }

  .theme-editor__preview {
    grid-area: preview;
  }

  .theme-editor__details {
    grid-area: details;
  }

  .theme-editor__controls {
    grid-area: controls;
    justify-content: flex-end;
  }
}

@media (max-width: 640px) {
  .theme-editor__tools {
    width: 100%;
    justify-content: flex-start;
  }

  .theme-editor__token {
    padding: 0.85rem;
  }

  .theme-editor__color-picker input {
    width: 36px;
    height: 36px;
  }
}
</style>
