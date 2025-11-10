<template>
  <ul v-if="logs.length" class="space-y-2 text-xs">
    <li
      v-for="log in logs"
      :key="log.id"
      class="flex flex-wrap items-baseline gap-3 rounded-2xl border border-soft bg-surface-muted px-4 py-3"
      :class="log.status === 'error' ? 'border-danger/40 text-danger' : ''"
    >
      <span class="text-muted">{{ log.time }}</span>
      <strong class="text-sm text-primary">{{ log.label }}</strong>
      <p class="text-secondary">{{ log.message }}</p>
    </li>
  </ul>
  <p v-else class="text-xs text-muted">{{ emptyLabel }}</p>
</template>

<script setup>
defineProps({
  logs: {
    type: Array,
    default: () => []
  },
  emptyLabel: {
    type: String,
    default: ''
  }
})
</script>
