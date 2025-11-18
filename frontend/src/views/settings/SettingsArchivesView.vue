<template>
  <div class="mx-auto space-y-6">
    <!-- 头部说明区域 -->
    <section class="card-surface space-y-6">
      <div class="space-y-4 p-6 sm:p-8">
        <header class="space-y-3">
          <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-600">
              <ArrowDownTrayIcon class="h-5 w-5" />
            </div>
            <div class="flex-1">
              <p class="text-xs font-semibold uppercase tracking-[0.38em] text-slate-400">存档工具</p>
              <h2 class="mt-1 text-2xl font-bold text-slate-900">配置存档导入 / 导出</h2>
            </div>
          </div>
          <div class="ml-0 space-y-3 sm:ml-14 sm:pl-4">
            <p class="text-sm leading-relaxed text-slate-600">
              一键打包或恢复被 git 忽略的关键配置文件，便于在不同环境间快速迁移或备份恢复。
              存档将包含所有必要的环境配置和本地数据文件。
            </p>
            <div class="flex flex-wrap gap-3">
              <span class="inline-flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-2 text-sm font-medium text-amber-800 ring-1 ring-inset ring-amber-200">
                <ExclamationTriangleIcon class="h-4 w-4 shrink-0" />
                <span>导入会覆盖现有同名文件，请提前备份重要数据</span>
              </span>
            </div>
          </div>
        </header>
      </div>
    </section>

    <!-- 功能操作区域 -->
    <section class="grid gap-6 lg:grid-cols-2">
      <!-- 导出存档卡片 -->
      <div class="card-surface group relative overflow-hidden p-6 transition-all sm:p-8">
        <div class="space-y-5">
          <header class="space-y-3">
            <div class="inline-flex items-center gap-2.5 rounded-full bg-brand-100 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.3em] text-brand-700">
              <ArrowDownTrayIcon class="h-4 w-4 shrink-0" />
              <span>导出存档</span>
            </div>
            <p class="text-sm leading-relaxed text-slate-600">
              将当前环境的配置文件打包为 ZIP 存档，自动触发浏览器下载，便于迁移或人工备份。
            </p>
          </header>

          <div class="space-y-4">
            <button
              type="button"
              class="group/btn inline-flex w-full items-center justify-center gap-2.5 rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-brand-500  focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-brand-600 disabled:hover:shadow-sm"
              :disabled="exportState.loading"
              @click="handleExport"
            >
              <span v-if="exportState.loading" class="h-4 w-4 animate-spin rounded-full border-2 border-white/60 border-t-white"></span>
              <ArrowDownTrayIcon v-else class="h-4 w-4 shrink-0 transition-transform group-hover/btn:scale-110" />
              <span>{{ exportState.loading ? '打包中…' : '导出存档' }}</span>
            </button>

            <!-- 成功消息 -->
            <div v-if="exportState.message" class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 ring-1 ring-inset ring-emerald-100">
              <p class="flex items-center gap-2 text-sm font-medium text-emerald-800">
                <svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd" />
                </svg>
                <span>{{ exportState.message }}</span>
              </p>
            </div>

            <!-- 错误消息 -->
            <div v-if="exportState.error" class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 ring-1 ring-inset ring-rose-100">
              <p class="flex items-center gap-2 text-sm font-medium text-rose-800">
                <svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
                </svg>
                <span>{{ exportState.error }}</span>
              </p>
            </div>

            <!-- 缺失文件提示 -->
            <div v-if="exportState.missing.length > 0" class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 ring-1 ring-inset ring-amber-100">
              <p class="mb-2 text-xs font-semibold text-amber-800">以下路径在当前环境中未找到：</p>
              <ul class="space-y-1 text-xs text-amber-700">
                <li v-for="item in exportState.missing" :key="item" class="flex items-start gap-2">
                  <span class="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400"></span>
                  <span class="break-all">{{ item }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <!-- 导入存档卡片 -->
      <div class="card-surface group relative overflow-hidden p-6 transition-all sm:p-8">
        <div class="space-y-5">
          <header class="space-y-3">
            <div class="inline-flex items-center gap-2.5 rounded-full bg-slate-100 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.3em] text-slate-700">
              <ArrowUpTrayIcon class="h-4 w-4 shrink-0" />
              <span>导入存档</span>
            </div>
            <p class="text-sm leading-relaxed text-slate-600">
              选择之前导出的 ZIP 存档文件并上传，系统将自动解压并恢复相应的配置文件。
            </p>
          </header>

          <div class="space-y-4">
            <!-- 文件选择 -->
            <div class="space-y-2.5">
              <label class="block text-sm font-semibold text-slate-700">选择 ZIP 文件</label>
              <div class="relative">
                <input
                  type="file"
                  accept=".zip,application/zip"
                  class="block w-full cursor-pointer rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-700 file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-slate-100 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-slate-700 hover:file:bg-slate-200 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1 transition-colors"
                  @change="handleFileChange"
                />
              </div>
              <p v-if="importState.selectedName" class="flex items-center gap-2 text-xs text-slate-500">
                <svg class="h-3.5 w-3.5 shrink-0 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span class="truncate font-medium">已选择：{{ importState.selectedName }}</span>
              </p>
            </div>

            <!-- 导入按钮 -->
            <button
              type="button"
              class="group/btn inline-flex w-full items-center justify-center gap-2.5 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-slate-800  focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-slate-900 disabled:hover:shadow-sm"
              :disabled="importState.loading || !importState.file"
              @click="handleImport"
            >
              <span v-if="importState.loading" class="h-4 w-4 animate-spin rounded-full border-2 border-white/70 border-t-white"></span>
              <ArrowUpTrayIcon v-else class="h-4 w-4 shrink-0 transition-transform group-hover/btn:scale-110" />
              <span>{{ importState.loading ? '导入中…' : '上传并导入' }}</span>
            </button>

            <!-- 成功消息 -->
            <div v-if="importState.message" class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 ring-1 ring-inset ring-emerald-100">
              <p class="flex items-center gap-2 text-sm font-medium text-emerald-800">
                <svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd" />
                </svg>
                <span>{{ importState.message }}</span>
              </p>
            </div>

            <!-- 错误消息 -->
            <div v-if="importState.error" class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 ring-1 ring-inset ring-rose-100">
              <p class="flex items-center gap-2 text-sm font-medium text-rose-800">
                <svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
                </svg>
                <span>{{ importState.error }}</span>
              </p>
            </div>

            <!-- 恢复的文件列表 -->
            <div v-if="importState.restored.length" class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 ring-1 ring-inset ring-emerald-100">
              <p class="mb-2 text-xs font-semibold text-emerald-800">已恢复的文件：</p>
              <ul class="space-y-1 text-xs text-emerald-700">
                <li v-for="item in importState.restored" :key="item" class="flex items-start gap-2">
                  <svg class="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
                  </svg>
                  <span class="break-all">{{ item }}</span>
                </li>
              </ul>
            </div>

            <!-- 跳过的文件列表 -->
            <div v-if="importState.skipped.length" class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 ring-1 ring-inset ring-amber-100">
              <p class="mb-2 text-xs font-semibold text-amber-800">被跳过的文件（不在允许范围或校验失败）：</p>
              <ul class="space-y-1 text-xs text-amber-700">
                <li v-for="item in importState.skipped" :key="item" class="flex items-start gap-2">
                  <span class="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400"></span>
                  <span class="break-all">{{ item }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { ArrowDownTrayIcon, ArrowUpTrayIcon, ExclamationTriangleIcon } from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'

const { ensureApiBase } = useApiBase()

const buildApiUrl = async (path) => {
  const base = await ensureApiBase()
  return `${base}/api${path}`
}

const exportState = reactive({
  loading: false,
  message: '',
  error: '',
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
