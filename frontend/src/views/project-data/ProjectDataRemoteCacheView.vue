<template>
  <div class="space-y-8">
    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h1 class="text-2xl font-semibold text-slate-900">远程数据缓存</h1>
        <p class="text-sm text-slate-500">
          指定分析时间区间，将远程数据库中的专题内容缓存到本地，便于后续项目数据分析。
        </p>
      </header>

      <div class="grid gap-4 lg:grid-cols-2">
        <label class="space-y-2 text-sm">
          <span class="font-medium text-slate-700">专题名称</span>
          <select
            class="w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm text-slate-700  transition focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            :disabled="topicsLoading" :value="selectedTopic" @change="handleTopicChange($event.target.value)">
            <option value="">请选择远程专题</option>
            <option v-for="topic in topics" :key="topic" :value="topic">
              {{ topic }}
            </option>
          </select>
          <p v-if="topicsError" class="text-xs text-rose-600">{{ topicsError }}</p>
          <p v-else-if="topicsLoading" class="text-xs text-slate-500">正在加载远程专题列表…</p>
        </label>
        <div class="rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-500">
          <p class="text-xs uppercase tracking-widest text-slate-400">时间区间</p>
          <p class="mt-1 text-base font-semibold text-slate-900">
            {{
              availability.start && availability.end
                ? `${availability.start} → ${availability.end}`
                : '尚未获取可用区间'
            }}
          </p>
          <p v-if="availability.error" class="text-xs text-rose-500">{{ availability.error }}</p>
        </div>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <label class="space-y-2 text-sm">
          <span class="font-medium text-slate-700">开始日期</span>
          <input v-model="fetchForm.start" type="date"
            class="w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            :disabled="!selectedTopic" />
        </label>
        <label class="space-y-2 text-sm">
          <span class="font-medium text-slate-700">结束日期</span>
          <input v-model="fetchForm.end" type="date"
            class="w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            :disabled="!selectedTopic" placeholder="默认与开始日期相同" />
        </label>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <button type="button"
          class="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-600/90 px-4 py-2 text-sm font-semibold text-white  transition hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          :disabled="fetchRunning || !canSubmitFetch" @click="triggerFetch">
          {{ fetchRunning ? '拉取中…' : '同步数据到本地' }}
        </button>
        <button type="button"
          class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          :disabled="availability.loading || !selectedTopic" @click="loadAvailability()">
          {{ availability.loading ? '获取中…' : '刷新可用区间' }}
        </button>
        <button type="button"
          class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          :disabled="cacheLoading || !selectedTopic" @click="refreshCaches">
          {{ cacheLoading ? '刷新中…' : '刷新缓存状态' }}
        </button>
        <span v-if="latestCache" class="text-xs text-slate-500">
          最近缓存时间：{{ formatTimestamp(latestCache.updated_at) }}
        </span>
      </div>
      <p v-if="fetchFeedback.message" class="rounded-2xl px-4 py-3 text-sm"
        :class="fetchFeedback.type === 'success' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-600'">
        {{ fetchFeedback.message }}
      </p>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">缓存概览</h2>
          <p class="text-sm text-slate-500">
            共 {{ cacheTotals.count }} 批 · 文件 {{ cacheTotals.files }} 个 · 总体积 {{ formatFileSize(cacheTotals.size) }}
          </p>
        </div>
        <div v-if="latestCache" class="text-xs text-slate-500">
          上次缓存区间：{{ formatRange(latestCache.date) }}
        </div>
      </header>

      <p v-if="!selectedTopic" class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-500">
        请选择远程专题以查看缓存记录。
      </p>
      <p v-else-if="cacheLoading" class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-500">
        缓存信息加载中…
      </p>
      <p v-else-if="cacheError" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">
        {{ cacheError }}
      </p>
      <p v-else-if="!caches.length" class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-500">
        当前专题尚未拉取过远程缓存，可先指定时间区间触发 fetch。
      </p>
      <ul v-else class="space-y-4">
        <li v-for="cache in caches" :key="cache.date" class="rounded-3xl border border-slate-200 bg-white/90 p-6 ">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p class="text-xs uppercase tracking-widest text-slate-400">缓存区间</p>
              <p class="text-lg font-semibold text-slate-900">{{ formatRange(cache.date) }}</p>
            </div>
            <div class="text-right text-sm text-slate-500">
              更新时间：{{ formatTimestamp(cache.updated_at) }}
            </div>
          </div>
          <dl class="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt class="text-xs uppercase tracking-widest text-slate-400">文件数量</dt>
              <dd class="text-base font-semibold text-slate-900">{{ cache.file_count || 0 }}</dd>
            </div>
            <div>
              <dt class="text-xs uppercase tracking-widest text-slate-400">缓存容量</dt>
              <dd class="text-base font-semibold text-slate-900">{{ formatFileSize(cache.total_size) }}</dd>
            </div>
            <div>
              <dt class="text-xs uppercase tracking-widest text-slate-400">包含渠道</dt>
              <dd class="text-base font-semibold text-slate-900">
                {{ cache.channels?.length ? cache.channels.length : 0 }}
              </dd>
            </div>
          </dl>
          <div v-if="cache.channels?.length" class="mt-4 flex flex-wrap gap-2">
            <span v-for="channel in cache.channels" :key="`${cache.date}-${channel}`"
              class="inline-flex items-center rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
              {{ channel }}
            </span>
          </div>
          <div v-if="cache.files?.length" class="mt-4 rounded-2xl border border-dashed border-slate-200 px-4 py-3">
            <p class="text-xs font-semibold uppercase tracking-widest text-slate-400">生成文件</p>
            <ul class="mt-2 space-y-1 text-sm text-slate-600">
              <li v-for="file in cache.files" :key="`${cache.date}-${file}`" class="truncate" :title="file">
                {{ file }}
              </li>
            </ul>
          </div>
          <div class="mt-4 rounded-2xl border border-slate-100 bg-slate-50/60 px-4 py-3">
            <p class="text-xs uppercase tracking-widest text-slate-400">缓存目录</p>
            <p class="mt-1 truncate text-sm font-medium text-slate-700" :title="cacheDirectoryFor(cache)">
              {{ cacheDirectoryFor(cache) || '未生成缓存目录' }}
            </p>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { useApiBase } from '../../composables/useApiBase'

