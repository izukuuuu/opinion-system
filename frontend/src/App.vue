<template>
  <div class="min-h-screen bg-base text-primary">
    <div
      v-if="isLandingLayout"
      class="flex min-h-screen flex-col"
    >
      <header class="flex items-center justify-between border-b border-soft bg-surface/90 px-6 py-4 backdrop-blur-sm sm:px-10">
        <div class="flex items-center gap-3">
          <span class="text-lg font-semibold text-primary">Opinion System</span>
          <span class="hidden text-sm text-secondary sm:inline">舆情监测系统</span>
        </div>
        <RouterLink
          :to="backendEntryRoute"
          class="inline-flex items-center justify-center rounded-full bg-white px-6 py-2 text-sm font-semibold text-primary shadow-sm transition hover:bg-primary/90 hover:text-gray-600 focus-ring-accent"
        >
          进入后台
        </RouterLink>
      </header>
      <main class="flex-1">
        <RouterView />
      </main>
    </div>

    <template v-else>
    <aside
      v-if="sidebarCollapsed"
      class="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:flex lg:w-20 lg:flex-col lg:border-r border-soft lg:bg-white"
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

    <header
      class="fixed inset-x-0 top-0 z-20 border-b border-soft bg-white/70 px-4 py-3 shadow-sm backdrop-blur lg:hidden"
    >
      <div class="flex items-center gap-3">
        <button
          type="button"
          class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-soft bg-surface text-secondary shadow-sm transition hover:border-brand-soft hover:text-primary focus-ring-accent"
          :aria-expanded="!sidebarCollapsed"
          :aria-label="sidebarToggleLabel"
          @click="toggleSidebar"
        >
          <ChevronDoubleRightIcon class="h-5 w-5" />
        </button>
        <div class="flex min-w-0 flex-1 flex-col">
          <p class="text-xs font-semibold uppercase tracking-[0.3em] text-muted">Opinion System</p>
          <p class="truncate text-base font-semibold text-primary">{{ pageTitle || '欢迎使用 Opinion System' }}</p>
        </div>
        <ActiveProjectSwitcher
          v-if="showGlobalProjectSwitcher"
          class="ml-auto shrink-0"
          :show-label="false"
        />
      </div>
    </header>

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
        class="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-soft bg-white shadow-lg lg:w-72 lg:shadow-sm"
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

        <div
          ref="sidebarScrollEl"
          :class="[
            'sidebar-scroll flex flex-1 flex-col gap-8 overflow-y-auto px-5 pb-8 pt-6',
            { 'sidebar-scroll--hidden': !isSidebarScrollbarVisible }
          ]"
        >
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
                custom
                v-slot="{ href, navigate }"
              >
                <a
                  :href="href"
                  @click="navigate"
                  class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-secondary transition hover:bg-brand-soft hover:text-primary focus-ring-accent"
                  :class="isGlobalLinkActive(link) ? 'bg-brand-soft text-brand-600' : ''"
                >
                  <component :is="link.icon" class="h-5 w-5 text-muted" />
                  <div class="flex flex-col">
                    <span>{{ link.label }}</span>
                    <span class="text-xs font-normal text-muted">{{ link.description }}</span>
                  </div>
                </a>
              </RouterLink>
            </section>
          </nav>
        </div>
      </div>
    </Transition>

    <Transition
      enter-active-class="transition-opacity duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="!sidebarCollapsed"
        class="fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-sm lg:hidden"
        @click="toggleSidebar"
        aria-hidden="true"
      ></div>
    </Transition>

    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 -translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-2"
    >
      <header
        v-if="showCompactHeader"
        class="fixed inset-x-0 top-0 z-20 hidden items-center gap-3 border-b border-soft px-6 py-3 backdrop-blur lg:flex"
        :style="[compactHeaderStyle, compactHeaderOffsetStyle]"
      >
        <div class="flex min-w-0 items-center gap-2">
          <p class="shrink-0 text-xs font-semibold uppercase tracking-[0.3em] text-muted">Opinion System</p>
          <p class="truncate text-base font-semibold text-primary">{{ pageTitle || '欢迎使用 Opinion System' }}</p>
        </div>
      </header>
    </Transition>

    <div class="flex min-h-screen">
      <div
          :class="[
          'flex min-h-screen flex-1 flex-col px-0 pt-[4rem] lg:pt-0',
          sidebarCollapsed ? 'lg:pl-20' : 'lg:pl-72'
        ]"
      >
        <header
          ref="mainHeaderEl"
          class="flex flex-col gap-4 border-b border-soft bg-surface px-6 py-6"
        >
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <p class="text-sm font-semibold uppercase tracking-[0.3em] text-muted">舆情监测系统</p>
            <ActiveProjectSwitcher v-if="showGlobalProjectSwitcher" class="hidden lg:inline-flex" />
          </div>
          <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ pageTitle || '欢迎使用 Opinion System' }}</h1>
        </header>
        <main class="flex-1 px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
          <RouterView />
        </main>
      </div>
    </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  BeakerIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  CircleStackIcon,
  HomeIcon,
  CloudArrowDownIcon,
  Cog6ToothIcon,
  DocumentArrowUpIcon,
  DocumentTextIcon,
  ArrowsRightLeftIcon,
  PresentationChartLineIcon,
  Squares2X2Icon,
  TableCellsIcon,
  MagnifyingGlassCircleIcon,
  SparklesIcon,
  ChartBarIcon
} from '@heroicons/vue/24/outline'
import ActiveProjectSwitcher from './components/ActiveProjectSwitcher.vue'
import './assets/colors.css'

