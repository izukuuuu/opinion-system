<template>
  <div class="space-y-10">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">上传原始数据</h1>
        <p class="text-sm text-secondary">创建专题并上传 Excel/CSV 文件，生成标准化存档。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <CloudArrowUpIcon class="h-4 w-4" />
        <span>步骤 1 · 上传</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6 lg:mx-auto lg:max-w-5xl xl:mx-0 xl:max-w-none">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">创建专题</h2>
        <p class="text-sm text-secondary">填写专题名称后创建记录，系统将用于跟踪后续流程。</p>
      </header>
      <form
        class="grid gap-4 sm:grid-cols-[minmax(0,320px)] lg:grid-cols-[minmax(0,420px),minmax(0,340px)] xl:grid-cols-[minmax(0,3fr),minmax(0,2fr)]"
        @submit.prevent="createTopic"
      >
        <div class="space-y-4">
          <label class="space-y-1 text-sm">
            <span class="font-medium text-secondary">专题名称</span>
            <input
              v-model.trim="topicName"
              type="text"
              required
              class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="例如：2024-两会舆情"
            />
          </label>
          <label class="space-y-1 text-sm">
            <span class="font-medium text-secondary">专题说明（可选）</span>
            <textarea
              v-model.trim="topicDescription"
              rows="3"
              class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200 resize-none"
              :placeholder="selectedTags.length ? '补充专题背景、抓取渠道等信息，将自动附加在标签前缀之后。' : '补充专题背景、抓取渠道等信息。'"
            ></textarea>
          </label>
          <div class="space-y-2 rounded-xl border border-dashed border-soft bg-surface px-3.5 py-3 text-xs text-secondary">
            <div class="flex items-center gap-2 text-[13px] font-medium text-secondary">
              <TagIcon class="h-4 w-4 text-brand-500" />
              推荐标签
            </div>
            <p class="text-xs text-muted">点击快速补充专题说明，可多选。</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="tag in suggestedTags"
                :key="tag"
                type="button"
                class="inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium transition focus:outline-none focus:ring-2 focus:ring-brand-200"
                :class="selectedTags.includes(tag)
                  ? 'border-brand bg-brand-soft text-brand-700 shadow-sm'
                  : 'border-soft bg-white text-secondary hover:border-brand-soft hover:text-brand-600'"
                @click="toggleTag(tag)"
              >
                <span>{{ tag }}</span>
              </button>
            </div>
            <div v-if="selectedTags.length" class="space-y-1 rounded-xl bg-surface px-3 py-2 text-xs text-secondary">
              <p class="font-semibold text-primary">已选标签</p>
              <p class="text-muted">{{ selectedTags.join(' · ') }}</p>
            </div>
          </div>
          <div class="flex items-center justify-end pt-2">
            <button
              type="submit"
              class="btn-base btn-tone-primary inline-flex items-center gap-2 px-5 py-2"
              :disabled="creating || !topicName"
            >
              <span v-if="creating">创建中…</span>
              <span v-else>创建专题</span>
            </button>
          </div>
        </div>
        <aside
          class="rounded-xl border border-soft bg-surface px-4 py-3 text-xs leading-relaxed text-secondary lg:max-w-sm xl:max-w-none"
        >
          <h3 class="mb-2 text-xs font-medium text-secondary">填写说明</h3>
          <ul class="list-disc list-inside space-y-1.5 text-xs text-muted">
            <li>专题名称将作为后续 API 调用的参数，建议使用字母、数字与短横线组合。</li>
            <li>可先创建专题再上传数据，也可直接上传，系统会在需要时自动创建专题。</li>
            <li>描述信息用于团队协作记录，可随时在设置中更新。</li>
          </ul>
        </aside>
      </form>
      <p
        v-if="createError"
        class="mt-2 rounded-xl border border-rose-100 bg-rose-50 px-4 py-2 text-xs text-rose-600"
      >
        {{ createError }}
      </p>
      <p
        v-if="createSuccess"
        class="mt-2 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-2 text-xs text-emerald-600"
      >
        {{ createSuccess }}
      </p>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-xl font-semibold text-primary">上传原始表格</h2>
          <p class="text-sm text-secondary">
            支持 .xlsx、.xls、.csv 文件。
          </p>
        </div>
        <span v-if="topicName" class="badge-soft rounded-full px-3 py-1 text-xs font-semibold text-secondary">
          当前专题：{{ topicName }}
        </span>
      </header>

      <template v-if="canUpload">
        <form class="space-y-5" @submit.prevent="uploadDataset">
          <div
            class="flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed border-brand-soft bg-surface-muted px-6 text-center text-sm text-secondary transition hover:border-brand hover:bg-brand-soft hover:text-brand-600"
            :class="{ 'border-brand bg-surface text-brand-600 shadow-inner': uploadFiles.length || dragActive }"
            @dragenter.prevent="handleDragEnter"
            @dragover.prevent="handleDragOver"
            @dragleave.prevent="handleDragLeave"
            @drop.prevent="handleDrop"
          >
            <input
              ref="fileInput"
              type="file"
              class="hidden"
              accept=".xlsx,.xls,.csv,.jsonl"
              multiple
              @change="handleFileChange"
            />
            <button type="button" class="flex flex-col items-center gap-2 text-sm" @click="fileInput?.click()">
              <DocumentArrowUpIcon class="h-10 w-10 text-slate-300" />
              <span class="font-medium">
                {{ uploadFiles.length ? selectedFileSummary : '点击或拖拽文件到此处' }}
              </span>
              <span class="text-xs text-slate-400">
                {{ uploadFiles.length ? `已选择 ${uploadFiles.length} 个文件` : '最大 50MB/单文件 · 支持拖拽、批量选择' }}
              </span>
            </button>
          </div>
          <div
            v-if="uploadFiles.length"
            class="space-y-2 rounded-2xl border border-soft bg-white/80 px-4 py-3 text-xs text-secondary shadow-sm"
          >
            <div class="flex items-center justify-between">
              <span class="font-semibold text-primary">待上传文件</span>
              <button
                type="button"
                class="text-rose-600 transition hover:text-rose-500"
                @click="clearSelectedFiles()"
              >
                清空
              </button>
            </div>
            <ul class="space-y-1 text-sm text-primary">
              <li
                v-for="(file, index) in uploadFiles"
                :key="`${file.name}-${file.lastModified}-${index}`"
                class="flex items-center justify-between gap-2 rounded-xl bg-surface-muted px-3 py-2 text-xs text-secondary"
              >
                <span class="truncate text-sm text-primary">{{ file.name }}</span>
                <button
                  type="button"
                  class="text-rose-600 transition hover:text-rose-500"
                  @click="removeSelectedFile(index)"
                >
                  移除
                </button>
              </li>
            </ul>
          </div>
          <div
            v-if="uploadStatuses.length"
            class="space-y-3 rounded-2xl border border-dashed border-slate-200 bg-white/80 px-4 py-3 text-xs text-secondary shadow-sm"
          >
            <div class="flex items-center justify-between text-[13px] font-semibold text-primary">
              <span>批量上传进度</span>
              <span>{{ uploadProgress.completed }}/{{ uploadProgress.total }} · {{ uploadProgress.percent }}%</span>
            </div>
            <div class="h-2 w-full rounded-full bg-slate-200">
              <div
                class="h-full rounded-full bg-brand transition-all"
                :style="{ width: `${Math.max(uploadProgress.percent, uploadProgress.completed ? 10 : 0)}%` }"
              ></div>
            </div>
            <ul class="space-y-1 text-sm text-primary">
              <li
                v-for="status in uploadStatuses"
                :key="status.key"
                class="flex items-center justify-between gap-2 rounded-xl bg-surface-muted px-3 py-2 text-xs text-secondary"
              >
                <span class="truncate text-sm text-primary">{{ status.name }}</span>
                <span
                  class="font-semibold"
                  :class="status.status === 'success'
                    ? 'text-emerald-600'
                    : status.status === 'error'
                      ? 'text-rose-600'
                      : 'text-slate-500'"
                >
                  {{ status.message }}
                </span>
              </li>
            </ul>
          </div>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button type="submit" class="btn-base btn-tone-primary px-6 py-2" :disabled="uploading">
              {{ uploading ? '上传中…' : '上传并生成存档' }}
            </button>
            <div class="space-y-1 text-sm">
              <p v-if="uploadHelper && !uploadError && !uploadSuccess" class="text-secondary">
                {{ uploadHelper }}
              </p>
              <p v-if="uploadError" class="text-rose-600">{{ uploadError }}</p>
              <p v-if="uploadSuccess" class="text-emerald-600">{{ uploadSuccess }}</p>
            </div>
          </div>
        </form>
        <transition name="fade" mode="out-in">
          <article
            v-if="latestDataset"
            key="dataset-card"
            class="rounded-3xl border border-brand-soft bg-white/90 p-6 shadow-inner"
          >
            <header class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="text-xs uppercase tracking-widest text-muted">最新上传</p>
                <h3 class="text-lg font-semibold text-primary">{{ latestDataset.display_name }}</h3>
                <p class="text-xs text-secondary">
                  数据集 ID：{{ latestDataset.id }} · 行列：{{ latestDataset.rows }} 行 × {{ latestDataset.column_count }} 列
                </p>
              </div>
              <span class="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">上传成功</span>
            </header>
            <div
              v-if="hasMultipleDatasets"
              class="mt-4 space-y-2 rounded-2xl bg-amber-50/80 px-4 py-3 text-xs leading-relaxed text-amber-800"
            >
              <p>
                本次上传共包含 {{ uploadedDatasets.length }} 个数据集，字段映射将一次性同步到所有数据集。
                为了确保 Merge / Clean 等后续流程顺利，请保证这些数据集来源一致、字段命名完全相同。
              </p>
              <ul class="flex flex-wrap gap-2 text-[11px] text-amber-700">
                <li
                  v-for="dataset in uploadedDatasets"
                  :key="`dataset-chip-${dataset.id}`"
                  class="rounded-full bg-white/70 px-3 py-1 font-semibold"
                >
                  {{ dataset.display_name || dataset.id }}
                </li>
              </ul>
            </div>
            <dl class="mt-4 grid gap-3 text-sm text-secondary sm:grid-cols-2 lg:grid-cols-3">
              <div class="rounded-2xl bg-surface-muted px-4 py-3">
                <dt class="text-[11px] uppercase tracking-widest text-muted">文件大小</dt>
                <dd class="mt-1 font-semibold text-primary">{{ formatFileSize(latestDataset.file_size) }}</dd>
              </div>
              <div class="rounded-2xl bg-surface-muted px-4 py-3">
                <dt class="text-[11px] uppercase tracking-widest text-muted">生成 JSONL</dt>
                <dd class="mt-1 truncate text-primary" :title="latestDataset.jsonl_file">
                  {{ latestDataset.jsonl_file }}
                </dd>
              </div>
              <div class="rounded-2xl bg-surface-muted px-4 py-3">
                <dt class="text-[11px] uppercase tracking-widest text-muted">生成 PKL</dt>
                <dd class="mt-1 truncate text-primary" :title="latestDataset.pkl_file">
                  {{ latestDataset.pkl_file }}
                </dd>
              </div>
              <div class="rounded-2xl bg-surface-muted px-4 py-3">
                <dt class="text-[11px] uppercase tracking-widest text-muted">Meta 清单</dt>
                <dd class="mt-1 truncate text-primary" :title="latestDataset.json_file">
                  {{ latestDataset.json_file }}
                </dd>
              </div>
              <div class="rounded-2xl bg-surface-muted px-4 py-3">
                <dt class="text-[11px] uppercase tracking-widest text-muted">专题名称</dt>
                <dd class="mt-1 text-primary">{{ latestDataset.project }}</dd>
              </div>
              <div class="rounded-2xl bg-surface-muted px-4 py-3">
                <dt class="text-[11px] uppercase tracking-widest text-muted">专题标识</dt>
                <dd class="mt-1 text-primary">{{ latestDataset.topic_label || '未设置' }}</dd>
              </div>
              <div class="rounded-2xl bg-surface-muted px-4 py-3">
                <dt class="text-[11px] uppercase tracking-widest text-muted">更新于</dt>
                <dd class="mt-1 text-primary">{{ formatTimestamp(latestDataset.stored_at) }}</dd>
              </div>
            </dl>
            <footer class="mt-4 flex flex-wrap items-center gap-3 text-xs text-secondary">
              <span
                v-if="Array.isArray(latestDataset.columns) && latestDataset.columns.length"
                class="rounded-full bg-surface-muted px-3 py-1"
              >
                字段：{{ latestDataset.columns.join(', ') }}
              </span>
              <span
                v-if="latestDataset.topic_label"
                class="rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600"
              >
                专题标识：{{ latestDataset.topic_label }}
              </span>
              <RouterLink
                class="inline-flex items-center gap-1 rounded-full bg-brand px-4 py-1 text-xs font-semibold text-white shadow transition hover:bg-brand-600"
                :to="{ name: 'project-data', query: { project: latestDataset.project } }"
              >
                前往数据管理
              </RouterLink>
            </footer>
            <section v-if="latestDataset" class="mt-6 space-y-4">
              <header class="space-y-1">
                <h4 class="text-sm font-semibold text-primary">字段映射</h4>
                <p class="text-xs text-secondary">
                  指定专题标识、日期、标题、正文与作者列，系统将在预处理与后续流程中使用这些字段。
                </p>
                <p v-if="hasMultipleDatasets" class="rounded-2xl bg-amber-50/80 px-3 py-2 text-[11px] text-amber-700">
                  当前选项仅展示所有数据集中共同存在的列。若列表为空，请检查各数据集字段是否对齐，或在数据管理页面统一列名后重试。
                </p>
                <p v-if="!datasetColumns.length" class="text-xs text-muted">当前尚未识别到字段列表，可先保存专题标识。</p>
              </header>
              <div class="grid gap-4 sm:grid-cols-2">
                <label class="space-y-1 text-xs sm:col-span-2">
                  <span class="font-medium text-secondary">专题标识（可选）</span>
                  <input
                    v-model="columnMappingForm.topic"
                    type="text"
                    class="w-full rounded-2xl border border-soft px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                    placeholder="为该数据集设置自定义专题名称"
                  />
                </label>
                <label class="space-y-1 text-xs">
                  <span class="font-medium text-secondary">日期列</span>
                  <select
                    v-model="columnMappingForm.date"
                    class="w-full rounded-2xl border border-soft px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                  >
                    <option value="">未指定</option>
                    <option v-for="column in datasetColumns" :key="`date-${column}`" :value="column">
                      {{ column }}
                    </option>
                  </select>
                </label>
                <label class="space-y-1 text-xs">
                  <span class="font-medium text-secondary">标题列</span>
                  <select
                    v-model="columnMappingForm.title"
                    class="w-full rounded-2xl border border-soft px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                  >
                    <option value="">未指定</option>
                    <option v-for="column in datasetColumns" :key="`title-${column}`" :value="column">
                      {{ column }}
                    </option>
                  </select>
                </label>
                <label class="space-y-1 text-xs">
                  <span class="font-medium text-secondary">正文列</span>
                  <select
                    v-model="columnMappingForm.content"
                    class="w-full rounded-2xl border border-soft px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                  >
                    <option value="">未指定</option>
                    <option v-for="column in datasetColumns" :key="`content-${column}`" :value="column">
                      {{ column }}
                    </option>
                  </select>
                </label>
                <label class="space-y-1 text-xs">
                  <span class="font-medium text-secondary">作者列</span>
                  <select
                    v-model="columnMappingForm.author"
                    class="w-full rounded-2xl border border-soft px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
                  >
                    <option value="">未指定</option>
                    <option v-for="column in datasetColumns" :key="`author-${column}`" :value="column">
                      {{ column }}
                    </option>
                  </select>
                </label>
              </div>
              <div class="flex flex-wrap items-center gap-3 text-xs">
                <button
                  type="button"
                  class="inline-flex items-center gap-2 rounded-full border border-brand-soft px-4 py-1.5 text-xs font-semibold text-brand-600 transition hover:bg-brand-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="mappingSaving"
                  @click="saveColumnMapping"
                >
                  {{ mappingSaving ? '保存中…' : '保存字段映射' }}
                </button>
                <p v-if="mappingError" class="text-rose-600">{{ mappingError }}</p>
                <p v-else-if="mappingSuccess" class="text-emerald-600">{{ mappingSuccess }}</p>
              </div>
            </section>
          </article>
        </transition>
      </template>
      <div
        v-else
        class="rounded-3xl border border-dashed border-brand-soft bg-surface-muted px-6 py-8 text-center text-sm text-secondary"
      >
        请先创建标题后再操作。
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { CloudArrowUpIcon, DocumentArrowUpIcon, TagIcon } from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'