const { backendBase, callApi } = useApiBase()

const topics = ref([])
const topicsLoading = ref(false)
const topicsError = ref('')
const selectedTopic = ref('')

const availability = reactive({
  start: '',
  end: '',
  loading: false,
  error: '',
})
let availabilityRequestId = 0

const fetchForm = reactive({
  start: '',
  end: '',
})
const fetchRunning = ref(false)
const fetchFeedback = reactive({
  type: '',
  message: '',
})

const caches = ref([])
const cacheLoading = ref(false)
const cacheError = ref('')
const cacheRoot = ref('')
const cacheTotals = reactive({ files: 0, size: 0, count: 0 })
const latestCache = ref(null)

const canSubmitFetch = computed(() => {
  if (!selectedTopic.value) return false
  if (!fetchForm.start) return false
  return true
})

const resetCacheState = () => {
  caches.value = []
  latestCache.value = null
  cacheTotals.files = 0
  cacheTotals.size = 0
  cacheTotals.count = 0
  cacheRoot.value = ''
}

const resetAvailabilityState = () => {
  availability.start = ''
  availability.end = ''
  availability.error = ''
  fetchForm.start = ''
  fetchForm.end = ''
}

const normalizeTopicOptions = (records) => {
  return records
    .map((record) => String(record?.name || '').trim())
    .filter((name, index, arr) => name && arr.indexOf(name) === index)
}

const loadTopics = async () => {
  topicsLoading.value = true
  topicsError.value = ''
  try {
    const response = await callApi('/api/query', {
      method: 'POST',
      body: JSON.stringify({ include_counts: false })
    })
    const databases = response?.data?.databases ?? []
    topics.value = normalizeTopicOptions(databases)
    if (!topics.value.length) {
      selectedTopic.value = ''
      resetAvailabilityState()
      resetCacheState()
      return
    }
    if (!selectedTopic.value || !topics.value.includes(selectedTopic.value)) {
      selectedTopic.value = topics.value[0]
    }
  } catch (error) {
    topicsError.value = error instanceof Error ? error.message : '无法加载远程专题'
    topics.value = []
    selectedTopic.value = ''
    resetAvailabilityState()
    resetCacheState()
  } finally {
    topicsLoading.value = false
  }
}

const loadAvailability = async (topicOverride = null) => {
  const topicSource = topicOverride ?? selectedTopic.value
  const topic = (topicSource ?? '').trim()
  if (!topic) {
    resetAvailabilityState()
    return
  }
  const requestId = ++availabilityRequestId
  availability.loading = true
  availability.error = ''
  try {
    const params = new URLSearchParams({ topic })
    const payload = await callApi(`/api/fetch/availability?${params.toString()}`, { method: 'GET' })
    if (requestId !== availabilityRequestId) return
    const range = payload?.data?.range ?? {}
    availability.start = range.start || ''
    availability.end = range.end || availability.start || ''
    fetchForm.start = availability.start || ''
    fetchForm.end = availability.end || availability.start || ''
  } catch (error) {
    if (requestId !== availabilityRequestId) return
    availability.start = ''
    availability.end = ''
    availability.error = error instanceof Error ? error.message : '无法获取时间区间'
    fetchForm.start = ''
    fetchForm.end = ''
  } finally {
    if (requestId === availabilityRequestId) {
      availability.loading = false
    }
  }
}