const isClient = typeof window !== 'undefined'
const SIDEBAR_SCROLLBAR_HIDE_DELAY = 2000
const sidebarScrollEl = ref(null)
const isSidebarScrollbarVisible = ref(true)
let sidebarScrollbarHideTimer = null
let cleanupSidebarScrollListeners

const navigationGroups = [
  {
    label: '主页',
    links: [
      {
        label: '系统简介',
        description: 'OpinionSystem 平台概览',
        to: { name: 'home' },
        icon: HomeIcon
      }
    ]
  },
  {
    label: '概览',
    links: [
      {
        label: '数据集',
        description: '远程数据库已上传数据',
        to: { name: 'overview-datasets' },
        icon: TableCellsIcon
      }
    ]
  },
  {
    label: '数据获取',
    links: [
      {
        label: '平台数据获取',
        description: '通过 API 获得公开平台数据',
        to: { name: 'data-acquisition-platform' },
        icon: CloudArrowDownIcon
      }
    ]
  },
  {
    label: '项目管理',
    links: [
      {
        label: '新建专题',
        description: '上传数据并完成初始化流程',
        to: { name: 'topic-create-overview' },
        match: [
          'topic-create-overview',
          'topic-create-upload',
          'topic-create-preprocess',
          'topic-create-filter',
          'topic-create-ingest'
        ],
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
    label: '舆情特征',
    links: [
      {
        label: '基础分析',
        description: '查看专题基础指标',
        to: { name: 'project-data-analysis' },
        match: [
          'project-data-analysis',
          'project-data-analysis-run',
          'project-data-analysis-view'
        ],
        icon: PresentationChartLineIcon
      },
      {
        label: '内容分析',
        description: '配置内容编码提示词',
        to: { name: 'content-analysis-prompt' },
        icon: DocumentTextIcon
      },
      {
        label: '智能解读',
        description: '舆情特征智能解读',
        to: { name: 'data-interpretation-engine' },
        icon: SparklesIcon
      }
    ]
  },
  {
    label: '深度分析',
    links: [
      {
        label: '舆论流体力学',
        description: '舆情发展趋势洞察',
        to: { name: 'deep-analysis-fluid-dynamics' },
        icon: ChartBarIcon
      }
    ]
  },
  {
    label: '数据检索',
    links: [
      {
        label: 'TagRAG 检索',
        description: '基于标签的智能问答',
        to: { name: 'data-retrieval-tagrag' },
        icon: MagnifyingGlassCircleIcon
      },
      {
        label: 'RouterRAG 检索',
        description: '多模型协同智能问答',
        to: { name: 'data-retrieval-routerrag' },
        icon: ArrowsRightLeftIcon
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
        label: '系统设置',
        description: '配置数据库与模型参数',
        to: { name: 'settings-databases' },
        match: ['settings', 'settings-backend', 'settings-databases', 'settings-ai', 'settings-theme', 'settings-archives'],
        icon: Cog6ToothIcon
      }
    ]
  }
]

const navigationLinks = navigationGroups.reduce(
  (links, group) => links.concat(group.links),
  []
)

const showGlobalProjectSwitcher = false

const route = useRoute()
const isLandingLayout = computed(() => route.meta?.layout === 'landing')
const backendEntryRoute = { name: 'overview-datasets' }

const pageTitle = computed(() => route.meta?.title ?? '')

const isGlobalLinkActive = (link) => {
  if (Array.isArray(link.match) && link.match.length) {
    return link.match.includes(route.name)
  }
  if (link.to?.name && route.name === link.to.name) {
    return true
  }
  if (link.to?.name && Array.isArray(route.matched)) {
    return route.matched.some((record) => record.name === link.to.name)
  }
  return false
}

const mediaQuery =
  typeof window !== 'undefined' ? window.matchMedia('(min-width: 1024px)') : null

const sidebarCollapsed = ref(mediaQuery ? !mediaQuery.matches : false)
const lastDesktopSidebarState = ref(mediaQuery?.matches ? sidebarCollapsed.value : false)
const isDesktop = ref(mediaQuery ? mediaQuery.matches : false)
let cleanupMediaQueryListener
let cleanupHeaderObserver
const mainHeaderEl = ref(null)
const isMainHeaderVisible = ref(true)

const showCompactHeader = computed(
  () => isDesktop.value && !isLandingLayout.value && !isMainHeaderVisible.value
)

const compactHeaderStyle = computed(() => ({
  background: 'rgba(255, 255, 255, 0.6)'
}))

const compactHeaderOffsetStyle = computed(() => {
  if (!isDesktop.value) return {}
  const left = sidebarCollapsed.value ? '5rem' : '18rem'
  return { left, right: '0' }
})

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value

  if (mediaQuery?.matches) {
    lastDesktopSidebarState.value = sidebarCollapsed.value
  }
}

const sidebarToggleLabel = computed(() =>
  sidebarCollapsed.value ? '展开侧边栏' : '收起侧边栏'
)

const clearSidebarScrollbarTimer = () => {
  if (!isClient || !sidebarScrollbarHideTimer) return
  window.clearTimeout(sidebarScrollbarHideTimer)
  sidebarScrollbarHideTimer = null
}

const scheduleSidebarScrollbarHide = () => {
  if (!isClient) return
  clearSidebarScrollbarTimer()
  sidebarScrollbarHideTimer = window.setTimeout(() => {
    isSidebarScrollbarVisible.value = false
  }, SIDEBAR_SCROLLBAR_HIDE_DELAY)
}

const handleSidebarActivity = () => {
  if (!isClient) return
  isSidebarScrollbarVisible.value = true
  scheduleSidebarScrollbarHide()
}

const detachSidebarScrollListeners = () => {
  if (typeof cleanupSidebarScrollListeners === 'function') {
    cleanupSidebarScrollListeners()
    cleanupSidebarScrollListeners = undefined
  }
}

const attachSidebarScrollListeners = (element) => {
  if (!element) return
  const passiveEvents = ['scroll', 'wheel', 'touchstart']
  const activeEvents = ['pointermove', 'mouseenter']

  passiveEvents.forEach((eventName) => {
    element.addEventListener(eventName, handleSidebarActivity, { passive: true })
  })
  activeEvents.forEach((eventName) => {
    element.addEventListener(eventName, handleSidebarActivity)
  })

  cleanupSidebarScrollListeners = () => {
    passiveEvents.forEach((eventName) => {
      element.removeEventListener(eventName, handleSidebarActivity)
    })
    activeEvents.forEach((eventName) => {
      element.removeEventListener(eventName, handleSidebarActivity)
    })
  }
}

watch(
  () => sidebarScrollEl.value,
  (element, previous) => {
    if (previous) {
      detachSidebarScrollListeners()
    }
    if (element && isClient) {
      attachSidebarScrollListeners(element)
      handleSidebarActivity()
    }
  }
)

watch(
  () => sidebarCollapsed.value,
  (collapsed) => {
    if (collapsed) {
      clearSidebarScrollbarTimer()
      isSidebarScrollbarVisible.value = false
      return
    }
    if (sidebarScrollEl.value) {
      handleSidebarActivity()
    }
  }
)

watch(
  () => mainHeaderEl.value,
  (element) => {
    if (cleanupHeaderObserver) {
      cleanupHeaderObserver()
      cleanupHeaderObserver = undefined
    }

    if (!element || !isClient || !('IntersectionObserver' in window)) {
      isMainHeaderVisible.value = true
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        isMainHeaderVisible.value = entry.isIntersecting
      },
      { threshold: [0, 0.01] }
    )
    observer.observe(element)
    cleanupHeaderObserver = () => observer.disconnect()
  }
)

watch(
  () => isDesktop.value,
  (desktop) => {
    if (!desktop) {
      isMainHeaderVisible.value = true
    }
  }
)

onMounted(() => {
  if (!mediaQuery) return

  isDesktop.value = mediaQuery.matches

  if (mediaQuery.matches) {
    lastDesktopSidebarState.value = sidebarCollapsed.value
  }

  const listener = (event) => {
    isDesktop.value = event.matches

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
  clearSidebarScrollbarTimer()
  detachSidebarScrollListeners()
  cleanupHeaderObserver?.()
})
</script>
