<template>
  <div class="space-y-6 pb-12">
    <section class="relative overflow-hidden rounded-3xl border border-soft bg-surface p-1">
      <div
        class="relative overflow-hidden rounded-[22px] bg-gradient-to-br from-brand-600 via-brand-700 to-indigo-900 px-6 py-10 text-white sm:px-10 sm:py-12"
      >
        <div class="absolute inset-0 overflow-hidden opacity-20 pointer-events-none">
          <div class="absolute -top-1/4 -left-1/4 h-[400px] w-[400px] rounded-full bg-white/30 blur-[100px]"></div>
          <div class="absolute -bottom-1/4 -right-1/4 h-[300px] w-[300px] rounded-full bg-brand-400 blur-[80px]"></div>
        </div>

        <div class="relative z-10 grid gap-8 lg:grid-cols-2 lg:items-center">
          <div class="space-y-6">
            <div class="space-y-2">
              <div
                class="inline-flex items-center rounded-full border border-white/10 bg-white/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-brand-100 backdrop-blur-md"
              >
                Basic Analysis Module
              </div>
              <h1 class="text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
                专题基础分析
              </h1>
              <p class="max-w-xl text-base font-medium leading-relaxed text-brand-50/80">
                面向专题数据的标准分析工作流，聚焦趋势、情感、发布者与地域分布等核心指标，帮助团队快速完成基础洞察。
              </p>
            </div>

            <div class="flex flex-wrap gap-2 text-[10px]">
              <span
                v-for="tag in activeDimensions"
                :key="tag"
                class="rounded-full border border-white/5 bg-white/10 px-3 py-1 font-semibold text-white backdrop-blur-sm"
              >
                {{ tag }}
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-3 pt-2">
              <button
                type="button"
                class="group inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-brand-800 transition-all active:scale-95"
                @click="goToRun"
              >
                <PlayIcon class="h-4 w-4 fill-current" />
                <span class="text-sm font-bold">立即配置分析任务</span>
              </button>

              <button
                type="button"
                class="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-2.5 text-sm text-white transition-all"
                @click="scrollToProcess"
              >
                <InformationCircleIcon class="h-4 w-4" />
                <span>工作流说明</span>
              </button>
            </div>
          </div>

          <div class="hidden lg:block">
            <div class="relative rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-md">
              <h3 class="mb-3 text-xs font-bold text-brand-200">核心分析能力 (Core Capabilities)</h3>
              <ul class="space-y-2.5 text-[13px] text-white/70">
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                  <span>声量趋势与异常峰值识别，快速定位传播拐点</span>
                </li>
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                  <span>情感、地域、发布者等多维统计统一输出</span>
                </li>
                <li class="flex items-start gap-3">
                  <div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></div>
                  <span>AI 摘要联动图表结果，辅助团队快速形成判断</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="workflow-section" class="topic-prep-workflow">
      <header class="topic-prep-workflow__header px-0">
        <h2 class="topic-prep-workflow__title">分析流程</h2>
        <p class="topic-prep-workflow__description">
          从配置任务到查看结果，基础分析保持统一的三段式工作流。
        </p>
      </header>

      <div class="topic-prep-workflow__grid topic-prep-workflow__grid--compact">
        <article
          v-for="step in steps"
          :key="step.title"
          class="topic-prep-workflow__card"
        >
          <div class="topic-prep-workflow__index">{{ step.index }}</div>
          <div class="topic-prep-workflow__body">
            <div class="topic-prep-workflow__meta topic-prep-workflow__meta--tight">
              <h3 class="topic-prep-workflow__step-title">{{ step.title }}</h3>
              <p class="topic-prep-workflow__step-subtitle topic-prep-workflow__step-subtitle--muted text-[11px] tracking-[0.25em]">
                {{ step.subtitle }}
              </p>
            </div>
            <p class="topic-prep-workflow__step-description">{{ step.description }}</p>
          </div>
          <button
            type="button"
            class="topic-prep-workflow__action opacity-100 translate-x-0"
            @click="router.push(step.route)"
          >
            <span>前往执行</span>
            <ArrowSmallRightIcon class="topic-prep-workflow__action-icon" />
          </button>
        </article>
      </div>
    </section>

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
import '../../../assets/topic-preparation-workflow.css'

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
