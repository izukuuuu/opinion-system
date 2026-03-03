<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-primary">筛选数据</h1>
        <p class="text-sm text-secondary">配置提示词模板并独立执行 Filter，输出与专题高度相关的内容。</p>
      </div>
      <div
        class="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
        <AdjustmentsHorizontalIcon class="h-4 w-4" />
        <span>Filter</span>
      </div>
    </header>

    <!-- Template Configuration -->
    <section class="card-surface p-8 space-y-8">
      <header class="space-y-1">
        <h2 class="text-lg font-bold text-primary">提示词模板</h2>
        <p class="text-xs text-secondary">
          筛选依赖专题专属的 YAML 模板，请填写舆情主题与分类标签。
        </p>
      </header>

      <div class="grid gap-8 lg:grid-cols-2">
        <div class="space-y-6">
          <label class="space-y-2 block">
            <span class="text-xs font-bold text-primary ml-1">舆情主题</span>
            <input v-model.trim="templateState.theme" type="text"
              class="w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted"
              placeholder="例如：控烟政策、校园安全等" />
          </label>

          <div class="space-y-3">
            <span class="text-xs font-bold text-primary ml-1">需要提取的分类</span>
            <div class="flex flex-wrap items-center gap-2">
              <div class="relative flex-1 min-w-[200px]">
                <input v-model.trim="templateState.categoryInput" type="text"
                  class="w-full rounded-2xl border-0 bg-base-soft px-4 py-3 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted"
                  placeholder="输入分类后回车添加" @keyup.enter.prevent="addCategory" />
                <button type="button"
                  class="absolute right-2 top-2 rounded-xl bg-white px-3 py-1 text-xs font-bold text-brand-600 border border-black/5 transition hover:bg-brand-50 disabled:opacity-50"
                  :disabled="!templateState.categoryInput" @click="addCategory">
                  添加
                </button>
              </div>
            </div>

            <div v-if="templateState.categories.length"
              class="flex flex-wrap gap-2 rounded-2xl border border-dashed border-black/10 bg-brand-50/20 p-4">
              <span v-for="(category, index) in templateState.categories" :key="`${category}-${index}`"
                class="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-medium text-secondary border border-black/5">
                <span>{{ category }}</span>
                <button type="button"
                  class="rounded-full p-0.5 text-muted hover:bg-rose-50 hover:text-rose-600 transition-colors"
                  @click="removeCategory(index)">
                  <XMarkIcon class="h-3 w-3" />
                </button>
              </span>
            </div>
            <p v-else class="text-[10px] text-muted pl-1">请至少添加一个分类，筛选结果会根据列表进行归类。</p>
          </div>
        </div>

        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-primary ml-1">模板预览</span>
            <span v-if="templateState.exists"
              class="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
              <CheckIcon class="h-3 w-3" /> 已保存
            </span>
          </div>
          <!-- Refined Preview Widget -->
          <div class="rounded-3xl border border-black/5 bg-[#1e1e1e] p-5 relative overflow-hidden group">
            <div
              class="absolute top-0 left-0 right-0 h-8 bg-white/5 border-b border-white/5 flex items-center px-4 gap-1.5">
              <div class="w-2.5 h-2.5 rounded-full bg-rose-500/50"></div>
              <div class="w-2.5 h-2.5 rounded-full bg-amber-500/50"></div>
              <div class="w-2.5 h-2.5 rounded-full bg-emerald-500/50"></div>
            </div>
            <pre
              class="mt-6 max-h-52 overflow-y-auto whitespace-pre-wrap break-words text-[11px] leading-relaxed text-blue-200/90 font-mono scrollbar-dark">{{ templatePreview }}</pre>
          </div>
          <p v-if="templateState.metadataMissing && storedTemplate" class="text-[10px] text-rose-500 pl-1">
            当前模板缺少元数据，请完善主题与分类后保存。
          </p>
        </div>
      </div>

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-2">
        <button type="button"
          class="inline-flex items-center gap-2 rounded-full bg-brand-600 px-8 py-3 text-sm font-bold text-white transition-colors hover:bg-brand-700 disabled:opacity-60"
          :disabled="!canSaveTemplate || templateState.saving" @click="saveTemplate">
          <span v-if="templateState.saving">保存中...</span>
          <span v-else>更新模板配置</span>
        </button>
        <transition name="fade">
          <p v-if="templateState.success || templateState.error" class="text-xs font-medium px-4 py-2 rounded-xl"
            :class="templateState.error ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600'">
            {{ templateState.error || templateState.success }}
          </p>
        </transition>
      </div>
    </section>

    <!-- Execution Section -->
    <section class="card-surface p-8 space-y-8">
      <header class="space-y-1">
        <h2 class="text-lg font-bold text-primary">执行筛选</h2>
        <p class="text-xs text-secondary">
          选择数据集与处理日期后启动筛选。
        </p>
      </header>

      <div v-if="aiConfigLine"
        class="rounded-2xl bg-brand-50/50 px-5 py-3 text-xs font-medium text-brand-700 flex items-center gap-3 border border-brand-100/50">
        <div class="p-2 rounded-xl bg-white/50">
          <SparklesIcon class="h-4 w-4 text-brand-600" />
        </div>
        <div class="flex flex-col gap-0.5">
          <span class="text-[10px] opacity-60 uppercase tracking-wider font-bold">Current AI Engine</span>
          <span>{{ aiConfigLine }}</span>
        </div>
      </div>

      <form class="space-y-6">
        <div class="grid gap-6 md:grid-cols-2">
          <label class="space-y-2 block">
            <span class="text-xs font-bold text-primary ml-1">选择项目</span>
            <div class="flex gap-2">
              <div class="relative flex-1">
                <select v-if="projectOptions.length" v-model="selectedProjectName"
                  class="w-full appearance-none rounded-2xl border-0 bg-base-soft py-4 pl-4 pr-10 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 disabled:opacity-60"
                  :disabled="projectsLoading">
                  <option disabled value="">请选择项目</option>
                  <option v-for="option in projectOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
                <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-secondary/50">
                  <ChevronDownIcon class="w-4 h-4" />
                </div>
              </div>
              <button type="button"
                class="shrink-0 rounded-2xl bg-brand-50/30 px-4 text-secondary hover:text-brand-600 hover:bg-brand-50 transition-colors"
                :disabled="projectsLoading" @click.prevent="refreshProjects" title="刷新项目">
                <ArrowPathIcon class="h-5 w-5" :class="{ 'animate-spin': projectsLoading }" />
              </button>
            </div>
            <p v-if="projectsError" class="text-xs text-rose-600 pl-1">{{ projectsError }}</p>
          </label>

          <label class="space-y-2 block">
            <span class="text-xs font-bold text-primary ml-1">选择待处理数据集</span>
            <div class="flex gap-2">
              <div class="relative flex-1">
                <select v-if="datasetOptions.length" v-model="selectedDatasetId"
                  class="w-full appearance-none rounded-2xl border-0 bg-base-soft py-4 pl-4 pr-10 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 disabled:opacity-60"
                  :disabled="datasetsLoading">
                  <option v-for="option in datasetOptions" :key="option.id" :value="option.id">
                    {{ option.label }}
                  </option>
                </select>
                <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-secondary/50">
                  <ChevronDownIcon class="w-4 h-4" />
                </div>
              </div>
              <button type="button"
                class="shrink-0 rounded-2xl bg-brand-50/30 px-4 text-secondary hover:text-brand-600 hover:bg-brand-50 transition-colors"
                :disabled="datasetsLoading" @click.prevent="refreshDatasets" title="刷新数据集">
                <ArrowPathIcon class="h-5 w-5" :class="{ 'animate-spin': datasetsLoading }" />
              </button>
            </div>
            <p v-if="datasetsError" class="text-xs text-rose-600 pl-1">{{ datasetsError }}</p>
          </label>
        </div>

        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-primary ml-1">选择数据清洗存档 (Clean Archive)</span>
            <button type="button"
              class="text-[10px] font-bold text-brand-600 hover:text-brand-700 disabled:opacity-50 transition-colors"
              :disabled="cleanArchivesState.loading" @click.prevent="fetchCleanArchives({ force: true })">
              {{ cleanArchivesState.loading ? '加载中...' : '刷新列表' }}
            </button>
          </div>

          <div v-if="cleanArchivesState.loading"
            class="rounded-2xl border-0 bg-brand-50/30 p-8 text-center text-xs text-secondary animate-pulse">
            正在查找相关存档...
          </div>
          <div v-else-if="!cleanArchivesState.data.length"
            class="rounded-2xl border border-dashed border-black/10 bg-brand-50/10 p-8 text-center text-xs text-secondary">
            暂无 Clean 存档，处理前请确保该日期已完成数据清洗步骤。
          </div>
          <div v-else class="flex flex-wrap gap-3" role="radiogroup">
            <button v-for="archive in cleanArchivesState.data" :key="archive.date" type="button" role="radio"
              class="group relative inline-flex flex-col gap-1 rounded-[1.25rem] border px-5 py-3 text-left transition-all"
              :class="selectedCleanDate === archive.date
                ? 'bg-brand-600 border-brand-600 text-white'
                : 'bg-white border-black/5 text-secondary hover:border-brand-200 hover:bg-brand-50/30'"
              :aria-checked="selectedCleanDate === archive.date" @click="selectCleanArchive(archive.date)">
              <span class="text-sm font-bold">{{ archive.date }}</span>
              <span class="text-[10px] opacity-70"
                :class="selectedCleanDate === archive.date ? 'text-brand-100' : 'text-muted'">
                {{ archive.channels?.length || 0 }} 渠道数据集
              </span>
              <span v-if="archive.matches_dataset"
                class="absolute -top-1.5 -right-1.5 block h-4 w-4 rounded-full bg-emerald-500 border-2 border-white ring- emerald-100"
                title="数据集匹配">
                <CheckIcon class="p-0.5 text-white" />
              </span>
            </button>
          </div>
          <p v-if="cleanArchivesState.error" class="text-xs text-rose-600 pl-1">{{ cleanArchivesState.error }}</p>
        </div>
      </form>

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-4">
        <button type="button"
          class="inline-flex items-center gap-2 rounded-full bg-brand-600 px-10 py-3 text-sm font-bold text-white transition-all hover:bg-brand-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="triggerState.requesting" @click="runFilter">
          <SparklesIcon class="h-4 w-4" />
          <span>{{ triggerState.requesting ? '正在启动...' : '开始执行数据筛选' }}</span>
        </button>
        <transition name="fade">
          <p v-if="triggerState.message" class="text-xs font-bold px-5 py-2.5 rounded-xl border"
            :class="triggerState.success ? 'bg-emerald-50 border-emerald-100 text-emerald-700' : 'bg-rose-50 border-rose-100 text-rose-700'">
            {{ triggerState.message }}
          </p>
        </transition>
      </div>
    </section>

    <!-- Run Progress & Results -->
    <section class="rounded-3xl bg-surface p-8 border border-black/5 space-y-8">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-lg font-bold text-primary">运行进度 & 结果</h2>
          <p class="text-xs text-secondary">
            实时查看筛选进度与结果摘要。
          </p>
        </div>
        <div class="text-[10px] font-bold text-secondary bg-brand-50 px-3 py-1.5 rounded-full border border-brand-100">
          最后更新: {{ summaryUpdatedAt || '等待同步' }}
        </div>
      </header>

      <!-- Premium Progress Widget -->
      <div class="group space-y-6 rounded-3xl bg-brand-50/20 p-6 border border-brand-100/50">
        <div class="space-y-3">
          <div class="flex items-center justify-between text-xs font-bold">
            <span class="text-primary flex items-center gap-2">
              <div class="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse"></div>
              总体完成进度
            </span>
            <span class="text-brand-600">{{ progressPercent }}%</span>
          </div>
          <div class="h-3 rounded-full bg-white border border-black/5 p-0.5 overflow-hidden">
            <div
              class="h-full rounded-full bg-gradient-to-r from-brand-400 to-brand-600 transition-all duration-700 ease-out"
              :style="{ width: `${progressPercent}%` }"></div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div class="rounded-2xl bg-white p-4 border border-black/5 transition-colors group-hover:bg-brand-50/50">
            <div class="text-[10px] text-muted font-bold uppercase tracking-wider mb-1">Total Items</div>
            <div class="text-lg font-bold text-primary">{{ statusState.progress.total }}</div>
          </div>
          <div class="rounded-2xl bg-white p-4 border border-black/5 transition-colors group-hover:bg-brand-50/50">
            <div class="text-[10px] text-muted font-bold uppercase tracking-wider mb-1">Processed</div>
            <div class="text-lg font-bold text-primary">{{ statusState.progress.completed }}</div>
          </div>
          <div class="rounded-2xl bg-white p-4 border border-black/5 transition-colors group-hover:bg-brand-50/50">
            <div class="text-[10px] text-muted font-bold uppercase tracking-wider mb-1">Kept (Passed)</div>
            <div class="text-xl font-bold text-brand-600">{{ statusState.progress.kept }}</div>
          </div>
          <div class="rounded-2xl bg-white p-4 border border-black/5 transition-colors group-hover:bg-brand-50/50">
            <div class="text-[10px] text-muted font-bold uppercase tracking-wider mb-1">Tokens Usage</div>
            <div class="text-xl font-bold text-secondary">{{ tokenUsageDisplay }}</div>
          </div>
        </div>
      </div>

      <!-- Live Logs -->
      <div class="space-y-3">
        <div class="flex items-center justify-between px-1">
          <span class="text-xs font-bold text-primary">实时处理动态</span>
          <span class="text-[10px] text-muted font-medium">Auto-scrolling · Recent {{ recentLimit }}</span>
        </div>
        <div
          class="max-h-80 overflow-y-auto rounded-3xl bg-brand-50/10 p-3 space-y-2 border border-black/5 sidebar-scroll">
          <div v-if="!statusState.recentRecords.length"
            class="flex flex-col items-center justify-center py-12 text-muted">
            <ClockIcon class="mb-3 h-8 w-8 opacity-20" />
            <span class="text-xs font-medium">任务暂未启动，正在等待后端数据包...</span>
          </div>
          <transition-group name="list" tag="div" class="space-y-2">
            <div v-for="(record, index) in statusState.recentRecords"
              :key="`${index}-${record.channel}-${record.index}`"
              class="rounded-2xl bg-white p-4 border border-black/5 transition hover:border-brand-200">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-3">
                  <span
                    class="rounded-lg px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-brand-50 text-brand-700 border border-brand-100/50">
                    {{ record.channel }}
                  </span>
                  <span class="text-[10px] text-muted font-medium">{{ formatTimestamp(record.updated_at).split(' ')[1]
                    }}</span>
                </div>
                <span class="rounded-full px-3 py-0.5 text-[10px] font-bold"
                  :class="record.status === 'kept' ? 'bg-emerald-500 text-white' : 'bg-rose-50 text-rose-600 border border-rose-100'">
                  {{ record.status === 'kept' ? '✓ 保留' : '✕ 过滤' }}
                </span>
              </div>
              <p class="text-[13px] leading-relaxed text-primary line-clamp-2">{{ record.preview || '（内容解析中...）' }}</p>
              <div v-if="record.classification" class="mt-2 flex flex-wrap gap-1">
                <span
                  class="inline-flex items-center rounded-md bg-brand-50 px-2 py-1 text-[10px] font-bold text-brand-700">
                  <HashtagIcon class="mr-1 h-3 w-3" />
                  {{ record.classification }}
                </span>
              </div>
            </div>
          </transition-group>
        </div>
      </div>

      <p v-if="statusState.message"
        class="rounded-2xl bg-rose-50 border border-rose-100 px-5 py-3 text-xs font-bold text-rose-600">
        {{ statusState.message }}
      </p>

      <!-- Final Summary -->
      <div v-if="statusState.summary.completed || statusState.summary.total_rows > 0"
        class="pt-6 border-t border-black/5">
        <header class="flex flex-wrap items-center justify-between gap-4 mb-6 px-1">
          <div class="flex items-center gap-2">
            <div class="w-1.5 h-6 bg-brand-600 rounded-full"></div>
            <h3 class="text-base font-bold text-primary">典型样本分析</h3>
          </div>
          <div class="flex bg-brand-50/50 p-1 rounded-2xl border border-black/5">
            <button v-for="tab in summaryTabOptions" :key="tab.value" type="button"
              class="px-5 py-2 text-[11px] font-bold rounded-xl transition-all"
              :class="summaryTab === tab.value ? 'bg-white text-brand-600 border border-black/5' : 'text-secondary hover:text-primary'"
              @click="summaryTab = tab.value">
              {{ tab.label }}
            </button>
          </div>
        </header>

        <div class="grid gap-4 md:grid-cols-2">
          <div v-if="!currentSummarySamples.length"
            class="col-span-full rounded-3xl bg-brand-50/10 p-10 text-center text-xs text-secondary border border-dashed border-black/10">
            {{ summaryEmptyMessage }}
          </div>
          <article v-for="(item, index) in currentSummarySamples" :key="`${summaryTab}-${item.channel}-${index}`"
            class="rounded-2xl bg-white p-5 border border-black/5 transition hover:border-brand-200 group">
            <div class="flex items-center justify-between mb-3">
              <span
                class="rounded-md bg-brand-50 px-2 py-0.5 text-[10px] font-bold text-brand-700 border border-brand-100/50">{{
                  item.channel }}</span>
              <span class="text-[10px] text-muted font-bold">#{{ item.index }}</span>
            </div>
            <h4 class="text-sm font-bold text-primary mb-2 line-clamp-1 group-hover:text-brand-600 transition-colors">{{
              item.title || '无标题记录' }}</h4>
            <p class="text-[12px] leading-[1.6] text-secondary line-clamp-4">{{ item.preview }}</p>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  AdjustmentsHorizontalIcon,
  SparklesIcon,
  PlusIcon,
  XMarkIcon,
  CheckIcon,
  ArrowPathIcon,
  ClockIcon,
  HashtagIcon,
  ChevronDownIcon
} from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'
import { useTopicCreationProject } from '../../composables/useTopicCreationProject'

