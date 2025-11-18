<template>
  <div class="grid gap-2.5 lg:grid-cols-2">
    <article
      v-for="item in items"
      :key="item.id"
      class="flex h-full flex-col rounded-2xl border border-soft bg-white/80 p-3 shadow-sm transition hover:border-brand-soft"
    >
      <header class="flex items-center gap-2 text-sm text-primary">
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
            <component :is="item.icon" class="h-4 w-4" />
          </span>
          <div class="space-y-0.5">
            <p class="font-semibold leading-tight">{{ item.label }}</p>
        </div>
      </header>
      <p class="mt-2 whitespace-pre-line text-sm leading-relaxed text-secondary">
        {{ item.aiSummary || item.textSnapshot || '暂未生成概览' }}
      </p>
    </article>
  </div>
</template>

<script setup>
defineProps({
  items: {
    type: Array,
    default: () => []
  }
})
</script>
