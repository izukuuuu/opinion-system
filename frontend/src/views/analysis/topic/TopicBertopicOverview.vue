<template>
  <div class="space-y-12 pb-12">
    <!-- Hero Section -->
    <section class="relative overflow-hidden rounded-3xl bg-surface border border-soft p-1">
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
                Advanced Topic Modeling
              </div>
              <h1 class="text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
                BERTopic + Qwen 分析
              </h1>
              <p class="max-w-xl text-base text-brand-50/80 leading-relaxed font-medium">
                结合最先进的深度学习框架，实现语义化的主题聚类与大模型智能命名。精准捕捉舆情底层逻辑。
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
                <span class="text-sm font-bold">立即部署分析任务</span>
              </button>

              <button type="button"
                class="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-2.5 text-white text-sm transition-all"
                @click="scrollToProcess">
                <InformationCircleIcon class="h-4 w-4" />
                <span>工作流说明</span>
              </button>
            </div>
          </div>

          <!-- Feature highlight -->
          <div class="hidden lg:block">
            <div class="relative rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-md">
              <h3 class="mb-3 text-xs font-bold text-brand-200">引擎核心能力 (Engine Core)</h3>
              <ul class="space-y-2.5 text-[13px] text-white/70">
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                  <span>基于 Sentence-BERT 的高维语义向量嵌入</span>
                </li>
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                  <span>Qwen 大模型驱动的主题聚类与语义降噪</span>
                </li>
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                  <span>多尺度 c-TF-IDF 关键字重要性评分系统</span>
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
          通过深度学习引擎，将海量非结构化文本转化为结构化主题洞察。
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
                前往分执行分析
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
        <h2 class="text-xl font-bold text-primary tracking-tight">智能解读示例</h2>
        <div class="h-px flex-1 bg-soft mx-4 hidden sm:block"></div>
        <span class="text-[10px] font-bold text-muted uppercase tracking-widest">LLM + BERTopic</span>
      </div>

      <div class="card-surface p-6 space-y-8">
        <!-- Mockup: Dimensional Result -->
        <div class="rounded-xl border border-soft bg-surface-muted/20 p-5 overflow-hidden relative">
          <div class="flex items-center gap-3 mb-4">
            <div class="h-7 w-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white">
              <SparklesIcon class="h-4 w-4" />
            </div>
            <h3 class="text-base font-bold text-primary tracking-tight">Qwen 智能聚类结果</h3>
          </div>

          <div class="flex flex-wrap gap-3">
            <div v-for="topic in ['公共卫生预警', '医患矛盾', '政策反馈', '国际形势']" :key="topic"
              class="px-4 py-2 bg-white rounded-full border border-soft text-xs font-bold text-primary">
              {{ topic }}
            </div>
          </div>

          <div class="mt-6 p-4 rounded-xl bg-white border border-soft">
            <div class="flex items-center gap-2 mb-2">
              <div class="h-2 w-2 rounded-full bg-green-500"></div>
              <span class="text-[10px] font-bold text-muted uppercase tracking-wider">Analysis Result</span>
            </div>
            <p class="text-sm text-secondary leading-relaxed">
              分析显示，BERTopic 提取的 14 个原始主题已被 LLM 自动合并为 4 个宏观话题。其中“公共卫生预警”占比最高 (42.5%)，反映了公众近期的主要关切点。
            </p>
          </div>
        </div>

        <!-- Capability Grid -->
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="example in examples" :key="example.title"
            class="flex flex-col rounded-xl border border-soft bg-surface-muted/30 p-4 transition-all">
            <div class="mb-3 flex items-center justify-between">
              <div class="flex h-9 w-9 items-center justify-center rounded-lg" :class="example.colorClass">
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
  ChartBarIcon,
  MagnifyingGlassIcon,
  MapIcon,
  TagIcon,
  FunnelIcon
} from '@heroicons/vue/24/solid'

const router = useRouter()

const goToRun = () => {
  router.push({ name: 'topic-analysis-bertopic-run' })
}

const scrollToProcess = () => {
  const el = document.getElementById('workflow-section')
  if (el) el.scrollIntoView({ behavior: 'smooth' })
}

const activeDimensions = ['Sentence-BERT', 'UMAP 降维', 'HDBSCAN', 'Qwen-Turbo', 'c-TF-IDF', '智能命名']

const steps = [
  {
    index: 1,
    title: '参数配置',
    subtitle: '配置分析引擎',
    description: '选择数据源并指定时间区间。系统将自动调用 BERTopic 算法与 Qwen 大模型进行联合计算。',
    route: { name: 'topic-analysis-bertopic-run' }
  },
  {
    index: 2,
    title: '模型可视化',
    subtitle: '核心资产浏览',
    description: '浏览主题聚类结果与大模型重构后的分类体系。支持全局 2D 降维坐标查看与主题分布统计。',
    route: { name: 'topic-analysis-bertopic-view' }
  }
]

const examples = [
  {
    id: 'TS',
    title: '主题文档统计',
    icon: ChartBarIcon,
    colorClass: 'bg-purple-50 text-purple-600',
    description: '展示每个主题包含的文档数量，清晰呈现主题影响力。'
  },
  {
    id: 'KW',
    title: '主题关键词',
    icon: MagnifyingGlassIcon,
    colorClass: 'bg-blue-50 text-blue-600',
    description: '核心关键词权重分析，精准刻画主题语义边界。'
  },
  {
    id: 'UM',
    title: '降维可视化',
    icon: MapIcon,
    colorClass: 'bg-emerald-50 text-emerald-600',
    description: '将高维文档映射至 2D 平面，直观展示主题间距。'
  },
  {
    id: 'LLm',
    title: '智能再聚类',
    icon: SparklesIcon,
    colorClass: 'bg-amber-50 text-amber-600',
    description: 'Qwen 智能驱动，将零散主题合并为更具业务价值的分类。'
  },
  {
    id: 'TN',
    title: '大模型命名',
    icon: TagIcon,
    colorClass: 'bg-indigo-50 text-indigo-600',
    description: '语义化重构主题标题，告别难以理解的词堆叠。'
  },
  {
    id: 'SY',
    title: '层级拓扑',
    icon: FunnelIcon,
    colorClass: 'bg-rose-50 text-rose-600',
    description: '直观展示原始分群与大模型主题的演化与合并逻辑。'
  }
]
</script>
