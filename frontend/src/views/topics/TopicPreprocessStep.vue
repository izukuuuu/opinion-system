<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">数据预处理</h1>
        <p class="text-sm text-secondary">按日期依次执行 Merge、Clean，生成标准化结果。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <FunnelIcon class="h-4 w-4" />
        <span>步骤 2 · 预处理</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">选择数据集</h2>
        <p class="text-sm text-secondary">
          请选择需要预处理的数据集，系统会自动使用当前项目名称与处理日期执行任务。
        </p>
      </header>
<form class="space-y-4">
  <p class="text-xs text-secondary">
    当前项目：<span class="font-semibold text-primary">{{ currentProjectName }}</span>
  </p>
  <label class="space-y-1 text-sm">
    <span class="font-medium text-secondary">选择数据集</span>
    <div class="flex flex-wrap items-center gap-3">
      <select
        v-if="datasetOptions.length"
        v-model="selectedDatasetId"
        class="inline-flex min-w-[220px] items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
        :disabled="datasetsLoading"
      >
        <option v-for="option in datasetOptions" :key="option.id" :value="option.id">
          {{ option.label }}
        </option>
      </select>
      <span v-else class="text-xs text-muted">
        当前项目暂无可用数据集，请先在“项目数据”页面完成上传。
      </span>
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="datasetsLoading"
        @click="refreshDatasets"
      >
        {{ datasetsLoading ? '加载中…' : '刷新数据集' }}
      </button>
    </div>
    <p v-if="datasetsError" class="mt-2 rounded-2xl bg-rose-50 px-3 py-1 text-xs text-rose-600">
      {{ datasetsError }}
    </p>
  </label>
</form>
<p v-if="parameterError" class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600">{{ parameterError }}</p>
    </section>

    <section class="space-y-5">
      <div class="card-surface flex flex-wrap items-center justify-between gap-3 p-6">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">预处理执行</h2>
          <p class="text-sm text-secondary">可单独运行每个步骤，或使用一键执行快速完成 Merge 与 Clean。</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-brand-soft px-4 py-2 text-sm font-semibold text-brand-600 transition hover:bg-brand-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="pipeline.running"
          @click="runPipeline"
        >
          <SparklesIcon class="h-4 w-4" />
          <span>{{ pipeline.running ? '执行中…' : '一键执行 Pipeline' }}</span>
        </button>
      </div>

      <div class="space-y-5">
        <article
          v-for="operation in operations"
          :key="operation.key"
          class="card-surface space-y-4 p-6"
        >
          <header class="flex items-center gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-2xl bg-brand-soft text-brand-600">
              <component :is="operation.icon" class="h-5 w-5" />
            </span>
            <div>
              <p class="text-xs uppercase tracking-[0.2em] text-muted">{{ operation.subtitle }}</p>
              <h3 class="text-base font-semibold text-primary">{{ operation.title }}</h3>
            </div>
          </header>
          <p class="text-sm leading-relaxed text-secondary">
            {{ operation.description }}
          </p>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              class="btn-base btn-tone-primary px-4 py-1.5"
              :disabled="statuses[operation.key].running"
              @click="runOperation(operation.key)"
            >
              <span v-if="statuses[operation.key].running">执行中…</span>
              <span v-else>执行 {{ operation.label }}</span>
            </button>
            <p
              v-if="statuses[operation.key].message"
              :class="[
                'text-sm rounded-2xl px-3 py-1.5',
                statuses[operation.key].success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
              ]"
            >
              {{ statuses[operation.key].message }}
            </p>
          </div>
        </article>
      </div>

      <p v-if="pipeline.message" :class="[
        'rounded-2xl px-4 py-2 text-sm',
          pipeline.success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
      ]">
        {{ pipeline.message }}
      </p>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useActiveProject } from '../../composables/useActiveProject'
import {
  FunnelIcon,
  ArrowPathRoundedSquareIcon,
  TrashIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const processingDate = ref('')
const parameterError = ref('')
const { activeProjectName } = useActiveProject()
const datasets = ref([])
const datasetsLoading = ref(false)
const datasetsError = ref('')
const selectedDatasetId = ref('')
const lastFetchedProjectName = ref('')

const datasetTimestampFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
})

const operations = [
  {
    key: 'merge',
    label: 'Merge',
    title: '合并 Merge',
    subtitle: 'Step 01',
    description: '整合 TRS 导出的多份原始 Excel，生成标准化的主题数据表。',
    endpoint: `${API_BASE_URL}/merge`,
    icon: ArrowPathRoundedSquareIcon
  },
  {
    key: 'clean',
    label: 'Clean',
    title: '清洗 Clean',
    subtitle: 'Step 02',
    description: '执行数据清洗，补齐字段与格式，移除重复与异常值，为下一步筛选做好准备。',
    endpoint: `${API_BASE_URL}/clean`,
    icon: TrashIcon
  }
]

const statuses = reactive(
  operations.reduce((acc, operation) => {
    acc[operation.key] = { running: false, success: null, message: '' }
    return acc
  }, {})
)

const pipeline = reactive({
  running: false,
  success: null,
  message: ''
})