const { ensureApiBase } = useApiBase()

const topicName = ref('')
const topicDescription = ref('')
const selectedTags = ref([])

const creating = ref(false)
const createError = ref('')
const createSuccess = ref('')

const fileInput = ref(null)
const uploadFiles = ref([])
const dragActive = ref(false)
const dragCounter = ref(0)
const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref('')
const uploadStatuses = ref([])
const uploadedDatasets = ref([])
const latestDataset = computed(() => {
  const list = uploadedDatasets.value
  return list.length ? list[list.length - 1] : null
})
const columnMappingForm = reactive({
  topic: '',
  date: '',
  title: '',
  content: '',
  author: ''
})
const mappingSaving = ref(false)
const mappingError = ref('')
const mappingSuccess = ref('')

const suggestedTags = Object.freeze([
  '舆情监测',
  '新闻采集',
  '社交媒体',
  '自动化报告',
  '关键事件',
  '专家研判'
])

const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}

const canUpload = computed(() => Boolean(createSuccess.value))

const uploadHelper = computed(() => {
  if (uploading.value) return ''
  if (!canUpload.value) return '请先创建专题后再操作'
  if (!topicName.value) return '请先填写专题名称'
  if (!uploadFiles.value.length) return '请选择需要上传的文件'
  return ''
})

