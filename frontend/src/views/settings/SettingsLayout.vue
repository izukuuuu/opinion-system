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

    <div class="flex flex-col gap-6 pb-20 lg:flex-row lg:items-start lg:pb-0">
      <CollapsibleSidebar
        :items="navigationItems"
        :is-active-fn="isNavItemActive"
      />
      <div class="min-w-0 flex-1">
        <RouterView />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import {
  ChevronRightIcon,
  Cog6ToothIcon,
  CircleStackIcon,
  CpuChipIcon,
  ArrowDownTrayIcon,
  ServerStackIcon,
  SwatchIcon,
  DocumentMagnifyingGlassIcon,
  BeakerIcon,
  HashtagIcon
} from '@heroicons/vue/24/outline'
import CollapsibleSidebar from '../../components/navigation/CollapsibleSidebar.vue'

const navigationItems = [
  {
    key: 'settings-databases',
    label: '数据库连接',
    to: { name: 'settings-databases' },
    icon: CircleStackIcon
  },
  {
    key: 'settings-ai',
    label: 'AI 服务配置',
    to: { name: 'settings-ai' },
    icon: CpuChipIcon
  },
  {
    key: 'settings-rag',
    label: 'RAG 配置',
    to: { name: 'settings-rag' },
    icon: DocumentMagnifyingGlassIcon
  },
  {
    key: 'settings-bertopic',
    label: 'BERTopic 配置',
    to: { name: 'settings-bertopic' },
    icon: HashtagIcon
  },
  {
    key: 'settings-backend',
    label: '后端地址',
    to: { name: 'settings-backend' },
    icon: ServerStackIcon
  },
  {
    key: 'settings-archives',
    label: '存档导入导出',
    to: { name: 'settings-archives' },
    icon: ArrowDownTrayIcon
  },
  {
    key: 'settings-theme',
    label: '主题颜色',
    to: { name: 'settings-theme' },
    icon: SwatchIcon
  },
  {
    key: 'settings-experimental',
    label: '实验性功能',
    to: { name: 'settings-experimental' },
    icon: BeakerIcon
  }
]

const route = useRoute()
const router = useRouter()

const currentBreadcrumb = computed(() => route.meta?.breadcrumb || route.meta?.title || '')
const isNavItemActive = (item) => {
  const target = item?.to
  if (!target?.name) return false
  if (route.name === target.name) return true
  if (Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === target.name)
  }
  return false
}

onMounted(() => {
  if (route.name === 'settings' && navigationItems.length > 0) {
    router.replace(navigationItems[0].to)
  }
})
</script>