const { ensureApiBase } = useApiBase()
const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}
const POLL_INTERVAL = 1000
const RECENT_LIMIT = 40

const {
  projectOptions,
  projectsLoading,
  projectsError,
  selectedProjectName,
  loadProjects,
  refreshProjects
} = useTopicCreationProject()

const datasets = ref([])
const datasetsLoading = ref(false)
const datasetsError = ref('')
const selectedDatasetId = ref('')
const lastFetchedProjectName = ref('')
const cleanArchivesState = reactive({
  loading: false,
  error: '',
  data: [],
  latest: '',
  lastProject: '',
  lastDataset: ''
})
const selectedCleanDate = ref('')

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
    percentage: 0,
    tokens: 0
  },
  recentRecords: [],
  summary: {
    total_rows: 0,
    kept_rows: 0,
    discarded_rows: 0,
    token_usage: 0,
    completed: false,
    updated_at: ''
  },
  relevantSamples: [],
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
const supportsEventSource = typeof window !== 'undefined' && typeof window.EventSource !== 'undefined'
const statusStream = ref(null)
const usingPollingFallback = ref(!supportsEventSource)

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
const tokenNumberFormatter = new Intl.NumberFormat('zh-CN')

const currentProjectName = computed(() => selectedProjectName.value || '')

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

