<template>
  <section class="datasets-page">
    <!-- Page Header -->
    <header class="page-header">
      <div class="breadcrumb">
        <span class="breadcrumb-badge">
          <TableCellsIcon class="icon-sm" />
          <span>数据集</span>
        </span>
        <ChevronRightIcon class="icon-sm text-muted" />
        <span class="text-secondary">远程数据库</span>
      </div>
      <div class="header-right">
        <div v-if="loading" class="status-badge status-loading">
          <ArrowPathIcon class="icon-sm animate-spin" />
          正在刷新最新数据…
        </div>
        <div v-else-if="queriedAt" class="status-badge status-idle">
          <ServerStackIcon class="icon-sm" />
          最近刷新：{{ queriedAt }}
        </div>
        <button type="button" class="btn-secondary" @click="refresh" :disabled="loading">
          <ArrowPathIcon class="icon-sm" :class="{ 'animate-spin': loading }" />
          刷新数据
        </button>
      </div>
    </header>

    <!-- Main Content Card -->
    <section class="main-card">

      <!-- Error Alert -->
      <section v-if="error" class="alert alert-danger" role="alert">
        <p>{{ error }}</p>
        <p class="alert-hint">请检查后端服务与数据库配置，稍后再试。</p>
      </section>

      <!-- Loading State -->
      <section v-if="loading" class="loading-state">
        <ArrowPathIcon class="icon-md animate-spin text-brand" />
        <span>正在刷新最新的数据库信息…</span>
      </section>

      <!-- Summary Stats -->
      <section v-if="hasData && !loading" class="stats-grid">
        <article class="stat-card">
          <span class="stat-value">{{ animatedDatabaseCount }}</span>
          <span class="stat-label">业务数据库</span>
        </article>
        <article class="stat-card">
          <span class="stat-value">{{ animatedTableCount }}</span>
          <span class="stat-label">总表数</span>
        </article>
        <article class="stat-card">
          <span class="stat-value">{{ animatedRowCount }}</span>
          <span class="stat-label">已统计行数</span>
        </article>
      </section>

      <!-- Database Cards -->
      <section v-if="hasData && !loading" class="database-grid">
        <article v-for="database in databases" :key="database.name" class="database-card">
          <header class="database-header">
            <div class="database-title">
              <CircleStackIcon class="icon-sm text-brand" />
              <h2>{{ database.name }}</h2>
            </div>
            <p class="database-meta">
              {{ database.table_count }} 张表 · {{ formatNumber(database.total_rows) }} 行
            </p>
            <button class="btn-icon text-muted hover:text-danger" title="删除数据库"
              @click="confirmDeleteDatabase(database)">
              <TrashIcon class="icon-sm" />
            </button>
          </header>
          <ul class="table-grid">
            <li v-for="table in database.tables" :key="table.name" class="table-item"
              :class="{ 'table-item-error': table.error }">
              <button type="button" class="table-button" @click="openTablePreview(database, table)">
                <span v-if="getPlatformIcon(table.name)" class="table-icon">
                  <img :src="getPlatformIcon(table.name)" :alt="`${table.name} 图标`" />
                </span>
                <span v-else class="table-icon table-icon-placeholder">
                  <CircleStackIcon class="icon-md" />
                </span>
                <span class="table-name" :class="{ 'text-danger': table.error }">
                  {{ table.name }}
                </span>
                <span v-if="table.error" class="table-count text-danger">{{ table.error }}</span>
                <span v-else class="table-count">{{ formatNumber(table.record_count) }} 行</span>
              </button>
            </li>
          </ul>
          <p v-if="!database.tables.length" class="empty-hint">该库暂无业务表。</p>
        </article>
      </section>

      <!-- Empty State -->
      <p v-if="!loading && !hasData && !error" class="empty-state">
        未检索到业务数据库，请确认配置是否正确。
      </p>
    </section>

    <AppModal v-model="isPreviewOpen" eyebrow="数据预览" :title="previewTitle" cancel-text="关闭" confirm-text="确定"
      :show-footer="false" width="max-w-5xl" :show-close="true" @cancel="closeTablePreview">
      <template #description>
        <p v-if="previewRows.length" class="text-sm text-slate-500">
          当前展示前 {{ previewRows.length }} 条记录，更多数据请在数据库中查看。
        </p>
        <p v-else-if="previewError" class="rounded-2xl bg-rose-50 px-4 py-2 text-sm text-rose-500">
          {{ previewError }}
        </p>
        <p v-else class="text-sm text-slate-500">暂无预览数据，请稍后重试。</p>
      </template>

      <div v-if="previewRows.length" class="max-h-[420px] overflow-auto rounded-2xl border border-slate-200">
        <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead class="sticky top-0 bg-slate-50">
            <tr>
              <th v-for="column in previewColumns" :key="column" :class="getPreviewColumnClasses(column, 'header')">
                {{ column }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr v-for="(row, rowIndex) in previewRows" :key="rowIndex" class="hover:bg-slate-50">
              <td v-for="column in previewColumns" :key="column" :class="getPreviewColumnClasses(column, 'cell')"
                :title="column === 'url' ? formatPreviewCell(row[column]) : ''">
                {{ formatPreviewCell(row[column]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">
        {{ previewError || '暂无预览数据，请刷新后重试。' }}
      </p>
      <div class="mt-4 flex justify-end">
        <button type="button"
          class="inline-flex items-center justify-center rounded-full border border-soft px-4 py-2 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
          @click="closeTablePreview">
          关闭
        </button>
      </div>
    </AppModal>

    <!-- Delete Confirmation Modal -->
    <AppModal v-model="isDeleteModalOpen" eyebrow="删除数据库" title="确认删除此数据库？" cancel-text="取消" confirm-text="删除"
      confirm-tone="danger" :confirm-loading="isDeleting" description="此操作将永久删除该数据库及其所有数据，无法撤销。"
      @cancel="closeDeleteModal" @confirm="deleteDatabase">
      <div v-if="databaseToDelete" class="mt-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <div class="flex items-center gap-2 mb-2">
          <CircleStackIcon class="h-5 w-5 text-slate-500" />
          <span class="font-medium text-slate-700">{{ databaseToDelete.name }}</span>
        </div>
        <p class="text-sm text-slate-500">
          包含 {{ databaseToDelete.table_count }} 张表，约 {{ formatNumber(databaseToDelete.total_rows) }} 行数据
        </p>
      </div>
    </AppModal>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  ChartBarIcon,
  CircleStackIcon,
  ChevronRightIcon,
  ServerStackIcon,
  TableCellsIcon,
  TrashIcon
} from '@heroicons/vue/24/outline'

import AppModal from '../components/AppModal.vue'
import { useApiBase } from '../composables/useApiBase'

const { callApi } = useApiBase()

const loading = ref(false)
const error = ref('')
const payload = ref(null)
const selectedTable = ref(null)

// Delete state
const isDeleteModalOpen = ref(false)
const isDeleting = ref(false)
const databaseToDelete = ref(null)

const numberFormatter = new Intl.NumberFormat('zh-CN')
const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return numberFormatter.format(Number(value))
}

const normalizePlatformName = (name) => String(name ?? '').replace(/\s+/g, '').toLowerCase()

const platformIconMap = Object.freeze(
  [
    { file: '微信.svg', names: ['微信'] },
    { file: '微博.svg', names: ['微博'] },
    { file: '新闻APP.svg', names: ['新闻app', '新闻APP', '新闻App'] },
    { file: '新闻网站.svg', names: ['新闻网站', '网站'] },
    { file: '自媒体.svg', names: ['自媒体', '自媒体号'] },
    { file: '视频.svg', names: ['视频'] },
    { file: '论坛.svg', names: ['论坛'] },
    { file: '电子报.svg', names: ['电子报'] },
    { file: '推特.svg', names: ['推特', 'twitter', 'Twitter'] },
    { file: '脸书.svg', names: ['脸书', 'facebook', 'Facebook', 'fb', 'FB'] },
    { file: '油管.svg', names: ['油管', 'youtube', 'YouTube'] },
    { file: '照片墙.svg', names: ['照片墙', 'instagram', 'Instagram', 'ins', 'INS'] },
    { file: 'telegram.svg', names: ['telegram', 'Telegram', 'tg', 'TG'] },
    { file: 'tiktok.svg', names: ['tiktok', 'TikTok'] }
  ].reduce((acc, { file, names }) => {
    const iconUrl = new URL(`../drawable/platform-icons/${file}`, import.meta.url).href
    names.forEach((name) => {
      acc[normalizePlatformName(name)] = iconUrl
    })
    return acc
  }, {})
)

const getPlatformIcon = (name) => platformIconMap[normalizePlatformName(name)] ?? ''

const queriedAt = computed(() => {
  if (!payload.value?.queried_at) return ''
  try {
    return new Date(payload.value.queried_at).toLocaleString()
  } catch (err) {
    return payload.value.queried_at
  }
})

const summaryStats = computed(() => {
  const summary = payload.value?.summary ?? {}
  return {
    databaseCount: summary.database_count ?? 0,
    tableCount: summary.table_count ?? 0,
    rowCount: summary.row_count ?? 0
  }
})

// Animated counters
const animatedDatabaseCount = ref(0)
const animatedTableCount = ref(0)
const animatedRowCount = ref(0)

const animateNumber = (start, end, duration, callback) => {
  const startTime = performance.now()
  const diff = end - start

  const step = (currentTime) => {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / duration, 1)
    // Easing: ease-out cubic
    const easedProgress = 1 - Math.pow(1 - progress, 3)
    const current = Math.round(start + diff * easedProgress)
    callback(current)

    if (progress < 1) {
      requestAnimationFrame(step)
    }
  }

  requestAnimationFrame(step)
}

watch(() => summaryStats.value, (newStats) => {
  if (newStats.databaseCount > 0) {
    animateNumber(0, newStats.databaseCount, 800, (v) => animatedDatabaseCount.value = formatNumber(v))
  }
  if (newStats.tableCount > 0) {
    animateNumber(0, newStats.tableCount, 1000, (v) => animatedTableCount.value = formatNumber(v))
  }
  if (newStats.rowCount > 0) {
    animateNumber(0, newStats.rowCount, 1200, (v) => animatedRowCount.value = formatNumber(v))
  }
}, { immediate: true })

const hasPayload = computed(() => Boolean(payload.value))
const databases = computed(() => payload.value?.databases ?? [])
const hasData = computed(() => databases.value.length > 0)

const isInitialLoading = computed(() => loading.value && !hasPayload.value)
const isRefreshing = computed(() => loading.value && hasPayload.value)

const isPreviewOpen = computed({
  get: () => Boolean(selectedTable.value),
  set: (value) => {
    if (!value) {
      selectedTable.value = null
    }
  }
})

const previewTitle = computed(() => {
  if (!selectedTable.value) return '数据预览'
  const databaseName = selectedTable.value.databaseName || ''
  const tableName = selectedTable.value.table?.name || ''
  return databaseName && tableName ? `${databaseName} · ${tableName}` : tableName || '数据预览'
})

const previewColumns = computed(() => selectedTable.value?.table?.preview?.columns ?? [])
const previewRows = computed(() => selectedTable.value?.table?.preview?.rows ?? [])
const previewError = computed(() => {
  const table = selectedTable.value?.table
  if (!table) return ''
  return table.preview_error || table.error || ''
})

const openTablePreview = (database, table) => {
  selectedTable.value = {
    databaseName: database.name,
    table
  }
}

const closeTablePreview = () => {
  selectedTable.value = null
}

const confirmDeleteDatabase = (database) => {
  databaseToDelete.value = database
  isDeleteModalOpen.value = true
}

const closeDeleteModal = () => {
  isDeleteModalOpen.value = false
  databaseToDelete.value = null
}

const deleteDatabase = async () => {
  if (!databaseToDelete.value) return

  isDeleting.value = true
  try {
    const response = await callApi(`/api/database/${databaseToDelete.value.name}`, {
      method: 'DELETE'
    })

    if (response && response.status === 'ok') {
      closeDeleteModal()
      // Refresh list
      refresh()
    } else {
      throw new Error(response?.message || '删除失败')
    }
  } catch (err) {
    console.error(err)
    alert(err.message || '删除过程中发生错误')
  } finally {
    isDeleting.value = false
  }
}

const formatPreviewCell = (value) => {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (err) {
      return String(value)
    }
  }
  return String(value)
}

