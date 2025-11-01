<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">数据预处理</h1>
        <p class="text-sm text-secondary">按日期依次执行 Merge、Clean、Filter，生成标准化结果。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <FunnelIcon class="h-4 w-4" />
        <span>步骤 2 · 预处理</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">准备参数</h2>
        <p class="text-sm text-secondary">
          请填写专题名称与专题所属日期。系统将基于该日期定位上传的原始数据文件。
        </p>
      </header>
<form class="grid gap-4 md:grid-cols-2">
  <p class="md:col-span-2 text-xs text-secondary">
    当前项目：<span class="font-semibold text-primary">{{ currentProjectName }}</span>
  </p>
  <label class="space-y-1 text-sm">
    <span class="font-medium text-secondary">专题名称</span>
    <input
      v-model.trim="topic"
      type="text"
      required
      class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
      placeholder="例如：2024-lianghui"
    />
  </label>
  <label class="space-y-1 text-sm md:col-span-2">
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
    <p v-if="datasetsError" class="rounded-2xl bg-rose-50 px-3 py-1 text-xs text-rose-600 mt-2">
      {{ datasetsError }}
    </p>
  </label>
  <label class="space-y-1 text-sm">
    <span class="font-medium text-secondary">专题日期</span>
    <div class="space-y-2">
      <input
        v-model="date"
        type="date"
        required
        :min="dateRange.min"
        :max="dateRange.max"
        :disabled="dateState.loading"
        class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200 disabled:cursor-wait disabled:opacity-70"
      />
      <div class="flex flex-wrap items-center gap-3">
        <select
          v-if="dateOptions.length"
          class="inline-flex min-w-[200px] items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
          :disabled="dateState.loading"
          :value="selectedDateOption"
          @change="selectSuggestedDate($event.target.value)"
        >
          <option value="">从可用日期中选择…</option>
          <option v-for="option in dateOptions" :key="option" :value="option">{{ formatDateOption(option) }}</option>
        </select>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="!canRefreshDateState"
          @click="refreshDateState"
        >
          {{ dateState.loading ? '读取中…' : '重新读取日期' }}
        </button>
      </div>
      <p v-if="dateState.loading" class="rounded-2xl bg-surface-muted px-3 py-1 text-xs text-secondary">
        正在读取专题数据中的日期字段…
      </p>
      <p v-else-if="dateState.error" class="rounded-2xl bg-rose-50 px-3 py-1 text-xs text-rose-600">
        {{ dateState.error }}
      </p>
    </div>
  </label>
</form>
<p v-if="parameterError" class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600">{{ parameterError }}</p>
    </section>

    <section class="space-y-5">
      <div class="card-surface flex flex-wrap items-center justify-between gap-3 p-6">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">预处理执行</h2>
          <p class="text-sm text-secondary">可单独运行每个步骤，或使用一键执行快速完成全部流程。</p>
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
  AdjustmentsHorizontalIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const topic = ref('')
const date = ref('')
const parameterError = ref('')
const { activeProjectName } = useActiveProject()
const datasets = ref([])
const datasetsLoading = ref(false)
const datasetsError = ref('')
const selectedDatasetId = ref('')
const lastLoadedSummaryKey = ref('')
const lastFetchedProjectName = ref('')

const weekdayLabels = ['日', '一', '二', '三', '四', '五', '六']
const datasetTimestampFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
})

const dateState = reactive({
  loading: false,
  error: '',
  min: '',
  max: '',
  column: '',
  dataset: null,
  values: [],
  truncated: false,
  uniqueCount: 0,
  columnMapping: {}
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
    description: '执行数据清洗，补齐字段与格式，移除重复与异常值，确保数据稳定。',
    endpoint: `${API_BASE_URL}/clean`,
    icon: TrashIcon
  },
  {
    key: 'filter',
    label: 'Filter',
    title: '筛选 Filter',
    subtitle: 'Step 03',
    description: '调用 AI 相关性筛选模型，保留与专题高度关联的数据。',
    endpoint: `${API_BASE_URL}/filter`,
    icon: AdjustmentsHorizontalIcon
  }
]

const statuses = reactive({
  merge: { running: false, success: null, message: '' },
  clean: { running: false, success: null, message: '' },
  filter: { running: false, success: null, message: '' }
})

const pipeline = reactive({
  running: false,
  success: null,
  message: ''
})

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
const dateOptions = computed(() => Array.isArray(dateState.values) ? dateState.values : [])
const selectedDateOption = computed(() => (dateOptions.value.includes(date.value) ? date.value : ''))
const dateRange = computed(() => ({
  min: dateState.min || '',
  max: dateState.max || ''
}))
const canRefreshDateState = computed(() => {
  if (dateState.loading) return false
  return Boolean(selectedDatasetId.value && currentProjectName.value)
})

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

const formatDateOption = (value) => {
  if (!value) return ''
  try {
    const dateObj = new Date(`${value}T00:00:00`)
    if (Number.isNaN(dateObj.getTime())) return value
    const weekday = weekdayLabels[dateObj.getDay()]
    return `${value}（周${weekday}）`
  } catch (error) {
    return value
  }
}

const selectSuggestedDate = (value) => {
  if (!value) return
  date.value = value
}

