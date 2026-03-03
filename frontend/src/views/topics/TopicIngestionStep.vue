<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-primary">数据入库</h1>
        <p class="text-sm text-secondary">将本地筛选后的数据集上传到远程数据库。</p>
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
          配置目标项目与数据集信息，系统将自动识别待入库的筛选存档。
        </p>
      </header>

      <div class="grid gap-8 md:grid-cols-2">
        <!-- 1. Project Selection -->
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

        <!-- 2. Processing Date -->
        <label class="space-y-2 block">
          <span class="text-xs font-bold text-primary ml-1">筛选筛选完成日期</span>
          <div class="relative">
            <template v-if="availableDates.length">
              <select v-model="processingDate"
                class="w-full appearance-none rounded-2xl border-0 bg-base-soft py-4 pl-4 pr-10 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20">
                <option v-for="date in availableDates" :key="date" :value="date">{{ date }}</option>
              </select>
              <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-secondary/50">
                <ChevronDownIcon class="w-4 h-4" />
              </div>
            </template>
            <template v-else>
              <div class="flex items-center gap-2">
                <input v-model="processingDate" type="date"
                  class="flex-1 rounded-2xl border-0 bg-base-soft px-4 py-4 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20" />
                <button type="button"
                  class="shrink-0 rounded-2xl bg-brand-50 px-4 py-4 text-xs font-bold text-brand-600 border border-brand-100/50 hover:bg-brand-100 transition-colors"
                  @click="resetToToday">
                  今天
                </button>
              </div>
            </template>
          </div>
          <p class="text-[10px] text-muted pl-1 opacity-70">系统已自动关联最近一次成功的筛选记录。</p>
        </label>
      </div>

      <div class="grid gap-8 md:grid-cols-2">
        <!-- 3. Dataset Name -->
        <label class="space-y-2 block">
          <span class="text-xs font-bold text-primary ml-1">正式数据集名称</span>
          <input v-model.trim="datasetNameInput" type="text"
            class="w-full rounded-2xl border-0 bg-base-soft px-4 py-4 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted"
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

      <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between pt-4">
        <button type="button"
          class="inline-flex items-center gap-3 rounded-full bg-brand-600 px-10 py-3 text-sm font-bold text-white transition-all hover:bg-brand-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="uploadState.running" @click="runUpload">
          <ArrowTrendingUpIcon class="h-5 w-5" />
          <span>{{ uploadState.running ? '任务传输中...' : '启动数据入库' }}</span>
        </button>
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
    <section class="mute-card-surface p-8 space-y-8">
      <header class="flex flex-wrap items-center justify-between gap-6">
        <div class="space-y-1">
          <h2 class="text-lg font-bold text-primary">传输历史记录</h2>
          <p class="text-xs text-secondary font-medium">最近完成的数据入库任务流水。</p>
        </div>
        <div class="flex items-center gap-2 bg-white px-4 py-2 rounded-full border border-black/5">
          <div class="w-1.5 h-1.5 rounded-full bg-brand-500"></div>
          <span class="text-[10px] font-bold text-secondary tracking-widest uppercase">History Logs</span>
        </div>
      </header>

      <div v-if="!runHistory.length"
        class="flex flex-col items-center justify-center py-20 rounded-[2rem] border-2 border-dashed border-black/5 bg-white/50 text-secondary">
        <ArchiveBoxIcon class="h-12 w-12 text-black/10 mb-4" />
        <span class="text-xs font-bold opacity-40">暂无入库运行记录</span>
      </div>

      <div v-else class="grid gap-4">
        <transition-group name="list">
          <article v-for="entry in runHistory" :key="entry.timestamp"
            class="relative overflow-hidden rounded-[1.5rem] bg-white p-6 border border-black/5 transition hover:border-brand-200 group">
            <div class="flex flex-wrap items-start justify-between gap-6">
              <div class="space-y-3">
                <div class="flex items-center gap-3">
                  <div class="h-8 w-8 rounded-lg flex items-center justify-center border border-black/5"
                    :class="entry.success ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'">
                    <CheckIcon v-if="entry.success" class="h-4 w-4" />
                    <XMarkIcon v-else class="h-4 w-4" />
                  </div>
                  <div>
                    <h3 class="text-sm font-black text-primary group-hover:text-brand-600 transition-colors">{{
                      entry.topic_label || '未命名数据集' }}</h3>
                  </div>
                </div>
                <div
                  class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-bold text-secondary opacity-60 pl-11">
                  <span class="flex items-center gap-1.5">
                    <RectangleStackIcon class="h-3.5 w-3.5" /> {{ entry.project }}
                  </span>
                  <span class="flex items-center gap-1.5">
                    <CalendarDaysIcon class="h-3.5 w-3.5" /> {{ entry.date }}
                  </span>
                  <span class="flex items-center gap-1.5">
                    <ClockIcon class="h-3.5 w-3.5" /> {{ formatHistoryTimestamp(entry.timestamp).split(' ')[1] }}
                  </span>
                </div>
              </div>
              <div class="flex flex-col items-end gap-2 text-right">
                <span class="text-[10px] font-black tracking-wider text-muted uppercase">{{
                  formatHistoryTimestamp(entry.timestamp).split(' ')[0] }}</span>
                <p class="text-xs font-bold text-secondary/80 max-w-sm leading-relaxed">
                  {{ entry.message }}
                </p>
              </div>
            </div>
            <!-- Decorative corner accent -->
            <div
              class="absolute -bottom-2 -right-2 h-10 w-10 bg-brand-50 group-hover:bg-brand-100 transition-colors rotate-45">
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
  XMarkIcon
} from '@heroicons/vue/24/outline'
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