const getPreviewColumnClasses = (column, type = 'cell') => {
  const name = String(column || '').toLowerCase()
  const baseHeader = 'px-4 py-3 text-left font-semibold text-slate-600'
  const baseCell = 'px-4 py-3 text-left text-slate-700 align-top'

  const widthClasses = {
    title: 'min-w-[16rem] max-w-[22rem]',
    contents: 'min-w-[24rem] max-w-[30rem]',
    url: 'min-w-[10rem] max-w-[12rem]'
  }

  const typeBase = type === 'header' ? baseHeader : baseCell

  if (name === 'url' && type !== 'header') {
    return `${typeBase} ${widthClasses.url} whitespace-nowrap truncate text-brand-600`
  }

  if (name === 'title' || name === 'contents') {
    const width = widthClasses[name]
    const textWrap = type === 'header' ? '' : 'whitespace-pre-wrap break-words'
    return `${typeBase} ${width} ${textWrap}`.trim()
  }

  if (name === 'url') {
    return `${typeBase} ${widthClasses.url}`
  }

  return typeBase
}

const refresh = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await callApi('/api/query', { method: 'POST', body: JSON.stringify({}) })
    if (response && response.status === 'ok') {
      payload.value = response.data ?? null
    } else {
      const message = response && typeof response === 'object' ? response.message : ''
      throw new Error(message || '数据库查询失败')
    }
  } catch (err) {
    console.error(err)
    error.value = err instanceof Error ? err.message : '请求失败'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
/* ===== Page Layout ===== */
.datasets-page {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* ===== Page Header ===== */
.page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.875rem;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.breadcrumb-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background-color: rgb(var(--color-brand-100) / 1);
  color: rgb(var(--color-brand-600) / 1);
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
}

.status-loading {
  background-color: rgb(var(--color-accent-50) / 1);
  color: rgb(var(--color-brand-600) / 1);
}

.status-idle {
  background-color: var(--color-surface-muted);
  color: var(--color-text-muted);
}

/* ===== Main Card ===== */
.main-card {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  border-radius: 1.5rem;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border-soft);
}

