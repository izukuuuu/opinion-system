<template>
  <div class="space-y-10">
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 px-6 py-10 text-white sm:px-10">
      <div class="absolute inset-0 opacity-40">
        <div class="absolute -top-28 left-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-white/25 blur-3xl"></div>
        <div class="absolute bottom-0 right-10 h-56 w-56 rounded-full bg-brand-200/80 blur-3xl"></div>
      </div>
      <div class="relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
        <div class="space-y-4">
          <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/70">基础分析</p>
          <h1 class="text-3xl font-semibold sm:text-4xl">专题基础分析</h1>
          <p class="text-lg text-white/80">
            可查看专题各类指标的基础分析，并展示相应可视化内容。
          </p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-brand-700 transition hover:bg-gray-50 focus-ring-accent"
          @click="goToRun"
        >
          <span class="flex h-9 w-9 items-center justify-center rounded-full bg-brand-50 text-brand-700">
            <PlayCircleIcon class="h-5 w-5" />
          </span>
          <span class="text-base font-semibold">立即运行分析</span>
        </button>
      </div>
    </section>

    <section class="space-y-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-primary">基础分析流程</h2>
        <p class="text-sm text-secondary">请先针对各个专题运行各项基础分析功能之后，在查看分析界面查看基础统计</p>
      </header>
      <div class="grid gap-6 md:grid-cols-3">
        <article
          v-for="step in steps"
          :key="step.title"
          class="card-surface flex flex-col gap-4 p-6"
        >
          <div class="flex items-center gap-3">
            <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-lg font-semibold text-brand-600">
              {{ step.index }}
            </span>
            <div>
              <h3 class="text-lg font-semibold text-primary">{{ step.title }}</h3>
              <p class="text-sm text-secondary">{{ step.subtitle }}</p>
            </div>
          </div>
          <p class="flex-1 text-sm leading-relaxed text-secondary">
            {{ step.description }}
          </p>
          <button
            type="button"
            class="inline-flex items-center gap-2 self-start rounded-full border border-brand-soft px-4 py-1.5 text-sm font-semibold text-brand-600 transition hover:bg-brand-soft focus-ring-accent"
            @click="router.push(step.route)"
          >
            <ArrowRightIcon class="h-4 w-4" />
            前往
          </button>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowRightIcon, PlayCircleIcon } from '@heroicons/vue/24/outline'

const router = useRouter()

const goToRun = () => {
  router.push({ name: 'project-data-analysis-run' })
}

const steps = [
  {
    index: 1,
    title: '运行分析',
    subtitle: '拉取数据并执行',
    description: '选择远程数据库的专题并指定时间区间，运行基础分析，结果将保存到后台以供查看。',
    route: { name: 'project-data-analysis-run' }
  },
  {
    index: 2,
    title: '查看分析',
    subtitle: '刷新与浏览结果',
    description: '从历史记录中选择分析任务，查看可视化面板，并快速定位到具体模块。',
    route: { name: 'project-data-analysis-view' }
  }
]
</script>
