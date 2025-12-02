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
        <label class="space-y-1 text-sm">
          <span class="font-medium text-secondary">选择项目</span>
          <div class="flex flex-wrap items-center gap-3">
            <select
              v-if="projectOptions.length"
              v-model="selectedProjectName"
              class="inline-flex min-w-[220px] items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              :disabled="projectsLoading"
            >
              <option disabled value="">请选择项目</option>
              <option v-for="option in projectOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <span v-else class="text-xs text-muted">
              暂无项目，请先在“项目数据”模块创建。
            </span>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="projectsLoading"
              @click.prevent="refreshProjects"
            >
              {{ projectsLoading ? '加载中…' : '刷新项目' }}
            </button>
          </div>
          <p v-if="projectsError" class="mt-2 rounded-2xl bg-rose-50 px-3 py-1 text-xs text-rose-600">
            {{ projectsError }}
          </p>
        </label>
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
        <div class="space-y-2 text-sm">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span class="font-medium text-secondary">选择 Clean 存档</span>
              <p class="text-xs text-muted">请选择要执行筛选的 Clean 输出日期。</p>
            </div>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="cleanArchivesState.loading"
              @click.prevent="fetchCleanArchives({ force: true })"
            >
              {{ cleanArchivesState.loading ? '刷新中…' : '刷新存档' }}
            </button>
          </div>
          <p v-if="cleanArchivesState.error" class="rounded-2xl bg-rose-100 px-3 py-1 text-xs text-rose-600">
            {{ cleanArchivesState.error }}
          </p>
          <div v-if="cleanArchivesState.loading" class="rounded-2xl bg-surface-muted px-3 py-2 text-xs text-muted">
            存档加载中…
          </div>
          <p v-else-if="!cleanArchivesState.data.length" class="rounded-2xl bg-surface-muted px-3 py-2 text-xs text-muted">
            暂未找到 Clean 存档，请确认已完成清洗。
          </p>
          <div
            v-else
            class="flex flex-wrap gap-2"
            role="radiogroup"
            aria-label="Clean 存档"
          >
            <button
              v-for="archive in cleanArchivesState.data"
              :key="archive.date"
              type="button"
              role="radio"
              class="inline-flex flex-col gap-1 rounded-2xl border px-3 py-2 text-left text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              :class="selectedCleanDate === archive.date
                ? 'border-brand-soft bg-brand-soft/70 text-brand-700 shadow-sm'
                : 'border-soft bg-surface text-secondary hover:border-brand-soft hover:text-brand-600'"
              :aria-checked="selectedCleanDate === archive.date"
              @click="selectCleanArchive(archive.date)"
            >
              <span class="text-sm font-semibold text-primary">{{ archive.date }}</span>
              <span class="text-[11px] text-muted">
                {{ archive.channels?.length || 0 }} 渠道 · 更新于 {{ archive.updated_at?.slice(0, 19) || '—' }}
              </span>
              <span
                v-if="archive.matches_dataset"
                class="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700"
              >
                匹配当前数据集
              </span>
            </button>
          </div>
        </div>
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
        <dl class="grid gap-3 text-xs text-secondary sm:grid-cols-4">
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
          <div class="rounded-2xl bg-surface-muted px-4 py-3">
            <dt class="text-[11px] uppercase tracking-widest text-muted">Token 消耗</dt>
            <dd class="mt-1 text-base font-semibold text-primary">
              {{ tokenUsageDisplay }}
              <span class="ml-1 text-xs text-muted">token</span>
            </dd>
          </div>
        </dl>
      </div>

      <div class="space-y-3">
        <div class="flex items-center justify-between text-sm">
          <span class="font-medium text-secondary">当前处理状态</span>
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

      <div class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 class="text-sm font-medium text-secondary">样本摘要预览</h3>
            <p class="text-xs text-muted">切换查看被保留与被剔除的代表性内容。</p>
          </div>
          <div class="inline-flex items-center gap-1 rounded-full bg-surface-muted p-1 text-xs font-semibold">
            <button
              v-for="tab in summaryTabOptions"
              :key="tab.value"
              type="button"
              class="rounded-full px-3 py-1.5 transition"
              :class="[
                summaryTab === tab.value
                  ? 'bg-white text-primary shadow-sm'
                  : 'text-muted hover:text-primary'
              ]"
              @click="summaryTab = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <p
            v-if="!currentSummarySamples.length"
            class="rounded-2xl border border-dashed border-soft bg-surface-muted px-4 py-3 text-xs text-muted"
          >
            {{ summaryEmptyMessage }}
          </p>
          <article
            v-for="(item, index) in currentSummarySamples"
            :key="`${summaryTab}-${item.channel}-${index}`"
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
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  AdjustmentsHorizontalIcon,
  SparklesIcon,
  PlusIcon,
  XMarkIcon
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
  selectCleanArchive('', { force: true })
}

function syncCleanArchiveSelection() {
  const archives = Array.isArray(cleanArchivesState.data) ? cleanArchivesState.data : []
  if (!archives.length) {
    selectCleanArchive('', { force: true })
    return
  }
  if (!selectedCleanDate.value || !archives.some((item) => item.date === selectedCleanDate.value)) {
    const preferred = archives.find((item) => item.matches_dataset)
    const fallback = (preferred && preferred.date) || cleanArchivesState.latest || archives[0]?.date || ''
    selectCleanArchive(fallback, { force: true })
  }
}

