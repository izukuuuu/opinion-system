<template>
  <section class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <nav class="flex items-center gap-2">
        <RouterLink
          :to="rootNavigation.to"
          class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition focus-ring-accent hover:bg-brand-soft hover:text-brand-600"
        >
          <Squares2X2Icon class="h-4 w-4" />
          <span>{{ rootNavigation.label }}</span>
        </RouterLink>
        <ChevronRightIcon class="h-4 w-4 text-muted" />
        <span class="text-secondary">{{ breadcrumbLabel }}</span>
      </nav>
      <RouterLink
        :to="rootNavigation.to"
        class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
      >
        <ChevronLeftIcon class="h-4 w-4" />
        返回工作台
      </RouterLink>
    </header>

    <div class="flex flex-col gap-6 lg:flex-row lg:items-start">
      <aside class="flex w-full shrink-0 flex-col gap-3 lg:w-64">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="group inline-flex items-center justify-between rounded-2xl border px-4 py-3 text-left transition focus-ring-accent"
          :class="[
            activeTab === tab.key
              ? 'border-brand-soft bg-brand-soft text-brand-600 shadow-sm'
              : 'border-transparent bg-surface text-secondary hover:border-brand-soft hover:bg-accent-faint hover:text-brand-600'
          ]"
          role="tab"
          :id="`database-tab-${tab.key}`"
          :aria-selected="activeTab === tab.key"
          :aria-controls="`database-panel-${tab.key}`"
          @click="setActiveTab(tab.key)"
        >
          <span class="flex items-start gap-3">
            <div class="mt-0.5 rounded-xl bg-white/70 p-2 text-brand-600 shadow-sm">
              <component :is="tab.icon" class="h-4 w-4" />
            </div>
            <span class="flex flex-col gap-1">
              <span class="font-semibold">{{ tab.label }}</span>
              <span class="text-xs text-muted">{{ tab.description }}</span>
            </span>
          </span>
          <ChevronRightIcon class="h-4 w-4 text-muted transition group-hover:text-brand-500" />
        </button>
      </aside>

      <div class="flex-1 min-w-0 space-y-6">
        <section class="card-surface space-y-6 p-6">
          <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex items-start gap-4">
              <CircleStackIcon class="h-12 w-12 text-brand" />
              <div class="space-y-1">
                <h1 class="text-2xl font-semibold text-slate-900">数据库概览</h1>
                <p class="text-sm text-slate-500">连接后端数据库，查看数据库的连接信息、库表结构与数据量。</p>
              </div>
            </div>
            <div class="inline-flex items-center gap-2 rounded-full bg-accent-faint px-3 py-1 text-xs font-semibold text-brand-600" v-if="loading">
              <ArrowPathIcon class="h-4 w-4 animate-spin" />
              正在刷新最新数据…
            </div>
            <div v-else-if="queriedAt" class="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
              <ServerStackIcon class="h-4 w-4" />
              最近刷新：{{ queriedAt }}
            </div>
          </div>

          <section v-if="error" class="rounded-3xl border border-rose-200 bg-rose-50/70 p-6 text-sm text-rose-600" role="alert">
            <p>{{ error }}</p>
            <p class="mt-2 text-rose-400">请检查后端服务与数据库配置，稍后再试。</p>
          </section>
        </section>

        <section
          v-if="activeTab === 'overview'"
          class="space-y-6"
          role="tabpanel"
          id="database-panel-overview"
          aria-labelledby="database-tab-overview"
        >
          <section
            v-if="isInitialLoading"
            class="flex flex-col items-center gap-2 rounded-3xl border border-slate-200 bg-white/80 p-10 text-sm text-slate-500"
          >
            <ArrowPathIcon class="h-6 w-6 animate-spin text-brand" />
            正在刷新最新的数据库信息…
          </section>

          <section v-if="hasData" class="grid gap-6 lg:grid-cols-2">
            <article class="card-surface space-y-4 p-6">
              <header class="space-y-1">
                <h2 class="text-lg font-semibold text-slate-900">连接信息</h2>
                <p class="text-sm text-slate-500">查看远程服务器连接配置</p>
              </header>
              <dl class="grid gap-3">
                <div v-for="detail in connectionDetails" :key="detail.label" class="flex flex-col rounded-2xl bg-slate-50/80 px-4 py-3">
                  <dt class="text-xs uppercase tracking-widest text-slate-400">{{ detail.label }}</dt>
                  <dd class="text-sm font-medium text-slate-700">{{ detail.value }}</dd>
                </div>
              </dl>
            </article>

            <article class="card-surface space-y-4 p-6">
              <header class="space-y-1">
                <h2 class="text-lg font-semibold text-slate-900">数据量统计</h2>
                <p class="text-sm text-slate-500">当前存储的专题数据量</p>
              </header>
              <ul class="grid gap-4 sm:grid-cols-3">
                <li class="rounded-2xl bg-brand-soft p-4 text-center">
                  <span class="text-xs uppercase tracking-widest text-brand">业务数据库</span>
                  <strong class="mt-2 block text-2xl font-semibold text-brand-strong">{{ summaryStats.databaseCount }}</strong>
                </li>
                <li class="rounded-2xl bg-brand-soft p-4 text-center">
                  <span class="text-xs uppercase tracking-widest text-brand">总表数</span>
                  <strong class="mt-2 block text-2xl font-semibold text-brand-strong">{{ summaryStats.tableCount }}</strong>
                </li>
                <li class="rounded-2xl bg-brand-soft p-4 text-center">
                  <span class="text-xs uppercase tracking-widest text-brand">已统计行数</span>
                  <strong class="mt-2 block text-2xl font-semibold text-brand-strong">{{ summaryStats.rowCount }}</strong>
                </li>
              </ul>
            </article>
          </section>

          <section v-if="isRefreshing" class="grid gap-6 lg:grid-cols-2">
            <div class="h-48 rounded-3xl bg-slate-200/70 animate-pulse"></div>
            <div class="h-48 rounded-3xl bg-slate-200/70 animate-pulse"></div>
          </section>

          <section v-if="hasData" class="grid gap-6">
            <article v-for="database in databases" :key="database.name" class="card-surface space-y-5 p-6">
              <header class="flex flex-wrap items-center justify-between gap-3">
                <h3 class="text-xl font-semibold text-slate-900">{{ database.name }}</h3>
                <p class="text-sm text-slate-500">{{ database.table_count }} 张表 · {{ formatNumber(database.total_rows) }} 行</p>
              </header>
              <ul class="space-y-2">
                <li
                  v-for="table in database.tables"
                  :key="table.name"
                  class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/70 bg-slate-50/80 px-4 py-3"
                  :class="{ 'border-rose-200 bg-rose-50/80 text-rose-600': table.error }"
                >
                  <span class="font-medium">{{ table.name }}</span>
                  <span v-if="table.error" class="text-sm">{{ table.error }}</span>
                  <span v-else class="text-sm text-slate-500">{{ formatNumber(table.record_count) }} 行</span>
                </li>
              </ul>
              <p v-if="!database.tables.length" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">该库暂无业务表。</p>
            </article>
          </section>

          <p v-if="!loading && !hasData && !error" class="rounded-3xl border border-slate-200 bg-white/80 p-8 text-center text-sm text-slate-500">
            未检索到业务数据库，请确认配置是否正确。
          </p>
        </section>

        <section
          v-else
          class="card-surface space-y-4 p-6"
          role="tabpanel"
          id="database-panel-raw"
          aria-labelledby="database-tab-raw"
        >
          <div v-if="hasPayload" class="space-y-4">
            <header class="space-y-1">
              <h2 class="text-lg font-semibold text-slate-900">原始响应数据</h2>
              <p class="text-sm text-slate-500">以下内容展示了后端返回的完整 JSON，便于对照排查。</p>
            </header>
            <pre class="max-h-[480px] max-w-full overflow-x-auto rounded-2xl bg-slate-900/90 p-4 text-xs text-emerald-100">
          {{ rawPayload }}
        </pre>
          </div>
          <p v-else class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">
            暂无可展的数据，请先点击右下角的“刷新数据”按钮获取最新结果。
          </p>
        </section>
      </div>
    </div>

    <button
      type="button"
      class="fixed bottom-6 right-6 inline-flex items-center justify-center gap-2 rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white shadow-lg transition focus-ring-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-300"
      @click="refresh"
      :disabled="loading"
      aria-label="刷新数据库数据"
    >
      <ArrowPathIcon
        class="h-4 w-4"
        :class="{ 'animate-spin text-white/80': loading }"
      />
      <span class="hidden sm:inline">刷新数据</span>
    </button>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  ArrowPathIcon,
  CircleStackIcon,
  CodeBracketSquareIcon,
  ServerStackIcon,
  Squares2X2Icon,
  ChevronRightIcon,
  ChevronLeftIcon
} from '@heroicons/vue/24/outline'

