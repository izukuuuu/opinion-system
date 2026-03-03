<template>
  <div class="space-y-10">
    <!-- Hero Section -->
    <section
      class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 via-brand-500 to-accent-500 px-8 py-16 text-white sm:px-12 lg:px-16 space-shadow-none">
      <div class="absolute inset-0 opacity-30 mix-blend-overlay">
        <div class="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-white/20 blur-[100px]"></div>
        <div
          class="absolute bottom-0 right-0 h-[30rem] w-[30rem] translate-x-1/3 translate-y-1/3 rounded-full bg-accent-300/30 blur-[120px]">
        </div>
      </div>
      <div class="relative flex flex-col gap-10 lg:flex-row lg:items-center lg:justify-between">
        <div class="space-y-6 max-w-2xl">
          <div
            class="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-1.5 text-sm font-medium text-white/90 backdrop-blur-md border border-white/10">
            <span class="flex h-2 w-2 rounded-full bg-accent-300"></span>
            舆情分析工作台
          </div>
          <h1 class="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl text-white">
            启动新的<br />舆情专题
          </h1>
          <p class="text-lg text-white/80 leading-relaxed max-w-xl">
            通过简单的四步流程，快速完成数据上传、清洗、筛选与入库。系统将自动构建分析所需的结构化存档。
          </p>
        </div>
        <button type="button"
          class="group relative inline-flex items-center gap-3 overflow-hidden rounded-full bg-white px-8 py-4 text-brand-900 transition-all hover:bg-gray-50 active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          @click="goToUpload">
          <div
            class="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 group-hover:bg-brand-200 transition-colors">
            <CloudArrowUpIcon class="h-6 w-6 text-brand-700" />
          </div>
          <span class="text-lg font-bold tracking-tight">立即上传数据</span>
        </button>
      </div>
    </section>

    <!-- Navigation Cards -->
    <section class="space-y-8">
      <header class="space-y-3 px-2">
        <h2 class="text-lg font-bold text-primary">专题筹备流程</h2>
        <p class="text-base text-secondary max-w-3xl">
          按照顺序完成数据准备，每一步都会生成独立的存档，方便随时回溯与调整。
        </p>
      </header>

      <div class="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        <article v-for="stage in stages" :key="stage.title"
          class="group relative flex flex-col justify-between card-surface p-6 transition-all hover:bg-surface-soft hover:scale-[1.01] active:scale-[0.99] cursor-pointer"
          @click="router.push(stage.route)">
          <!-- Decorative Background Number -->
          <div
            class="absolute -right-4 -top-6 text-[120px] font-bold leading-none text-brand-600 opacity-10 select-none group-hover:text-brand-600 group-hover:opacity-20 group-hover:translate-x-2 transition-all duration-500">
            {{ stage.index }}
          </div>

          <div class="relative space-y-4">
            <div
              class="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition-colors group-hover:bg-brand-100 group-hover:text-brand-700">
              <component :is="stage.icon" class="h-7 w-7" />
            </div>

            <div class="space-y-2">
              <h3 class="text-lg font-bold text-primary group-hover:text-brand-900 transition-colors">{{ stage.title }}
              </h3>
              <p class="text-sm font-medium text-brand-600/80 uppercase tracking-wider">{{ stage.subtitle }}</p>
            </div>

            <p class="text-sm leading-relaxed text-secondary group-hover:text-primary/90 transition-colors">
              {{ stage.description }}
            </p>
          </div>

          <div
            class="relative mt-6 flex items-center gap-2 text-sm font-semibold text-brand-600 opacity-0 -translate-x-2 transition-all group-hover:opacity-100 group-hover:translate-x-0">
            <span>前往配置</span>
            <ArrowRightIcon class="h-4 w-4" />
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  ArrowRightIcon,
  CloudArrowUpIcon,
  FunnelIcon,
  AdjustmentsHorizontalIcon,
  ArrowTrendingUpIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()

const goToUpload = () => {
  router.push({ name: 'topic-create-upload' })
}

const stages = [
  {
    index: 1,
    title: '上传原始数据',
    subtitle: 'Upload',
    description: '将获取到的 Excel/CSV 专题素材上传至系统，自动生成标准化存档。',
    route: { name: 'topic-create-upload' },
    icon: CloudArrowUpIcon
  },
  {
    index: 2,
    title: '数据预处理',
    subtitle: 'Preprocess',
    description: '执行 Merge 与 Clean，清洗数据并补齐字段，为分析做好准备。',
    route: { name: 'topic-create-preprocess' },
    icon: FunnelIcon
  },
  {
    index: 3,
    title: '筛选数据',
    subtitle: 'Filter',
    description: '配置 AI 提示词模板，智能筛选出与专题高度相关的高价值内容。',
    route: { name: 'topic-create-filter' },
    icon: AdjustmentsHorizontalIcon
  },
  {
    index: 4,
    title: '入库',
    subtitle: 'Ingest',
    description: '将清洗筛选后的最终数据写入数据库，供后续深度分析使用。',
    route: { name: 'topic-create-ingest' },
    icon: ArrowTrendingUpIcon
  },
]
</script>
