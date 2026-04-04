<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">Database Clean</p>
          <h2 class="mt-2 text-xl font-semibold text-primary">数据库去重</h2>
          <p class="mt-2 text-sm text-secondary">
            按标准化后的 `contents` 去重，保留 `published_at` 最早、再按 `id` 最小的一条；若有删除，会自动同步本地缓存。
          </p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600"
          :disabled="projectsLoading || databasesLoading"
          @click="refreshAll"
        >
          <ArrowPathIcon class="h-4 w-4" :class="projectsLoading || databasesLoading ? 'animate-spin' : ''" />
          刷新上下文
        </button>
      </div>

      <div class="grid gap-5 xl:grid-cols-[1.1fr,1fr]">
        <div class="space-y-4 rounded-3xl border border-soft bg-surface-muted/60 p-5">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="space-y-2">
              <span class="text-xs font-semibold text-muted">项目</span>
              <select v-model="selectedProjectName" class="input" :disabled="projectsLoading || !projectOptions.length">
                <option value="" disabled>请选择项目</option>
                <option v-for="option in projectOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
              <p v-if="projectsError" class="text-xs text-danger">{{ projectsError }}</p>
            </label>

            <label class="space-y-2">
              <span class="text-xs font-semibold text-muted">数据集</span>
              <select v-model="selectedDatasetId" class="input" :disabled="datasetsLoading || !datasetOptions.length">
                <option value="">项目级默认上下文</option>
                <option v-for="option in datasetOptions" :key="option.id" :value="option.id">{{ option.label }}</option>
              </select>
              <p v-if="datasetsError" class="text-xs text-danger">{{ datasetsError }}</p>
            </label>

            <label class="space-y-2 md:col-span-2">
              <span class="text-xs font-semibold text-muted">数据库</span>
              <select v-model="selectedDatabase" class="input" :disabled="databasesLoading || !databaseOptions.length">
                <option value="" disabled>{{ databaseOptions.length ? '请选择数据库' : '暂无数据库' }}</option>
                <option v-for="option in databaseOptions" :key="option.name" :value="option.name">
                  {{ option.name }} · {{ option.tableCount }} 张表
                </option>
              </select>
              <p v-if="databasesError" class="text-xs text-danger">{{ databasesError }}</p>
            </label>
          </div>

          <div class="rounded-2xl border border-soft bg-white p-4">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">表范围</p>
                <p class="mt-1 text-xs text-secondary">默认全选。无 `contents` 或 `id` 的表会在后端自动跳过并写入审计结果。</p>
              </div>
              <div class="flex items-center gap-2 text-xs">
                <button type="button" class="text-brand-600 transition hover:text-brand-700" @click="selectAllTables">全选</button>
                <button type="button" class="text-secondary transition hover:text-primary" @click="clearSelectedTables">清空</button>
              </div>
            </div>

            <div v-if="tableOptions.length" class="mt-4 grid gap-2 md:grid-cols-2">
              <label
                v-for="table in tableOptions"
                :key="table.name"
                class="flex items-center justify-between gap-3 rounded-2xl border border-soft px-3 py-2 text-sm text-secondary"
              >
                <span class="flex items-center gap-2">
                  <input v-model="selectedTables" type="checkbox" :value="table.name" class="h-4 w-4 rounded border-soft text-brand-600 focus:ring-brand-400" />
                  <span class="font-medium text-primary">{{ table.name }}</span>
                </span>
                <span class="text-xs text-muted">{{ formatInteger(table.rowCount) }} 行</span>
              </label>
            </div>
            <p v-else class="mt-4 text-sm text-secondary">当前数据库暂无可选数据表。</p>
          </div>
        </div>

        <div class="space-y-4 rounded-3xl border border-brand-200 bg-brand-50/50 p-5">
          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs text-muted">当前范围</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ currentProjectName || '未选择项目' }}</p>
            <p class="mt-1 text-xs text-secondary">
              数据库 {{ selectedDatabase || '—' }} · 表 {{ selectedTables.length || tableOptions.length ? selectedTables.length : 0 }} / {{ tableOptions.length }}
            </p>
          </div>

          <div class="rounded-2xl border border-soft bg-white px-4 py-3">
            <p class="text-xs text-muted">任务状态</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ statusLabel }}</p>
            <p class="mt-1 text-xs text-secondary">{{ deduplicateState.message || '等待执行。' }}</p>
          </div>

          <button
            type="button"
            class="btn-primary inline-flex w-full items-center justify-center gap-2"
            :disabled="!canRun || deduplicateState.running"
            @click="runDeduplicate"
          >
            <SparklesIcon class="h-4 w-4" />
            {{ deduplicateState.running ? '去重执行中…' : '开始数据库去重' }}
          </button>

          <div class="rounded-2xl border border-soft bg-white px-4 py-4">
            <div class="flex items-center justify-between gap-3 text-xs text-secondary">
              <span>整体进度</span>
              <span>{{ deduplicateState.progress.percentage }}%</span>
            </div>
            <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
              <div class="h-full rounded-full bg-brand transition-all duration-500" :style="{ width: `${deduplicateState.progress.percentage}%` }" />
            </div>
            <p class="mt-3 text-xs text-secondary">
              {{ deduplicateState.progress.completed_tables }} / {{ deduplicateState.progress.total_tables }} 张表
              <span v-if="deduplicateState.progress.deleted_rows"> · 已删除 {{ formatInteger(deduplicateState.progress.deleted_rows) }} 条</span>
            </p>
          </div>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="text-base font-semibold text-primary">结果与审计</h3>
          <p class="mt-1 text-sm text-secondary">完成后可查看整体删除量、每表结果以及缓存刷新后续动作。</p>
        </div>
      </div>

      <div v-if="deduplicateResult" class="grid gap-4 xl:grid-cols-[0.9fr,1.1fr]">
        <div class="grid gap-3 sm:grid-cols-2">
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4">
            <p class="text-xs text-muted">删除记录</p>
            <p class="mt-1 text-2xl font-semibold text-primary">{{ formatInteger(deduplicateResult.deleted_rows || 0) }}</p>
          </div>
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4">
            <p class="text-xs text-muted">缺失表</p>
            <p class="mt-1 text-2xl font-semibold text-primary">{{ (deduplicateResult.missing_tables || []).length }}</p>
          </div>
          <div class="rounded-2xl border border-soft bg-surface-muted/60 px-4 py-4 sm:col-span-2">
            <p class="text-xs text-muted">缓存刷新</p>
            <p class="mt-1 text-sm font-semibold text-primary">{{ deduplicateResult.follow_up?.message || '未返回后续动作。' }}</p>
          </div>
        </div>

        <div class="rounded-2xl border border-soft bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-primary">按表结果</p>
            <span class="text-xs text-secondary">{{ (deduplicateResult.tables || []).length }} 项</span>
          </div>
          <div v-if="(deduplicateResult.tables || []).length" class="mt-4 space-y-2">
            <div
              v-for="table in deduplicateResult.tables"
              :key="table.table"
              class="rounded-2xl border border-soft px-4 py-3"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <p class="text-sm font-semibold text-primary">{{ table.table }}</p>
                <span class="text-xs text-secondary">{{ table.status === 'skipped' ? '已跳过' : '已完成' }}</span>
              </div>
              <p class="mt-2 text-xs text-secondary">
                <span v-if="table.reason">{{ table.reason }}</span>
                <span v-else>命中 {{ formatInteger(table.duplicate_rows || 0) }} 条，删除 {{ formatInteger(table.deleted_rows || 0) }} 条。</span>
              </p>
            </div>
          </div>
          <p v-else class="mt-4 text-sm text-secondary">还没有可展示的审计结果。</p>
        </div>
      </div>
      <p v-else class="text-sm text-secondary">尚未执行数据库去重。</p>

      <div class="rounded-2xl border border-soft bg-slate-950 px-4 py-4">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Task Log</p>
        <div v-if="deduplicateState.logs.length" class="mt-3 max-h-64 space-y-2 overflow-y-auto">
          <div v-for="item in deduplicateState.logs" :key="`${item.ts}-${item.message}`" class="rounded-xl bg-slate-900/80 px-3 py-2 text-xs text-slate-200">
            <p class="font-medium text-slate-100">{{ item.message }}</p>
            <p class="mt-1 text-[11px] text-slate-400">{{ formatTimestamp(item.ts) }}</p>
          </div>
        </div>
        <p v-else class="mt-3 text-sm text-slate-300">等待任务日志。</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ArrowPathIcon, SparklesIcon } from '@heroicons/vue/24/outline'
