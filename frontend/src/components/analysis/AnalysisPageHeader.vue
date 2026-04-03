<template>
  <section class="analysis-page-header">
    <div class="analysis-page-header__main">
      <div class="space-y-2">
        <p v-if="eyebrow" class="analysis-page-header__eyebrow">{{ eyebrow }}</p>
        <div class="space-y-2">
          <h1 class="analysis-page-header__title">{{ title }}</h1>
          <p v-if="description" class="analysis-page-header__description">{{ description }}</p>
        </div>
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
    </div>

    <dl v-if="metaItems.length" class="analysis-meta-list">
      <div v-for="item in metaItems" :key="`${item.label}-${item.value}`" class="analysis-meta-list__item">
        <span v-if="item.icon" class="analysis-meta-list__icon">
          <component :is="item.icon" class="h-4 w-4" />
        </span>
        <div class="space-y-1">
          <dt class="analysis-meta-list__label">{{ item.label }}</dt>
          <dd class="analysis-meta-list__value">{{ item.value }}</dd>
        </div>
      </div>
    </dl>
  </section>
</template>

<script setup>
import { RouterLink } from 'vue-router'

defineProps({
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
  metaItems: {
    type: Array,
    default: () => []
  },
  actions: {
    type: Array,
    default: () => []
  }
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
