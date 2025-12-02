<template>
  <div class="flex w-full flex-col gap-8 lg:flex-row lg:items-start">
    <CollapsibleSidebar
      :items="sidebarItems"
      :active-key="activeSidebarKey"
    />
    <main class="flex-1">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { CloudArrowDownIcon, ServerStackIcon } from '@heroicons/vue/24/outline'
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import CollapsibleSidebar from '../../components/navigation/CollapsibleSidebar.vue'

const route = useRoute()

const sidebarItems = [
  {
    key: 'project-data',
    label: '本地数据管理',
    description: '本地项目与数据集信息',
    icon: ServerStackIcon,
    to: { name: 'project-data' },
  },
  {
    key: 'project-data-remote-cache',
    label: '远程数据缓存',
    description: '缓存用于分析的存档文件',
    icon: CloudArrowDownIcon,
    to: { name: 'project-data-remote-cache' },
  },
]

const activeSidebarKey = computed(() => {
  const name = typeof route.name === 'string' ? route.name : ''
  const matched = sidebarItems.find((item) => item.key === name)
  return matched?.key ?? 'project-data'
})
</script>