async function fetchCleanArchives({ force = false } = {}) {
  const projectName = (currentProjectName.value || '').trim()
  if (!projectName) {
    resetArchivesState()
    return
  }
  const datasetId = (selectedDatasetId.value || '').trim()
  if (
    !force &&
    cleanArchivesState.lastProject === projectName &&
    cleanArchivesState.lastDataset === datasetId &&
    cleanArchivesState.data.length
  ) {
    return
  }

  cleanArchivesState.loading = true
  cleanArchivesState.error = ''
  try {
    const params = new URLSearchParams({ layers: 'clean' })
    if (datasetId) {
      params.append('dataset_id', datasetId)
    }
    const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(projectName)}/archives?${params.toString()}`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法获取 Clean 存档')
    }
    const archives = result.archives || {}
    cleanArchivesState.data = Array.isArray(archives.clean) ? archives.clean : []
    cleanArchivesState.latest = result.latest?.clean || ''
    cleanArchivesState.lastProject = projectName
    cleanArchivesState.lastDataset = datasetId
    syncCleanArchiveSelection()
  } catch (err) {
    cleanArchivesState.error = err instanceof Error ? err.message : '无法获取 Clean 存档'
    cleanArchivesState.data = []
    cleanArchivesState.latest = ''
    cleanArchivesState.lastProject = ''
    cleanArchivesState.lastDataset = ''
    selectCleanArchive('', { force: true })
  } finally {
    cleanArchivesState.loading = false
  }
}

async function loadTemplate(projectName) {
  templateState.loading = true
  templateState.error = ''
  templateState.success = ''
  try {
    const params = new URLSearchParams({ project: projectName })
    const endpoint = await buildApiUrl(`/filter/template?${params.toString()}`)
    const response = await fetch(endpoint)
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
    const endpoint = await buildApiUrl('/filter/template')
    const response = await fetch(endpoint, {
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
  const projectName = (currentProjectName.value || '').trim()
  const dateValue = (selectedCleanDate.value || '').trim()
  if (!projectName || !dateValue) {
    resetStatusState()
    return
  }
  if (!silent) {
    statusLoading.value = true
    statusState.message = ''
  }

  try {
    const params = new URLSearchParams({
      project: projectName,
      date: dateValue
    })
    const endpoint = await buildApiUrl(`/filter/status?${params.toString()}`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法获取筛选状态')
    }
    applyStatusPayload(result.data)
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
  resetArchivesState()
}

function resetStatusState() {
  statusState.progress = {
    total: 0,
    completed: 0,
    kept: 0,
    failed: 0,
    percentage: 0,
    tokens: 0
  }
  statusState.recentRecords = []
  statusState.summary = {
    total_rows: 0,
    kept_rows: 0,
    discarded_rows: 0,
    token_usage: 0,
    completed: false,
    updated_at: ''
  }
  statusState.relevantSamples = []
  statusState.irrelevantSamples = []
  statusState.message = ''
  statusState.running = false
  summaryTab.value = summaryTabOptions[0].value
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

function disablePollingFallback() {
  if (!usingPollingFallback.value) {
    stopPolling()
    return
  }
  usingPollingFallback.value = false
  stopPolling()
}

function enablePollingFallback() {
  if (usingPollingFallback.value) return
  usingPollingFallback.value = true
  if (statusState.running) {
    startPolling()
  }
}

function closeStatusStream() {
  if (statusStream.value) {
    statusStream.value.close()
    statusStream.value = null
  }
}

async function openStatusStream() {
  if (!supportsEventSource) {
    enablePollingFallback()
    return
  }
  const projectName = (currentProjectName.value || '').trim()
  const dateValue = (selectedCleanDate.value || '').trim()
  if (!projectName || !dateValue) {
    closeStatusStream()
    return
  }
  disablePollingFallback()
  const params = new URLSearchParams({
    project: projectName,
    date: dateValue
  })
  closeStatusStream()
  const endpoint = await buildApiUrl(`/filter/status/stream?${params.toString()}`)
  const source = new EventSource(endpoint)
  statusStream.value = source
  source.onmessage = (event) => {
    if (!event.data) return
    try {
      const payload = JSON.parse(event.data)
      if (payload && payload.data) {
        applyStatusPayload(payload.data)
        statusState.message = ''
      }
    } catch {
      // ignore malformed chunks
    }
  }
  source.addEventListener('done', () => {
    closeStatusStream()
  })
  source.addEventListener('error', () => {
    closeStatusStream()
    enablePollingFallback()
    loadFilterStatus({ silent: true })
  })
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
  if (!selectedCleanDate.value) {
    triggerState.success = false
    triggerState.message = '请选择需要筛选的 Clean 存档'
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
      date: selectedCleanDate.value
    }
    if (selectedDatasetId.value) {
      payload.dataset_id = selectedDatasetId.value
    }
    const endpoint = await buildApiUrl('/filter')
    const response = await fetch(endpoint, {
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
      openStatusStream()
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