const uploadProgress = computed(() => {
  const total = uploadStatuses.value.length
  if (!total) {
    return { total: 0, completed: 0, percent: 0, running: false }
  }
  const completed = uploadStatuses.value.filter((item) => ['success', 'error'].includes(item.status)).length
  const running = uploadStatuses.value.some((item) => item.status === 'uploading')
  const percent = Math.round((completed / total) * 100)
  return { total, completed, percent, running }
})

const hasMultipleDatasets = computed(() => uploadedDatasets.value.length > 1)

const datasetColumns = computed(() => {
  const batches = uploadedDatasets.value
  if (!batches.length) {
    return []
  }
  const columnSets = batches.map((dataset) => {
    if (!dataset || !Array.isArray(dataset.columns)) return []
    return dataset.columns.map((column) => column.toString())
  })
  if (!columnSets.length) return []
  return columnSets.reduce((acc, columns) => {
    if (!acc.length) return columns
    return acc.filter((column) => columns.includes(column))
  }, columnSets[0])
})

const mappingTargets = computed(() => uploadedDatasets.value)

const tagPrefix = computed(() => {
  if (!selectedTags.value.length) return ''
  return selectedTags.value.map((item) => `#${item}`).join(' · ')
})

const descriptionPayload = computed(() => {
  const prefix = tagPrefix.value
  const body = topicDescription.value.trim()
  if (prefix && body) {
    return `${prefix}\n\n${body}`
  }
  return prefix || body
})

