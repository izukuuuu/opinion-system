<template>
  <div class="mx-auto flex max-w-6xl flex-col gap-10 px-6 pb-24 pt-16 sm:px-10 lg:px-12">
    <section class="flex items-start justify-between gap-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">Today Hot Overview</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-primary sm:text-4xl">首页 · 今日热点</h1>
      </div>
      <RouterLink
        :to="{ name: 'system-intro' }"
        class="inline-flex items-center justify-center rounded-full border border-soft px-5 py-2 text-sm font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
      >
        查看系统介绍
      </RouterLink>
    </section>

    <section class="rounded-[34px] border border-soft/80 bg-surface px-8 py-9 shadow-[0_20px_55px_rgba(15,23,42,0.08)]">
      <div class="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div class="space-y-2">
          <h2 class="text-2xl font-semibold tracking-tight text-primary sm:text-3xl">今日热点概览</h2>
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center rounded-full border border-soft px-4 py-2 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
          :disabled="hotLoading"
          @click="refreshHotOverview(true)"
        >
          {{ hotLoading ? '加载中...' : '刷新热点' }}
        </button>
      </div>

      <div v-if="hotError" class="mt-6 rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-600">
        {{ hotError }}
      </div>

      <div v-else-if="hotLoading" class="mt-8 grid gap-4 sm:grid-cols-2">
        <div class="h-24 animate-pulse rounded-2xl bg-base/80"></div>
        <div class="h-24 animate-pulse rounded-2xl bg-base/80"></div>
      </div>

      <div v-else-if="hotOverview" class="mt-8 space-y-8">
        <div class="rounded-[24px] border border-soft/80 bg-base/70 px-6 py-6">
          <h3 class="text-lg font-semibold text-primary">关键词聚合</h3>
          <div class="mt-4 flex flex-wrap gap-3">
            <span
              v-for="(keyword, keywordIndex) in hotKeywords"
              :key="`${keywordLabel(keyword)}-${keywordIndex}`"
              class="inline-flex rounded-full border px-4 py-1.5 text-sm font-semibold"
              :class="keywordChipClass(keyword)"
            >
              {{ keywordLabel(keyword) }}
            </span>
          </div>
          <p class="mt-5 text-sm leading-7 text-secondary">{{ hotOverview.overview }}</p>
          <p
            v-if="hotOverview.detailed_overview"
            class="mt-4 border-t border-soft/80 pt-4 text-sm leading-7 text-secondary"
          >
            {{ hotOverview.detailed_overview }}
          </p>
          <p class="mt-3 text-xs text-muted">
            快照日期：{{ formatSnapshotDate(hotOverview.snapshot_date) }} · 生成时间：{{ formatLocalTime(hotOverview.generated_at) }} · 来源：{{ hotOverview.summary_source }}
          </p>
        </div>

        <div v-if="hotSections.length" class="space-y-10">
          <section
            v-for="section in hotSections"
            :key="section.title"
            class="space-y-4"
          >
            <div class="flex items-center gap-3">
              <h3 class="text-2xl font-semibold tracking-tight text-primary">{{ section.title }}</h3>
              <span class="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-surface">
                {{ section.badge || '关注' }}
              </span>
            </div>
            <div class="grid gap-5 xl:grid-cols-3 lg:grid-cols-2">
              <article
                v-for="(card, cardIndex) in section.cards || []"
                :key="`${section.title}-${card.headline}-${cardIndex}`"
                class="rounded-[28px] border border-soft/70 bg-surface px-6 py-6 shadow-[0_12px_35px_rgba(15,23,42,0.06)]"
              >
                <div class="flex items-start justify-between gap-3">
                  <h4 class="text-2xl leading-8 font-semibold text-primary">{{ card.headline }}</h4>
                  <span class="whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold" :class="stanceClass(card.stance)">
                    {{ card.stance || '中性' }}
                  </span>
                </div>
                <div class="mt-4 h-2 overflow-hidden rounded-full bg-base">
                  <div
                    class="h-full rounded-full bg-primary/80 transition-[width] duration-500 ease-out"
                    :style="{ width: `${normalizeHeat(card.heat)}%` }"
                  ></div>
                </div>
                <p class="mt-4 text-sm font-semibold text-primary">热度 {{ normalizeHeat(card.heat) }}</p>
                <p class="mt-3 text-sm leading-7 text-secondary">{{ card.summary }}</p>

                <div v-if="getBackground(card.headline)" class="mt-4 rounded-xl bg-indigo-50/60 p-3.5 border border-indigo-100/60">
                  <p class="text-[13px] text-indigo-800/80 leading-relaxed">
                    <span class="font-semibold text-indigo-900/90 mr-1">AI 背景探测:</span>
                    {{ getBackground(card.headline) }}
                  </p>
                </div>

                <div class="mt-5 flex flex-wrap gap-2 border-t border-soft/70 pt-4">
                  <span
                    v-for="(tag, tagIndex) in card.tags || []"
                    :key="`${tagLabel(tag)}-${tagIndex}`"
                    class="rounded-full border px-3 py-1 text-xs font-medium"
                    :class="tagChipClass(tag)"
                  >
                    {{ tagLabel(tag) }}
                  </span>
                </div>
              </article>
            </div>
          </section>
        </div>

        <div class="rounded-[24px] border border-soft/70 bg-surface px-6 py-6">
          <div class="flex items-center justify-between gap-4">
            <h3 class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">原始榜单</h3>
            <span class="text-xs text-muted">共 {{ (hotOverview.items || []).length }} 条</span>
          </div>
          <div class="mt-4 max-h-[420px] overflow-y-auto pr-2">
            <ol class="space-y-3">
              <li
                v-for="(item, idx) in hotOverview.items || []"
                :key="`${item.title}-${idx}`"
                class="rounded-xl border border-soft/60 bg-base/60 px-4 py-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <p class="text-sm font-semibold leading-6 text-primary">
                    {{ idx + 1 }}. {{ item.title }}
                  </p>
                  <a
                    v-if="item.url"
                    :href="item.url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="shrink-0 text-xs font-semibold text-brand-600 hover:text-brand-700"
                  >
                    查看
                  </a>
                </div>
                <p class="mt-1 text-xs text-muted">
                  {{ item.source || '未知来源' }} · 排名 #{{ item.rank || '--' }} · 热度指数 {{ item.heat_score || '--' }}
                </p>
              </li>
            </ol>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useApiBase } from '@/composables/useApiBase'