/* ===== Alerts ===== */
.alert {
  padding: 1rem 1.25rem;
  border-radius: 1rem;
  font-size: 0.875rem;
}

.alert-danger {
  background-color: rgb(var(--color-danger-50) / 1);
  border: 1px solid rgb(var(--color-danger-200) / 1);
  color: rgb(var(--color-danger-500) / 1);
}

.alert-hint {
  margin-top: 0.5rem;
  opacity: 0.8;
}

/* ===== Loading State ===== */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 3rem 2rem;
  border-radius: 1rem;
  background-color: var(--color-bg-base-soft);
  border: 1px solid var(--color-border-soft);
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

/* ===== Stats Grid ===== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1.5rem 1rem;
  border-radius: 1rem;
  background-color: rgb(var(--color-brand-100) / 1);
  border: 1px solid rgb(var(--color-brand-200) / 0.5);
  text-align: center;
}

.stat-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: rgb(var(--color-brand-700) / 1);
  line-height: 1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: rgb(var(--color-brand-600) / 1);
}

/* ===== Database Grid ===== */
.database-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
}

@media (max-width: 1280px) {
  .database-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .database-grid {
    grid-template-columns: 1fr;
  }
}

.skeleton-card {
  height: 6rem;
  border-radius: 1rem;
  background-color: var(--color-surface-muted);
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.5;
  }
}