import { useBackendClient } from '../composables/useBackendClient'

const { callApi } = useBackendClient()

const loading = ref(false)
const error = ref('')
const payload = ref(null)
const activeTab = ref('overview')

const numberFormatter = new Intl.NumberFormat('zh-CN')
const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return numberFormatter.format(Number(value))
}

const tabs = Object.freeze([
  {
    key: 'overview',
    label: '数据概览',
    description: '连接信息与统计',
    icon: CircleStackIcon
  },
  {
    key: 'raw',
    label: '原始 JSON',
    description: '查看接口原始响应',
    icon: CodeBracketSquareIcon
  }
])

const setActiveTab = (key) => {
  if (tabs.some((tab) => tab.key === key)) {
    activeTab.value = key
  }
}

const route = useRoute()

const breadcrumbLabel = computed(() => route.meta?.breadcrumb || route.meta?.title || '数据库概览')
const rootNavigation = {
  to: { name: 'topic-create-overview' },
  label: '专题工作台'
}

const queriedAt = computed(() => {
  if (!payload.value?.queried_at) return ''
  try {
    return new Date(payload.value.queried_at).toLocaleString()
  } catch (err) {
    return payload.value.queried_at
  }
})

const connectionDetails = computed(() => {
  const connection = payload.value?.connection ?? {}
  const items = [
    { label: '驱动', value: connection.driver || '未知' },
    { label: '主机', value: connection.host || '未配置' },
    { label: '端口', value: connection.port || '未配置' },
    { label: '默认数据库', value: connection.database || '未配置' },
    { label: '用户名', value: connection.username || '未配置' },
    {
      label: '密码配置',
      value: connection.has_password ? '已配置' : '未配置'
    }
  ]
  return items.filter((item) => item.value !== undefined && item.value !== null)
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

const rawPayload = computed(() => JSON.stringify(payload.value, null, 2))

const isInitialLoading = computed(() => loading.value && !hasPayload.value)
const isRefreshing = computed(() => loading.value && hasPayload.value)

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
