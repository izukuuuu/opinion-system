<template>
  <div class="mx-auto max-w-3xl space-y-6">
    <section class="rounded-xl border border-dashed border-soft bg-surface-muted px-8 py-10 text-center">
      <h2 class="text-2xl font-semibold text-primary md:text-3xl">{{ title }}</h2>
      <p class="mt-4 text-sm text-secondary md:text-base">
        此功能正在规划中，欢迎提供需求反馈帮助我们完善「{{ title }}」模块。
      </p>
      <div
        v-if="description"
        class="mx-auto mt-6 inline-flex items-center gap-2 rounded-full bg-brand-soft/60 px-4 py-2 text-xs font-medium text-brand-700"
      >
        <SparklesIcon class="h-4 w-4" />
        <span>{{ description }}</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { SparklesIcon } from '@heroicons/vue/24/outline'

const route = useRoute()

const title = computed(() => route.meta?.title ?? '功能占位')
const description = computed(() => route.meta?.placeholder ?? '')
</script>
