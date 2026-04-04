<template>
  <section class="card-surface space-y-6 p-6">
    <header class="settings-page-header">
      <p class="settings-page-eyebrow">存档工具</p>
      <h2 class="settings-page-title">环境存档导入与导出</h2>
      <p class="settings-page-desc">
        打包当前环境的重要配置和项目数据，或从已有存档恢复到当前环境。
      </p>
    </header>

    <div class="settings-message-warning">
      导入会覆盖现有同名内容，开始前请先备份重要数据。
    </div>

    <section class="settings-section settings-section-split">
      <header class="settings-section-header">
        <h3 class="settings-section-title">导出存档</h3>
        <p class="settings-section-desc">将当前环境整理成 ZIP 存档并下载到本地。</p>
      </header>

      <div class="space-y-4">
        <button
          type="button"
          class="btn-primary w-full px-6 py-3 text-sm"
          :disabled="exportState.loading"
          @click="handleExport"
        >
          <span v-if="exportState.loading" class="h-4 w-4 animate-spin rounded-full border-2 border-white/60 border-t-white"></span>
          <ArrowDownTrayIcon v-else class="h-4 w-4 shrink-0" />
          <span>{{ exportState.loading ? '打包中…' : '导出存档' }}</span>
        </button>

        <div v-if="exportState.message" class="settings-message-success">
          {{ exportState.message }}
        </div>

        <div v-if="exportState.error" class="settings-message-error">
          {{ exportState.error }}
        </div>

        <div v-if="exportState.included.length > 0" class="settings-help-block">
          <p class="mb-2 text-xs font-semibold text-primary">本次存档包含：</p>
          <ul class="space-y-1 text-xs text-secondary">
            <li v-for="item in exportState.included" :key="item" class="flex items-start gap-2">
              <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-soft"></span>
              <span class="break-all">{{ item }}</span>
            </li>
          </ul>
        </div>

        <div v-if="exportState.missing.length > 0" class="settings-message-warning">
          <p class="mb-2 text-xs font-semibold">以下内容未找到：</p>
          <ul class="space-y-1 text-xs">
            <li v-for="item in exportState.missing" :key="item" class="flex items-start gap-2">
              <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-warning-soft"></span>
              <span class="break-all">{{ item }}</span>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <section class="settings-section settings-section-split">
      <header class="settings-section-header">
        <h3 class="settings-section-title">导入存档</h3>
        <p class="settings-section-desc">上传之前导出的 ZIP 存档并恢复到当前环境。</p>
      </header>

      <div class="space-y-4">
        <label class="space-y-2.5">
          <span class="block text-sm font-semibold text-primary">选择 ZIP 文件</span>
          <input
            type="file"
            accept=".zip,application/zip"
            class="input block w-full cursor-pointer file:mr-4 file:cursor-pointer file:rounded-full file:border-0 file:bg-surface-muted file:px-4 file:py-2 file:text-sm file:font-semibold file:text-secondary"
            @change="handleFileChange"
          />
        </label>

        <p v-if="importState.selectedName" class="text-xs text-muted">
          已选择：{{ importState.selectedName }}
        </p>

        <button
          type="button"
          class="btn-primary w-full px-6 py-3 text-sm"
          :disabled="importState.loading || !importState.file"
          @click="handleImport"
        >
          <span v-if="importState.loading" class="h-4 w-4 animate-spin rounded-full border-2 border-white/70 border-t-white"></span>
          <ArrowUpTrayIcon v-else class="h-4 w-4 shrink-0" />
          <span>{{ importState.loading ? '导入中…' : '上传并导入' }}</span>
        </button>

        <div v-if="importState.message" class="settings-message-success">
          {{ importState.message }}
        </div>

        <div v-if="importState.error" class="settings-message-error">
          {{ importState.error }}
        </div>

        <div v-if="importState.restored.length" class="settings-help-block">
          <p class="mb-2 text-xs font-semibold text-primary">已恢复的内容：</p>
          <ul class="space-y-1 text-xs text-secondary">
            <li v-for="item in importState.restored" :key="item" class="flex items-start gap-2">
              <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-success-soft"></span>
              <span class="break-all">{{ item }}</span>
            </li>
          </ul>
        </div>

        <div v-if="importState.skipped.length" class="settings-message-warning">
          <p class="mb-2 text-xs font-semibold">以下内容已跳过：</p>
          <ul class="space-y-1 text-xs">
            <li v-for="item in importState.skipped" :key="item" class="flex items-start gap-2">
              <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-warning-soft"></span>
              <span class="break-all">{{ item }}</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  </section>
