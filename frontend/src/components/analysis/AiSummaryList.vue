<template>
  <div class="space-y-4">
    <article
      v-for="item in items"
      :key="item.id"
      class="rounded-2xl border border-soft bg-surface-muted/40 p-4 shadow-sm"
    >
      <header class="flex flex-wrap items-start justify-between gap-3">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
            <component :is="item.icon" class="h-5 w-5" />
          </span>
          <div class="space-y-1">
            <p class="text-sm font-semibold text-primary">
              {{ item.label }}
              <span class="ml-2 text-xs font-normal text-muted">{{ item.target }}</span>
            </p>
            <p class="text-xs text-muted">
              {{ item.aiSummary ? 'AI 精简摘要' : '基于数据的概览' }}
            </p>
          </div>
        </div>
        <span class="text-xs text-muted">{{ item.updatedAt || '' }}</span>
      </header>
      <p class="whitespace-pre-line text-sm leading-relaxed text-secondary">
        {{ item.aiSummary || item.textSnapshot || '暂未生成概览' }}
      </p>
      <details
        v-if="item.textSnapshot"
        class="mt-3 rounded-2xl border border-dashed border-soft px-3 py-2 text-xs text-muted"
      >
        <summary class="cursor-pointer text-brand-600">展开原始概览</summary>
        <pre class="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-secondary">{{ item.textSnapshot }}</pre>
      </details>
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
