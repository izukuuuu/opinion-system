<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">筛选数据</h1>
        <p class="text-sm text-secondary">配置提示词模板并独立执行 Filter，输出与专题高度相关的内容。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <AdjustmentsHorizontalIcon class="h-4 w-4" />
        <span>步骤 3 · 筛选</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">提示词模板</h2>
        <p class="text-sm text-secondary">
          筛选依赖专题专属的 YAML 模板，请填写舆情主题与分类标签，保存后可随时调整。
        </p>
      </header>

      <div class="grid gap-6 lg:grid-cols-2">
        <div class="space-y-4">
          <label class="space-y-1 text-sm">
            <span class="font-medium text-secondary">舆情主题</span>
            <input
              v-model.trim="templateState.theme"
              type="text"
              class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="例如：控烟政策、校园安全等"
            />
          </label>

          <div class="space-y-2 text-sm">
            <span class="font-medium text-secondary">需要的分类</span>
            <div class="flex flex-wrap items-center gap-3">
              <input
                v-model.trim="templateState.categoryInput"
                type="text"
                class="flex-1 min-w-[180px] rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                placeholder="输入分类后点击添加"
                @keyup.enter.prevent="addCategory"
              />
              <button
                type="button"
                class="inline-flex items-center gap-1 rounded-full border border-brand-soft px-3 py-1.5 text-xs font-semibold text-brand-600 transition hover:bg-brand-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="!templateState.categoryInput"
                @click="addCategory"
              >
                <PlusIcon class="h-4 w-4" />
                添加分类
              </button>
            </div>
            <div
              v-if="templateState.categories.length"
              class="flex flex-wrap gap-2 rounded-3xl border border-dashed border-brand-soft bg-surface-muted px-4 py-3 text-xs text-secondary"
            >
              <span
                v-for="(category, index) in templateState.categories"
                :key="`${category}-${index}`"
                class="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1 text-secondary shadow-sm"
              >
                <span class="font-medium text-primary">{{ category }}</span>
                <button
                  type="button"
                  class="rounded-full p-0.5 text-muted transition hover:text-rose-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-rose-400"
                  @click="removeCategory(index)"
                >
                  <XMarkIcon class="h-3.5 w-3.5" />
                </button>
              </span>
            </div>
            <p v-else class="text-xs text-muted">请至少添加一个分类，筛选结果会根据列表进行归类。</p>
          </div>
        </div>

        <div class="space-y-3">
          <div class="flex items-center justify-between text-sm">
            <span class="font-medium text-secondary">模板预览</span>
            <span v-if="templateState.exists" class="text-xs text-muted">
              已保存于 <code class="rounded bg-surface-muted px-1 py-0.5 text-[11px] text-secondary">configs/prompt/filter</code>
            </span>
          </div>
          <div class="rounded-3xl border border-dashed border-soft bg-surface-muted/70 p-4">
            <pre class="max-h-60 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-secondary">
{{ templatePreview }}</pre>
          </div>
          <p
            v-if="templateState.metadataMissing && storedTemplate"
            class="text-xs text-muted"
          >
            当前模板缺少元数据，请完善主题与分类后保存，新模板会覆盖已有内容。
          </p>
        </div>
      </div>

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          class="btn-base btn-tone-primary inline-flex items-center gap-2 px-6 py-2"
          :disabled="!canSaveTemplate || templateState.saving"
          @click="saveTemplate"
        >
          <span v-if="templateState.saving">保存中…</span>
          <span v-else>保存模板</span>
        </button>
        <p
          v-if="templateState.success || templateState.error"
          :class="[
            'text-sm rounded-2xl px-3 py-1.5',
            templateState.error ? 'bg-rose-100 text-rose-600' : 'bg-emerald-100 text-emerald-600'
          ]"
        >
          {{ templateState.error || templateState.success }}
        </p>
      </div>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">执行筛选</h2>
        <p class="text-sm text-secondary">
          选择数据集与处理日期后启动筛选。筛选过程会调用大模型，结果与进度可在下方实时查看。
        </p>
      </header>

      <p class="rounded-2xl bg-surface-muted px-4 py-2 text-xs font-medium text-secondary">
        <span class="text-muted">当前 AI 配置：</span>
        <span class="text-primary">{{ aiConfigLine }}</span>
      </p>

      <form class="space-y-4">
        <p class="text-xs text-secondary">
          当前项目：<span class="font-semibold text-primary">{{ currentProjectName || '未选择' }}</span>
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
              @click.prevent="refreshDatasets"
            >
              {{ datasetsLoading ? '加载中…' : '刷新数据集' }}
            </button>
          </div>
          <p v-if="datasetsError" class="mt-2 rounded-2xl bg-rose-50 px-3 py-1 text-xs text-rose-600">
            {{ datasetsError }}
          </p>
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium text-secondary">处理日期</span>
          <div class="flex flex-wrap items-center gap-3">
            <input
              v-model="processingDate"
              type="date"
              class="rounded-2xl border border-soft px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              @click.prevent="refreshProcessingDate"
            >
              <ClockIcon class="h-4 w-4" />
              使用今日
            </button>
          </div>
        </label>
      </form>

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-brand-soft px-5 py-2 text-sm font-semibold text-brand-600 transition hover:bg-brand-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="triggerState.requesting"
          @click="runFilter"
        >
          <SparklesIcon class="h-4 w-4" />
          <span>{{ triggerState.requesting ? '启动中…' : '开始筛选' }}</span>
        </button>
        <p
          v-if="triggerState.message"
          :class="[
            'text-sm rounded-2xl px-3 py-1.5',
            triggerState.success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
          ]"
        >
          {{ triggerState.message }}
        </p>
      </div>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-xl font-semibold text-primary">运行进度</h2>
          <span class="text-xs text-muted">
            最近更新：{{ summaryUpdatedAt || '—' }}
          </span>
        </div>
        <p class="text-sm text-secondary">
          筛选过程中会持续更新进度与记录，最多保留最近 {{ recentLimit }} 条。列表可滚动查看。
        </p>
      </header>

      <div class="space-y-3 rounded-3xl border border-dashed border-soft bg-white/80 p-5">
        <div class="flex items-center justify-between text-xs text-secondary">
          <span>总体进度</span>
          <span>{{ progressPercent }}%</span>
        </div>
        <div class="h-2 rounded-full bg-surface-muted">
          <div
            class="h-full rounded-full bg-brand transition-all"
            :style="{ width: `${progressPercent}%` }"
          ></div>
        </div>
        <dl class="grid gap-3 text-xs text-secondary sm:grid-cols-3">
          <div class="rounded-2xl bg-surface-muted px-4 py-3">
            <dt class="text-[11px] uppercase tracking-widest text-muted">总任务</dt>
            <dd class="mt-1 text-base font-semibold text-primary">{{ statusState.progress.total }}</dd>
          </div>
          <div class="rounded-2xl bg-surface-muted px-4 py-3">
            <dt class="text-[11px] uppercase tracking-widest text-muted">已完成</dt>
            <dd class="mt-1 text-base font-semibold text-primary">{{ statusState.progress.completed }}</dd>
          </div>
          <div class="rounded-2xl bg-surface-muted px-4 py-3">
            <dt class="text-[11px] uppercase tracking-widest text-muted">保留</dt>
            <dd class="mt-1 text-base font-semibold text-primary">{{ statusState.progress.kept }}</dd>
          </div>
        </dl>
      </div>

      <div class="space-y-3">
        <div class="flex items-center justify-between text-sm">
          <span class="font-medium text-secondary">最近处理记录</span>
          <span class="text-xs text-muted">
            {{ statusState.recentRecords.length ? `展示最近 ${statusState.recentRecords.length} 条` : '暂无记录' }}
          </span>
        </div>
        <div class="max-h-72 overflow-y-auto rounded-3xl border border-dashed border-soft bg-surface-muted/60 p-4">
          <p v-if="!statusState.recentRecords.length" class="text-xs text-muted">
            筛选尚未开始或记录已清理，启动任务后可在此处查看实时进度。
          </p>
          <ul v-else class="space-y-3 text-sm">
            <li
              v-for="(record, index) in statusState.recentRecords"
              :key="`${index}-${record.channel}-${record.index}`"
              class="rounded-2xl border border-soft bg-white px-4 py-3 shadow-sm"
            >
              <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div class="flex flex-wrap items-center gap-2 text-secondary">
                  <span class="rounded-full bg-brand-soft/60 px-2 py-0.5 font-semibold text-brand-600">
                    {{ record.channel || 'unknown' }}
                  </span>
                  <span
                    :class="[
                      'rounded-full px-2 py-0.5 font-semibold',
                      record.status === 'kept'
                        ? 'bg-emerald-100 text-emerald-600'
                        : 'bg-rose-100 text-rose-600'
                    ]"
                  >
                    {{ record.status === 'kept' ? '保留' : '过滤' }}
                  </span>
                  <span class="text-muted">{{ formatTimestamp(record.updated_at) }}</span>
                </div>
                <span v-if="record.classification" class="text-muted">
                  分类：{{ record.classification }}
                </span>
              </div>
              <div class="mt-2 space-y-1">
                <p v-if="record.title" class="text-sm font-medium text-primary">{{ record.title }}</p>
                <p class="text-sm leading-relaxed text-secondary">
                  {{ record.preview || '（无内容预览）' }}
                </p>
              </div>
            </li>
          </ul>
        </div>
      </div>

      <p
        v-if="statusState.message"
        class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600"
      >
        {{ statusState.message }}
      </p>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">筛选结果摘要</h2>
        <p class="text-sm text-secondary">
          筛选前共有 {{ statusState.summary.total_rows }} 行，筛选后保留 {{ statusState.summary.kept_rows }} 行，
          剔除 {{ filteredOutCount }} 行。
        </p>
      </header>

      <dl class="grid gap-3 text-sm text-secondary sm:grid-cols-3">
        <div class="rounded-2xl bg-surface-muted px-4 py-3">
          <dt class="text-[11px] uppercase tracking-widest text-muted">筛选前</dt>
          <dd class="mt-1 text-lg font-semibold text-primary">{{ statusState.summary.total_rows }}</dd>
        </div>
        <div class="rounded-2xl bg-surface-muted px-4 py-3">
          <dt class="text-[11px] uppercase tracking-widest text-muted">筛选后</dt>
          <dd class="mt-1 text-lg font-semibold text-primary">{{ statusState.summary.kept_rows }}</dd>
        </div>
        <div class="rounded-2xl bg-surface-muted px-4 py-3">
          <dt class="text-[11px] uppercase tracking-widest text-muted">剔除</dt>
          <dd class="mt-1 text-lg font-semibold text-primary">{{ filteredOutCount }}</dd>
        </div>
      </dl>

      <div class="space-y-3">
        <h3 class="text-sm font-medium text-secondary">无关内容示例</h3>
        <div class="grid gap-3 md:grid-cols-2">
          <p
            v-if="!statusState.irrelevantSamples.length"
            class="rounded-2xl border border-dashed border-soft bg-surface-muted px-4 py-3 text-xs text-muted"
          >
            尚未收集到无关样本。完成一次筛选后，可在此查看被剔除的代表性片段。
          </p>
          <article
            v-for="(item, index) in statusState.irrelevantSamples"
            :key="`${item.channel}-${index}`"
            class="flex flex-col gap-2 rounded-2xl border border-soft bg-white px-4 py-3 text-sm text-secondary shadow-sm"
          >
            <div class="flex items-center justify-between text-xs text-muted">
              <span class="rounded-full bg-surface-muted px-2 py-0.5 font-semibold text-secondary">
                {{ item.channel || 'unknown' }}
              </span>
              <span>#{{ item.index }}</span>
            </div>
            <p class="font-medium text-primary">{{ item.title || '（未提供标题）' }}</p>
            <p class="leading-relaxed">{{ item.preview || '（无摘要）' }}</p>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  AdjustmentsHorizontalIcon,
  SparklesIcon,
  PlusIcon,
  XMarkIcon,
  ClockIcon
} from '@heroicons/vue/24/outline'
import { useActiveProject } from '../../composables/useActiveProject'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
const POLL_INTERVAL = 4000
const RECENT_LIMIT = 40

