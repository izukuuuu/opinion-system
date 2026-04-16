<template>
  <AnalysisModuleLayout
    module-label="媒体识别与打标"
    :overview-route="{ name: 'analysis-media-tagging' }"
    :steps="steps"
    :current-breadcrumb="currentBreadcrumb"
    :is-overview="isOverview"
    :is-active-fn="isActive"
    :module-icon="MegaphoneIcon"
  >
    <RouterView />
  </AnalysisModuleLayout>
</template>

<script setup>
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import {
  ChartBarSquareIcon,
  MegaphoneIcon,
  PlayCircleIcon,
  Squares2X2Icon
} from '@heroicons/vue/24/outline'
import AnalysisModuleLayout from '../../../components/analysis/AnalysisModuleLayout.vue'

const steps = [
  {
    key: 'overview',
    label: '流程概览',
    to: { name: 'analysis-media-tagging' },
    icon: Squares2X2Icon,
    description: '了解媒体识别与打标流程'
  },
  {
    key: 'run',
    label: '运行识别',
    to: { name: 'analysis-media-tagging-run' },
    icon: PlayCircleIcon,
    description: '选择专题并启动识别任务'
  },
  {
    key: 'view',
    label: '查看结果',
    to: { name: 'analysis-media-tagging-view' },
    icon: ChartBarSquareIcon,
    description: '维护候选媒体与共享字典'
  }
]

const route = useRoute()

const isOverview = computed(() => route.name === 'analysis-media-tagging')
const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')

const isActive = (itemOrTarget) => {
  const target = itemOrTarget?.to ?? itemOrTarget
  if (!target?.name) return false
  if (route.name === target.name) return true
  if (Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === target.name)
  }
  return false
}
</script>