/* ===== Database Card ===== */
.database-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem;
  border-radius: 1rem;
  background-color: var(--color-bg-base-soft);
  border: 1px solid var(--color-border-soft);
}

.database-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.database-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.database-title h2 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.database-meta {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin: 0;
}

/* ===== Table Grid ===== */
.table-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

@media (min-width: 1536px) {
  .table-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* ===== Table Item ===== */
.table-item {
  border-radius: 0.75rem;
  background-color: var(--color-surface);
  border: 1px solid rgb(var(--color-brand-200) / 0.6);
  overflow: hidden;
}

.table-item-error {
  background-color: rgb(var(--color-danger-50) / 1);
  border-color: rgb(var(--color-danger-200) / 1);
}

.table-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 1rem 0.75rem;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: center;
}

.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.25rem;
  border-radius: 0.375rem;
  transition: all 0.2s;
  background: transparent;
  border: none;
  cursor: pointer;
}

.btn-icon:hover {
  background-color: var(--color-surface);
}

.text-danger {
  color: rgb(var(--color-danger-500) / 1);
}

.hover\:text-danger:hover {
  color: rgb(var(--color-danger-500) / 1);
}

.table-button:focus {
  outline: none;
}

.table-button:focus-visible {
  outline: 2px solid var(--color-focus-outline);
  outline-offset: -2px;
  border-radius: 0.75rem;
}

.table-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border-radius: 0.75rem;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border-soft);
}

.table-icon img {
  width: 2rem;
  height: 2rem;
}

.table-icon-placeholder {
  border-style: dashed;
  color: var(--color-text-muted);
}

.table-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-primary);
}

.table-count {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

/* ===== Empty States ===== */
.empty-hint {
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  background-color: var(--color-surface-muted);
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin: 0;
}

.empty-state {
  padding: 2rem;
  border-radius: 1rem;
  background-color: var(--color-bg-base-soft);
  border: 1px solid var(--color-border-soft);
  text-align: center;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

/* ===== Icon Sizes ===== */
.icon-sm {
  width: 1rem;
  height: 1rem;
}

.icon-md {
  width: 1.5rem;
  height: 1.5rem;
}

.icon-lg {
  width: 2rem;
  height: 2rem;
}
</style>