const tokenUsageDisplay = computed(() => {
  const value = Number(statusState.summary.token_usage || statusState.progress.tokens || 0)
  if (!Number.isFinite(value) || value <= 0) {
    return '0'
  }
  return tokenNumberFormatter.format(value)
})

const summaryUpdatedAt = computed(() => formatTimestamp(statusState.summary.updated_at))
const recentLimit = computed(() => RECENT_LIMIT)

const summaryTabOptions = [
  { value: 'relevant', label: '有关摘要' },
  { value: 'irrelevant', label: '无关摘要' }
]
const summaryTab = ref(summaryTabOptions[0].value)
const currentSummarySamples = computed(() =>
  summaryTab.value === 'relevant' ? statusState.relevantSamples : statusState.irrelevantSamples
)
const summaryEmptyMessage = computed(() =>
  summaryTab.value === 'relevant'
    ? '尚未收集到有关样本。执行筛选后，可在此查看保留内容摘要。'
    : '尚未收集到无关样本。完成一次筛选后，可在此查看被剔除的代表性片段。'
)

function applyStatusPayload(raw) {
  const data = raw && typeof raw === 'object' ? raw : {}
  statusState.running = Boolean(data.running)
  const progress = data.progress || {}
  statusState.progress = {
    total: Number(progress.total || 0),
    completed: Number(progress.completed || 0),
    kept: Number(progress.kept || 0),
    failed: Number(progress.failed || 0),
    percentage: Number(progress.percentage || 0),
    tokens: Number(progress.token_usage || 0)
  }
  const recent = Array.isArray(data.recent_records) ? data.recent_records : []
  statusState.recentRecords = recent.slice(0, RECENT_LIMIT)
  const summary = data.summary || {}
  statusState.summary = {
    total_rows: Number(summary.total_rows || 0),
    kept_rows: Number(summary.kept_rows || 0),
    discarded_rows: Number(summary.discarded_rows || 0),
    token_usage: Number(summary.token_usage || statusState.progress.tokens || 0),
    completed: Boolean(summary.completed),
    updated_at: summary.updated_at || ''
  }
  statusState.relevantSamples = Array.isArray(data.relevant_samples) ? data.relevant_samples : []
  statusState.irrelevantSamples = Array.isArray(data.irrelevant_samples) ? data.irrelevant_samples : []
  statusState.aiConfig = {
    provider: data.ai_config?.provider || '',
    model: data.ai_config?.model || '',
    qps: data.ai_config?.qps ?? null,
    batch_size: data.ai_config?.batch_size ?? null,
    truncation: data.ai_config?.truncation ?? null
  }
}

