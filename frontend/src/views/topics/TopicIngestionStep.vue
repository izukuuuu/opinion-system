<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">数据入库</h1>
        <p class="text-sm text-secondary">
          读取筛选后的 JSONL 并写入业务库表，可直接调用 `/api/upload` 校验整个“入库”环节。
        </p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <ArrowTrendingUpIcon class="h-4 w-4" />
        <span>步骤 4 · 入库</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">准备入库参数</h2>
        <p class="text-sm text-secondary">
          请选择需要写入的专题与日期，系统将默认读取 Filter 阶段产物并写入同名数据库。
        </p>
      </header>

      <div class="space-y-2 text-xs text-secondary">
        <p>
          当前项目：
          <span class="font-semibold text-primary">
            {{ activeProjectName || '尚未选择' }}
          </span>
        </p>
        <p class="text-muted">
          为防止误操作，执行前请确认 Filter 目录内的 JSONL 已最终定版。
        </p>
      </div>

      <div class="grid gap-6 md:grid-cols-2">
        <label class="space-y-2 text-sm">
          <span class="font-medium text-secondary">数据集名称</span>
          <input
            v-model.trim="datasetNameInput"
            type="text"
            class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
            placeholder="例如：校园安全专项-筛选结果"
          />
          <p class="text-xs text-muted">用于记录上传批次的显示名称，不等同于数据库标识。</p>
        </label>

        <label class="space-y-2 text-sm">
          <span class="font-medium text-secondary">数据存储标识（数据库名 / Bucket）</span>
          <div class="rounded-2xl border border-dashed border-soft bg-surface-muted px-4 py-2 text-sm">
            {{ bucketName || '请选择一个项目后自动填充' }}
          </div>
          <p class="text-xs text-muted">自动与当前项目的 Filter 目录保持一致，不可手动修改。</p>
        </label>
      </div>

      <label class="space-y-2 text-sm">
        <span class="font-medium text-secondary">筛选完成日期</span>
        <template v-if="availableDates.length">
          <select
            v-model="processingDate"
            class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
          >
            <option
              v-for="date in availableDates"
              :key="date"
              :value="date"
            >
              {{ date }}
            </option>
          </select>
          <p class="text-xs text-muted">
            选项来自项目记录（projects.json / storage），默认选中最近一次筛选。
          </p>
        </template>
        <template v-else>
          <div class="flex flex-wrap items-center gap-2">
            <input
              v-model="processingDate"
              type="date"
              class="flex-1 rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              @click="resetToToday"
            >
              使用今天
            </button>
          </div>
        </template>
      </label>

      <div
        class="rounded-3xl border border-dashed border-brand-soft bg-brand-soft-muted px-5 py-4 text-xs leading-relaxed text-secondary"
      >
        <p class="font-semibold text-brand-700">
          预计读取目录：
          <code class="rounded bg-white/70 px-2 py-0.5 text-[11px] text-brand-700">
            {{ inferredFilterPath || 'backend/data/projects/<topic>/filter/<date>' }}
          </code>
        </p>
        <p class="mt-2 text-muted">
          决策逻辑：系统将为每个 JSONL（以频道命名）创建/追加
          <code class="rounded bg-white px-1 py-0.5 text-[11px] text-secondary">topic.channel</code>
          表，并使用标准字段结构。在运行前请确认数据库具备写入权限。
        </p>
      </div>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">执行入库</h2>
        <p class="text-sm text-secondary">
          按照步骤核对数据后点击按钮即可写入数据库；如需在服务器上人工执行，可参考下方命令。
        </p>
      </header>

      <div class="rounded-3xl border border-dashed border-soft bg-surface-muted/60 p-5 text-sm text-secondary">
        <p class="text-xs uppercase tracking-[0.3em] text-muted">执行提示</p>
        <ol class="mt-3 space-y-2 pl-5">
          <li class="marker:text-brand-500">
            确认上一步的筛选结果已经整理完毕，目录与上方“预计读取目录”一致。
          </li>
          <li class="marker:text-brand-500">
            点击下方“一键入库”，系统会调用 <code class="rounded bg-white px-1 py-0.5 text-[11px] text-primary">/api/upload</code>、自动建表并写入数据。
          </li>
          <li class="marker:text-brand-500">
            如果希望在服务器上手动执行，可输入：
            <code class="mt-1 block rounded bg-white px-2 py-1 text-[11px] text-primary">{{ cliCommand }}</code>
          </li>
        </ol>
        <p class="mt-3 text-xs text-muted">
          * 入库完成后会显示成功/失败信息，并在下方的运行记录中保留本次操作。
        </p>
      </div>

      <div class="space-y-4">
        <button
          type="button"
          class="btn-base btn-tone-primary w-full justify-center px-5 py-2 text-sm sm:w-auto"
          :disabled="uploadState.running"
          @click="runUpload"
        >
          {{ uploadState.running ? '执行中…' : '执行 /api/upload 入库' }}
        </button>

        <p
          v-if="parameterError"
          class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600"
        >
          {{ parameterError }}
        </p>

        <p
          v-if="uploadState.message"
          :class="[
            'rounded-2xl px-4 py-2 text-sm',
            uploadState.success ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-600'
          ]"
        >
          {{ uploadState.message }}
        </p>

        <div
          v-if="uploadState.lastResponse"
          class="rounded-3xl border border-dashed border-soft bg-white/80 p-4 text-xs text-secondary"
        >
          <p class="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">响应详情</p>
          <pre class="max-h-60 overflow-y-auto whitespace-pre-wrap break-words">
{{ formattedResponse }}
          </pre>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-xl font-semibold text-primary">运行记录</h2>
          <span class="text-xs text-muted">
            {{ runHistory.length ? `保留最近 ${runHistory.length} 次` : '暂无记录' }}
          </span>
        </div>
        <p class="text-sm text-secondary">
          记录包含执行时间、专题与日期，便于快速复查某一次入库的状态。
        </p>
      </header>

      <div
        v-if="!runHistory.length"
        class="rounded-3xl border border-dashed border-soft bg-surface-muted/60 px-5 py-4 text-sm text-muted"
      >
        目前没有历史执行，配置参数后点击“执行入库”即可在此查看结果。
      </div>
      <ul v-else class="space-y-3 text-sm">
        <li
          v-for="entry in runHistory"
          :key="entry.timestamp"
          class="rounded-3xl border border-soft bg-white px-5 py-4 shadow-sm"
        >
          <div class="flex flex-wrap items-center justify-between gap-3 text-xs">
            <div class="flex flex-wrap items-center gap-2 text-secondary">
              <span
                :class="[
                  'rounded-full px-2 py-0.5 font-semibold',
                  entry.success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
                ]"
              >
                {{ entry.success ? '成功' : '失败' }}
              </span>
              <span class="text-muted">{{ formatHistoryTimestamp(entry.timestamp) }}</span>
            </div>
            <div class="text-right text-xs text-secondary">
              <code class="block rounded bg-surface-muted px-2 py-0.5 text-[11px]">
                数据库：{{ entry.topic }}
              </code>
              <span class="mt-1 block text-muted">日期：{{ entry.date }}</span>
            </div>
          </div>
          <p v-if="entry.topic_label || entry.project" class="mt-2 text-xs text-secondary">
            专题：{{ entry.topic_label || entry.project }}
            <span
              v-if="entry.topic_label && entry.project && entry.topic_label !== entry.project"
              class="ml-2 text-muted"
            >
              （项目：{{ entry.project }}）
            </span>
          </p>
          <p class="mt-2 text-sm text-primary">
            {{ entry.message }}
          </p>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  ArrowTrendingUpIcon
} from '@heroicons/vue/24/outline'
import { useActiveProject } from '../../composables/useActiveProject'
import { useApiBase } from '../../composables/useApiBase'