const { callApi } = useApiBase()
const hotOverview = ref(null)
const hotLoading = ref(true)
const hotError = ref('')
const hotKeywords = computed(() => hotOverview.value?.keyword_pool || [])
const hotSections = computed(() => hotOverview.value?.sections || [])

const refreshHotOverview = async (forceRefresh = false) => {
  hotLoading.value = true
  hotError.value = ''
  try {
    const query = forceRefresh ? '?mode=fast&limit=30&refresh=1' : '?mode=fast&limit=30'
    const response = await callApi(`/api/home/today-hot-overview${query}`)
    const payload = response?.data
    if (!payload || typeof payload !== 'object') {
      throw new Error('热点数据格式异常')
    }
    hotOverview.value = payload
  } catch (error) {
    hotError.value = error instanceof Error ? error.message : '获取今日热点失败'
    hotOverview.value = null
  } finally {
    hotLoading.value = false
  }
}

const getBackground = (headline) => {
  if (!hotOverview.value || !hotOverview.value._backgrounds) return ''
  return hotOverview.value._backgrounds[headline] || ''
}

const formatLocalTime = (value) => {
  if (!value) return '未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { hour12: false })
}

const formatSnapshotDate = (value) => {
  const text = String(value || '').trim()
  if (!text) return '未知'
  return text
}

const normalizeHeat = (value) => {
  const num = Number(value)
  if (Number.isNaN(num)) return 60
  return Math.max(1, Math.min(100, Math.round(num)))
}

const stanceClass = (stance) => {
  if (stance === '正向') return 'bg-emerald-50 text-emerald-700 border border-emerald-200'
  if (stance === '负向') return 'bg-rose-50 text-rose-700 border border-rose-200'
  return 'bg-slate-100 text-slate-700 border border-slate-200'
}

const TAG_CLUSTER_CLASS = {
  geopolitics: 'bg-blue-50 text-blue-700 border-blue-200',
  policy: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  economy: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  technology: 'bg-violet-50 text-violet-700 border-violet-200',
  industry: 'bg-amber-50 text-amber-700 border-amber-200',
  society: 'bg-rose-50 text-rose-700 border-rose-200',
  default: 'bg-slate-100 text-slate-700 border-slate-200'
}

const normalizeCluster = (value) => {
  const cluster = String(value || '').trim().toLowerCase()
  return TAG_CLUSTER_CLASS[cluster] ? cluster : 'default'
}

const keywordLabel = (keyword) => {
  if (keyword && typeof keyword === 'object') {
    return String(keyword.text || keyword.name || '').trim()
  }
  return String(keyword || '').trim()
}

const keywordChipClass = (keyword) => {
  const cluster = keyword && typeof keyword === 'object' ? keyword.cluster : ''
  return TAG_CLUSTER_CLASS[normalizeCluster(cluster)] || TAG_CLUSTER_CLASS.default
}

const tagLabel = (tag) => {
  if (tag && typeof tag === 'object') {
    return String(tag.name || tag.text || '').trim()
  }
  return String(tag || '').trim()
}

const tagChipClass = (tag) => {
  const cluster = tag && typeof tag === 'object' ? tag.cluster : ''
  return TAG_CLUSTER_CLASS[normalizeCluster(cluster)] || TAG_CLUSTER_CLASS.default
}

onMounted(() => {
  refreshHotOverview(false)
})
</script>
