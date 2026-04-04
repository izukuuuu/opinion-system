<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <nav class="flex items-center gap-2">
        <RouterLink
          :to="{ name: 'processing-deduplicate' }"
          class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition focus-ring-accent"
          :class="isRoot ? 'bg-brand-soft text-brand-600' : 'text-secondary hover:bg-brand-soft hover:text-brand-600'"
        >
          <Cog8ToothIcon class="h-4 w-4" />
          <span>数据处理</span>
        </RouterLink>
        <template v-if="!isRoot">
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
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  ChevronRightIcon,
  Cog8ToothIcon,
  FunnelIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'
import CollapsibleSidebar from '../../components/navigation/CollapsibleSidebar.vue'

const route = useRoute()

const steps = [
  {
    key: 'deduplicate',
    label: '数据库去重',
    to: { name: 'processing-deduplicate' },
    icon: SparklesIcon,
    description: '清理重复内容'
  },
  {
    key: 'postclean',
    label: '后清洗',
    to: { name: 'processing-postclean' },
    icon: FunnelIcon,
    description: '排除词与发布者黑名单'
  }
]

const isActive = (itemOrTarget) => {
  const target = itemOrTarget?.to ?? itemOrTarget
  if (!target?.name) return false
  if (route.name === target.name) return true
  if (Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === target.name)
  }
  return false
}

const isRoot = computed(() => route.name === 'processing-deduplicate')
const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')
</script>
