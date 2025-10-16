<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <nav class="flex items-center gap-2">
        <RouterLink
          :to="{ name: 'topic-create-overview' }"
          class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition focus-ring-accent hover:bg-brand-soft hover:text-brand-600"
          :class="isOverview ? 'bg-brand-soft text-brand-600' : 'text-secondary'"
        >
          <Squares2X2Icon class="h-4 w-4" />
          <span>流程概览</span>
        </RouterLink>
        <template v-if="!isOverview">
          <ChevronRightIcon class="h-4 w-4 text-muted" />
          <span class="text-secondary">{{ currentBreadcrumb }}</span>
        </template>
      </nav>
      <RouterLink
        v-if="!isOverview"
        :to="{ name: 'topic-create-overview' }"
        class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
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
          class="inline-flex items-center justify-between rounded-2xl border border-soft px-4 py-3 text-sm font-semibold transition focus-ring-accent"
          :class="[
            isActive(step.to)
              ? 'border-brand-soft bg-brand-soft text-brand-600 shadow-sm'
              : 'bg-surface text-secondary hover:border-brand-soft hover:bg-accent-faint hover:text-brand-600'
          ]"
        >
          <span class="flex items-center gap-2">
            <component :is="step.icon" class="h-4 w-4" />
            <span>{{ step.label }}</span>
          </span>
          <ChevronRightIcon class="h-4 w-4 text-muted" />
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
