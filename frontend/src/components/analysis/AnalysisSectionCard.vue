<template>
  <section class="analysis-section-card" :class="toneClass">
    <header v-if="title || description || actions.length" class="analysis-section-card__header">
      <div class="space-y-1.5">
        <h2 v-if="title" class="analysis-section-card__title">{{ title }}</h2>
        <p v-if="description" class="analysis-section-card__description">{{ description }}</p>
      </div>

      <div v-if="actions.length" class="analysis-toolbar">
        <component
          :is="action.to ? RouterLink : 'button'"
          v-for="action in actions"
          :key="`${action.label}-${action.variant || 'secondary'}`"
          v-bind="resolveActionProps(action)"
          :class="actionClass(action.variant || 'secondary')"
          @click="handleAction(action, $event)"
        >
          <component :is="action.icon" v-if="action.icon" class="h-4 w-4" />
          <span>{{ action.label }}</span>
        </component>
      </div>
    </header>

    <div class="analysis-section-card__body">
      <slot />
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  description: {
    type: String,
    default: ''
  },
  actions: {
    type: Array,
    default: () => []
  },
  tone: {
    type: String,
    default: 'default'
  }
})

const toneClass = computed(() => {
  if (props.tone === 'soft') return 'analysis-section-card--soft'
  if (props.tone === 'emphasis') return 'analysis-section-card--emphasis'
  return ''
})

const resolveActionProps = (action) => {
  if (action?.to) {
    return { to: action.to }
  }
  return { type: 'button' }
}

const handleAction = (action, event) => {
  if (typeof action?.onClick === 'function') {
    action.onClick(event)
  }
}

const actionClass = (variant) => [
  'analysis-toolbar__action focus-ring-accent',
  `analysis-toolbar__action--${variant}`
]
</script>
