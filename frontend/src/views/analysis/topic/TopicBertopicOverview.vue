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

      <div class="topic-prep-workflow">
        <div class="topic-prep-workflow__grid topic-prep-workflow__grid--compact">
          <article v-for="step in steps" :key="step.title" class="topic-prep-workflow__card">
            <div class="topic-prep-workflow__index">{{ step.index }}</div>
            <div class="topic-prep-workflow__body">
              <div class="topic-prep-workflow__meta topic-prep-workflow__meta--tight">
                <h3 class="topic-prep-workflow__step-title">{{ step.title }}</h3>
                <p class="topic-prep-workflow__step-subtitle">{{ step.subtitle }}</p>
              </div>
              <p class="topic-prep-workflow__step-description">
                {{ step.description }}
              </p>
            </div>
            <button
              type="button"
              class="topic-prep-workflow__action opacity-100 translate-x-0"
              @click="router.push(step.route)"
            >
              前往执行分析
              <ArrowSmallRightIcon class="topic-prep-workflow__action-icon" />
            </button>
          </article>
        </div>
      </div>
    </section>

    <!-- Multi-Agent Architecture Section -->
    <section class="space-y-6">
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold text-primary tracking-tight">多智能体协同架构 (Multi-Agent Workflow)</h2>
        <div class="h-px flex-1 bg-soft mx-4 hidden sm:block"></div>
        <span class="text-[10px] font-bold text-brand-600 uppercase tracking-widest bg-brand-50 px-2 py-1 rounded-full">LangGraph Pipeline</span>
      </div>

      <div class="card-surface p-8 relative overflow-hidden bg-gradient-to-br from-slate-50/50 to-white">
        <!-- Background Decoration -->
        <div class="absolute -right-20 -top-20 w-64 h-64 bg-brand-50 rounded-full blur-3xl opacity-50 pointer-events-none"></div>
        <div class="absolute -left-20 -bottom-20 w-64 h-64 bg-indigo-50 rounded-full blur-3xl opacity-50 pointer-events-none"></div>

        <div class="relative z-10 flex flex-col items-center max-w-4xl mx-auto pl-4 sm:pl-0">
          
          <!-- Node 1 -->
          <div class="w-full max-w-md bg-white rounded-2xl border border-brand-100/50 shadow-sm p-5 relative group hover:shadow-md transition-shadow">
            <div class="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 font-bold text-[11px] ring-4 ring-white">1</div>
            <div class="ml-4 flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div class="p-2.5 bg-blue-50 text-blue-600 rounded-xl shrink-0"><MagnifyingGlassIcon class="w-5 h-5"/></div>
              <div>
                <h3 class="text-sm font-bold text-gray-900 flex items-center gap-1.5 break-words">Scope Analyst <span class="text-[11px] font-medium text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">范围分析师</span></h3>
                <p class="text-xs text-gray-500 mt-1.5 leading-relaxed shrink">基于原始主题的词袋与样本分布，动态推荐合理的聚类数量上限，避免“一刀切”。</p>
              </div>
            </div>
          </div>

          <!-- Arrow -->
          <div class="w-0.5 h-8 bg-gradient-to-b from-brand-200 to-indigo-200"></div>

          <!-- Multi-agent Loop Container -->
          <div class="w-full relative bg-indigo-50/30 rounded-3xl border border-indigo-100/50 p-6 pt-9 pb-8 mt-2 shadow-[inset_0_2px_10px_rgba(0,0,0,0.01)]">
            <div class="absolute -top-3 left-1/2 -translate-x-1/2 bg-white text-indigo-600 text-[10px] font-bold px-3.5 py-1 rounded-full uppercase tracking-widest border border-indigo-100 shadow-sm flex items-center gap-1.5 whitespace-nowrap">
              <span class="relative flex h-2 w-2">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                <span class="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
              </span>
              Core Refinement Loop (Max 3 Iters)
            </div>

            <div class="flex flex-col items-center gap-6">
              <!-- Node 2 -->
              <div class="w-full max-w-md bg-white rounded-2xl border border-indigo-100/50 shadow-sm p-5 relative hover:shadow-md transition-shadow z-10">
                <div class="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-[11px] ring-4 ring-indigo-50">2</div>
                <div class="ml-4 flex flex-col sm:flex-row items-start sm:items-center gap-4">
                  <div class="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl shrink-0"><SparklesIcon class="w-5 h-5"/></div>
                  <div>
                    <h3 class="text-sm font-bold text-gray-900 flex items-center gap-1.5 break-words">Cluster Strategist <span class="text-[11px] font-medium text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">聚类策略师</span></h3>
                    <p class="text-xs text-gray-500 mt-1.5 leading-relaxed">整合由主导视角、手工种子词、强制合并构成的业务规则，将碎片化主题进行高维语义聚类。</p>
                  </div>
                </div>
              </div>

              <!-- Internal Arrow -->
              <div class="flex flex-col items-center relative gap-1">
                <ArrowSmallDownIcon class="w-5 h-5 text-indigo-300"/>
              </div>

              <!-- Node 3 -->
              <div class="w-full max-w-md bg-white rounded-2xl border border-pink-100/50 shadow-sm p-4 sm:p-5 relative hover:shadow-md transition-shadow z-10">
                <div class="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-pink-100 flex items-center justify-center text-pink-700 font-bold text-[11px] ring-4 ring-indigo-50">3</div>
                <div class="ml-4 flex flex-col sm:flex-row items-start sm:items-center gap-4">
                  <div class="p-2.5 bg-pink-50 text-pink-600 rounded-xl shrink-0"><ScaleIcon class="w-5 h-5"/></div>
                  <div>
                    <h3 class="text-sm font-bold text-gray-900 flex items-center gap-1.5 break-words">Relevance Judge <span class="text-[11px] font-medium text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">相关性裁判</span></h3>
                    <p class="text-[11px] sm:text-xs text-gray-600 mt-1.5 divide-y divide-gray-100 leading-relaxed">
                      <span class="block pb-1.5">搭载 <strong>Sentence-BERT</strong> 语义向量审查。对不相关的残余底料执行一票否决。</span>
                      <span class="block pt-1.5 text-emerald-600 font-medium"><ShieldCheckIcon class="w-3.5 h-3.5 inline mr-1 -mt-0.5"/>触发大主题保护及最大丢弃率限制兜底</span>
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Loopback visual -->
            <div class="hidden sm:flex absolute left-6 lg:left-8 top-[88px] bottom-[94px] w-12 border-l-2 border-t-2 border-b-2 border-dashed border-indigo-300 rounded-l-2xl items-center opacity-60 z-0">
              <div class="absolute -left-[19px] bg-indigo-50 p-1 text-indigo-500 rotate-90 text-[9px] font-bold tracking-widest rounded shadow-sm border border-indigo-100">RETRY</div>
            </div>
            <!-- Arrow head for loopback -->
            <div class="hidden sm:block absolute left-[54px] lg:left-[62px] top-[79px] text-indigo-400 transform -translate-x-1/2 -rotate-90">
              <ArrowSmallRightIcon class="w-4 h-4"/>
            </div>

          </div>

          <!-- Arrow -->
          <div class="w-0.5 h-8 bg-gradient-to-b from-indigo-200 to-purple-200"></div>

          <!-- Node 4 -->
          <div class="w-full max-w-md bg-white rounded-2xl border border-purple-100/50 shadow-sm p-5 relative hover:shadow-md transition-shadow pt-6 border-t-purple-200">
            <div class="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center text-purple-700 font-bold text-[11px] ring-4 ring-white">4</div>
            <div class="ml-4 flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div class="p-2.5 bg-purple-50 text-purple-600 rounded-xl shrink-0"><FunnelIcon class="w-5 h-5"/></div>
              <div>
                <h3 class="text-sm font-bold text-gray-900 flex items-center gap-1.5 break-words">Custom Filter Judge <span class="text-[11px] font-medium text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">定制过滤器</span></h3>
                <p class="text-xs text-gray-500 mt-1.5 leading-relaxed">执行系统级及项目级的排除规则（如：排除"无关噪音"）。逐一对聚类执行语义核对裁剪。</p>
              </div>
            </div>
            <div class="absolute right-3 -top-2.5 bg-gray-50 text-gray-400 border border-gray-100 text-[9px] px-2 py-0.5 rounded uppercase font-bold tracking-wider shadow-sm">Optional</div>
          </div>

          <!-- Arrow -->
          <div class="w-0.5 h-8 bg-gradient-to-b from-purple-200 to-emerald-200"></div>

          <!-- Node 5 -->
          <div class="w-full max-w-md bg-white rounded-2xl border border-emerald-100/50 shadow-sm p-5 relative hover:shadow-md transition-shadow overflow-hidden">
            <div class="absolute right-0 top-0 w-24 h-24 bg-gradient-to-br from-emerald-50/50 to-transparent rounded-bl-[100px] pointer-events-none"></div>
            <div class="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-700 font-bold text-[11px] ring-4 ring-white">5</div>
            <div class="ml-4 flex flex-col sm:flex-row items-start sm:items-center gap-4 relative z-10">
              <div class="p-2.5 bg-emerald-50 text-emerald-600 rounded-xl shrink-0"><TagIcon class="w-5 h-5"/></div>
              <div>
                <h3 class="text-sm font-bold text-gray-900 flex items-center gap-1.5 break-words">Naming & Keywords <span class="text-[11px] font-medium text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">文采润色师</span></h3>
                <p class="text-xs text-gray-500 mt-1.5 leading-relaxed">对经过层层筛选的高质量聚类进行最终语义化包装，生成高可读性的名称和精准摘要标签。</p>
              </div>
            </div>
          </div>

        </div>
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
import '../../../assets/topic-preparation-workflow.css'

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
  FunnelIcon,
  ScaleIcon,
  ShieldCheckIcon,
  ArrowSmallDownIcon
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
