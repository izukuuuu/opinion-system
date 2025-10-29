<template>
  <section class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-brand-600">
          <TableCellsIcon class="h-4 w-4" />
          <span>数据集</span>
        </span>
        <ChevronRightIcon class="h-4 w-4 text-muted" />
        <span class="text-secondary">远程数据库</span>
      </div>
      <div
        v-if="loading"
        class="inline-flex items-center gap-2 rounded-full bg-accent-faint px-3 py-1 text-xs font-semibold text-brand-600"
      >
        <ArrowPathIcon class="h-4 w-4 animate-spin" />
        正在刷新最新数据…
      </div>
      <div
        v-else-if="queriedAt"
        class="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500"
      >
        <ServerStackIcon class="h-4 w-4" />
        最近刷新：{{ queriedAt }}
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-start gap-4">
          <TableCellsIcon class="h-12 w-12 text-brand" />
          <div class="space-y-1">
            <h1 class="text-2xl font-semibold text-slate-900">数据集概览</h1>
            <p class="text-sm text-slate-500">查看并预览已经同步到远程数据库的专题数据表。</p>
          </div>
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center gap-2 rounded-full border border-soft px-4 py-2 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
          @click="refresh"
          :disabled="loading"
        >
          <ArrowPathIcon
            class="h-4 w-4"
            :class="{ 'animate-spin text-brand-500': loading }"
          />
          刷新数据
        </button>
      </div>

      <section v-if="error" class="rounded-3xl border border-rose-200 bg-rose-50/70 p-6 text-sm text-rose-600" role="alert">
        <p>{{ error }}</p>
        <p class="mt-2 text-rose-400">请检查后端服务与数据库配置，稍后再试。</p>
      </section>

      <section
        v-if="isInitialLoading"
        class="flex flex-col items-center gap-2 rounded-3xl border border-slate-200 bg-white/80 p-10 text-sm text-slate-500"
      >
        <ArrowPathIcon class="h-6 w-6 animate-spin text-brand" />
        正在刷新最新的数据库信息…
      </section>

      <section v-if="hasData" class="grid gap-6 lg:grid-cols-3">
        <article class="rounded-3xl bg-brand-soft px-5 py-6 text-center">
          <span class="text-xs uppercase tracking-widest text-brand">业务数据库</span>
          <strong class="mt-2 block text-2xl font-semibold text-brand-strong">{{ summaryStats.databaseCount }}</strong>
        </article>
        <article class="rounded-3xl bg-brand-soft px-5 py-6 text-center">
          <span class="text-xs uppercase tracking-widest text-brand">总表数</span>
          <strong class="mt-2 block text-2xl font-semibold text-brand-strong">{{ summaryStats.tableCount }}</strong>
        </article>
        <article class="rounded-3xl bg-brand-soft px-5 py-6 text-center">
          <span class="text-xs uppercase tracking-widest text-brand">已统计行数</span>
          <strong class="mt-2 block text-2xl font-semibold text-brand-strong">{{ summaryStats.rowCount }}</strong>
        </article>
      </section>

      <section v-if="isRefreshing" class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="index in 3"
          :key="index"
          class="h-48 rounded-3xl bg-slate-200/70 animate-pulse"
        ></div>
      </section>

      <section v-if="hasData" class="space-y-6">
        <article
          v-for="database in databases"
          :key="database.name"
          class="card-surface space-y-5 border border-slate-200/80 bg-white/90 p-6 shadow-sm"
        >
          <header class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <CircleStackIcon class="h-5 w-5 text-brand" />
              <h2 class="text-lg font-semibold text-slate-900">{{ database.name }}</h2>
            </div>
            <p class="text-sm text-slate-500">
              {{ database.table_count }} 张表 · {{ formatNumber(database.total_rows) }} 行
            </p>
          </header>
          <ul class="grid gap-4 sm:grid-cols-3 xl:grid-cols-5">
            <li
              v-for="table in database.tables"
              :key="table.name"
              class="group relative h-full overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-50/80 text-center transition hover:border-brand-soft hover:bg-white/90"
              :class="{ 'border-rose-200 bg-rose-50/80 text-rose-600': table.error }"
            >
              <button
                type="button"
                class="flex h-full w-full flex-col items-center gap-3 p-4 text-center focus:outline-none focus-visible:ring-4 focus-visible:ring-brand/30 focus-visible:ring-offset-2 focus-visible:ring-offset-white"
                @click="openTablePreview(database, table)"
              >
                <span
                  v-if="getPlatformIcon(table.name)"
                  class="flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm transition group-hover:scale-[1.03]"
                >
                  <img :src="getPlatformIcon(table.name)" :alt="`${table.name} 图标`" class="h-9 w-9" />
                </span>
                <span
                  v-else
                  class="flex h-14 w-14 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white text-slate-400 transition group-hover:scale-[1.03]"
                >
                  <CircleStackIcon class="h-6 w-6" />
                </span>
                <span class="font-medium text-slate-900" :class="{ 'text-rose-600': table.error }">
                  {{ table.name }}
                </span>
                <span v-if="table.error" class="text-xs text-rose-500">{{ table.error }}</span>
                <span v-else class="text-xs text-slate-500">{{ formatNumber(table.record_count) }} 行</span>
              </button>
            </li>
          </ul>
          <p
            v-if="!database.tables.length"
            class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500"
          >
            该库暂无业务表。
          </p>
        </article>
      </section>

      <p
        v-if="!loading && !hasData && !error"
        class="rounded-3xl border border-slate-200 bg-white/80 p-8 text-center text-sm text-slate-500"
      >
        未检索到业务数据库，请确认配置是否正确。
      </p>
    </section>

    <AppModal
      v-model="isPreviewOpen"
      eyebrow="数据预览"
      :title="previewTitle"
      cancel-text="关闭"
      confirm-text="确定"
      :show-footer="false"
      width="max-w-5xl"
      :show-close="true"
      @cancel="closeTablePreview"
    >
      <template #description>
        <p v-if="previewRows.length" class="text-sm text-slate-500">
          当前展示前 {{ previewRows.length }} 条记录，更多数据请在数据库中查看。
        </p>
        <p v-else-if="previewError" class="rounded-2xl bg-rose-50 px-4 py-2 text-sm text-rose-500">
          {{ previewError }}
        </p>
        <p v-else class="text-sm text-slate-500">暂无预览数据，请稍后重试。</p>
      </template>

      <div
        v-if="previewRows.length"
        class="max-h-[420px] overflow-auto rounded-2xl border border-slate-200"
      >
        <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead class="sticky top-0 bg-slate-50">
            <tr>
              <th
                v-for="column in previewColumns"
                :key="column"
                :class="getPreviewColumnClasses(column, 'header')"
              >
                {{ column }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr
              v-for="(row, rowIndex) in previewRows"
              :key="rowIndex"
              class="hover:bg-slate-50"
            >
              <td
                v-for="column in previewColumns"
                :key="column"
                :class="getPreviewColumnClasses(column, 'cell')"
                :title="column === 'url' ? formatPreviewCell(row[column]) : ''"
              >
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
        <button
          type="button"
          class="inline-flex items-center justify-center rounded-full border border-soft px-4 py-2 text-sm font-medium text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
          @click="closeTablePreview"
        >
          关闭
        </button>
      </div>
    </AppModal>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  ArrowPathIcon,
  CircleStackIcon,
  ChevronRightIcon,
  ServerStackIcon,
  TableCellsIcon
} from '@heroicons/vue/24/outline'

import AppModal from '../components/AppModal.vue'
import { useBackendClient } from '../composables/useBackendClient'

const { callApi } = useBackendClient()

const loading = ref(false)
const error = ref('')
const payload = ref(null)
const selectedTable = ref(null)

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
    { file: '新闻网站.svg', names: ['新闻网站'] },
    { file: '自媒体.svg', names: ['自媒体', '自媒体号'] },
    { file: '视频.svg', names: ['视频'] },
    { file: '论坛.svg', names: ['论坛'] },
    { file: '电子报.svg', names: ['电子报'] }
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
    databaseCount: summary.database_count ? formatNumber(summary.database_count) : '0',
    tableCount: summary.table_count ? formatNumber(summary.table_count) : '0',
    rowCount: summary.row_count ? formatNumber(summary.row_count) : '0'
  }
})

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
