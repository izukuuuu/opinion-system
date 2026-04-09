<template>
  <div class="space-y-10">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-primary">上传原始数据</h1>
        <p class="text-sm text-secondary">创建专题并上传 Excel/CSV 文件，系统将自动生成标准化存档。</p>
      </div>
      <div
        class="inline-flex items-center gap-2 rounded-full bg-brand-50 px-4 py-1.5 text-sm font-semibold text-brand-700 ring-1 ring-brand-200/50">
        <CloudArrowUpIcon class="h-5 w-5" />
        <span>Step 1 · Upload</span>
      </div>
    </header>

    <div class="grid gap-8 xl:grid-cols-[1fr,minmax(320px,1fr)]">
      <!-- Left Column: Create Topic Form -->
      <section class="card-surface p-8 flex flex-col gap-6">
        <header class="space-y-2">
          <h2 class="text-lg font-bold text-primary">创建专题</h2>
          <p class="text-xs text-secondary">
            填写专题信息以建立档案，后续数据将自动归档至此专题下。
          </p>
        </header>

        <form @submit.prevent="createTopic" class="flex flex-col gap-6 flex-1">
          <div class="space-y-5">
            <div class="space-y-2">
              <label class="text-sm font-bold text-primary ml-1">专题名称</label>
              <input v-model.trim="topicName" type="text" required
                class="w-full rounded-2xl border-0 bg-base-soft px-5 py-4 text-sm ring-1 ring-inset ring-black/5 transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted"
                placeholder="例如：2024-两会舆情专项" />
            </div>

            <div class="space-y-2">
              <label class="text-sm font-bold text-primary ml-1">专题说明</label>
              <textarea v-model.trim="topicDescription" rows="4"
                class="w-full resize-none rounded-2xl border-0 bg-base-soft px-5 py-4 text-sm ring-1 ring-inset ring-black/5 transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted"
                :placeholder="selectedTags.length ? '补充更多背景信息...' : '简要描述专题背景、抓取渠道等信息...'"></textarea>
            </div>

            <div class="space-y-3 rounded-3xl bg-surface-variant/50 p-5">
              <div class="flex items-center gap-2 text-sm font-bold text-primary">
                <TagIcon class="h-4 w-4 text-brand-500" />
                <span>快速标签</span>
              </div>
              <div class="flex flex-wrap gap-2">
                <button v-for="tag in suggestedTags" :key="tag" type="button"
                  class="inline-flex items-center rounded-full px-4 py-1.5 text-xs font-medium transition-all active:scale-95"
                  :class="selectedTags.includes(tag)
                    ? 'bg-brand-600 text-white'
                    : 'bg-white text-secondary ring-1 ring-black/5 hover:bg-gray-50'" @click="toggleTag(tag)">
                  {{ tag }}
                </button>
              </div>
              <div v-if="selectedTags.length" class="pt-2 text-xs text-secondary pl-1">
                已选：<span class="font-medium text-primary">{{ selectedTags.join(' · ') }}</span>
              </div>
            </div>
          </div>

          <div class="mt-auto flex items-center justify-end pt-4">
            <div class="mr-auto text-xs text-rose-500 font-medium" v-if="createError">{{ createError }}</div>
            <div class="mr-auto text-xs text-emerald-600 font-medium" v-if="createSuccess">{{ createSuccess }}</div>
            <button type="submit"
              class="inline-flex items-center gap-2 rounded-full bg-brand-600 px-8 py-3 text-sm font-bold text-white transition-all hover:bg-brand-700 disabled:opacity-60 disabled:cursor-not-allowed"
              :disabled="creating || !topicName">
              <span v-if="creating"
                class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
              <span v-else>创建专题</span>
            </button>
          </div>
        </form>
      </section>

      <!-- Right Column: Upload Area -->
      <section class="card-surface p-8 flex flex-col gap-6">
        <header class="flex items-center justify-between">
          <div class="space-y-1">
            <h2 class="text-lg font-bold text-primary">上传文件</h2>
            <p class="text-xs text-secondary">
              支持 .xlsx, .xls, .csv
            </p>
          </div>
          <div v-if="topicName"
            class="hidden sm:inline-flex items-center rounded-full bg-base-soft px-3 py-1 text-xs font-medium text-secondary">
            当前：{{ topicName }}
          </div>
        </header>

        <template v-if="canUpload">
          <form class="flex-1 flex flex-col gap-6" @submit.prevent="uploadDataset">
            <!-- Drop Zone -->
            <div
              class="relative flex min-h-[240px] cursor-pointer flex-col items-center justify-center gap-4 rounded-3xl border-2 border-dashed transition-all duration-300"
              :class="[
                uploadFiles.length || dragActive
                  ? 'border-brand-400 bg-brand-50/50'
                  : 'border-gray-200 bg-base-soft/50 hover:border-brand-300 hover:bg-base-soft'
              ]" @dragenter.prevent="handleDragEnter" @dragover.prevent="handleDragOver"
              @dragleave.prevent="handleDragLeave" @drop.prevent="handleDrop" @click="fileInput?.click()">
              <input ref="fileInput" type="file" class="hidden" accept=".xlsx,.xls,.csv,.jsonl" multiple
                @change="handleFileChange" />

              <div class="rounded-full bg-white p-4 ring-1 ring-black/5 transition-transform duration-300"
                :class="{ 'scale-110': dragActive }">
                <DocumentArrowUpIcon class="h-8 w-8 text-brand-500" />
              </div>

              <div class="text-center space-y-1">
                <p class="text-sm font-semibold text-primary">
                  {{ uploadFiles.length ? `已选择 ${uploadFiles.length} 个文件` : '点击选择或拖拽上传' }}
                </p>
                <p class="text-[11px] text-muted">
                  {{ uploadFiles.length ? '再次点击可继续添加' : '单文件最大 50MB · 支持批量上传' }}
                </p>
              </div>
            </div>

            <!-- File List Pills -->
            <div v-if="uploadFiles.length" class="flex flex-wrap gap-2">
              <div v-for="(file, index) in uploadFiles" :key="`${file.name}-${index}`"
                class="inline-flex items-center gap-2 rounded-full border border-gray-100 bg-white pl-4 pr-2 py-1.5 text-sm transition hover:scale-105">
                <span class="max-w-[150px] truncate text-secondary font-medium">{{ file.name }}</span>
                <button type="button"
                  class="rounded-full p-1 text-muted hover:bg-rose-50 hover:text-rose-600 transition-colors"
                  @click.stop="removeSelectedFile(index)">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                    <path
                      d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                  </svg>
                </button>
              </div>
              <button v-if="uploadFiles.length > 0" type="button"
                class="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50 transition-colors"
                @click.stop="clearSelectedFiles">
                清空全部
              </button>
            </div>

            <!-- Upload Progress -->
            <div v-if="uploadStatuses.length" class="space-y-3 rounded-2xl bg-surface-variant/30 p-4">
              <div class="flex justify-between items-center text-xs font-bold text-secondary uppercase tracking-wider">
                <span>Batch Progress</span>
                <span>{{ uploadProgress.percent }}%</span>
              </div>
              <div class="h-3 w-full overflow-hidden rounded-full bg-base-soft">
                <div class="h-full rounded-full bg-brand-500 transition-all duration-500 ease-out"
                  :style="{ width: `${uploadProgress.percent}%` }"></div>
              </div>
              <div class="space-y-1 max-h-32 overflow-y-auto pr-2 sidebar-scroll">
                <div v-for="status in uploadStatuses" :key="status.key"
                  class="flex items-center justify-between text-xs py-1">
                  <span class="truncate text-secondary max-w-[70%]">{{ status.name }}</span>
                  <span class="px-2 py-0.5 rounded-full font-medium"
                    :class="status.status === 'success' ? 'bg-emerald-100 text-emerald-700' : status.status === 'error' ? 'bg-rose-100 text-rose-700' : 'text-muted'">
                    {{ status.message }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Action Button -->
            <button type="submit"
              class="mt-auto w-full rounded-full bg-primary-900 py-4 text-sm font-bold text-white transition-all hover:bg-primary-800 active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
              :disabled="uploading">
              {{ uploading ? '正在上传...' : '上传并生成存档' }}
            </button>
          </form>

          <!-- Success Card -->
          <transition name="fade" mode="out-in">
            <article v-if="latestDataset" key="dataset-success"
              class="mt-6 rounded-3xl bg-emerald-50/80 p-6 border border-emerald-100">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <p class="text-xs font-bold text-emerald-600 uppercase tracking-wider mb-1">SUCCESS</p>
                  <h3 class="text-lg font-bold text-emerald-900">{{ latestDataset.display_name }}</h3>
                  <div class="mt-2 flex flex-wrap gap-2 text-xs">
                    <span class="rounded-full bg-emerald-100/50 px-2 py-0.5 text-emerald-800 font-medium">{{
                      formatFileSize(latestDataset.file_size) }}</span>
                    <span class="rounded-full bg-emerald-100/50 px-2 py-0.5 text-emerald-800 font-medium">{{
                      latestDataset.rows }} 行</span>
                  </div>
                </div>
                <div class="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6">
                    <path fill-rule="evenodd"
                      d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z"
                      clip-rule="evenodd" />
                  </svg>
                </div>
              </div>

              <!-- Mapping Section -->
              <div class="mt-6 border-t border-emerald-200/50 pt-4">
                <h4 class="text-sm font-bold text-emerald-900 mb-2">字段映射</h4>
                <div class="grid grid-cols-2 gap-3">
                  <AppSelect
                    :options="columnSelectOptions"
                    :value="columnMappingForm.date"
                    placeholder="日期列 (未指定)"
                    @change="columnMappingForm.date = $event"
                  />
                  <AppSelect
                    :options="columnSelectOptions"
                    :value="columnMappingForm.title"
                    placeholder="标题列 (未指定)"
                    @change="columnMappingForm.title = $event"
                  />
                  <AppSelect
                    :options="columnSelectOptions"
                    :value="columnMappingForm.content"
                    placeholder="正文列 (未指定)"
                    @change="columnMappingForm.content = $event"
                  />
                  <AppSelect
                    :options="columnSelectOptions"
                    :value="columnMappingForm.author"
                    placeholder="作者列 (未指定)"
                    @change="columnMappingForm.author = $event"
                  />
                </div>
                <div class="mt-4 flex justify-end">
                  <button type="button"
                    class="rounded-full bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                    @click="saveColumnMapping" :disabled="mappingSaving">
                    {{ mappingSaving ? '保存中' : '保存映射' }}
                  </button>
                </div>
              </div>
            </article>
          </transition>
        </template>

        <div v-else
          class="flex-1 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-gray-200 bg-base-soft/30 p-8 text-center">
          <div class="rounded-full bg-gray-50 p-4 mb-4">
            <CloudArrowUpIcon class="h-8 w-8 text-gray-300" />
          </div>
          <p class="text-secondary font-medium">等待创建专题</p>
          <p class="text-xs text-muted mt-1">请先在左侧完成专题信息填写</p>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { CloudArrowUpIcon, DocumentArrowUpIcon, TagIcon } from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
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

const columnSelectOptions = computed(() =>
  datasetColumns.value.map(col => ({ value: col, label: col }))
)

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
