<template>
  <section class="analysis-hero">
    <div class="analysis-hero__backdrop"></div>
    <div class="analysis-hero__grid">
      <div class="space-y-6">
        <div class="space-y-3">
          <p v-if="eyebrow" class="analysis-hero__eyebrow">{{ eyebrow }}</p>
          <div class="space-y-3">
            <h1 class="analysis-hero__title">{{ title }}</h1>
            <p v-if="description" class="analysis-hero__description">{{ description }}</p>
          </div>
        </div>

        <div v-if="tags.length" class="flex flex-wrap gap-2">
          <span v-for="tag in tags" :key="tag" class="analysis-chip analysis-chip--hero">
            {{ tag }}
          </span>
        </div>

        <div v-if="hasActions" class="flex flex-wrap items-center gap-3">
          <component
            :is="primaryAction.to ? RouterLink : 'button'"
            v-if="primaryAction"
            v-bind="resolveActionProps(primaryAction)"
            :class="actionClass(primaryAction.variant || 'primary')"
            @click="handleAction(primaryAction, $event)"
          >
            <component :is="primaryAction.icon" v-if="primaryAction.icon" class="h-4 w-4" />
            <span>{{ primaryAction.label }}</span>
          </component>
          <component
            :is="secondaryAction.to ? RouterLink : 'button'"
            v-if="secondaryAction"
            v-bind="resolveActionProps(secondaryAction)"
            :class="actionClass(secondaryAction.variant || 'secondary')"
            @click="handleAction(secondaryAction, $event)"
          >
            <component :is="secondaryAction.icon" v-if="secondaryAction.icon" class="h-4 w-4" />
            <span>{{ secondaryAction.label }}</span>
          </component>
        </div>
      </div>

      <aside v-if="highlights.length" class="analysis-hero__panel">
        <p class="analysis-hero__panel-eyebrow">主要输出</p>
        <ul class="space-y-3">
          <li v-for="item in highlights" :key="item.title || item" class="analysis-hero__highlight">
            <div class="analysis-hero__highlight-dot"></div>
            <div class="space-y-1">
              <p class="text-sm font-semibold text-primary">{{ item.title || item }}</p>
              <p v-if="item.description" class="text-sm text-secondary">{{ item.description }}</p>
            </div>
          </li>
        </ul>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({
  eyebrow: {
    type: String,
    default: ''
  },
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  },
  tags: {
    type: Array,
    default: () => []
  },
  primaryAction: {
    type: Object,
    default: null
  },
  secondaryAction: {
    type: Object,
    default: null
  },
  highlights: {
    type: Array,
    default: () => []
  }
})

const hasActions = computed(() => Boolean(props.primaryAction || props.secondaryAction))

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
  'analysis-hero__action focus-ring-accent',
  variant === 'secondary' ? 'analysis-hero__action--secondary' : 'analysis-hero__action--primary'
]
</script>
