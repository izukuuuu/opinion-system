<template>
  <div class="space-y-6 pb-12">
    <AnalysisPageHero
      eyebrow="基础分析模块"
      title="专题基础分析"
      description="面向专题数据的标准分析工作流，聚焦趋势、情感、发布者与地域分布等核心指标，帮助团队快速完成基础洞察。"
      :tags="activeDimensions"
      :primary-action="primaryAction"
      :secondary-action="secondaryAction"
      :highlights="heroHighlights"
    />

    <AnalysisSectionCard
      title="分析流程"
      description="从配置任务到查看结果，基础分析保持统一的三段式工作流。"
    >
      <div id="workflow-section" class="grid gap-4 md:grid-cols-2">
        <article
          v-for="step in steps"
          :key="step.title"
          class="rounded-[1.6rem] border border-soft bg-surface-muted p-5 transition hover:border-brand-soft hover:bg-brand-soft-muted"
        >
          <div class="flex items-start gap-4">
            <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-soft text-base font-semibold text-secondary">
              {{ step.index }}
            </div>
            <div class="space-y-3">
              <div class="space-y-1">
                <h3 class="text-lg font-semibold text-primary">{{ step.title }}</h3>
                <p class="text-[11px] font-semibold uppercase tracking-[0.25em] text-muted">
                  {{ step.subtitle }}
                </p>
              </div>
              <p class="text-sm leading-6 text-secondary">
                {{ step.description }}
              </p>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-sm font-semibold text-secondary transition hover:text-primary"
                @click="router.push(step.route)"
              >
                <span>前往执行</span>
                <ArrowSmallRightIcon class="h-4 w-4" />
              </button>
            </div>
          </div>
        </article>
      </div>
    </AnalysisSectionCard>

    <AnalysisSectionCard
      title="分析解读示例"
      description="结果页会以同一套版式展示摘要、图表和关键指标。"
      tone="soft"
    >
      <div class="space-y-6">
        <div class="rounded-[1.75rem] border border-brand-soft bg-brand-soft-muted p-5">
          <div class="mb-4 flex items-center gap-3">
            <div class="flex h-9 w-9 items-center justify-center rounded-2xl bg-brand-500 text-white">
              <SparklesIcon class="h-4 w-4" />
            </div>
            <div class="space-y-1">
              <h3 class="text-base font-semibold text-primary">AI 摘要解读</h3>
              <p class="text-sm text-secondary">重点发现、关键指标和分析维度按照统一摘要卡展示。</p>
            </div>
          </div>

          <div class="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(240px,0.8fr)]">
            <div class="space-y-4">
              <p class="text-sm leading-7 text-secondary">
                “2025 年 9 月 23 日声量达到峰值，讨论主阵地集中在社交媒体；公众最关注健康风险、戒烟建议与成本争议，整体情绪稳定，但医疗负担相关讨论存在潜在负面外溢风险。”
              </p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="id in activeDimensionIds"
                  :key="id"
                  class="analysis-chip rounded-xl border border-soft bg-white text-[11px] text-secondary"
                >
                  # {{ id }}
                </span>
              </div>
            </div>

            <div class="rounded-[1.5rem] border border-white/70 bg-white p-4">
              <p class="text-[11px] font-semibold uppercase tracking-[0.28em] text-muted">核心发现</p>
              <ul class="mt-3 space-y-2 text-sm text-secondary">
                <li class="flex items-center gap-2">
                  <CheckBadgeIcon class="h-4 w-4 text-emerald-600" />
                  <span>峰值时间：9 月 23 日</span>
                </li>
                <li class="flex items-center gap-2">
                  <CheckBadgeIcon class="h-4 w-4 text-emerald-600" />
                  <span>主导渠道：社交平台与自媒体</span>
                </li>
                <li class="flex items-center gap-2">
                  <CheckBadgeIcon class="h-4 w-4 text-emerald-600" />
                  <span>风险主题：医疗成本争议</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <article
            v-for="example in examples"
            :key="example.title"
            class="rounded-[1.5rem] border border-soft bg-white p-4 transition hover:border-brand-soft hover:bg-brand-soft-muted"
          >
            <div class="mb-4 flex items-center justify-between">
              <div class="flex h-10 w-10 items-center justify-center rounded-2xl" :class="example.colorClass">
                <component :is="example.icon" class="h-4 w-4" />
              </div>
              <span class="text-[10px] font-semibold uppercase tracking-[0.28em] text-muted/70">{{ example.id }}</span>
            </div>
            <h4 class="text-sm font-semibold text-primary">{{ example.title }}</h4>
            <p class="mt-2 text-sm leading-6 text-secondary">
              {{ example.description }}
            </p>
          </article>
        </div>
      </div>
    </AnalysisSectionCard>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowSmallRightIcon,
  ChartBarIcon,
  CheckBadgeIcon,
  HeartIcon,
  InformationCircleIcon,
  MapPinIcon,
  PlayIcon,
  SparklesIcon,
  TagIcon
} from '@heroicons/vue/24/solid'
import AnalysisPageHero from '../../../components/analysis/AnalysisPageHero.vue'
import AnalysisSectionCard from '../../../components/analysis/AnalysisSectionCard.vue'

