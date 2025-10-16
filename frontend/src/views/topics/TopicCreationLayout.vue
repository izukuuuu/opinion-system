<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
      <nav class="flex items-center gap-2">
        <RouterLink
          :to="{ name: 'topic-create-overview' }"
          class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition hover:bg-indigo-50 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
          :class="isOverview ? 'bg-indigo-50 text-indigo-600' : 'text-slate-500'"
        >
          <Squares2X2Icon class="h-4 w-4" />
          <span>流程概览</span>
        </RouterLink>
        <template v-if="!isOverview">
          <ChevronRightIcon class="h-4 w-4 text-slate-400" />
          <span class="text-slate-600">{{ currentBreadcrumb }}</span>
        </template>
      </nav>
      <RouterLink
        v-if="!isOverview"
        :to="{ name: 'topic-create-overview' }"
        class="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-500 transition hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
      >
        <ChevronLeftIcon class="h-4 w-4" />
        返回开始页
      </RouterLink>
    </header>

    <div class="flex flex-col gap-6 lg:flex-row lg:items-start">
      <aside class="flex w-full shrink-0 flex-col gap-3 lg:w-56">
        <RouterLink
          v-for="step in steps"
          :key="step.label"
          :to="step.to"
          class="inline-flex items-center justify-between rounded-2xl border border-slate-200 px-4 py-3 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
          :class="[
            isActive(step.to)
              ? 'border-indigo-200 bg-indigo-50 text-indigo-600 shadow-sm'
              : 'bg-white text-slate-600 hover:border-indigo-200 hover:bg-indigo-50/40 hover:text-indigo-600'
          ]"
        >
          <span class="flex items-center gap-2">
            <component :is="step.icon" class="h-4 w-4" />
            <span>{{ step.label }}</span>
          </span>
          <ChevronRightIcon class="h-4 w-4 text-slate-400" />
        </RouterLink>
      </aside>
      <div class="flex-1 min-w-0">
        <RouterView />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  ArrowTrendingUpIcon,
  BeakerIcon,
  CloudArrowUpIcon,
  FunnelIcon,
  ChevronRightIcon,
  Squares2X2Icon,
  ChevronLeftIcon
} from '@heroicons/vue/24/outline'

const steps = [
  {
    label: '流程概览',
    to: { name: 'topic-create-overview' },
    icon: Squares2X2Icon
  },
  {
    label: '上传',
    to: { name: 'topic-create-upload' },
    icon: CloudArrowUpIcon
  },
  {
    label: '数据预处理',
    to: { name: 'topic-create-preprocess' },
    icon: FunnelIcon
  },
  {
    label: '入库',
    to: { name: 'topic-create-ingest' },
    icon: ArrowTrendingUpIcon
  },
  {
    label: '基本分析',
    to: { name: 'topic-create-analysis' },
    icon: BeakerIcon
  }
]

const route = useRoute()

const isActive = (target) => {
  if (!target?.name) return false
  if (route.name === target.name) return true
  // 当访问别名路径时保持当前状态
  if (Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === target.name)
  }
  return false
}

const isOverview = computed(() => route.name === 'topic-create-overview')
const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')
</script>
