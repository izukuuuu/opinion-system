<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <nav class="flex items-center gap-2" aria-label="面包屑">
        <RouterLink
          :to="{ name: 'test' }"
          class="inline-flex items-center gap-1 rounded-full px-3 py-1 transition focus-ring-accent hover:bg-brand-soft hover:text-brand-600"
        >
          <Squares2X2Icon class="h-4 w-4" />
          <span>工具面板</span>
        </RouterLink>
        <ChevronRightIcon class="h-4 w-4 text-muted" />
        <span class="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-brand-600">
          {{ activePanel.label }}
        </span>
      </nav>
      <span class="inline-flex items-center gap-2 rounded-full border border-soft px-3 py-1 text-xs font-medium text-muted">
        <SparklesIcon class="h-4 w-4" />
        多场景调试助手
      </span>
    </header>

    <div class="flex flex-col gap-6 lg:flex-row lg:items-start">
      <aside class="flex w-full shrink-0 flex-col gap-3 lg:w-56">
        <button
          v-for="panel in panels"
          :key="panel.id"
          type="button"
          class="inline-flex items-center justify-between rounded-2xl border border-soft px-4 py-3 text-sm font-semibold transition focus-ring-accent"
          :class="panel.id === activeTab
            ? 'border-brand-soft bg-brand-soft text-brand-600 shadow-sm'
            : 'bg-surface text-secondary hover:border-brand-soft hover:bg-accent-faint hover:text-brand-600'"
          @click="activate(panel.id)"
        >
          <span class="flex items-center gap-2">
            <component :is="panel.icon" class="h-4 w-4" />
            <span>{{ panel.label }}</span>
          </span>
          <ChevronRightIcon class="h-4 w-4 text-muted" />
        </button>
      </aside>

      <div class="flex-1 min-w-0">
        <section class="test-panel">
          <header class="test-panel__header">
            <component :is="activePanel.icon" class="test-panel__icon" />
            <div>
              <h1>{{ activePanel.heading }}</h1>
              <p>{{ activePanel.description }}</p>
            </div>
          </header>
          <div class="test-panel__body">
            <component :is="activeComponent" />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  BeakerIcon,
  ChartBarIcon,
  ChevronRightIcon,
  SparklesIcon,
  Squares2X2Icon
} from '@heroicons/vue/24/outline'
import ApiWorkbench from '../components/ApiWorkbench.vue'
import AnalyzeWorkbench from '../components/AnalyzeWorkbench.vue'

const panels = [
  {
    id: 'api',
    label: '接口调试',
    heading: '接口调试工作区',
    description: '在此快速验证 API，方便排查管线、查询及分析任务。',
    icon: BeakerIcon,
    component: ApiWorkbench
  },
  {
    id: 'analyze',
    label: 'Analyze 分析',
    heading: 'Analyze 分析台',
    description: '组合查询条件，调用 Analyze 服务完成快速洞察与分析。',
    icon: ChartBarIcon,
    component: AnalyzeWorkbench
  }
]

const activeTab = ref('api')

const activate = (id) => {
  activeTab.value = id
}

const activePanel = computed(() => panels.find((panel) => panel.id === activeTab.value) || panels[0])

const activeComponent = computed(() => activePanel.value.component)
</script>

<style scoped>
.test-panel {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding: 2.5rem;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 25px 60px -30px rgba(15, 23, 42, 0.35);
  width: 100%;
  box-sizing: border-box;
}

.test-panel__header {
  display: flex;
  gap: 1.5rem;
  align-items: center;
}

.test-panel__icon {
  width: 3rem;
  height: 3rem;
  color: var(--color-brand-600-hex);
}

.test-panel__header h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.test-panel__header p {
  margin: 0.35rem 0 0;
  color: var(--color-text-secondary);
  max-width: 640px;
}

.test-panel__body {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

@media (max-width: 1024px) {
  .test-panel {
    padding: 2rem;
  }
}

@media (max-width: 640px) {
  .test-panel {
    padding: 1.75rem;
    border-radius: 22px;
  }

  .test-panel__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .test-panel__icon {
    width: 2.5rem;
    height: 2.5rem;
  }
}
</style>