const toggleTag = (tag) => {
  if (selectedTags.value.includes(tag)) {
    selectedTags.value = selectedTags.value.filter((item) => item !== tag)
  } else {
    selectedTags.value = [...selectedTags.value, tag]
  }
}

const formatFileSize = (value) => {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const size = bytes / Math.pow(1024, exponent)
  return `${size.toFixed(size >= 100 || exponent === 0 ? 0 : 1)} ${units[exponent]}`
}

const datetimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
})

const formatTimestamp = (value) => {
  if (!value) return '—'
  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return datetimeFormatter.format(date)
  } catch (error) {
    return value
  }
}

const applyDatasetMapping = (dataset) => {
  if (!dataset || typeof dataset !== 'object') {
    columnMappingForm.date = ''
    columnMappingForm.title = ''
    columnMappingForm.content = ''
    columnMappingForm.author = ''
    columnMappingForm.topic = ''
    mappingError.value = ''
    mappingSuccess.value = ''
    return
  }
  const mapping = typeof dataset.column_mapping === 'object' && dataset.column_mapping !== null
    ? dataset.column_mapping
    : {}
  columnMappingForm.topic = typeof dataset.topic_label === 'string' ? dataset.topic_label.trim() : ''
  columnMappingForm.date = mapping.date || ''
  columnMappingForm.title = mapping.title || ''
  columnMappingForm.content = mapping.content || ''
  columnMappingForm.author = mapping.author || ''
  mappingError.value = ''
}

