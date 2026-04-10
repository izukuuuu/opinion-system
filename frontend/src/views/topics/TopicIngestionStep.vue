<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-primary">数据入库</h1>
        <p class="text-sm text-secondary">将筛选结果入库，或直接基于清洗数据生成中间数据后入库。</p>
      </div>
      <div
        class="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
        <ArrowTrendingUpIcon class="h-4 w-4" />
        <span>Ingest</span>
      </div>
    </header>

    <!-- Configuration Section -->
    <section class="card-surface p-8 space-y-8">
      <header class="space-y-1">
        <h2 class="text-lg font-bold text-primary">入库配置</h2>
        <p class="text-xs text-secondary">
          配置目标项目与数据集信息，系统将自动识别待入库的处理存档。
        </p>
      </header>

      <div class="grid gap-8 md:grid-cols-2">
        <!-- 1. Project Selection -->
        <label class="space-y-2 block">
          <span class="text-xs font-bold text-primary ml-1">选择项目</span>
          <div class="flex gap-2">
            <AppSelect
              class="flex-1"
              :options="projectSelectOptions"
              :value="selectedProjectName"
              :disabled="projectsLoading"
              @change="selectedProjectName = $event"
            />
            <button type="button"
              class="shrink-0 rounded-2xl bg-brand-50/30 px-4 text-secondary hover:text-brand-600 hover:bg-brand-50 transition-colors"
              :disabled="projectsLoading" @click.prevent="refreshProjects" title="刷新项目">
              <ArrowPathIcon class="h-5 w-5" :class="{ 'animate-spin': projectsLoading }" />
            </button>
          </div>
          <p v-if="projectsError" class="text-xs text-rose-600 pl-1">{{ projectsError }}</p>
        </label>

        <!-- 2. Processing Date -->
        <label class="space-y-2 block">
          <span class="text-xs font-bold text-primary ml-1">处理日期</span>
          <div class="relative">
            <template v-if="availableDates.length">
              <AppSelect
                :options="availableDateSelectOptions"
                :value="processingDate"
                @change="processingDate = $event"
              />
            </template>
            <template v-else>
              <div class="flex items-center gap-2">
                <input v-model="processingDate" type="date"
                  class="input flex-1 py-4" />
                <button type="button"
                  class="shrink-0 rounded-2xl bg-brand-50 px-4 py-4 text-xs font-bold text-brand-600 border border-brand-100/50 hover:bg-brand-100 transition-colors"
                  @click="resetToToday">
                  今天
                </button>
              </div>
            </template>
          </div>
          <p class="text-[10px] text-muted pl-1 opacity-70">优先使用筛选日期，也可用于从清洗层直接入库。</p>
        </label>
      </div>

      <div class="grid gap-8 md:grid-cols-2">
        <!-- 3. Dataset Name -->
        <label class="space-y-2 block">
          <span class="text-xs font-bold text-primary ml-1">正式数据集名称</span>
          <input v-model.trim="datasetNameInput" type="text"
            class="input py-4"
            placeholder="例如：控烟政策-12月第1周" />
        </label>

        <!-- 4. Storage ID (Read-only) -->
        <div class="space-y-2">
          <span class="text-xs font-bold text-primary ml-1">云端存储路径 (Storage Identifier)</span>
          <div
            class="w-full rounded-2xl border border-dashed border-black/10 bg-brand-50/10 px-4 py-4 text-xs text-secondary font-mono flex items-center gap-2">
            <ArchiveBoxIcon class="h-4 w-4 opacity-50" />
            {{ bucketName || '项目未加载...' }}
          </div>
        </div>
      </div>

      <!-- Path Info -->
      <transition name="fade">
        <div v-if="inferredFilterPath" class="rounded-[1.5rem] bg-brand-50/50 p-6 border border-brand-100/30">
          <div class="flex items-start gap-4">
            <div
              class="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-brand-600 border border-brand-100/30">
              <FolderIcon class="h-5 w-5" />
            </div>
            <div class="space-y-2">
              <p class="text-xs font-black text-brand-800 tracking-wider">PREVIEW SOURCE PATH</p>
              <code class="block text-[11px] font-mono text-brand-600/80 break-all leading-relaxed">{{
                inferredFilterPath }}</code>
            </div>
          </div>
        </div>
      </transition>

      <div class="space-y-3 pt-4">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div class="flex flex-wrap items-center gap-3">
            <button type="button"
              class="inline-flex items-center gap-3 rounded-full bg-brand-600 px-8 py-3 text-sm font-bold text-white transition-all hover:bg-brand-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="uploadState.running" @click="runUpload()">
              <ArrowTrendingUpIcon class="h-5 w-5" />
              <span>{{ uploadState.running ? '任务传输中...' : '按筛选结果入库' }}</span>
            </button>
            <button type="button"
              class="inline-flex items-center gap-3 rounded-full border border-brand-200 bg-white px-8 py-3 text-sm font-bold text-brand-700 transition-all hover:bg-brand-50 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="uploadState.running" @click="runUpload({ prepareIntermediateFromClean: true })">
              <ArrowPathIcon class="h-5 w-5" />
              <span>{{ uploadState.running ? '任务传输中...' : '跳过筛选直接入库' }}</span>
            </button>
          </div>
        </div>
        <p class="text-[10px] text-muted pl-1 opacity-70">跳过筛选时，会从 clean 层直接生成 filter 中间数据后入库。</p>

        <!-- 高级选项：由本地缓存重建 -->
        <div class="pt-4 border-t border-soft">
          <button type="button" @click="showAdvanced = !showAdvanced"
            class="flex items-center gap-2 text-xs font-medium text-secondary hover:text-primary transition-colors">
            <ChevronDownIcon class="h-4 w-4 transition-transform" :class="showAdvanced ? 'rotate-180' : ''" />
            <span>高级选项</span>
          </button>
          <transition name="fade">
            <div v-if="showAdvanced" class="mt-4 space-y-4">
              <div class="rounded-2xl border border-amber-200 bg-amber-50/50 p-5 space-y-4">
                <div class="space-y-1">
                  <h3 class="text-sm font-bold text-amber-800">由本地缓存重建</h3>
                  <p class="text-xs text-amber-600">直接从 fetch 层本地缓存数据重建数据库，不经过 merge/clean/filter 流程。</p>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                  <button type="button"
                    class="inline-flex items-center gap-2 rounded-full border border-amber-300 bg-white px-5 py-2 text-xs font-bold text-amber-700 transition-all hover:bg-amber-50 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="fetchDatesLoading" @click="loadFetchDates">
                    <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': fetchDatesLoading }" />
                    <span>获取缓存时间</span>
                  </button>
                  <template v-if="fetchDates.length > 0">
                    <AppSelect
                      :options="fetchDateSelectOptions"
                      :value="selectedFetchDate"
                      @change="selectedFetchDate = $event"
                    />
                    <button type="button"
                      class="inline-flex items-center gap-2 rounded-full bg-amber-600 px-5 py-2 text-xs font-bold text-white transition-all hover:bg-amber-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
                      :disabled="uploadState.running || !selectedFetchDate" @click="runUpload({ rebuildFromFetch: true, fetchDate: selectedFetchDate })">
                      <CircleStackIcon class="h-4 w-4" />
                      <span>{{ uploadState.running ? '重建中...' : '开始重建' }}</span>
                    </button>
                  </template>
                  <span v-else-if="fetchDatesLoaded && fetchDates.length === 0" class="text-xs text-amber-600">暂无本地缓存</span>
                </div>
                <p v-if="fetchDatesError" class="text-xs text-rose-600">{{ fetchDatesError }}</p>
              </div>
            </div>
          </transition>
        </div>

        <transition name="fade">
          <div v-if="uploadState.message || parameterError" class="flex items-center gap-2 px-6 py-3 rounded-2xl border"
            :class="(uploadState.success && !parameterError) ? 'bg-emerald-50 border-emerald-100 text-emerald-700' : 'bg-rose-50 border-rose-100 text-rose-700'">
            <component :is="uploadState.success ? CheckIcon : ExclamationCircleIcon" class="h-4 w-4" />
            <span class="text-xs font-bold">{{ parameterError || uploadState.message }}</span>
          </div>
        </transition>
      </div>
    </section>

    <!-- History -->
    <section class="mute-card-surface p-8 space-y-6">
      <header class="space-y-1">
        <h2 class="text-lg font-bold text-primary">传输历史记录</h2>
        <p class="text-xs text-secondary font-medium">最近完成的数据入库任务流水。</p>
      </header>

      <div v-if="!runHistory.length"
        class="flex flex-col items-center justify-center rounded-3xl border border-dashed border-soft bg-surface px-6 py-16 text-center text-secondary">
        <ArchiveBoxIcon class="mb-4 h-12 w-12 text-muted/40" />
        <span class="text-sm font-semibold text-primary">暂无入库运行记录</span>
        <p class="mt-2 text-xs text-secondary">完成一次入库后，最近任务会显示在这里。</p>
      </div>

      <div v-else class="space-y-4">
        <transition-group name="list">
          <article v-for="entry in runHistory" :key="entry.timestamp"
            class="card-surface p-5 space-y-3">
            <div class="flex items-start gap-3">
              <div
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border"
                :class="entry.success ? 'border-emerald-100 bg-emerald-50 text-emerald-600' : 'border-rose-100 bg-rose-50 text-rose-600'">
                <CheckIcon v-if="entry.success" class="h-4 w-4" />
                <XMarkIcon v-else class="h-4 w-4" />
              </div>
              <div class="min-w-0 flex-1 space-y-1">
                <div class="flex items-center gap-2">
                  <h3 class="text-sm font-bold text-primary">{{ entry.topic_label || '未命名数据集' }}</h3>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="entry.success ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'">
                    {{ entry.success ? '已完成' : '执行失败' }}
                  </span>
                </div>
                <p class="text-xs text-secondary">{{ entry.message }}</p>
              </div>
            </div>
            <div class="flex flex-wrap gap-2 pl-11">
              <span class="inline-flex items-center gap-1 rounded-full border border-soft bg-base-soft px-2.5 py-1 text-[10px] font-medium text-secondary">
                <RectangleStackIcon class="h-3 w-3" /> {{ entry.project }}
              </span>
              <span class="inline-flex items-center gap-1 rounded-full border border-soft bg-base-soft px-2.5 py-1 text-[10px] font-medium text-secondary">
                <CalendarDaysIcon class="h-3 w-3" /> {{ entry.date }}
              </span>
              <span class="inline-flex items-center gap-1 rounded-full border border-soft bg-base-soft px-2.5 py-1 text-[10px] font-medium text-secondary">
                <ClockIcon class="h-3 w-3" /> {{ formatHistoryTime(entry.timestamp) }}
              </span>
              <span class="inline-flex items-center rounded-full border border-soft bg-base-soft px-2.5 py-1 text-[10px] font-medium text-secondary">
                {{ historyModeLabel(entry.mode) }}
              </span>
            </div>
          </article>
        </transition-group>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  ArrowTrendingUpIcon,
  ArrowPathIcon,
  ChevronDownIcon,
  ArchiveBoxIcon,
  CheckIcon,
  ExclamationCircleIcon,
  FolderIcon,
  CalendarDaysIcon,
  ClockIcon,
  RectangleStackIcon,
  XMarkIcon,
  CircleStackIcon
} from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
import { useApiBase } from '../../composables/useApiBase'
import { useTopicCreationProject } from '../../composables/useTopicCreationProject'

