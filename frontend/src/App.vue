<template>
  <div class="min-h-screen bg-base text-primary">
    <aside
      v-if="sidebarCollapsed"
      class="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:flex lg:w-20 lg:flex-col lg:border-r border-soft lg:bg-surface"
    >
      <div class="flex flex-col items-center gap-3 border-b border-soft px-3 py-4">
        <button
          type="button"
          class="flex h-10 w-10 items-center justify-center rounded-md border border-soft bg-surface text-secondary transition hover:border-brand-soft hover:text-primary focus-ring-accent"
          :aria-expanded="!sidebarCollapsed"
          :aria-label="sidebarToggleLabel"
          @click="toggleSidebar"
        >
          <ChevronDoubleRightIcon class="h-4 w-4" />
        </button>
      </div>
      <nav class="flex flex-1 flex-col items-center gap-4 py-6">
        <RouterLink
          v-for="link in navigationLinks"
          :key="link.label"
          :to="link.to"
          class="group relative flex h-11 w-11 items-center justify-center rounded-lg text-muted transition hover:bg-brand-soft hover:text-brand-600 focus-ring-accent"
          :title="link.label"
          :aria-label="link.label"
          active-class="bg-brand-soft text-brand-600"
        >
          <component :is="link.icon" class="h-5 w-5" />
          <span
            class="pointer-events-none absolute left-full top-1/2 z-10 ml-3 -translate-y-1/2 whitespace-nowrap rounded-md bg-brand-200 px-2 py-1 text-xs font-medium text-secondary opacity-0 shadow-lg transition duration-150 ease-out group-hover:translate-x-1 group-hover:opacity-100"
            aria-hidden="true"
          >
            {{ link.label }}
          </span>
        </RouterLink>
      </nav>
    </aside>

    <button
      v-if="sidebarCollapsed"
      type="button"
      class="fixed left-4 top-6 z-40 inline-flex items-center gap-2 rounded-md border border-soft bg-surface/90 px-3 py-2 text-xs font-medium text-secondary shadow-sm backdrop-blur transition hover:border-brand-soft hover:text-primary focus-ring-accent lg:hidden"
      :aria-expanded="!sidebarCollapsed"
      :aria-label="sidebarToggleLabel"
      @click="toggleSidebar"
    >
      <ChevronDoubleRightIcon class="h-4 w-4" />
      <span>展开侧边栏</span>
    </button>

    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 -translate-x-4"
      enter-to-class="opacity-100 translate-x-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 translate-x-0"
      leave-to-class="opacity-0 -translate-x-4"
    >
      <div
        v-if="!sidebarCollapsed"
        class="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-soft bg-surface shadow-lg lg:w-72 lg:shadow-sm"
      >
        <div class="flex items-center justify-between border-b border-soft px-5 py-4">
          <div class="flex flex-col h-10 justify-center overflow-hidden">
            <span class="text-lg font-semibold text-primary">Opinion System</span>
            <span class="text-sm text-secondary">舆情监测系统</span>
          </div>
          <button
            type="button"
            class="flex h-10 w-10 items-center justify-center rounded-md border border-soft bg-surface text-secondary transition hover:border-brand-soft hover:text-primary focus-ring-accent"
            :aria-label="sidebarToggleLabel"
            @click="toggleSidebar"
          >
            <ChevronDoubleLeftIcon class="h-4 w-4" />
            <span class="sr-only">收起侧边栏</span>
          </button>
        </div>

        <div class="flex flex-1 flex-col gap-8 overflow-y-auto px-5 pb-8 pt-6">
          <nav class="space-y-8">
            <section
              v-for="group in navigationGroups"
              :key="group.label"
              class="space-y-4"
            >
              <h2 class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ group.label }}</h2>
              <RouterLink
                v-for="link in group.links"
                :key="link.label"
                :to="link.to"
                class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-secondary transition hover:bg-brand-soft hover:text-primary focus-ring-accent"
                active-class="bg-brand-soft text-brand-600"
              >
                <component :is="link.icon" class="h-5 w-5 text-muted" />
                <div class="flex flex-col">
                  <span>{{ link.label }}</span>
                  <span class="text-xs font-normal text-muted">{{ link.description }}</span>
                </div>
              </RouterLink>
            </section>
          </nav>
        </div>
      </div>
    </Transition>

    <div
      v-if="!sidebarCollapsed"
      class="fixed inset-0 z-30 bg-slate-900/30 backdrop-blur-sm transition lg:hidden"
      @click="toggleSidebar"
      aria-hidden="true"
    ></div>

    <div class="flex min-h-screen">
      <div
        :class="[
          'flex min-h-screen flex-1 flex-col px-0',
          sidebarCollapsed ? 'lg:pl-20' : 'lg:pl-72'
        ]"
      >
        <header class="flex flex-col gap-4 border-b border-soft bg-surface px-6 py-6">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <p class="text-sm font-semibold uppercase tracking-[0.3em] text-muted">舆情监测系统</p>
            <div class="inline-flex items-center gap-2 rounded-md border border-soft bg-surface-muted px-3 py-1.5 text-sm text-secondary" role="status" aria-live="polite">
              <BriefcaseIcon class="h-4 w-4 text-muted" aria-hidden="true" />
              <span class="font-medium text-muted">当前项目：</span>
              <span class="font-semibold text-primary">{{ activeProjectName || '未选择项目' }}</span>
            </div>
          </div>
          <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ pageTitle || '欢迎使用 Opinion System' }}</h1>
        </header>
        <main class="flex-1 px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
          <RouterView />
        </main>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  BeakerIcon,
  BriefcaseIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  CircleStackIcon,
  Cog6ToothIcon,
  DocumentArrowUpIcon,
  Squares2X2Icon
} from '@heroicons/vue/24/outline'
import { useActiveProject } from './composables/useActiveProject'

