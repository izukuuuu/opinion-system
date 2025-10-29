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
      <aside class="flex w-full shrink-0 flex-col gap-3 lg:w-64">
        <RouterLink
          v-for="step in steps"
          :key="step.label"
          :to="step.to"
          class="group inline-flex items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm transition focus-ring-accent"
          :class="[
            isActive(step.to)
              ? 'border-brand-soft bg-brand-soft text-brand-600 shadow-sm'
              : 'border-transparent bg-surface text-secondary hover:border-brand-soft hover:bg-accent-faint hover:text-brand-600'
          ]"
          role="tab"
          :aria-current="isActive(step.to) ? 'page' : undefined"
        >
          <span class="flex items-start gap-3">
            <div class="mt-0.5 rounded-xl bg-white/70 p-2 text-brand-600 shadow-sm">
              <component :is="step.icon" class="h-4 w-4" />
            </div>
            <span class="flex flex-col gap-1">
              <span class="font-semibold">{{ step.label }}</span>
              <span v-if="step.description" class="text-xs text-muted">{{ step.description }}</span>
            </span>
          </span>
          <ChevronRightIcon class="h-4 w-4 text-muted transition group-hover:text-brand-500" />
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
    icon: Squares2X2Icon,
    description: '快速了解专题创建的核心步骤'
  },
  {
    label: '上传',
    to: { name: 'topic-create-upload' },
    icon: CloudArrowUpIcon,
    description: '导入原始文件，启动流程'
  },
  {
    label: '数据预处理',
    to: { name: 'topic-create-preprocess' },
    icon: FunnelIcon,
    description: '清洗并筛选关键字段'
  },
  {
    label: '入库',
    to: { name: 'topic-create-ingest' },
    icon: ArrowTrendingUpIcon,
    description: '提交数据写入业务数据库'
  },
  // 基本分析迁移到项目数据模块，此处保留前三个操作步骤
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
