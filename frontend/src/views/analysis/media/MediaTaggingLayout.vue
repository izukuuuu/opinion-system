<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <nav class="flex items-center gap-2">
        <RouterLink
          :to="{ name: 'analysis-media-tagging' }"
          class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition focus-ring-accent"
          :class="isRoot ? 'bg-brand-soft text-brand-600' : 'text-secondary hover:bg-brand-soft hover:text-brand-600'"
        >
          <MegaphoneIcon class="h-4 w-4" />
          <span>媒体打标</span>
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
import { ChevronRightIcon, MegaphoneIcon, TagIcon } from '@heroicons/vue/24/outline'
import CollapsibleSidebar from '../../../components/navigation/CollapsibleSidebar.vue'

const route = useRoute()

const steps = [
  {
    key: 'media-tagging',
    label: '媒体打标',
    to: { name: 'analysis-media-tagging' },
    icon: TagIcon,
    description: '识别与标注媒体来源'
  }
]

const isActive = (item) => {
  const target = item?.to ?? item
  if (!target?.name) return false
  if (route.name === target.name) return true
  if (Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === target.name)
  }
  return false
}

const isRoot = computed(() => route.name === 'analysis-media-tagging')
const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')
</script>