const navigationGroups = [
  {
    label: '项目',
    links: [
      {
        label: '新建专题',
        description: '上传数据并完成初始化流程',
        to: { name: 'topic-create-overview' },
        icon: Squares2X2Icon
      },
      {
        label: '项目数据',
        description: '导入 Excel 并生成数据存档',
        to: { name: 'project-data' },
        icon: DocumentArrowUpIcon
      }
    ]
  },
  {
    label: '工具',
    links: [
      {
        label: '数据库',
        description: '查看库表与连接状态',
        to: { name: 'database' },
        icon: CircleStackIcon
      },
      {
        label: '测试工具',
        description: '未上线功能测试',
        to: { name: 'test' },
        icon: BeakerIcon
      },
      {
        label: '系统设置',
        description: '配置数据库与模型参数',
        to: { name: 'settings-databases' },
        icon: Cog6ToothIcon
      }
    ]
  }
]

const navigationLinks = navigationGroups.reduce(
  (links, group) => links.concat(group.links),
  []
)

const route = useRoute()

const pageTitle = computed(() => route.meta?.title ?? '')

const { activeProjectName } = useActiveProject()

const mediaQuery =
  typeof window !== 'undefined' ? window.matchMedia('(min-width: 1024px)') : null

const sidebarCollapsed = ref(mediaQuery ? !mediaQuery.matches : false)
const lastDesktopSidebarState = ref(mediaQuery?.matches ? sidebarCollapsed.value : false)
let cleanupMediaQueryListener

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value

  if (mediaQuery?.matches) {
    lastDesktopSidebarState.value = sidebarCollapsed.value
  }
}

const sidebarToggleLabel = computed(() =>
  sidebarCollapsed.value ? '展开侧边栏' : '收起侧边栏'
)

onMounted(() => {
  if (!mediaQuery) return

  if (mediaQuery.matches) {
    lastDesktopSidebarState.value = sidebarCollapsed.value
  }

  const listener = (event) => {
    if (event.matches) {
      sidebarCollapsed.value = lastDesktopSidebarState.value
      return
    }

    lastDesktopSidebarState.value = sidebarCollapsed.value
    sidebarCollapsed.value = true
  }

  if ('addEventListener' in mediaQuery) {
    mediaQuery.addEventListener('change', listener)
    cleanupMediaQueryListener = () => mediaQuery.removeEventListener('change', listener)
  } else {
    mediaQuery.addListener(listener)
    cleanupMediaQueryListener = () => mediaQuery.removeListener(listener)
  }
})

onBeforeUnmount(() => {
  cleanupMediaQueryListener?.()
})
</script>