const { ensureApiBase } = useApiBase()
const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}
const HISTORY_LIMIT = 6

const { activeProject, activeProjectName } = useActiveProject()

const datasetNameInput = ref('')
const processingDate = ref(getToday())
const parameterError = ref('')
const uploadState = reactive({
  running: false,
  success: null,
  message: '',
  details: null,
  lastResponse: null
})
const runHistory = ref([])

const slugifyName = (value) => {
  if (!value) return ''
  const normalised = value
    .trim()
    .toLowerCase()
    .replace(/[^\w-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
  return normalised || value.trim()
}

const normaliseStoragePath = (value) => {
  if (typeof value !== 'string') return ''
  return value.replace(/\\/g, '/').replace(/^\/+/, '').trim()
}

const resolveBucketFromProject = (project) => {
  if (!project || typeof project !== 'object') return ''
  const directId = typeof project.id === 'string' ? project.id.trim() : ''
  if (directId) return directId
  const legacyId = typeof project.identifier === 'string' ? project.identifier.trim() : ''
  if (legacyId) return legacyId
  const storagePath = normaliseStoragePath(project.storage_path)
  if (storagePath) {
    const parts = storagePath.split('/').filter(Boolean)
    return parts[parts.length - 1] || ''
  }
  const projectName = typeof project.name === 'string' ? project.name.trim() : ''
  return projectName ? slugifyName(projectName) : ''
}

const activeProjectBucket = computed(() => resolveBucketFromProject(activeProject.value))

const availableDates = computed(() => {
  const raw = activeProject.value?.dates
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean)
    .sort()
})

const bucketName = computed(() => activeProjectBucket.value || '')

const inferredFilterBase = computed(() => {
  const storagePath = normaliseStoragePath(activeProject.value?.storage_path)
  if (storagePath && bucketName.value === activeProjectBucket.value) {
    return `backend/data/${storagePath}`
  }
  if (bucketName.value) {
    return `backend/data/projects/${bucketName.value}`
  }
  return ''
})

const inferredFilterPath = computed(() => {
  if (!inferredFilterBase.value || !processingDate.value) return ''
  return `${inferredFilterBase.value}/filter/${processingDate.value}`
})
const cliCommand = computed(() => {
  const topic = bucketName.value || '<topic>'
  const date = processingDate.value || '<YYYY-MM-DD>'
  return `python backend/main.py Upload --topic ${topic} --date ${date}`
})
const formattedResponse = computed(() => {
  if (!uploadState.lastResponse) return ''
  try {
    return JSON.stringify(uploadState.lastResponse, null, 2)
  } catch (error) {
    return String(uploadState.lastResponse)
  }
})

watch(
  () => activeProject.value,
  (project) => {
    const projectName =
      typeof project?.name === 'string' && project.name.trim() ? project.name.trim() : ''
    if (!datasetNameInput.value && projectName) {
      datasetNameInput.value = projectName
    } else if (!datasetNameInput.value && activeProjectName.value) {
      datasetNameInput.value = activeProjectName.value
    }

    if (availableDates.value.length) {
      const latest = availableDates.value[availableDates.value.length - 1]
      if (!processingDate.value || !availableDates.value.includes(processingDate.value)) {
        processingDate.value = latest
      }
    }
  },
  { immediate: true }
)

watch(
  () => activeProjectName.value,
  (value) => {
    if (!datasetNameInput.value && value) {
      datasetNameInput.value = value
    }
  }
)

function getToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const resetToToday = () => {
  processingDate.value = getToday()
}

const historyTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit'
})