const getProcessingDate = () => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const refreshProcessingDate = () => {
  processingDate.value = getProcessingDate()
}

refreshProcessingDate()

const currentProjectName = computed(() => activeProjectName.value || 'GLOBAL')
const datasetOptions = computed(() =>
  datasets.value.map((item) => {
    const name = item.display_name || item.id
    const timestamp = formatTimestamp(item.stored_at)
    const parts = [name]
    if (item.topic_label) {
      parts.push(`专题：${item.topic_label}`)
    }
    if (timestamp && timestamp !== '—') {
      parts.push(`更新于 ${timestamp}`)
    }
    return {
      id: item.id,
      label: parts.join(' · '),
      raw: item
    }
  })
)
const formatTimestamp = (value) => {
  if (!value) return ''
  try {
    const dateObj = new Date(value)
    if (Number.isNaN(dateObj.getTime())) return value
    return datasetTimestampFormatter.format(dateObj)
  } catch (error) {
    return value
  }
}

const resetDatasetState = () => {
  datasets.value = []
  datasetsError.value = ''
  datasetsLoading.value = false
  selectedDatasetId.value = ''
  lastFetchedProjectName.value = ''
  refreshProcessingDate()
}

const fetchProjectDatasets = async (projectName, { force = false } = {}) => {
  const trimmed = projectName.trim()
  if (!trimmed) {
    resetDatasetState()
    return
  }
  if (!force && lastFetchedProjectName.value === trimmed && datasets.value.length) {
    return
  }

  datasetsLoading.value = true
  datasetsError.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(trimmed)}/datasets`)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法加载专题数据集')
    }
    const items = Array.isArray(result.datasets) ? result.datasets : []
    datasets.value = items.map((item) => ({
      ...item,
      topic_label: typeof item.topic_label === 'string' ? item.topic_label.trim() : ''
    }))
    lastFetchedProjectName.value = trimmed

    if (items.length) {
      const current = selectedDatasetId.value
      const exists = items.some((item) => item.id === current)
      selectedDatasetId.value = exists ? current : items[0].id
    } else {
      selectedDatasetId.value = ''
    }
  } catch (err) {
    datasets.value = []
    datasetsError.value = err instanceof Error ? err.message : '无法加载专题数据集'
    selectedDatasetId.value = ''
    lastFetchedProjectName.value = ''
  } finally {
    datasetsLoading.value = false
  }
}

const refreshDatasets = () => {
  const projectName = currentProjectName.value
  if (!projectName) return
  fetchProjectDatasets(projectName, { force: true })
}

watch(
  currentProjectName,
  (projectName) => {
    resetDatasetState()
    if (!projectName) return
    fetchProjectDatasets(projectName, { force: true })
  },
  { immediate: true }
)

watch(selectedDatasetId, (datasetId) => {
  if (!datasetId) return
  refreshProcessingDate()
})

const ensureParameters = () => {
  const projectName = currentProjectName.value ? currentProjectName.value.trim() : ''
  if (!projectName) {
    parameterError.value = '请先选择项目'
    return false
  }
  if (datasetOptions.value.length && !selectedDatasetId.value) {
    parameterError.value = '请选择需要处理的数据集'
    return false
  }
  refreshProcessingDate()
  parameterError.value = ''
  return true
}

const runOperation = async (key) => {
  if (!ensureParameters()) return
  const operation = operations.find((item) => item.key === key)
  if (!operation) return

  const state = statuses[key]
  state.running = true
  state.message = ''
  state.success = null

  try {
    const projectName = currentProjectName.value ? currentProjectName.value.trim() : ''
    const payload = {
      topic: projectName,
      date: processingDate.value
    }
    if (projectName) {
      payload.project = projectName
    }
    if (selectedDatasetId.value) {
      payload.dataset_id = selectedDatasetId.value
    }
    const response = await fetch(operation.endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    const ok = response.ok && result.status !== 'error'
    state.success = ok
    state.message = ok ? `${operation.label} 执行成功` : (result.message || `${operation.label} 执行失败`)
  } catch (err) {
    state.success = false
    state.message = err instanceof Error ? err.message : `${operation.label} 执行失败`
  } finally {
    state.running = false
  }
}

const runPipeline = async () => {
  if (!ensureParameters()) return
  pipeline.running = true
  pipeline.message = ''
  pipeline.success = null

  try {
    const projectName = currentProjectName.value ? currentProjectName.value.trim() : ''
    const payload = {
      topic: projectName,
      date: processingDate.value
    }
    if (projectName) {
      payload.project = projectName
    }
    if (selectedDatasetId.value) {
      payload.dataset_id = selectedDatasetId.value
    }
    const response = await fetch(`${API_BASE_URL}/pipeline`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    const ok = response.ok && result.status !== 'error'
    pipeline.success = ok
    pipeline.message = ok ? 'Pipeline 执行成功，Merge 与 Clean 均已完成。' : (result.message || 'Pipeline 执行失败')
  } catch (err) {
    pipeline.success = false
    pipeline.message = err instanceof Error ? err.message : 'Pipeline 执行失败'
  } finally {
    pipeline.running = false
  }
}
</script>