const updateUploadedDataset = (datasetId, updates) => {
  uploadedDatasets.value = uploadedDatasets.value.map((dataset) => {
    if (dataset.id !== datasetId) return dataset
    return {
      ...dataset,
      ...updates
    }
  })
}

const saveColumnMapping = async () => {
  const targets = mappingTargets.value
  if (!targets.length || !topicName.value) return
  mappingSaving.value = true
  mappingError.value = ''
  mappingSuccess.value = ''

  const payload = {
    column_mapping: {
      date: columnMappingForm.date || '',
      title: columnMappingForm.title || '',
      content: columnMappingForm.content || '',
      author: columnMappingForm.author || ''
    },
    topic_label: columnMappingForm.topic || ''
  }

  const failures = []
  let successCount = 0

  for (const dataset of targets) {
    try {
      const endpoint = await buildApiUrl(
        `/projects/${encodeURIComponent(dataset.project)}/datasets/${encodeURIComponent(dataset.id)}/mapping`
      )
      const response = await fetch(endpoint, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
      const result = await response.json()
      if (!response.ok || result.status !== 'ok') {
        throw new Error(result.message || '字段映射保存失败')
      }
      successCount += 1
      const nextTopicLabel = typeof result.topic_label === 'string' ? result.topic_label : payload.topic_label
      updateUploadedDataset(dataset.id, {
        column_mapping: result.column_mapping,
        topic_label: typeof nextTopicLabel === 'string' ? nextTopicLabel.trim() : ''
      })
    } catch (err) {
      failures.push({
        dataset,
        message: err instanceof Error ? err.message : '字段映射保存失败'
      })
    }
  }

  if (failures.length) {
    const failedNames = failures.map((failure) => failure.dataset.display_name || failure.dataset.id).join('、')
    mappingError.value =
      failures.length === targets.length
        ? `所有数据集字段映射保存失败：${failures[0].message}`
        : `部分数据集字段映射保存失败（${failedNames}），请检查后重试。`
  } else if (successCount) {
    mappingSuccess.value =
      successCount === 1 ? '字段映射已保存' : `字段映射已同步至 ${successCount} 个数据集`
    const firstTopic = uploadedDatasets.value[uploadedDatasets.value.length - 1]?.topic_label
    columnMappingForm.topic = typeof firstTopic === 'string' ? firstTopic.trim() : columnMappingForm.topic
  }

  mappingSaving.value = false
}

watch(
  latestDataset,
  (dataset, previous) => {
    const previousId = previous && typeof previous === 'object' ? previous.id : ''
    applyDatasetMapping(dataset)
    if (!dataset || dataset.id !== previousId) {
      mappingSuccess.value = ''
    }
  },
  { immediate: true }
)

watch(topicName, (current, previous) => {
  if (current !== previous && createSuccess.value) {
    createSuccess.value = ''
  }
})

const createTopic = async () => {
  if (!topicName.value) return
  creating.value = true
  createError.value = ''
  createSuccess.value = ''

  try {
    const endpoint = await buildApiUrl('/projects')
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: topicName.value,
        description: descriptionPayload.value || undefined,
        metadata: selectedTags.value.length ? { tags: selectedTags.value } : undefined
      })
    })

    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '专题创建失败')
    }
    createSuccess.value = '专题创建成功，可以继续上传数据。'
  } catch (err) {
    createError.value = err instanceof Error ? err.message : '专题创建失败'
  } finally {
    creating.value = false
  }
}