const { activeProjectName } = useActiveProject()

const processingDate = ref(getProcessingDate())
const datasets = ref([])
const datasetsLoading = ref(false)
const datasetsError = ref('')
const selectedDatasetId = ref('')
const lastFetchedProjectName = ref('')

const templateState = reactive({
  loading: false,
  exists: false,
  metadataMissing: false,
  theme: '',
  categories: [],
  categoryInput: '',
  saving: false,
  success: '',
  error: ''
})
const templateBaseline = reactive({
  theme: '',
  categories: []
})
const storedTemplate = ref('')

const statusState = reactive({
  loading: false,
  running: false,
  progress: {
    total: 0,
    completed: 0,
    kept: 0,
    failed: 0,
    percentage: 0
  },
  recentRecords: [],
  summary: {
    total_rows: 0,
    kept_rows: 0,
    discarded_rows: 0,
    completed: false,
    updated_at: ''
  },
  irrelevantSamples: [],
  aiConfig: {
    provider: '',
    model: '',
    qps: null,
    batch_size: null,
    truncation: null
  },
  message: ''
})

const triggerState = reactive({
  requesting: false,
  success: null,
  message: ''
})

const statusLoading = ref(false)
let pollHandle = null

const datasetTimestampFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
})

const summaryTimestampFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit'
})

