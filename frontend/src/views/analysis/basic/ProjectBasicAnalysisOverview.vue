<template>
  <div class="space-y-10 pb-12">
    <!-- Hero Section -->
    <section class="relative overflow-hidden rounded-3xl bg-surface border border-soft p-1 shadow-sm">
      <div
        class="relative overflow-hidden rounded-[22px] bg-gradient-to-br from-brand-600 via-brand-700 to-indigo-900 px-6 py-10 text-white sm:px-10 sm:py-12">
        <!-- Abstract background elements -->
        <div class="absolute inset-0 overflow-hidden opacity-20 pointer-events-none">
          <div class="absolute -top-1/4 -left-1/4 h-[400px] w-[400px] rounded-full bg-white/30 blur-[100px]"></div>
          <div class="absolute -bottom-1/4 -right-1/4 h-[300px] w-[300px] rounded-full bg-brand-400 blur-[80px]"></div>
        </div>

        <div class="relative z-10 grid gap-8 lg:grid-cols-2 lg:items-center">
          <div class="space-y-6">
            <div class="space-y-2">
              <div
                class="inline-flex items-center rounded-full bg-white/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-brand-100 backdrop-blur-md border border-white/10">
                Core Module
              </div>
              <h1 class="text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
                专题基础分析
              </h1>
              <p class="max-w-xl text-base text-brand-50/80 leading-relaxed font-medium">
                深度挖掘专题传播趋势、内容特征与公众反馈。提供多维度统计能力，助力科学决策与舆情研判。
              </p>
            </div>

            <div class="flex flex-wrap gap-2 text-[10px]">
              <span v-for="tag in activeDimensions" :key="tag"
                class="rounded-full bg-white/10 px-3 py-1 font-semibold text-white backdrop-blur-sm border border-white/5">
                {{ tag }}
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-3 pt-2">
              <button type="button"
                class="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-brand-800 transition-all active:scale-95 group"
                @click="goToRun">
                <PlayIcon class="h-4 w-4 fill-current" />
                <span class="text-sm font-bold">立即配置分析任务</span>
              </button>

              <button type="button"
                class="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-2.5 text-white text-sm transition-all"
                @click="scrollToProcess">
                <InformationCircleIcon class="h-4 w-4" />
                <span>了解工作流</span>
              </button>
            </div>
          </div>

          <!-- Feature highlight -->
          <div class="hidden lg:block">
            <div class="relative rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-md">
              <h3 class="mb-3 text-xs font-bold text-brand-200">主要输出 (Core Outputs)</h3>
              <ul class="space-y-2.5 text-[13px] text-white/70">
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400"></div>
                  <span>舆情声量峰值识别与全渠道分布统计</span>
                </li>
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400"></div>
                  <span>多颗粒度话题自动聚类与事实/观点研判</span>
                </li>
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400"></div>
                  <span>精细化情感极性分布与关键意见领袖画像</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Workflow Section -->
    <section id="workflow-section" class="space-y-6 scroll-mt-6">
      <div class="text-center space-y-1">
        <h2 class="text-2xl font-bold text-primary tracking-tight">分析流程</h2>
        <p class="mx-auto max-w-xl text-secondary text-sm">
          通过简单的三步，从原始数据到专业的可视化报告。
        </p>
      </div>

      <div class="grid gap-5 md:grid-cols-2">
        <article v-for="step in steps" :key="step.title" class="card-surface p-6 transition-all">
          <div class="flex items-start gap-4">
            <div
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-soft/50 text-lg font-black text-brand-600 border border-brand-soft">
              {{ step.index }}
            </div>
            <div class="space-y-3">
              <div class="space-y-0.5">
                <h3 class="text-lg font-bold text-primary">{{ step.title }}</h3>
                <p class="text-[11px] font-medium text-brand-600/70">{{ step.subtitle }}</p>
              </div>
              <p class="text-sm leading-relaxed text-secondary/80">
                {{ step.description }}
              </p>
              <button type="button"
                class="inline-flex items-center gap-1 text-sm font-bold text-brand-600 transition hover:underline group"
                @click="router.push(step.route)">
                前往执行
                <ArrowSmallRightIcon class="h-4 w-4" />
              </button>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- Example Section -->
    <section class="space-y-6">
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold text-primary tracking-tight">分析解读示例</h2>
        <div class="h-px flex-1 bg-soft mx-4 hidden sm:block"></div>
        <span class="text-[10px] font-bold text-muted uppercase tracking-widest">Insight Examples</span>
      </div>

      <div class="card-surface p-6 space-y-8">
        <!-- AI Summary Mockup -->
        <div class="rounded-xl bg-brand-soft/20 p-5 border border-brand-soft/30">
          <div class="flex items-center gap-3 mb-3">
            <div class="h-7 w-7 rounded-full bg-brand-500 flex items-center justify-center text-white">
              <SparklesIcon class="h-4 w-4" />
            </div>
            <h3 class="text-base font-bold text-primary">AI 摘要深度解读</h3>
          </div>

          <div class="grid gap-6 lg:grid-cols-3">
            <div class="lg:col-span-2 space-y-3">
              <p class="text-sm leading-relaxed text-secondary font-medium">
                “2025年9月23日舆情声量达峰值369，社交平台由自媒体主导。舆论聚合于戒烟建议与健康关联，关键词 nicotine、肺癌反映出公众侧重科学风险。整体情绪稳定，但负面风险点在于医疗成本争议。”
              </p>
              <div class="flex flex-wrap gap-2 pt-1">
                <span v-for="id in activeDimensionIds" :key="id"
                  class="inline-flex items-center rounded-md bg-white px-2 py-0.5 text-[9px] font-bold text-brand-600 border border-brand-soft shadow-sm">
                  # {{ id }}
                </span>
              </div>
            </div>
            <div class="bg-white/50 rounded-lg p-3.5 border border-white/50 space-y-2.5">
              <h4 class="text-[10px] font-black text-muted uppercase tracking-wider">核心发现</h4>
              <ul class="space-y-1.5 text-xs text-secondary">
                <li class="flex items-center gap-2">
                  <CheckBadgeIcon class="h-3.5 w-3.5 text-green-500" />
                  <span>峰值预警：9月23日</span>
                </li>
                <li class="flex items-center gap-2">
                  <CheckBadgeIcon class="h-3.5 w-3.5 text-green-500" />
                  <span>主导渠道：微信+自媒体</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Capability Grid -->
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div v-for="example in examples" :key="example.title"
            class="flex flex-col rounded-xl border border-soft bg-surface-muted/30 p-4 transition-all">
            <div class="mb-3 flex items-center justify-between">
              <div class="flex h-9 w-9 items-center justify-center rounded-lg shadow-sm" :class="example.colorClass">
                <component :is="example.icon" class="h-4 w-4" />
              </div>
              <span class="text-[9px] font-black text-muted opacity-30 uppercase">{{ example.id }}</span>
            </div>
            <h4 class="mb-1 text-sm font-bold text-primary">{{ example.title }}</h4>
            <p class="text-xs leading-relaxed text-secondary/80">
              {{ example.description }}
            </p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  ArrowSmallRightIcon,
  PlayIcon,
  InformationCircleIcon,
  SparklesIcon,
  CheckBadgeIcon,
  HeartIcon,
  TagIcon,
  MapPinIcon,
  ChartBarIcon
} from '@heroicons/vue/24/solid'

