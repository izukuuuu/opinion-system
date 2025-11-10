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

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">创建专题</h2>
        <p class="text-sm text-secondary">填写专题名称后创建记录，系统将用于跟踪后续流程。</p>
      </header>
      <form class="grid gap-4 sm:grid-cols-[minmax(0,320px)] lg:grid-cols-[minmax(0,400px),1fr]" @submit.prevent="createTopic">
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
              class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="补充专题背景、抓取渠道等信息。"
            ></textarea>
          </label>
          <div class="space-y-2 rounded-2xl border border-dashed border-brand-soft bg-surface-muted px-4 py-3 text-xs text-secondary">
            <div class="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
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
            <div v-if="selectedTags.length" class="space-y-1 rounded-2xl bg-white/80 px-3 py-2 text-xs text-secondary">
              <p class="font-semibold text-primary">已选标签</p>
              <p class="text-muted">{{ selectedTags.join(' · ') }}</p>
            </div>
          </div>
          <button
            type="submit"
            class="btn-base btn-tone-primary w-full gap-2 px-5 py-2"
            :disabled="creating || !topicName"
          >
            <span v-if="creating">创建中…</span>
            <span v-else>创建专题</span>
          </button>
        </div>
        <div class="rounded-3xl border border-dashed border-brand-soft bg-surface-muted p-4 text-sm text-secondary">
          <h3 class="text-sm font-semibold text-primary">提示</h3>
          <ul class="mt-2 space-y-2 text-xs leading-relaxed text-secondary">
            <li>专题名称将作为后续 API 调用的参数，建议使用字母、数字与短横线组合。</li>
            <li>可先创建专题再上传数据，也可直接上传，系统会在需要时自动创建专题。</li>
            <li>描述信息用于团队协作记录，可随时在设置中更新。</li>
          </ul>
        </div>
      </form>
      <p v-if="createError" class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600">{{ createError }}</p>
      <p v-if="createSuccess" class="rounded-2xl bg-emerald-100 px-4 py-2 text-sm text-emerald-600">{{ createSuccess }}</p>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-xl font-semibold text-primary">上传原始表格</h2>
          <p class="text-sm text-secondary">
            支持 .xlsx、.xls、.csv、.jsonl 文件。系统会自动生成 JSONL、PKL 与 Meta 清单。
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
            :class="{ 'border-brand bg-surface text-brand-600 shadow-inner': uploadFile }"
          >
            <input
              ref="fileInput"
              type="file"
              class="hidden"
              accept=".xlsx,.xls,.csv,.jsonl"
              @change="handleFileChange"
            />
            <button type="button" class="flex flex-col items-center gap-2 text-sm" @click="fileInput?.click()">
              <DocumentArrowUpIcon class="h-10 w-10 text-slate-300" />
              <span class="font-medium">
                {{ uploadFile ? uploadFile.name : '点击或拖拽文件到此处' }}
              </span>
              <span class="text-xs text-slate-400">最大支持 50MB</span>
            </button>
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
const uploadFile = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref('')
const latestDataset = ref(null)
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
  if (!uploadFile.value) return '请选择需要上传的文件'
  return ''
})

const datasetColumns = computed(() => {
  if (!latestDataset.value || !Array.isArray(latestDataset.value.columns)) return []
  return latestDataset.value.columns.map((column) => column.toString())
})

const toggleTag = (tag) => {
  if (selectedTags.value.includes(tag)) {
    selectedTags.value = selectedTags.value.filter((item) => item !== tag)
  } else {
    selectedTags.value = [...selectedTags.value, tag]
  }
  if (!topicDescription.value) {
    topicDescription.value = selectedTags.value.map((item) => `#${item}`).join(' · ')
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

const saveColumnMapping = async () => {
  if (!latestDataset.value || !topicName.value) return
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

  try {
    const endpoint = await buildApiUrl(
      `/projects/${encodeURIComponent(latestDataset.value.project)}/datasets/${encodeURIComponent(latestDataset.value.id)}/mapping`
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
    mappingSuccess.value = '字段映射已保存'
    latestDataset.value = {
      ...latestDataset.value,
      column_mapping: result.column_mapping,
      topic_label: typeof result.topic_label === 'string' ? result.topic_label : columnMappingForm.topic
    }
    columnMappingForm.topic = typeof latestDataset.value.topic_label === 'string' ? latestDataset.value.topic_label.trim() : ''
  } catch (err) {
    mappingError.value = err instanceof Error ? err.message : '字段映射保存失败'
  } finally {
    mappingSaving.value = false
  }
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
        description: topicDescription.value || undefined,
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

const handleFileChange = (event) => {
  const [file] = event.target.files || []
  uploadFile.value = file || null
  uploadError.value = ''
  uploadSuccess.value = ''
  latestDataset.value = null
}

const uploadDataset = async () => {
  if (!topicName.value) {
    uploadError.value = '请填写专题名称后再上传'
    return
  }
  if (!uploadFile.value) {
    uploadError.value = '请选择需要上传的文件'
    return
  }

  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = ''

  const formData = new FormData()
  formData.append('file', uploadFile.value)

  try {
    const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(topicName.value)}/datasets`)
    const response = await fetch(endpoint, {
      method: 'POST',
      body: formData
    })
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '上传失败')
    }
    uploadSuccess.value = '上传成功，已生成 JSONL 与 PKL 存档。'
    latestDataset.value = result.dataset
      ? { ...result.dataset, topic_label: typeof result.dataset.topic_label === 'string' ? result.dataset.topic_label.trim() : '' }
      : null
    uploadFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
  }
}
</script>