import { useProcessingScope } from '../../composables/useProcessingScope'

const POLL_INTERVAL = 3000

const {
  callApi,
  currentProjectName,
  projectOptions,
  projectsLoading,
  projectsError,
  selectedProjectName,
  loadProjects,
  refreshProjects,
  datasetOptions,
  datasetsLoading,
  datasetsError,
  selectedDatasetId,
  refreshDatasets,
  databaseOptions,
  databasesLoading,
  databasesError,
  selectedDatabase,
  tableOptions,
  loadDatabases
} = useProcessingScope()

const selectedTables = ref([])
const pollTimer = ref(null)
const deduplicateState = reactive({
  running: false,
  success: null,
  message: '',
  logs: [],
  progress: {
    total_tables: 0,
    completed_tables: 0,
    deleted_rows: 0,
    current_table: '',
    percentage: 0
  },
  result: null
})

const canRun = computed(() => Boolean(currentProjectName.value && selectedDatabase.value))
const deduplicateResult = computed(() => deduplicateState.result && typeof deduplicateState.result === 'object' ? deduplicateState.result : null)
const statusLabel = computed(() => {
  if (deduplicateState.running) return '正在执行'
  if (deduplicateState.success === true) return '已完成'
  if (deduplicateState.success === false) return '执行失败'
  return '待执行'
})

