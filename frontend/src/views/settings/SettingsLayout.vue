<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <nav class="flex items-center gap-2">
        <span class="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-brand-600">
          <Cog6ToothIcon class="h-4 w-4" />
          <span>系统设置</span>
        </span>
        <template v-if="currentBreadcrumb">
          <ChevronRightIcon class="h-4 w-4 text-muted" />
          <span class="text-secondary">{{ currentBreadcrumb }}</span>
        </template>
      </nav>
    </header>

    <div class="flex flex-col gap-6 lg:flex-row lg:items-start">
      <aside class="flex w-full shrink-0 flex-col gap-3 lg:w-56">
        <RouterLink
          v-for="item in navigationItems"
          :key="item.label"
          :to="item.to"
          class="inline-flex items-center justify-between rounded-2xl border border-soft px-4 py-3 text-sm font-semibold transition focus-ring-accent"
          :class="[
            isActive(item.to)
              ? 'border-brand-soft bg-brand-soft text-brand-600 shadow-sm'
              : 'bg-surface text-secondary hover:border-brand-soft hover:bg-accent-faint hover:text-brand-600'
          ]"
        >
          <span class="flex items-center gap-2">
            <component :is="item.icon" class="h-4 w-4" />
            <span>{{ item.label }}</span>
          </span>
          <ChevronRightIcon class="h-4 w-4 text-muted" />
        </RouterLink>
      </aside>
      <div class="min-w-0 flex-1">
        <RouterView />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  ChevronRightIcon,
  Cog6ToothIcon,
  CircleStackIcon,
  CpuChipIcon
} from '@heroicons/vue/24/outline'

const navigationItems = [
  {
    label: '数据库连接',
    to: { name: 'settings-databases' },
    icon: CircleStackIcon
  },
  {
    label: 'AI 服务配置',
    to: { name: 'settings-ai' },
    icon: CpuChipIcon
  }
]

const route = useRoute()
const router = useRouter()

const isActive = (target) => {
  if (!target?.name) return false
  if (route.name === target.name) return true
  if (Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === target.name)
  }
  return false
}

const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')

onMounted(() => {
  if (route.name === 'settings' && navigationItems.length > 0) {
    router.replace(navigationItems[0].to)
  }
})
</script>