watch(
  () => [templateState.theme, templateState.categories],
  () => {
    templateState.success = ''
    templateState.error = ''
  },
  { deep: true }
)

watch(
  () => [statusState.relevantSamples.length, statusState.irrelevantSamples.length],
  ([relevantCount, irrelevantCount]) => {
    if (summaryTab.value === 'relevant' && !relevantCount && irrelevantCount) {
      summaryTab.value = 'irrelevant'
    } else if (summaryTab.value === 'irrelevant' && !irrelevantCount && relevantCount) {
      summaryTab.value = 'relevant'
    }
  }
)

watch(
  () => statusState.running,
  (running) => {
    if (!usingPollingFallback.value) return
    if (running) {
      startPolling()
    } else {
      stopPolling()
    }
  }
)

onMounted(() => {
  loadProjects()
})

watch(
  currentProjectName,
  (project) => {
    stopPolling()
    closeStatusStream()
    resetDatasetState()
    resetArchivesState()
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
    openStatusStream()
  },
  { immediate: true }
)

watch(
  selectedDatasetId,
  () => {
    fetchCleanArchives({ force: true })
  }
)

watch(
  selectedCleanDate,
  (date) => {
    if (currentProjectName.value && date) {
      loadFilterStatus({ silent: true })
      openStatusStream()
    } else {
      closeStatusStream()
    }
  }
)