const resetDateState = () => {
  dateState.loading = false
  dateState.error = ''
  dateState.min = ''
  dateState.max = ''
  dateState.column = ''
  dateState.dataset = null
  dateState.values = []
  dateState.truncated = false
  dateState.uniqueCount = 0
  dateState.columnMapping = {}
}

const resetDatasetState = () => {
  datasets.value = []
  datasetsError.value = ''
  datasetsLoading.value = false
  selectedDatasetId.value = ''
  lastFetchedProjectName.value = ''
  date.value = ''
}

const loadDateState = async (datasetId = '', { force = false } = {}) => {
  const projectName = currentProjectName.value?.trim()
  if (!projectName) {
    resetDateState()
    lastLoadedSummaryKey.value = ''
    return
  }
  const cacheKey = `${projectName}::${datasetId || ''}`
  if (!force && lastLoadedSummaryKey.value === cacheKey && !dateState.error && dateState.values.length) {
    return
  }

  dateState.loading = true
  dateState.error = ''
  try {
    const url = new URL(`${API_BASE_URL}/projects/${encodeURIComponent(projectName)}/date-range`)
    if (datasetId) {
      url.searchParams.set('dataset_id', datasetId)
    }
    const response = await fetch(url.toString())
    let result
    try {
      result = await response.clone().json()
    } catch (parseError) {
      const fallback = await response.text()
      throw new Error(fallback || '日期范围接口返回异常')
    }
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法读取专题日期范围')
    }

    dateState.min = result.min_date || ''
    dateState.max = result.max_date || ''
    dateState.column = result.date_column || ''
    dateState.dataset = result.dataset || null
    dateState.values = Array.isArray(result.date_values) ? result.date_values : []
    dateState.truncated = Boolean(result.truncated)
    dateState.columnMapping = typeof result.column_mapping === 'object' && result.column_mapping !== null
      ? result.column_mapping
      : {}
    if (!topic.value && result.dataset && typeof result.dataset.topic_label === 'string' && result.dataset.topic_label) {
      topic.value = result.dataset.topic_label.trim()
    }
    const uniqueCount = Number(result.unique_date_count)
    dateState.uniqueCount = Number.isFinite(uniqueCount) && uniqueCount > 0
      ? uniqueCount
      : dateState.values.length

    if (dateState.values.length) {
      const latest = dateState.values[dateState.values.length - 1]
      if (!date.value || !dateState.values.includes(date.value)) {
        date.value = latest
      } else if (dateState.min && date.value < dateState.min) {
        date.value = dateState.min
      } else if (dateState.max && date.value > dateState.max) {
        date.value = dateState.max
      }
    } else if (dateState.min && dateState.max && (!date.value || date.value < dateState.min || date.value > dateState.max)) {
      date.value = dateState.min
    }

    if (result.dataset?.id && !selectedDatasetId.value) {
      selectedDatasetId.value = result.dataset.id
    }

    lastLoadedSummaryKey.value = cacheKey
  } catch (err) {
    resetDateState()
    dateState.error = err instanceof Error ? err.message : '无法读取专题日期范围'
    lastLoadedSummaryKey.value = ''
  } finally {
    dateState.loading = false
  }
}

const refreshDateState = () => {
  if (!selectedDatasetId.value) return
  loadDateState(selectedDatasetId.value, { force: true })
}

const fetchProjectDatasets = async (projectName, { force = false } = {}) => {
  const trimmed = projectName.trim()
  if (!trimmed) {
    resetDatasetState()
    resetDateState()
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
    resetDateState()
    if (!projectName) return
    fetchProjectDatasets(projectName, { force: true })
  },
  { immediate: true }
)

watch(selectedDatasetId, (datasetId) => {
  if (!datasetId) {
    resetDateState()
    date.value = ''
    return
  }
  const matched = datasets.value.find((item) => item.id === datasetId)
  if (!topic.value && matched && typeof matched.topic_label === 'string' && matched.topic_label) {
    topic.value = matched.topic_label.trim()
  }
  loadDateState(datasetId)
})

const ensureParameters = () => {
  topic.value = topic.value.trim()
  if (!topic.value) {
    parameterError.value = '请填写专题名称'
    return false
  }
  if (datasetOptions.value.length && !selectedDatasetId.value) {
    parameterError.value = '请选择需要处理的数据集'
    return false
  }
  if (!date.value) {
    parameterError.value = '请填写专题名称与日期后再执行操作'
    return false
  }
  if (dateState.min && date.value < dateState.min) {
    parameterError.value = `日期需不早于 ${dateState.min}`
    return false
  }
  if (dateState.max && date.value > dateState.max) {
    parameterError.value = `日期需不晚于 ${dateState.max}`
    return false
  }
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
    const payload = {
      topic: topic.value,
      date: date.value
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
    const payload = {
      topic: topic.value,
      date: date.value
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
    pipeline.message = ok ? 'Pipeline 执行成功，所有步骤均已完成。' : (result.message || 'Pipeline 执行失败')
  } catch (err) {
    pipeline.success = false
    pipeline.message = err instanceof Error ? err.message : 'Pipeline 执行失败'
  } finally {
    pipeline.running = false
  }
}
</script>