const formatHistoryTimestamp = (value) => {
  if (!value) return ''
  try {
    const dateObj = new Date(value)
    if (Number.isNaN(dateObj.getTime())) {
      return value
    }
    return historyTimeFormatter.format(dateObj)
  } catch (error) {
    return value
  }
}

const ensureParameters = () => {
  const topic = bucketName.value
  if (!topic) {
    parameterError.value = '未找到对应的数据库标识，请先选择项目。'
    return null
  }
  if (!processingDate.value) {
    parameterError.value = '请选择筛选对应的日期。'
    return null
  }
  if (!datasetNameInput.value.trim()) {
    parameterError.value = '请填写数据集名称。'
    return null
  }
  parameterError.value = ''
  const topicLabel = datasetNameInput.value.trim()
  const projectReference =
    typeof activeProjectName.value === 'string' ? activeProjectName.value.trim() : ''
  return {
    topic,
    date: processingDate.value,
    project: projectReference,
    topic_label: topicLabel
  }
}

const pushHistoryEntry = (payload, success, message) => {
  const entry = {
    ...payload,
    success,
    message,
    timestamp: new Date().toISOString()
  }
  runHistory.value = [entry, ...runHistory.value].slice(0, HISTORY_LIMIT)
}

const runUpload = async () => {
  const params = ensureParameters()
  if (!params) return

  const payload = {
    topic: params.topic,
    date: params.date
  }
  if (params.project) {
    payload.project = params.project
  }
  if (params.topic_label) {
    payload.topic_label = params.topic_label
  }

  uploadState.running = true
  uploadState.message = ''
  uploadState.success = null
  uploadState.details = null
  uploadState.lastResponse = null

  try {
    const endpoint = await buildApiUrl('/upload')
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    let result
    try {
      result = await response.json()
    } catch {
      result = { status: 'error', message: '无法解析后端响应' }
    }
    const ok = response.ok && result.status !== 'error'
    uploadState.success = ok
    uploadState.message = ok ? '筛选结果已成功写入数据库。' : result.message || '入库失败，请查看后端日志。'
    uploadState.details = result.data ?? null
    uploadState.lastResponse = result
    pushHistoryEntry(params, ok, uploadState.message)
  } catch (error) {
    uploadState.success = false
    uploadState.message =
      error instanceof Error ? error.message : '入库失败，请检查网络或服务器状态。'
    uploadState.details = null
    uploadState.lastResponse = null
    pushHistoryEntry(params, false, uploadState.message)
  } finally {
    uploadState.running = false
  }
}
</script>
