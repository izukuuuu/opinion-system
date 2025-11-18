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
      <CollapsibleSidebar :items="steps" :is-active-fn="isActive" />
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
  AdjustmentsHorizontalIcon,
  ChevronRightIcon,
  Squares2X2Icon,
  ChevronLeftIcon
} from '@heroicons/vue/24/outline'
import CollapsibleSidebar from '../../components/navigation/CollapsibleSidebar.vue'

const steps = [
  {
    key: 'overview',
    label: '流程概览',
    to: { name: 'topic-create-overview' },
    icon: Squares2X2Icon,
    description: '快速了解'
  },
  {
    key: 'upload',
    label: '上传',
    to: { name: 'topic-create-upload' },
    icon: CloudArrowUpIcon,
    description: '导入原始数据文件'
  },
  {
    key: 'preprocess',
    label: '数据预处理',
    to: { name: 'topic-create-preprocess' },
    icon: FunnelIcon,
    description: '数据合并与数据清洗'
  },
  {
    key: 'filter',
    label: '筛选',
    to: { name: 'topic-create-filter' },
    icon: AdjustmentsHorizontalIcon,
    description: 'AI 剔除无关内容'
  },
  {
    key: 'ingest',
    label: '入库',
    to: { name: 'topic-create-ingest' },
    icon: ArrowTrendingUpIcon,
    description: '写入远程舆情数据库'
  },
  // 基本分析迁移到项目数据模块，此处保留核心四个操作步骤
]

const route = useRoute()

const isActive = (itemOrTarget) => {
  const target = itemOrTarget?.to ?? itemOrTarget
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