const router = useRouter()

const goToRun = () => {
  router.push({ name: 'project-data-analysis-run' })
}

const scrollToProcess = () => {
  const el = document.getElementById('workflow-section')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const activeDimensions = ['地域分析', '关键词', '趋势洞察', '发布者画像', '情感分析', '声量概览', '话题分类']
const activeDimensionIds = ['Attitude', 'Classification', 'Geography', 'Keywords', 'Publishers', 'Trends', 'Volume']

const primaryAction = computed(() => ({
  label: '立即配置分析任务',
  icon: PlayIcon,
  variant: 'primary',
  onClick: goToRun
}))

const secondaryAction = computed(() => ({
  label: '了解工作流',
  icon: InformationCircleIcon,
  variant: 'secondary',
  onClick: scrollToProcess
}))

const heroHighlights = [
  { title: '声量峰值识别', description: '定位异常时间点与传播高峰。' },
  { title: '多维度特征统计', description: '统一输出趋势、地域、情感、发布者等结果。' },
  { title: 'AI 结果摘要', description: '自动汇总主要发现并与图表对应展示。' }
]

const steps = [
  {
    index: 1,
    title: '运行分析',
    subtitle: '数据生产节点',
    description: '选择专题、配置时间区间与分析维度，触发基础分析流水线。',
    route: { name: 'project-data-analysis-run' }
  },
  {
    index: 2,
    title: '查看结果',
    subtitle: '可视化洞察节点',
    description: '浏览图表、切换模块、查看 AI 摘要，并对比不同时间区间的结果。',
    route: { name: 'project-data-analysis-view' }
  }
]

const examples = [
  {
    id: 'AT',
    title: '情感分析',
    icon: HeartIcon,
    colorClass: 'bg-rose-50 text-rose-600',
    description: '识别公众情绪极性，帮助快速发现潜在的负面风险点。'
  },
  {
    id: 'CL',
    title: '话题分类',
    icon: TagIcon,
    colorClass: 'bg-amber-50 text-amber-600',
    description: '归纳讨论焦点，辅助团队判断议题结构与主要争议方向。'
  },
  {
    id: 'GE',
    title: '地域分析',
    icon: MapPinIcon,
    colorClass: 'bg-emerald-50 text-emerald-600',
    description: '观察传播热点区域与城市分布，识别空间扩散特征。'
  },
  {
    id: 'TR',
    title: '趋势洞察',
    icon: ChartBarIcon,
    colorClass: 'bg-sky-50 text-sky-600',
    description: '跟踪周期波动和舆情拐点，为后续深度分析提供入口。'
  }
]
</script>
