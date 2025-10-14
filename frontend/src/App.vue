<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/50 to-slate-50 text-slate-900">
    <aside
      :class="[
        'group fixed inset-y-0 left-0 z-30 flex flex-col border-r border-slate-200/60 bg-white/95 shadow-xl backdrop-blur transition-[transform,box-shadow] duration-300',
        sidebarCollapsed ? 'w-64 lg:w-24' : 'w-64 lg:w-72'
      ]"
    >
      <button
        type="button"
        class="group/toggle absolute left-full top-1/2 hidden -translate-y-1/2 items-center gap-2 rounded-full border border-white/60 bg-white/90 px-3 py-2 text-sm font-medium text-indigo-600 shadow-lg shadow-indigo-500/10 ring-1 ring-slate-900/5 backdrop-blur transition hover:-translate-x-0.5 hover:bg-indigo-50 hover:text-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 lg:flex"
        :aria-expanded="!sidebarCollapsed"
        :aria-label="sidebarToggleLabel"
        @click="toggleSidebar"
      >
        <span
          class="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 transition group-hover/toggle:bg-indigo-600 group-hover/toggle:text-white"
        >
          <component
            :is="sidebarCollapsed ? ChevronDoubleRightIcon : ChevronDoubleLeftIcon"
            class="h-4 w-4"
          />
        </span>
        <span class="whitespace-nowrap">{{ sidebarCollapsed ? '展开侧边栏' : '收起侧边栏' }}</span>
      </button>

      <div class="flex items-center gap-3 px-6 pb-6 pt-8">
          <RouterLink
            v-if="!sidebarCollapsed"
            to="/"
            class="flex flex-col text-left"
          >
            <span class="text-lg font-semibold text-slate-900">Opinion System</span>
            <span class="text-sm text-slate-500">舆情监测系统</span>
          </RouterLink>
          <RouterLink
            v-else
            to="/"
            class="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-100 text-sm font-semibold text-indigo-600"
            aria-label="Opinion System"
            title="Opinion System"
          >
            <span aria-hidden="true">OS</span>
          </RouterLink>
        <button
          type="button"
          class="ml-auto inline-flex items-center gap-2 rounded-full border border-white/60 bg-white/90 px-3 py-2 text-sm font-medium text-indigo-600 shadow shadow-indigo-500/10 ring-1 ring-slate-900/5 backdrop-blur transition hover:bg-indigo-50 hover:text-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 lg:hidden"
          :aria-expanded="!sidebarCollapsed"
          :aria-label="sidebarToggleLabel"
          @click="toggleSidebar"
        >
          <span
            class="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 transition group-hover:bg-indigo-600 group-hover:text-white"
          >
            <component
              :is="sidebarCollapsed ? ChevronDoubleRightIcon : ChevronDoubleLeftIcon"
              class="h-5 w-5"
            />
          </span>
          <span>{{ sidebarCollapsed ? '展开侧边栏' : '收起侧边栏' }}</span>
        </button>
      </div>

      <div class="flex flex-1 flex-col gap-8 overflow-y-auto px-4 pb-10">
          <nav v-if="!sidebarCollapsed" class="space-y-8">
            <section
              v-for="group in navigationGroups"
              :key="group.label"
              class="space-y-4"
            >
              <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-400">{{ group.label }}</h2>
              <RouterLink
                v-for="link in group.links"
                :key="link.label"
                :to="link.to"
                class="flex items-start gap-3 rounded-2xl px-4 py-3 text-left transition hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                active-class="bg-indigo-100/80 text-indigo-700 shadow-inner"
              >
                <component :is="link.icon" class="mt-0.5 h-5 w-5 text-indigo-500" />
                <div class="flex flex-col">
                  <span class="font-medium">{{ link.label }}</span>
                  <span class="text-sm text-slate-500">{{ link.description }}</span>
                </div>
              </RouterLink>
            </section>
          </nav>
          <nav v-else class="flex flex-col items-center gap-4 py-4">
            <RouterLink
              v-for="link in navigationLinks"
              :key="link.label"
              :to="link.to"
              class="flex h-12 w-12 items-center justify-center rounded-2xl text-slate-500 transition hover:bg-indigo-50 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              :title="link.label"
              :aria-label="link.label"
              active-class="bg-indigo-100/70 text-indigo-600"
            >
              <component :is="link.icon" class="h-5 w-5" />
              <span class="sr-only">{{ link.label }}</span>
            </RouterLink>
          </nav>
      </div>
    </aside>

    <div class="flex min-h-screen">
      <div
        aria-hidden="true"
        :class="[
          'flex-shrink-0',
          sidebarCollapsed ? 'w-64 lg:w-24' : 'w-64 lg:w-72'
        ]"
      ></div>

      <div class="flex min-h-screen flex-1 flex-col">
        <header class="flex flex-col gap-6 border-b border-slate-200/70 bg-white/80 px-6 pb-6 pt-10 backdrop-blur">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <p class="text-sm font-semibold uppercase tracking-[0.3em] text-slate-400">舆情系统控制台</p>
            <div class="inline-flex items-center gap-2 rounded-full bg-indigo-50/80 px-3 py-1.5 text-sm text-indigo-700" role="status" aria-live="polite">
              <BriefcaseIcon class="h-4 w-4" aria-hidden="true" />
              <span class="font-medium">当前项目：</span>
              <span class="font-semibold">{{ activeProjectName || '未选择项目' }}</span>
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

const sidebarCollapsed = ref(false)

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const sidebarToggleLabel = computed(() =>
  sidebarCollapsed.value ? '展开侧边栏' : '收起侧边栏'
)
</script>