onBeforeUnmount(() => {
  stopPolling()
  closeStatusStream()
})

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
    const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(trimmed)}/datasets`)
    const response = await fetch(endpoint)
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
    fetchCleanArchives({ force: true })
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

/**
 * FIX: resetDatasetState was missing, causing ReferenceError when switching projects.
 */
function resetDatasetState() {
  datasets.value = []
  datasetsLoading.value = false
  datasetsError.value = ''
  selectedDatasetId.value = ''
  lastFetchedProjectName.value = ''
}

function selectCleanArchive(date, { force = false } = {}) {
  const nextValue = typeof date === 'string' ? date.trim() : ''
  if (!force && nextValue === selectedCleanDate.value) {
    return
  }
  selectedCleanDate.value = nextValue
}

function resetArchivesState() {
  cleanArchivesState.loading = false
  cleanArchivesState.error = ''
  cleanArchivesState.data = []
  cleanArchivesState.latest = ''
  cleanArchivesState.lastProject = ''
  cleanArchivesState.lastDataset = ''
  selectedCleanDate.value = ''
}

async function fetchCleanArchives({ force = false } = {}) {
  const projectName = (currentProjectName.value || '').trim()
  if (!projectName) {
    resetArchivesState()
    return
  }
  if (!force && cleanArchivesState.lastProject === projectName && cleanArchivesState.data.length) {
    return
  }

  cleanArchivesState.loading = true
  cleanArchivesState.error = ''
  try {
    const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(projectName)}/archives?layers=clean`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法加载 Clean 存档')
    }
    const data = result.data || {}
    cleanArchivesState.data = Array.isArray(data.clean) ? data.clean : []
    cleanArchivesState.latest = data.latest?.clean || ''
    cleanArchivesState.lastProject = projectName
    cleanArchivesState.lastDataset = selectedDatasetId.value

    // Auto select latest if not set or invalid
    if (cleanArchivesState.data.length) {
      const hasCurrent = cleanArchivesState.data.some(d => d.date === selectedCleanDate.value)
      if (!selectedCleanDate.value || !hasCurrent) {
        // Prefer "matches_dataset" if available
        const match = cleanArchivesState.data.find(d => d.matches_dataset)
        selectedCleanDate.value = match ? match.date : cleanArchivesState.data[0].date
      }
    } else {
      selectedCleanDate.value = ''
    }
  } catch (err) {
    cleanArchivesState.error = err instanceof Error ? err.message : '无法加载存档'
    cleanArchivesState.data = []
  } finally {
    cleanArchivesState.loading = false
  }
}

