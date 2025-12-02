<template>
  <div class="space-y-10">
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 px-6 py-10 text-white sm:px-10">
      <div class="absolute inset-0 opacity-40">
        <div class="absolute -top-28 left-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-white/25 blur-3xl"></div>
        <div class="absolute bottom-0 right-10 h-56 w-56 rounded-full bg-brand-200/80 blur-3xl"></div>
      </div>
      <div class="relative space-y-6">
        <div class="space-y-4">
          <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/70">主题分析</p>
          <h1 class="text-3xl font-semibold sm:text-4xl">BERTopic + Qwen 主题分析</h1>
        </div>
        
        <div class="space-y-4">
          <p class="text-sm text-white/90">
            BERTopic 结合 Qwen 大模型，对专题数据进行主题建模和智能聚类，自动识别文档主题并生成主题关键词，帮助理解专题的核心议题和内容分布。
          </p>
          
          <div>
            <p class="mb-2 text-sm font-semibold text-white">主要输出</p>
            <p class="text-sm leading-relaxed text-white/80">
              系统会生成主题文档统计、主题关键词、文档 2D 坐标、大模型再聚类结果和主题关键词等数据，并以可视化图表形式展示分析结果。
            </p>
          </div>
          
          <div>
            <p class="mb-2 text-sm font-semibold text-white">分析维度</p>
            <div class="flex flex-wrap gap-2">
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">主题识别</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">关键词提取</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">主题聚类</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">降维可视化</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">智能合并</span>
              <span class="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">主题命名</span>
            </div>
          </div>
        </div>
        
        <div class="flex justify-end">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-brand-700 transition hover:bg-gray-50 focus-ring-accent"
            @click="goToRun"
          >
            <span class="flex h-7 w-7 items-center justify-center rounded-full bg-brand-50 text-brand-700">
              <PlayCircleIcon class="h-4 w-4" />
            </span>
            <span class="text-sm font-semibold">立即运行分析</span>
          </button>
        </div>
      </div>
    </section>

    <section class="space-y-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-primary">主题分析流程</h2>
        <p class="text-sm text-secondary">请先运行 BERTopic 分析生成主题数据，然后在查看结果界面查看可视化图表</p>
      </header>

      <div class="grid gap-6 md:grid-cols-2">
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

    <section class="space-y-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-primary">分析结果示例</h2>
      </header>

      <div class="card-surface space-y-6 p-5 sm:p-6">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50 text-purple-600">
                <ChartBarIcon class="h-4 w-4" />
              </div>
              <h4 class="text-sm font-semibold text-primary">主题文档统计</h4>
            </div>
            <p class="flex-1 text-sm leading-relaxed text-secondary">
              展示每个主题包含的文档数量，帮助了解主题的规模和重要性。
            </p>
          </article>

          <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                <MagnifyingGlassIcon class="h-4 w-4" />
              </div>
              <h4 class="text-sm font-semibold text-primary">主题关键词</h4>
            </div>
            <p class="flex-1 text-sm leading-relaxed text-secondary">
              每个主题的代表性关键词及其权重，反映主题的核心内容特征。
            </p>
          </article>

          <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50 text-green-600">
                <MapIcon class="h-4 w-4" />
              </div>
              <h4 class="text-sm font-semibold text-primary">文档 2D 坐标</h4>
            </div>
            <p class="flex-1 text-sm leading-relaxed text-secondary">
              通过 UMAP 降维将文档投影到二维空间，可视化主题间的距离与分布。
            </p>
          </article>

          <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50 text-orange-600">
                <SparklesIcon class="h-4 w-4" />
              </div>
              <h4 class="text-sm font-semibold text-primary">大模型再聚类</h4>
            </div>
            <p class="flex-1 text-sm leading-relaxed text-secondary">
              Qwen 大模型对 BERTopic 结果进行智能合并与命名，生成更易理解的主题分类。
            </p>
          </article>

          <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                <TagIcon class="h-4 w-4" />
              </div>
              <h4 class="text-sm font-semibold text-primary">大模型主题关键词</h4>
            </div>
            <p class="flex-1 text-sm leading-relaxed text-secondary">
              大模型重新命名后的主题及其关键词，提供更语义化的主题描述。
            </p>
          </article>

          <article class="flex h-full flex-col rounded-2xl border border-soft bg-base-soft p-4">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-pink-50 text-pink-600">
                <FunnelIcon class="h-4 w-4" />
              </div>
              <h4 class="text-sm font-semibold text-primary">桑基图</h4>
            </div>
            <p class="flex-1 text-sm leading-relaxed text-secondary">
              展示原始主题与 LLM 新主题之间的合并关系，直观呈现主题聚类过程。
            </p>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  ArrowRightIcon,
  PlayCircleIcon,
  ChartBarIcon,
  MagnifyingGlassIcon,
  MapIcon,
  SparklesIcon,
  TagIcon,
  FunnelIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()

const goToRun = () => {
  router.push({ name: 'topic-analysis-bertopic-run' })
}

const steps = [
  {
    index: 1,
    title: '运行分析',
    subtitle: '配置参数并执行',
    description: '选择专题并指定时间区间，配置 BERTopic 分析参数，运行主题分析生成结果文件。',
    route: { name: 'topic-analysis-bertopic-run' }
  },
  {
    index: 2,
    title: '查看结果',
    subtitle: '可视化分析结果',
    description: '从专题列表中选择已运行的分析任务，查看主题统计、关键词、降维坐标和 LLM 聚类结果。',
    route: { name: 'topic-analysis-bertopic-view' }
  }
]
</script>