const selectedFileSummary = computed(() => {
  if (!uploadFiles.value.length) return ''
  if (uploadFiles.value.length === 1) return uploadFiles.value[0].name
  if (uploadFiles.value.length === 2) return `${uploadFiles.value[0].name}、${uploadFiles.value[1].name}`
  return `${uploadFiles.value[0].name} 等 ${uploadFiles.value.length} 个文件`
})

const resetFileInput = () => {
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const addSelectedFiles = (files) => {
  if (!files.length) return false
  const existingKeys = new Set(
    uploadFiles.value.map((file) => `${file.name}-${file.size}-${file.lastModified}`)
  )
  const next = uploadFiles.value.slice()
  files.forEach((file) => {
    const key = `${file.name}-${file.size}-${file.lastModified}`
    if (!existingKeys.has(key)) {
      existingKeys.add(key)
      next.push(file)
    }
  })
  if (next.length === uploadFiles.value.length) {
    return false
  }
  uploadFiles.value = next
  uploadError.value = ''
  uploadSuccess.value = ''
  uploadedDatasets.value = []
  uploadStatuses.value = []
  return true
}

const handleFileChange = (event) => {
  const files = Array.from(event?.target?.files || [])
  addSelectedFiles(files)
  resetFileInput()
}

const clearSelectedFiles = ({ resetStatuses = true } = {}) => {
  uploadFiles.value = []
  resetFileInput()
  if (resetStatuses) {
    uploadStatuses.value = []
  }
}

const removeSelectedFile = (index) => {
  if (index < 0 || index >= uploadFiles.value.length) return
  const next = uploadFiles.value.slice()
  next.splice(index, 1)
  uploadFiles.value = next
  if (!next.length) {
    resetFileInput()
  }
}

const handleDragEnter = (event) => {
  event?.preventDefault?.()
  dragCounter.value += 1
  dragActive.value = true
}

const handleDragOver = (event) => {
  event?.preventDefault?.()
  if (!dragActive.value) {
    dragActive.value = true
  }
}

const handleDragLeave = (event) => {
  event?.preventDefault?.()
  dragCounter.value = Math.max(dragCounter.value - 1, 0)
  if (dragCounter.value === 0) {
    dragActive.value = false
  }
}

const handleDrop = (event) => {
  event?.preventDefault?.()
  const files = Array.from(event?.dataTransfer?.files || [])
  dragCounter.value = 0
  dragActive.value = false
  if (addSelectedFiles(files)) {
    resetFileInput()
  }
}

const normaliseDatasetPayload = (dataset) => {
  if (!dataset || typeof dataset !== 'object') return null
  return {
    ...dataset,
    topic_label: typeof dataset.topic_label === 'string' ? dataset.topic_label.trim() : ''
  }
}

const uploadDataset = async () => {
  if (!topicName.value) {
    uploadError.value = '请填写专题名称后再上传'
    return
  }
  if (!uploadFiles.value.length) {
    uploadError.value = '请选择需要上传的文件'
    return
  }

  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = ''

  uploadStatuses.value = uploadFiles.value.map((file, index) => ({
    key: `${file.name}-${file.size}-${file.lastModified}-${index}`,
    name: file.name,
    status: 'pending',
    message: '排队中'
  }))

  const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(topicName.value)}/datasets`)
  const successes = []
  const failures = []

  for (const [index, file] of uploadFiles.value.entries()) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      if (uploadStatuses.value[index]) {
        uploadStatuses.value[index].status = 'uploading'
        uploadStatuses.value[index].message = '上传中…'
      }
      const response = await fetch(endpoint, {
        method: 'POST',
        body: formData
      })
      const result = await response.json()
      if (!response.ok || result.status !== 'ok') {
        throw new Error(result.message || '上传失败')
      }
      const uploadedDatasetsRaw = Array.isArray(result.datasets)
        ? result.datasets
        : result.dataset
          ? [result.dataset]
          : []
      const datasetEntries = uploadedDatasetsRaw
        .map(normaliseDatasetPayload)
        .filter((dataset) => Boolean(dataset))
      const dataset = datasetEntries.length ? datasetEntries[datasetEntries.length - 1] : null
      successes.push({ file, dataset })
      if (uploadStatuses.value[index]) {
        uploadStatuses.value[index].status = 'success'
        uploadStatuses.value[index].message = '上传完成'
      }
    } catch (err) {
      failures.push({ file, message: err instanceof Error ? err.message : '上传失败' })
      if (uploadStatuses.value[index]) {
        uploadStatuses.value[index].status = 'error'
        uploadStatuses.value[index].message = err instanceof Error ? err.message : '上传失败'
      }
    }
  }

  const succeededDatasets = successes
    .map((entry) => entry.dataset)
    .filter((dataset) => dataset && typeof dataset === 'object')

  uploadedDatasets.value = succeededDatasets

  if (successes.length) {
    const successMessage =
      successes.length === 1
        ? `已成功上传 ${successes[0].file.name}`
        : `已成功上传 ${successes.length} 个文件`
    uploadSuccess.value = failures.length
      ? `${successMessage}，${failures.length} 个文件需要重试。`
      : `${successMessage}，已生成 JSONL 与 PKL 存档。`
  } else {
    uploadSuccess.value = ''
  }

  if (failures.length) {
    const failedNames = failures.map((entry) => entry.file?.name || '未知文件').join('、')
    const lastError = failures[failures.length - 1]?.message || '上传失败'
    uploadError.value =
      failures.length === uploadFiles.value.length
        ? `全部上传失败：${lastError}（${failedNames}）`
        : `部分文件上传失败：${lastError}（${failedNames}）`

    uploadFiles.value = failures.map((entry) => entry.file).filter((file) => Boolean(file))
    resetFileInput()
  } else {
    uploadError.value = ''
    clearSelectedFiles({ resetStatuses: false })
  }

  uploading.value = false
}
</script>