const currentProjectName = computed(() => activeProjectName.value || '')

const datasetOptions = computed(() =>
  datasets.value.map((item) => {
    const name = item.display_name || item.id
    const timestamp = formatDatasetTimestamp(item.stored_at)
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

const hasTemplateChanges = computed(() => {
  const sameTheme = templateState.theme === templateBaseline.theme
  if (!sameTheme) return true
  if (templateState.categories.length !== templateBaseline.categories.length) {
    return true
  }
  return templateState.categories.some((item, idx) => item !== templateBaseline.categories[idx])
})

const canSaveTemplate = computed(() => {
  return (
    templateState.theme.trim().length > 0 &&
    templateState.categories.length > 0 &&
    !templateState.saving &&
    hasTemplateChanges.value
  )
})

const templatePreview = computed(() => {
  if (
    templateState.metadataMissing &&
    storedTemplate.value &&
    !templateState.theme &&
    !templateState.categories.length
  ) {
    return storedTemplate.value
  }
  return composeTemplate(templateState.theme, templateState.categories)
})

const aiConfigLine = computed(() => {
  const provider = (statusState.aiConfig.provider || '').toUpperCase() || 'QWEN'
  const model = statusState.aiConfig.model || '默认模型'
  const qps = statusState.aiConfig.qps ?? '—'
  const batch = statusState.aiConfig.batch_size ?? '—'
  return `${provider} · ${model} · QPS: ${qps} · Batch: ${batch}`
})

const progressPercent = computed(() => {
  const value = Number(statusState.progress.percentage || 0)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
})

const filteredOutCount = computed(() => {
  const total = Number(statusState.summary.total_rows || 0)
  const kept = Number(statusState.summary.kept_rows || 0)
  return total > kept ? total - kept : 0
})

const summaryUpdatedAt = computed(() => formatTimestamp(statusState.summary.updated_at))
const recentLimit = computed(() => RECENT_LIMIT)

watch(
  () => [templateState.theme, templateState.categories],
  () => {
    templateState.success = ''
    templateState.error = ''
  },
  { deep: true }
)

watch(
  () => statusState.running,
  (running) => {
    if (running) {
      startPolling()
    } else {
      stopPolling()
    }
  }
)

watch(
  currentProjectName,
  (project) => {
    stopPolling()
    resetDatasetState()
    resetStatusState()
    templateState.theme = ''
    templateState.categories = []
    templateState.categoryInput = ''
    templateState.exists = false
    templateState.metadataMissing = false
    storedTemplate.value = ''
    templateBaseline.theme = ''
    templateBaseline.categories = []

    if (!project) return
    fetchProjectDatasets(project, { force: true })
    loadTemplate(project)
    loadFilterStatus()
  },
  { immediate: true }
)

watch(processingDate, () => {
  if (currentProjectName.value) {
    loadFilterStatus({ silent: true })
  }
})

onBeforeUnmount(() => {
  stopPolling()
})

function getProcessingDate() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function refreshProcessingDate() {
  processingDate.value = getProcessingDate()
}

function formatDatasetTimestamp(value) {
  if (!value) return ''
  try {
    const dateObj = new Date(value)
    if (Number.isNaN(dateObj.getTime())) return value
    return datasetTimestampFormatter.format(dateObj)
  } catch (error) {
    return value
  }
}

function formatTimestamp(value) {
  if (!value) return ''
  try {
    const dateObj = new Date(value)
    if (Number.isNaN(dateObj.getTime())) return ''
    return summaryTimestampFormatter.format(dateObj)
  } catch (error) {
    return ''
  }
}

function composeTemplate(theme, categories) {
  const subject = (theme || '').trim() || '该专题'
  const cleanedCategories = categories.map((item) => String(item || '').trim()).filter(Boolean)

  const lines = [
    `你是一名舆情筛选助手，请判断以下文本是否与“${subject}”专题相关，并输出 JSON 结果：`,
    '规则：',
    `1. 判断文本是否与${subject}相关，相关返回true，否则返回false；`
  ]

  if (cleanedCategories.length) {
    const optionText = cleanedCategories.join('、')
    lines.push(`2. 如果文本相关，请从以下分类中选择最贴切的一项：${optionText}。`)
    lines.push('返回格式: {"相关": true或false, "分类": "<分类名称，必须来自上述列表>"}')
  } else {
    lines.push('2. 如果文本相关，请给出合适的分类描述。')
    lines.push('返回格式: {"相关": true或false, "分类": "分类名称"}')
  }
  lines.push('文本：{text}')
  return lines.join('\n')
}

async function fetchProjectDatasets(projectName, { force = false } = {}) {
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

function refreshDatasets() {
  const projectName = currentProjectName.value
  if (!projectName) return
  fetchProjectDatasets(projectName, { force: true })
}

async function loadTemplate(projectName) {
  templateState.loading = true
  templateState.error = ''
  templateState.success = ''
  try {
    const params = new URLSearchParams({ project: projectName })
    const response = await fetch(`${API_BASE_URL}/filter/template?${params.toString()}`)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法加载模板')
    }
    const data = result.data || {}
    templateState.exists = Boolean(data.exists)
    templateState.theme = data.topic_theme || ''
    templateState.categories = Array.isArray(data.categories) ? data.categories.slice() : []
    templateState.metadataMissing =
      Boolean(data.exists) && !templateState.theme && !templateState.categories.length
    templateBaseline.theme = templateState.theme
    templateBaseline.categories = templateState.categories.slice()
    templateState.categoryInput = ''
    storedTemplate.value = data.template || ''
  } catch (err) {
    templateState.error = err instanceof Error ? err.message : '无法加载模板'
  } finally {
    templateState.loading = false
  }
}

async function saveTemplate() {
  if (!currentProjectName.value) {
    templateState.error = '请先选择项目'
    return
  }
  if (!templateState.theme.trim()) {
    templateState.error = '请填写舆情主题'
    return
  }
  if (!templateState.categories.length) {
    templateState.error = '请至少添加一个分类'
    return
  }

  templateState.saving = true
  templateState.error = ''
  templateState.success = ''

  try {
    const payload = {
      project: currentProjectName.value.trim(),
      topic_theme: templateState.theme.trim(),
      categories: templateState.categories.slice()
    }
    const response = await fetch(`${API_BASE_URL}/filter/template`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '模板保存失败')
    }
    const data = result.data || {}
    templateState.exists = true
    templateState.metadataMissing = false
    storedTemplate.value = data.template || composeTemplate(templateState.theme, templateState.categories)
    templateBaseline.theme = templateState.theme
    templateBaseline.categories = templateState.categories.slice()
    templateState.success = '模板已更新'
  } catch (err) {
    templateState.error = err instanceof Error ? err.message : '模板保存失败'
  } finally {
    templateState.saving = false
  }
}

async function loadFilterStatus({ silent = false } = {}) {
  if (!currentProjectName.value || !processingDate.value) {
    resetStatusState()
    return
  }
  if (!silent) {
    statusLoading.value = true
    statusState.message = ''
  }

  try {
    const params = new URLSearchParams({
      project: currentProjectName.value.trim(),
      date: processingDate.value
    })
    const response = await fetch(`${API_BASE_URL}/filter/status?${params.toString()}`)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法获取筛选状态')
    }
    const data = result.data || {}
    statusState.running = Boolean(data.running)
    const progress = data.progress || {}
    statusState.progress = {
      total: Number(progress.total || 0),
      completed: Number(progress.completed || 0),
      kept: Number(progress.kept || 0),
      failed: Number(progress.failed || 0),
      percentage: Number(progress.percentage || 0)
    }
    const recent = Array.isArray(data.recent_records) ? data.recent_records : []
    statusState.recentRecords = recent.slice(0, RECENT_LIMIT)
    const summary = data.summary || {}
    statusState.summary = {
      total_rows: Number(summary.total_rows || 0),
      kept_rows: Number(summary.kept_rows || 0),
      discarded_rows: Number(summary.discarded_rows || 0),
      completed: Boolean(summary.completed),
      updated_at: summary.updated_at || ''
    }
    statusState.irrelevantSamples = Array.isArray(data.irrelevant_samples)
      ? data.irrelevant_samples
      : []
    statusState.aiConfig = {
      provider: data.ai_config?.provider || '',
      model: data.ai_config?.model || '',
      qps: data.ai_config?.qps ?? null,
      batch_size: data.ai_config?.batch_size ?? null,
      truncation: data.ai_config?.truncation ?? null
    }
    statusState.message = ''
  } catch (err) {
    if (!silent) {
      statusState.message = err instanceof Error ? err.message : '无法获取筛选状态'
    }
    statusState.running = false
  } finally {
    if (!silent) {
      statusLoading.value = false
    }
  }
}

function resetDatasetState() {
  datasets.value = []
  datasetsError.value = ''
  datasetsLoading.value = false
  selectedDatasetId.value = ''
  lastFetchedProjectName.value = ''
}

function resetStatusState() {
  statusState.progress = {
    total: 0,
    completed: 0,
    kept: 0,
    failed: 0,
    percentage: 0
  }
  statusState.recentRecords = []
  statusState.summary = {
    total_rows: 0,
    kept_rows: 0,
    discarded_rows: 0,
    completed: false,
    updated_at: ''
  }
  statusState.irrelevantSamples = []
  statusState.message = ''
  statusState.running = false
}

function startPolling() {
  if (pollHandle) return
  pollHandle = setInterval(() => {
    loadFilterStatus({ silent: true })
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollHandle) {
    clearInterval(pollHandle)
    pollHandle = null
  }
}

function ensureParameters() {
  if (!currentProjectName.value.trim()) {
    triggerState.success = false
    triggerState.message = '请先选择项目'
    return false
  }
  if (datasetOptions.value.length && !selectedDatasetId.value) {
    triggerState.success = false
    triggerState.message = '请选择需要筛选的数据集'
    return false
  }
  if (!templateState.exists) {
    triggerState.success = false
    triggerState.message = '请先保存提示词模板'
    return false
  }
  if (!processingDate.value) {
    triggerState.success = false
    triggerState.message = '请填写处理日期'
    return false
  }
  triggerState.message = ''
  triggerState.success = null
  return true
}

async function runFilter() {
  if (!ensureParameters()) return
  triggerState.requesting = true
  triggerState.message = ''
  triggerState.success = null

  try {
    const payload = {
      topic: currentProjectName.value.trim(),
      project: currentProjectName.value.trim(),
      date: processingDate.value
    }
    if (selectedDatasetId.value) {
      payload.dataset_id = selectedDatasetId.value
    }
    const response = await fetch(`${API_BASE_URL}/filter`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    const ok = response.ok && result.status !== 'error'
    triggerState.success = ok
    triggerState.message = ok
      ? '筛选任务已启动，请稍候查看进度。'
      : result.message || '筛选执行失败'
    if (ok) {
      statusState.running = true
      loadFilterStatus()
    }
  } catch (err) {
    triggerState.success = false
    triggerState.message = err instanceof Error ? err.message : '筛选执行失败'
  } finally {
    triggerState.requesting = false
  }
}

function addCategory() {
  const value = (templateState.categoryInput || '').trim()
  if (!value) return
  if (!templateState.categories.includes(value)) {
    templateState.categories.push(value)
  }
  templateState.categoryInput = ''
}

function removeCategory(index) {
  templateState.categories.splice(index, 1)
}
</script>
