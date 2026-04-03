<template>
  <AnalysisModuleLayout
    module-label="基础分析"
    :overview-route="{ name: 'project-data-analysis' }"
    :steps="steps"
    :current-breadcrumb="currentBreadcrumb"
    :is-overview="isOverview"
    :is-active-fn="isActive"
  >
    <RouterView />
  </AnalysisModuleLayout>
</template>

<script setup>
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import {
  Squares2X2Icon,
  ChartBarSquareIcon,
  PlayCircleIcon
} from '@heroicons/vue/24/outline'
import AnalysisModuleLayout from '../../../components/analysis/AnalysisModuleLayout.vue'

const steps = [
  {
    key: 'overview',
    label: '流程概览',
    to: { name: 'project-data-analysis' },
    icon: Squares2X2Icon,
    description: '了解基础分析步骤'
  },
  {
    key: 'run',
    label: '运行分析',
    to: { name: 'project-data-analysis-run' },
    icon: PlayCircleIcon,
    description: '拉取数据并执行分析'
  },
  {
    key: 'view',
    label: '查看分析',
    to: { name: 'project-data-analysis-view' },
    icon: ChartBarSquareIcon,
    description: '查看已生成结果'
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

const isOverview = computed(() => route.name === 'project-data-analysis')
const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')
</script>