function addCategory() {
  const val = templateState.categoryInput.trim()
  if (!val) return
  if (!templateState.categories.includes(val)) {
    templateState.categories.push(val)
  }
  templateState.categoryInput = ''
}

function removeCategory(index) {
  templateState.categories.splice(index, 1)
}

function resetStatusState() {
  statusState.loading = false
  statusState.running = false
  statusState.progress = { total: 0, completed: 0, kept: 0, failed: 0, percentage: 0, tokens: 0 }
  statusState.recentRecords = []
  statusState.summary = { total_rows: 0, kept_rows: 0, discarded_rows: 0, completed: false, updated_at: '', token_usage: 0 }
  statusState.relevantSamples = []
  statusState.irrelevantSamples = []
  statusState.message = ''
}

async function loadTemplate(projectName) {
  templateState.loading = true
  templateState.exists = false
  templateState.metadataMissing = false
  storedTemplate.value = ''

  try {
    const endpoint = await buildApiUrl(`/filter/template?project_name=${encodeURIComponent(projectName)}`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (response.ok && result.status === 'ok') {
      templateState.exists = true
      const data = result.data || {}
      templateState.theme = data.theme || ''
      templateState.categories = Array.isArray(data.categories) ? data.categories : []
      if (!data.theme && (!data.categories || !data.categories.length)) {
        templateState.metadataMissing = true
        storedTemplate.value = data.raw_content || ''
      }
      // Update baseline
      templateBaseline.theme = templateState.theme
      templateBaseline.categories = [...templateState.categories]
    } else {
      // Not found or error, just reset
      templateState.theme = ''
      templateState.categories = []
    }
  } catch {
    // Ignore error
  } finally {
    templateState.loading = false
  }
}

async function saveTemplate() {
  if (templateState.saving) return
  templateState.saving = true
  templateState.success = ''
  templateState.error = ''

  try {
    const payload = {
      project_name: currentProjectName.value,
      theme: templateState.theme,
      categories: templateState.categories
    }
    const endpoint = await buildApiUrl('/filter/template')
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    if (response.ok && result.status === 'ok') {
      templateState.success = '模板配置已保存'
      templateState.exists = true
      templateState.metadataMissing = false
      templateBaseline.theme = templateState.theme
      templateBaseline.categories = [...templateState.categories]
    } else {
      throw new Error(result.message || '保存失败')
    }
  } catch (err) {
    templateState.error = err instanceof Error ? err.message : '保存失败'
  } finally {
    templateState.saving = false
  }
}

async function loadFilterStatus({ silent = false } = {}) {
  const project = currentProjectName.value
  const date = selectedCleanDate.value
  if (!project || !date) return

  if (!silent) statusLoading.value = true
  try {
    const endpoint = await buildApiUrl(`/filter/status?project_name=${encodeURIComponent(project)}&date=${date}`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (response.ok && result.status === 'ok') {
      applyStatusPayload(result.data)
    }
  } catch {
    // ignore
  } finally {
    if (!silent) statusLoading.value = false
  }
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

async function openStatusStream() {
  if (!supportsEventSource) {
    usingPollingFallback.value = true
    return
  }

  closeStatusStream()
  const project = currentProjectName.value
  const date = selectedCleanDate.value
  if (!project || !date) return

  const endpoint = await buildApiUrl(`/filter/stream?project_name=${encodeURIComponent(project)}&date=${date}`)
  const es = new EventSource(endpoint)
  statusStream.value = es

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      applyStatusPayload(data)
    } catch {
      // ignore parse error
    }
  }
  es.onerror = () => {
    // If stream fails, fallback to polling might be better, or just retry
    es.close()
    // For now we don't automatically fallback to polling to avoid flapping, 
    // unless strictly needed. The user can refresh page.
  }
}

function closeStatusStream() {
  if (statusStream.value) {
    statusStream.value.close()
    statusStream.value = null
  }
}

async function runFilter() {
  if (triggerState.requesting) return
  if (!currentProjectName.value || !selectedCleanDate.value) {
    triggerState.error = '请先选择项目与 Clean 存档'
    return
  }
  triggerState.requesting = true
  triggerState.success = null
  triggerState.message = ''

  try {
    const payload = {
      project_name: currentProjectName.value,
      date: selectedCleanDate.value,
      dataset_ids: selectedDatasetId.value ? [selectedDatasetId.value] : []
    }
    const endpoint = await buildApiUrl('/filter/run')
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    if (response.ok && result.status === 'ok') {
      triggerState.success = true
      triggerState.message = '筛选任务已提交'
      loadFilterStatus()
      if (usingPollingFallback.value) {
        startPolling()
      }
    } else {
      throw new Error(result.message || '提交失败')
    }
  } catch (err) {
    triggerState.success = false
    triggerState.message = err instanceof Error ? err.message : '请求失败'
  } finally {
    triggerState.requesting = false
  }
}
</script>

<style scoped>
.scrollbar-dark::-webkit-scrollbar {
  width: 6px;
}

.scrollbar-dark::-webkit-scrollbar-track {
  background: transparent;
}

.scrollbar-dark::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}

.scrollbar-dark::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

.list-enter-active,
.list-leave-active {
  transition: all 0.5s ease;
}

.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
</style>