const router = useRouter()

const goToRun = () => {
  router.push({ name: 'project-data-analysis-run' })
}

const scrollToProcess = () => {
  const el = document.getElementById('workflow-section')
  if (el) el.scrollIntoView({ behavior: 'smooth' })
}

const activeDimensions = ['地域分析', '关键词', '趋势洞察', '发布者', '情感分析', '声量概览', '话题分类']
const activeDimensionIds = ['Attitude', 'Classification', 'Geography', 'Keywords', 'Publishers', 'Trends', 'Volume']

const steps = [
  {
    index: 1,
    title: '运行分析',
    subtitle: '数据生产节点',
    description: '选择专题数据源，配置时间粒度，触发流水线。由后台完成数据清洗到特征抽取的全过程。',
    route: { name: 'project-data-analysis-run' }
  },
  {
    index: 2,
    title: '统计面板',
    subtitle: '可视化洞察节点',
    description: '浏览多维度的图表报告，分析异常波动。支持刷新同步最新数据，并生成结构化的摘要解读。',
    route: { name: 'project-data-analysis-view' }
  }
]

const examples = [
  {
    id: 'AT',
    title: '情感分析',
    icon: HeartIcon,
    colorClass: 'bg-rose-50 text-rose-600',
    description: '语义识别提取公众情绪极性，识别负面风险点。'
  },
  {
    id: 'CL',
    title: '话题分类',
    icon: TagIcon,
    colorClass: 'bg-amber-50 text-amber-600',
    description: '聚类讨论议题，区分事实陈述与评论。'
  },
  {
    id: 'GE',
    title: '地域分析',
    icon: MapPinIcon,
    colorClass: 'bg-emerald-50 text-emerald-600',
    description: '识别高发省份与城市，掌握空间传播规律。'
  },
  {
    id: 'TR',
    title: '趋势洞察',
    icon: ChartBarIcon,
    colorClass: 'bg-blue-50 text-blue-600',
    description: '追踪周期声量涨落，定位突发事件时间轴。'
  }
]
</script>