const loadCaches = async (topicOverride = null) => {
  const topicSource = topicOverride ?? selectedTopic.value
  const topic = (topicSource ?? '').trim()
  if (!topic) {
    resetCacheState()
    return
  }
  cacheLoading.value = true
  cacheError.value = ''
  try {
    const params = new URLSearchParams({ topic })
    const payload = await callApi(`/api/fetch/cache?${params.toString()}`, { method: 'GET' })
    if (payload?.status !== 'ok') {
      const message = payload?.message || '无法加载缓存信息'
      throw new Error(message)
    }
    caches.value = Array.isArray(payload.caches) ? payload.caches : []
    latestCache.value = payload.latest_cache || null
    cacheRoot.value = payload.cache_root || ''
    cacheTotals.files = Number(payload.totals?.files ?? 0)
    cacheTotals.size = Number(payload.totals?.size ?? 0)
    cacheTotals.count = Number(payload.count ?? caches.value.length)
  } catch (error) {
    cacheError.value = error instanceof Error ? error.message : '无法加载缓存信息'
    resetCacheState()
  } finally {
    cacheLoading.value = false
  }
}

const refreshCaches = () => {
  if (selectedTopic.value) {
    loadCaches(selectedTopic.value)
  }
}

const handleTopicChange = (topic) => {
  const next = typeof topic === 'string' ? topic : ''
  selectedTopic.value = next
}

const triggerFetch = async () => {
  const topic = (selectedTopic.value || '').trim()
  const start = (fetchForm.start || '').trim()
  const end = (fetchForm.end || start || '').trim()
  if (!topic || !start || !end) {
    fetchFeedback.type = 'error'
    fetchFeedback.message = '请选择专题并填写时间区间'
    return
  }
  fetchRunning.value = true
  fetchFeedback.type = ''
  fetchFeedback.message = ''
  try {
    const payload = await callApi('/api/fetch', {
      method: 'POST',
      body: JSON.stringify({ topic, start, end }),
    })
    if (payload?.status !== 'ok') {
      const message = payload?.message || '触发远程拉取失败'
      throw new Error(message)
    }
    fetchFeedback.type = 'success'
    fetchFeedback.message = `已触发 ${topic} ${start}→${end}`
    await loadCaches(topic)
  } catch (error) {
    fetchFeedback.type = 'error'
    fetchFeedback.message = error instanceof Error ? error.message : '触发远程拉取失败'
  } finally {
    fetchRunning.value = false
  }
}

const formatFileSize = (value) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let current = numeric
  let unitIndex = 0
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024
    unitIndex += 1
  }
  const precision = current >= 100 || unitIndex === 0 ? 0 : current >= 10 ? 1 : 2
  return `${current.toFixed(precision)} ${units[unitIndex]}`
}

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '未知时间'
  try {
    return new Date(timestamp).toLocaleString()
  } catch (error) {
    return timestamp
  }
}

const formatRange = (value) => {
  if (!value) return '—'
  const text = String(value)
  if (text.includes('_')) {
    const [start, end] = text.split('_')
    return `${start} → ${end || start}`
  }
  return text
}

const cacheDirectoryFor = (cache) => {
  if (!cache || typeof cache !== 'object') return cacheRoot.value || ''
  const cachedPath = typeof cache.path === 'string' ? cache.path.trim() : ''
  if (cachedPath) {
    return cachedPath
  }
  const dateValue = typeof cache.date === 'string' ? cache.date.trim() : ''
  if (cacheRoot.value && dateValue) {
    const trimmedRoot = cacheRoot.value.replace(/\/+$/, '')
    return `${trimmedRoot}/${dateValue}`
  }
  return cacheRoot.value || dateValue
}

watch(
  () => selectedTopic.value,
  (topic) => {
    fetchFeedback.type = ''
    fetchFeedback.message = ''
    if (topic) {
      loadAvailability(topic)
      loadCaches(topic)
    } else {
      resetAvailabilityState()
      resetCacheState()
      cacheError.value = ''
    }
  }
)

onMounted(() => {
  loadTopics()
})
</script>
