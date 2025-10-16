<template>
  <div class="min-h-screen bg-slate-100 text-slate-900">
    <aside
      v-if="sidebarCollapsed"
      class="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:flex lg:w-20 lg:flex-col lg:border-r lg:border-slate-200 lg:bg-white"
    >
      <div class="flex flex-col items-center gap-3 border-b border-slate-200 px-3 py-4">
        <button
          type="button"
          class="flex h-10 w-10 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
          :aria-expanded="!sidebarCollapsed"
          :aria-label="sidebarToggleLabel"
          @click="toggleSidebar"
        >
          <ChevronDoubleRightIcon class="h-4 w-4" />
        </button>
        <RouterLink
          to="/"
          class="flex h-12 w-12 items-center justify-center rounded-lg bg-slate-100 text-sm font-semibold text-slate-600"
          aria-label="Opinion System"
        >
          <span aria-hidden="true">OS</span>
        </RouterLink>
      </div>
      <nav class="flex flex-1 flex-col items-center gap-4 py-6">
        <RouterLink
          v-for="link in navigationLinks"
          :key="link.label"
          :to="link.to"
          class="flex h-11 w-11 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
          :title="link.label"
          :aria-label="link.label"
          active-class="bg-slate-100 text-indigo-600"
        >
          <component :is="link.icon" class="h-5 w-5" />
        </RouterLink>
      </nav>
    </aside>

    <button
      v-if="sidebarCollapsed"
      type="button"
      class="fixed left-4 top-6 z-40 inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white/90 px-3 py-2 text-xs font-medium text-slate-600 shadow-sm backdrop-blur transition hover:border-slate-300 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 lg:hidden"
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
        class="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-white shadow-lg lg:w-72 lg:shadow-sm"
      >
        <div class="flex h-16 items-center justify-between border-b border-slate-200 px-5">
          <div class="flex flex-col">
            <span class="text-lg font-semibold text-slate-900">Opinion System</span>
            <span class="text-sm text-slate-500">舆情监测系统</span>
          </div>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-md border border-transparent bg-slate-100 p-2 text-slate-500 transition hover:bg-slate-200 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
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
              <h2 class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{{ group.label }}</h2>
              <RouterLink
                v-for="link in group.links"
                :key="link.label"
                :to="link.to"
                class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
                active-class="bg-slate-100 text-indigo-600"
              >
                <component :is="link.icon" class="h-5 w-5 text-slate-400" />
                <div class="flex flex-col">
                  <span>{{ link.label }}</span>
                  <span class="text-xs font-normal text-slate-500">{{ link.description }}</span>
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
          'flex min-h-screen flex-1 flex-col px-4 sm:px-6 lg:px-10',
          sidebarCollapsed ? 'lg:pl-20' : 'lg:pl-72'
        ]"
      >
        <header class="flex flex-col gap-4 border-b border-slate-200 bg-white px-6 py-6">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <p class="text-sm font-semibold uppercase tracking-[0.3em] text-slate-400">舆情系统控制台</p>
            <div class="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-600" role="status" aria-live="polite">
              <BriefcaseIcon class="h-4 w-4 text-slate-500" aria-hidden="true" />
              <span class="font-medium text-slate-500">当前项目：</span>
              <span class="font-semibold text-slate-800">{{ activeProjectName || '未选择项目' }}</span>
            </div>
          </div>
          <h1 class="text-2xl font-semibold text-slate-900 md:text-3xl">{{ pageTitle || '欢迎使用 Opinion System' }}</h1>
        </header>
        <main class="flex-1 px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
          <RouterView />
        </main>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
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
        label: '项目面板',
        description: '查看项目记录',
        to: { name: 'projects' },
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
        label: '测试页面',
        description: 'API调用测试',
        to: { name: 'test' },
        icon: BeakerIcon
      },
      {
        label: '系统设置',
        description: '配置数据库与模型参数',
        to: { name: 'settings' },
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

const initialCollapsed =
  typeof window !== 'undefined' ? !window.matchMedia('(min-width: 1024px)').matches : false

const sidebarCollapsed = ref(initialCollapsed)

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const sidebarToggleLabel = computed(() =>
  sidebarCollapsed.value ? '展开侧边栏' : '收起侧边栏'
)
</script>