const { ensureApiBase } = useApiBase()
const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}
const HISTORY_LIMIT = 8

const {
  projectOptions,
  projectsLoading,
  projectsError,
  selectedProjectName,
  activeProject,
  activeProjectName,
  loadProjects,
  refreshProjects
} = useTopicCreationProject()

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

// 高级选项：本地缓存重建
const showAdvanced = ref(false)
const fetchDates = ref([])
const fetchDatesLoading = ref(false)
const fetchDatesLoaded = ref(false)
const fetchDatesError = ref('')
const selectedFetchDate = ref('')

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

// AppSelect options
const projectSelectOptions = computed(() => {
  const placeholder = { value: '', label: '请选择项目', disabled: true }
  if (!projectOptions.value.length) return [placeholder]
  return [placeholder, ...projectOptions.value]
})

const availableDateSelectOptions = computed(() =>
  availableDates.value.map(date => ({ value: date, label: date }))
)

const fetchDateSelectOptions = computed(() =>
  fetchDates.value.map(date => ({ value: date, label: date }))
)

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

onMounted(() => {
  loadProjects()
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

const loadFetchDates = async () => {
  if (!bucketName.value) {
    fetchDatesError.value = '请先选择项目'
    return
  }
  fetchDatesLoading.value = true
  fetchDatesError.value = ''
  fetchDatesLoaded.value = false
  try {
    const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(bucketName.value)}/fetch-dates`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (response.ok && result.status !== 'error') {
      fetchDates.value = result.dates || []
      if (fetchDates.value.length > 0 && !selectedFetchDate.value) {
        selectedFetchDate.value = fetchDates.value[0]
      }
    } else {
      fetchDatesError.value = result.message || '获取缓存时间失败'
    }
  } catch (error) {
    fetchDatesError.value = error instanceof Error ? error.message : '网络错误'
  } finally {
    fetchDatesLoading.value = false
    fetchDatesLoaded.value = true
  }
}

// 轮询 rebuild fetch 任务状态
let rebuildPollInterval = null

const startPollingRebuildStatus = async (topic, project, topicLabel, fetchDate, params) => {
  const database = topicLabel || topic
  const poll = async () => {
    try {
      const endpoint = await buildApiUrl(`/upload/rebuild-fetch/status?topic=${encodeURIComponent(topic)}&project=${encodeURIComponent(project)}&database=${encodeURIComponent(database)}&fetch_date=${encodeURIComponent(fetchDate)}`)
      const response = await fetch(endpoint)
      const result = await response.json()

      if (response.ok && result.status === 'ok') {
        const job = result.data
        const jobStatus = job.status

        if (jobStatus === 'completed') {
          uploadState.running = false
          uploadState.success = true
          uploadState.message = `本地缓存重建完成(${fetchDate})，共上传 ${job.result?.uploaded?.length || 0} 个表。`
          pushHistoryEntry(params, true, uploadState.message, 'rebuild')
          clearInterval(rebuildPollInterval)
          rebuildPollInterval = null
        } else if (jobStatus === 'error') {
          uploadState.running = false
          uploadState.success = false
          uploadState.message = job.message || '本地缓存重建失败'
          pushHistoryEntry(params, false, uploadState.message, 'rebuild')
          clearInterval(rebuildPollInterval)
          rebuildPollInterval = null
        } else {
          // 仍在运行中，更新进度消息
          const progress = job.progress || {}
          uploadState.message = `正在重建(${fetchDate})... ${progress.percentage || 0}% ${job.message || ''}`
        }
      }
    } catch (error) {
      // 轮询出错，继续尝试
    }
  }

  // 立即执行一次，然后每2秒轮询
  await poll()
  if (rebuildPollInterval) clearInterval(rebuildPollInterval)
  rebuildPollInterval = setInterval(poll, 2000)
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

const splitHistoryTimestamp = (value) => {
  const formatted = formatHistoryTimestamp(value)
  if (!formatted) {
    return { date: '', time: '' }
  }
  const [date = '', time = ''] = String(formatted).split(/\s+/, 2)
  return { date, time }
}

const formatHistoryTime = (value) => splitHistoryTimestamp(value).time

const historyModeLabel = (mode) => {
  if (mode === 'direct') return '跳过筛选'
  if (mode === 'rebuild') return 'fetch重建'
  return '筛选入库'
}

const ensureParameters = () => {
  const topic = bucketName.value
  if (!topic) {
    parameterError.value = '未找到对应的数据库标识，请先选择项目。'
    return null
  }
  if (!processingDate.value) {
    parameterError.value = '请选择处理日期。'
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

const pushHistoryEntry = (payload, success, message, mode = 'filter') => {
  const entry = {
    ...payload,
    success,
    message,
    mode,
    timestamp: new Date().toISOString()
  }
  runHistory.value = [entry, ...runHistory.value].slice(0, HISTORY_LIMIT)
}

const runUpload = async (options = {}) => {
  const params = ensureParameters()
  if (!params) return
  const prepareIntermediateFromClean = Boolean(options.prepareIntermediateFromClean)
  const rebuildFromFetch = Boolean(options.rebuildFromFetch)
  const fetchDate = options.fetchDate || ''

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
  if (prepareIntermediateFromClean) {
    payload.prepare_intermediate_from_clean = true
  }
  if (rebuildFromFetch) {
    payload.rebuild_from_fetch = true
    if (fetchDate) {
      payload.fetch_date = fetchDate
    }
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

    // 如果是 rebuild fetch 任务且被接受（202），开始轮询状态
    if (rebuildFromFetch && response.status === 202 && result.status === 'accepted') {
      uploadState.message = `已提交本地缓存重建任务(${fetchDate})，正在执行...`
      startPollingRebuildStatus(params.topic, params.project, params.topic_label, fetchDate, params)
      return
    }

    const ok = response.ok && result.status !== 'error'
    uploadState.success = ok
    uploadState.message = ok
      ? (rebuildFromFetch
        ? `已从本地缓存(${fetchDate || '默认'})重建数据并完成入库。`
        : prepareIntermediateFromClean
        ? '已从清洗层生成中间数据并完成入库。'
        : '筛选结果已成功写入数据库。')
      : result.message || '入库失败，请查看后端日志。'
    uploadState.details = result.data ?? null
    uploadState.lastResponse = result
    const mode = rebuildFromFetch ? 'rebuild' : (prepareIntermediateFromClean ? 'direct' : 'filter')
    pushHistoryEntry(params, ok, uploadState.message, mode)
  } catch (error) {
    uploadState.success = false
    uploadState.message =
      error instanceof Error ? error.message : '入库失败，请检查网络或服务器状态。'
    uploadState.details = null
    uploadState.lastResponse = null
    const mode = rebuildFromFetch ? 'rebuild' : (prepareIntermediateFromClean ? 'direct' : 'filter')
    pushHistoryEntry(params, false, uploadState.message, mode)
  } finally {
    if (!rebuildFromFetch) {
      uploadState.running = false
    }
  }
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-5px);
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
