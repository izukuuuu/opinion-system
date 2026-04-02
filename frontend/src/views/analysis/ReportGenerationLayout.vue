<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <nav class="flex items-center gap-2">
        <span class="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-brand-600">
          <DocumentTextIcon class="h-4 w-4" />
          <span>报告模块</span>
        </span>
        <template v-if="currentBreadcrumb">
          <ChevronRightIcon class="h-4 w-4 text-muted" />
          <span class="text-secondary">{{ currentBreadcrumb }}</span>
        </template>
      </nav>
    </header>

    <div class="flex flex-col gap-6 pb-20 lg:flex-row lg:items-start lg:pb-0">
      <CollapsibleSidebar :items="steps" :is-active-fn="isActive" />
      <div class="min-w-0 flex-1">
        <RouterView />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import {
  ChartBarSquareIcon,
  ChevronRightIcon,
  DocumentTextIcon,
  PlayCircleIcon
} from '@heroicons/vue/24/outline'
import CollapsibleSidebar from '../../components/navigation/CollapsibleSidebar.vue'

const steps = [
  {
    key: 'run',
    label: '运行报告',
    to: { name: 'report-generation-run' },
    icon: PlayCircleIcon,
    description: '选择专题并生成报告'
  },
  {
    key: 'view',
    label: '查看报告',
    to: { name: 'report-generation-view' },
    icon: ChartBarSquareIcon,
    description: '读取结果并导出报告'
  }
]

const route = useRoute()

const isActive = (itemOrTarget) => {
  const target = itemOrTarget?.to ?? itemOrTarget
  if (!target?.name) return false
  if (route.name === target.name) return true
  if (Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === target.name)
  }
  return false
}

const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')
</script>
