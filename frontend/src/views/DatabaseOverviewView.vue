<template>
  <section class="relative space-y-6">
    <header class="card-surface flex flex-col gap-6 p-6 text-sm text-slate-500">
      <nav class="flex flex-wrap items-center gap-2">
        <RouterLink
          :to="{ name: 'project-data' }"
          class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
        >
          <CircleStackIcon class="h-4 w-4" />
          <span>项目数据</span>
        </RouterLink>
        <ChevronRightIcon class="h-4 w-4 text-slate-300" />
        <span class="text-slate-600">数据库概览</span>
      </nav>
      <div class="flex flex-col gap-2 text-slate-700">
        <h1 class="text-2xl font-semibold text-slate-900">数据库概览</h1>
        <p>连接后端数据库，查看连接信息、库表结构与数据量。</p>
      </div>
      <footer v-if="queriedAt" class="flex items-center gap-2 text-xs text-slate-400">
        <ServerStackIcon class="h-4 w-4" />
        <span>最近一次查询：{{ queriedAt }}</span>
      </footer>
    </header>

    <div class="flex flex-col gap-6 lg:flex-row lg:items-start">
      <aside class="flex w-full shrink-0 flex-col gap-3 lg:w-60">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="inline-flex items-start justify-between rounded-2xl border px-4 py-3 text-left text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
          :class="[
            activeTab === tab.key
              ? 'border-indigo-200 bg-indigo-50 text-indigo-700 shadow-sm'
              : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200 hover:bg-indigo-50/70 hover:text-indigo-700'
          ]"
          :id="`database-tab-${tab.key}`"
          role="tab"
          :aria-selected="activeTab === tab.key"
          :aria-controls="`database-panel-${tab.key}`"
          @click="setActiveTab(tab.key)"
        >
          <span class="flex flex-col gap-1">
            <span class="flex items-center gap-2 text-sm">
              <component :is="tab.icon" class="h-4 w-4" />
              {{ tab.label }}
            </span>
            <span class="text-xs font-normal text-slate-400">{{ tab.description }}</span>
          </span>
          <ChevronRightIcon class="h-4 w-4 text-slate-300" />
        </button>
      </aside>

      <div class="flex-1 space-y-6" role="presentation">
        <section v-if="error" class="rounded-3xl border border-rose-200 bg-rose-50/70 p-6 text-sm text-rose-600" role="alert">
          <p>{{ error }}</p>
          <p class="mt-2 text-rose-400">请检查后端服务与数据库配置，稍后再试。</p>
        </section>

        <section
          v-if="activeTab === 'overview'"
          class="space-y-6"
          role="tabpanel"
          id="database-panel-overview"
          aria-labelledby="database-tab-overview"
        >
          <section v-if="loading" class="grid gap-6 lg:grid-cols-2">
            <div class="shimmer-card h-48 rounded-3xl bg-slate-200/70"></div>
            <div class="shimmer-card h-48 rounded-3xl bg-slate-200/70"></div>
          </section>

          <section v-if="hasData" class="grid gap-6 lg:grid-cols-2">
            <article class="card-surface space-y-4 p-6">
              <header class="space-y-1">
                <h2 class="text-lg font-semibold text-slate-900">连接信息</h2>
                <p class="text-sm text-slate-500">从配置文件推断出的数据库连接要素。</p>
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
                <p class="text-sm text-slate-500">帮助快速了解业务数据规模。</p>
              </header>
              <ul class="grid gap-4 sm:grid-cols-3">
                <li class="rounded-2xl bg-indigo-50/80 p-4 text-center">
                  <span class="text-xs uppercase tracking-widest text-indigo-500">业务数据库</span>
                  <strong class="mt-2 block text-2xl font-semibold text-indigo-700">{{ summaryStats.databaseCount }}</strong>
                </li>
                <li class="rounded-2xl bg-indigo-50/80 p-4 text-center">
                  <span class="text-xs uppercase tracking-widest text-indigo-500">总表数</span>
                  <strong class="mt-2 block text-2xl font-semibold text-indigo-700">{{ summaryStats.tableCount }}</strong>
                </li>
                <li class="rounded-2xl bg-indigo-50/80 p-4 text-center">
                  <span class="text-xs uppercase tracking-widest text-indigo-500">已统计行数</span>
                  <strong class="mt-2 block text-2xl font-semibold text-indigo-700">{{ summaryStats.rowCount }}</strong>
                </li>
              </ul>
            </article>
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
            <pre class="max-h-[480px] overflow-auto rounded-2xl bg-slate-900/90 p-4 text-xs text-emerald-100">{{ rawPayload }}</pre>
          </div>
          <p v-else class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">
            暂无可展的数据，请先点击右下角的“刷新数据”按钮获取最新结果。
          </p>
        </section>
      </div>
    </div>

    <button
      type="button"
      class="group fixed bottom-6 right-6 inline-flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg transition hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-300"
      @click="refresh"
      :disabled="loading"
      aria-label="刷新数据库概览"
    >
      <ArrowPathIcon
        class="h-6 w-6"
        :class="{ 'animate-spin text-indigo-200': loading }"
      />
      <span class="sr-only">刷新数据</span>
    </button>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  ArrowPathIcon,
  ChevronRightIcon,
  CircleStackIcon,
  CodeBracketSquareIcon,
  ServerStackIcon
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
const tabs = [
  {
    key: 'overview',
    label: '数据概览',
    description: '连接信息与库表统计',
    icon: CircleStackIcon
  },
  {
    key: 'raw',
    label: '原始 JSON',
    description: '调试响应内容',
    icon: CodeBracketSquareIcon
  }
]

const setActiveTab = (key) => {
  if (tabs.some((tab) => tab.key === key)) {
    activeTab.value = key
  }
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

const refresh = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await callApi('/database/overview')
    payload.value = response
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
.shimmer-card {
  position: relative;
  overflow: hidden;
}

.shimmer-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 0.7) 50%, rgba(255, 255, 255, 0) 100%);
  transform: translateX(-100%);
  animation: shimmer 1.6s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}
</style>
