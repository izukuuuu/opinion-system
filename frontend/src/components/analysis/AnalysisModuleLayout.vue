<template>
  <div class="analysis-shell">
    <header class="analysis-shell__header">
      <nav class="analysis-shell__breadcrumb" aria-label="分析流程导航">
        <span class="analysis-shell__badge">
          <component :is="moduleIcon" class="h-4 w-4" />
          <span>{{ moduleLabel }}</span>
        </span>
        <template v-if="currentBreadcrumb">
          <ChevronRightIcon class="h-4 w-4 text-muted" />
          <span class="text-secondary">{{ currentBreadcrumb }}</span>
        </template>
      </nav>

      <RouterLink
        v-if="showBackToOverview && !isOverview"
        :to="overviewRoute"
        class="analysis-shell__back focus-ring-accent"
      >
        <ChevronLeftIcon class="h-4 w-4" />
        <span>返回开始页</span>
      </RouterLink>
    </header>

    <div class="analysis-shell__body">
      <CollapsibleSidebar :items="steps" :is-active-fn="isActiveFn" />
      <div class="analysis-content">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PresentationChartLineIcon
} from '@heroicons/vue/24/outline'
import CollapsibleSidebar from '../navigation/CollapsibleSidebar.vue'

defineProps({
  moduleLabel: {
    type: String,
    required: true
  },
  moduleIcon: {
    type: [Object, Function],
    default: PresentationChartLineIcon
  },
  overviewRoute: {
    type: [String, Object],
    required: true
  },
  steps: {
    type: Array,
    required: true
  },
  currentBreadcrumb: {
    type: String,
    default: ''
  },
  showBackToOverview: {
    type: Boolean,
    default: true
  },
  isOverview: {
    type: Boolean,
    default: false
  },
  isActiveFn: {
    type: Function,
    default: null
  }
})
</script>