</template>

<script setup>
import { reactive } from 'vue'
import { ArrowDownTrayIcon, ArrowUpTrayIcon } from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'

const { ensureApiBase } = useApiBase()

const buildApiUrl = async (path) => {
  const base = await ensureApiBase()
  return `${base}${path}`
}

const exportState = reactive({
  loading: false,
  message: '',
  error: '',
  included: [],
  missing: []
})

const importState = reactive({
  loading: false,
  message: '',
  error: '',
  file: null,
  selectedName: '',
  restored: [],
  skipped: []
})

const parseFilename = (contentDisposition) => {
  if (!contentDisposition || typeof contentDisposition !== 'string') {
    return `opinion-backup-${Date.now()}.zip`
  }
  const utf8Match = contentDisposition.match(/filename\*=(?:UTF-8'')?([^;]+)/i)
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1].replace(/"/g, '').trim())
    } catch {
      return utf8Match[1].replace(/"/g, '').trim()
    }
  }
  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  if (plainMatch && plainMatch[1]) {
    return plainMatch[1].trim()
  }
  return `opinion-backup-${Date.now()}.zip`
}

const parseHeaderList = (value) => {
  if (!value || typeof value !== 'string') return []
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

const handleExport = async () => {
  exportState.loading = true
  exportState.error = ''
  exportState.message = ''
  exportState.included = []
  exportState.missing = []
  try {
    const endpoint = await buildApiUrl('/settings/archives/export')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('导出存档失败')
    }
    const blob = await response.blob()
    const downloadUrl = window.URL.createObjectURL(blob)
    const filename = parseFilename(response.headers.get('Content-Disposition'))
    const anchor = document.createElement('a')
    anchor.href = downloadUrl
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.URL.revokeObjectURL(downloadUrl)

    exportState.included = parseHeaderList(response.headers.get('X-Backup-Roots'))
    exportState.missing = parseHeaderList(response.headers.get('X-Backup-Missing'))
    exportState.message = '存档已生成并开始下载'
  } catch (err) {
    exportState.error = err instanceof Error ? err.message : '导出存档失败'
  } finally {
    exportState.loading = false
  }
}

const handleFileChange = (event) => {
  const [file] = event.target.files || []
  importState.file = file || null
  importState.selectedName = file ? file.name : ''
  importState.message = ''
  importState.error = ''
  importState.restored = []
  importState.skipped = []
}

const handleImport = async () => {
  if (!importState.file) {
    importState.error = '请先选择 ZIP 存档文件'
    return
  }
  importState.loading = true
  importState.error = ''
  importState.message = ''
  importState.restored = []
  importState.skipped = []

  try {
    const endpoint = await buildApiUrl('/settings/archives/import')
    const formData = new FormData()
    formData.append('file', importState.file)

    const response = await fetch(endpoint, {
      method: 'POST',
      body: formData
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || '导入存档失败')
    }
    const payload = await response.json()
    const data = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    importState.restored = Array.isArray(data.restored) ? data.restored : []
    importState.skipped = Array.isArray(data.skipped) ? data.skipped : []
    importState.message = `导入成功，写入 ${importState.restored.length} 个文件`
  } catch (err) {
    importState.error = err instanceof Error ? err.message : '导入存档失败'
  } finally {
    importState.loading = false
  }
}
</script>