watch(tableOptions, (items) => {
  const names = items.map((item) => item.name)
  if (!names.length) {
    selectedTables.value = []
    return
  }
  const preserved = selectedTables.value.filter((item) => names.includes(item))
  selectedTables.value = preserved.length ? preserved : [...names]
}, { immediate: true })

watch([currentProjectName, selectedDatasetId, selectedDatabase], async ([projectName, datasetId, database]) => {
  if (!projectName || !database) {
    stopPolling()
    resetState()
    return
  }
  await loadDeduplicateStatus({
    project: projectName,
    datasetId,
    database,
    silent: true
  })
})

watch(
  () => selectedTables.value.join('|'),
  async () => {
    if (!currentProjectName.value || !selectedDatabase.value) return
    await loadDeduplicateStatus({
      project: currentProjectName.value,
      datasetId: selectedDatasetId.value,
      database: selectedDatabase.value,
      silent: true
    })
  }
)

onMounted(async () => {
  await loadProjects()
  await loadDatabases()
})

onBeforeUnmount(() => {
  stopPolling()
})

async function refreshAll() {
  await Promise.all([refreshProjects(), refreshDatasets(), loadDatabases()])
}

function selectAllTables() {
  selectedTables.value = tableOptions.value.map((item) => item.name)
}

function clearSelectedTables() {
  selectedTables.value = []
}

function buildTableQueryParams(params, tables) {
  tables.forEach((table) => params.append('tables', table))
}

function applyPayload(payload) {
  if (!payload || typeof payload !== 'object') return
  deduplicateState.running = payload.status === 'running'
  deduplicateState.success = payload.status === 'completed' ? true : payload.status === 'error' ? false : deduplicateState.success
  deduplicateState.message = String(payload.message || deduplicateState.message || '')
  deduplicateState.logs = Array.isArray(payload.logs) ? payload.logs : []
  deduplicateState.progress = {
    total_tables: Number(payload.progress?.total_tables || 0),
    completed_tables: Number(payload.progress?.completed_tables || 0),
    deleted_rows: Number(payload.progress?.deleted_rows || 0),
    current_table: String(payload.progress?.current_table || ''),
    percentage: Number(payload.progress?.percentage || 0)
  }
  if (payload.result && typeof payload.result === 'object') {
    deduplicateState.result = payload.result
  }
}

function resetState() {
  deduplicateState.running = false
  deduplicateState.success = null
  deduplicateState.message = ''
  deduplicateState.logs = []
  deduplicateState.result = null
  deduplicateState.progress = {
    total_tables: 0,
    completed_tables: 0,
    deleted_rows: 0,
    current_table: '',
    percentage: 0
  }
}

async function runDeduplicate() {
  if (!canRun.value) return
  deduplicateState.success = null
  deduplicateState.message = ''
  try {
    const response = await callApi('/api/database/deduplicate', {
      method: 'POST',
      body: JSON.stringify({
        project: currentProjectName.value,
        dataset_id: selectedDatasetId.value || undefined,
        database: selectedDatabase.value,
        tables: selectedTables.value.length ? selectedTables.value : undefined
      })
    })
    applyPayload(response?.data || {})
    deduplicateState.running = true
    deduplicateState.message = response?.data?.message || '数据库去重任务已提交。'
    startPolling()
  } catch (error) {
    deduplicateState.success = false
    deduplicateState.message = error instanceof Error ? error.message : '启动数据库去重失败'
  }
}

async function loadDeduplicateStatus({ project, datasetId, database, silent = false }) {
  try {
    const params = new URLSearchParams()
    params.set('project', project)
    if (datasetId) params.set('dataset_id', datasetId)
    params.set('database', database)
    buildTableQueryParams(params, selectedTables.value)
    const response = await callApi(`/api/database/deduplicate/status?${params.toString()}`)
    applyPayload(response?.data || {})
    if (deduplicateState.running) {
      startPolling()
    } else {
      stopPolling()
    }
    return response?.data || null
  } catch (error) {
    if (!silent) {
      deduplicateState.success = false
      deduplicateState.message = error instanceof Error ? error.message : '读取去重状态失败'
    }
    return null
  }
}

function startPolling() {
  if (typeof window === 'undefined' || pollTimer.value) return
  pollTimer.value = window.setInterval(() => {
    if (!currentProjectName.value || !selectedDatabase.value) return
    loadDeduplicateStatus({
      project: currentProjectName.value,
      datasetId: selectedDatasetId.value,
      database: selectedDatabase.value,
      silent: true
    })
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (typeof window === 'undefined' || !pollTimer.value) return
  window.clearInterval(pollTimer.value)
  pollTimer.value = null
}

function formatInteger(value) {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '0'
  return new Intl.NumberFormat('zh-CN').format(num)
}

function formatTimestamp(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>
