<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface border p-1">
      <div class="rounded-[1.6rem] bg-brand-soft-muted px-6 py-10 sm:px-8 sm:py-12">
        <div class="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(300px,0.9fr)] lg:items-center">
          <div class="space-y-5">
            <div class="space-y-2">
              <div class="inline-flex items-center rounded-full border border-brand-soft bg-surface px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-brand-700">
                Media Tagging
              </div>
              <h1 class="text-3xl font-semibold tracking-tight text-primary sm:text-4xl">
                媒体识别与打标
              </h1>
              <p class="max-w-2xl text-base leading-7 text-secondary">
                先从原始语料里稳定整理出媒体候选名单，再由人工确认“官方媒体”与“地方媒体”标签，
                让后续 tools 直接读取可维护、可追溯的媒体资产。
              </p>
            </div>

            <div class="flex flex-wrap gap-2">
              <span
                v-for="tag in introTags"
                :key="tag"
                class="inline-flex items-center rounded-full border border-soft bg-surface px-3 py-1 text-xs font-medium text-secondary"
              >
                {{ tag }}
              </span>
            </div>

            <div class="flex flex-wrap gap-3 pt-1">
              <button
                type="button"
                class="btn-primary inline-flex items-center gap-2 rounded-full px-5 py-2.5"
                @click="router.push({ name: 'analysis-media-tagging-run' })"
              >
                <PlayIcon class="h-4 w-4" />
                <span>开始识别</span>
              </button>
              <button
                type="button"
                class="btn-secondary inline-flex items-center gap-2 rounded-full px-5 py-2.5"
                @click="scrollToWorkflow"
              >
                <InformationCircleIcon class="h-4 w-4" />
                <span>查看流程</span>
              </button>
            </div>
          </div>

          <div class="mute-card-surface space-y-4 p-5">
            <div class="space-y-1">
              <p class="text-xs font-semibold uppercase tracking-[0.28em] text-muted">V1 输出重点</p>
              <h2 class="text-lg font-semibold text-primary">先把名单整理准，再谈下游消费</h2>
            </div>
            <ul class="space-y-3 text-sm leading-6 text-secondary">
              <li class="flex items-start gap-3">
                <span class="mt-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-surface text-brand-700">
                  <CheckBadgeIcon class="h-4 w-4" />
                </span>
                <span>按发布量默认排序，优先处理最值得确认的媒体候选。</span>
              </li>
              <li class="flex items-start gap-3">
                <span class="mt-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-surface text-brand-700">
                  <CheckBadgeIcon class="h-4 w-4" />
                </span>
                <span>沉淀共享媒体字典，统一名称、别名和标签口径。</span>
              </li>
              <li class="flex items-start gap-3">
                <span class="mt-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-surface text-brand-700">
                  <CheckBadgeIcon class="h-4 w-4" />
                </span>
                <span>专题结果只向 tools 提供“已标记媒体”，避免未确认候选混入消费链路。</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <section id="workflow-section" class="scroll-mt-6">
      <AnalysisSectionCard
        title="三段式流程"
        description="入口、运行和结果页都沿用现有分析模块的工作方式，减少学习成本。"
      >
        <div class="grid gap-4 lg:grid-cols-3">
          <article
            v-for="step in steps"
            :key="step.title"
            class="card-surface px-5 py-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="space-y-2">
                <div class="inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-brand-soft text-brand-700">
                  <component :is="step.icon" class="h-4 w-4" />
                </div>
                <div>
                  <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">{{ step.eyebrow }}</p>
                  <h3 class="mt-1 text-lg font-semibold text-primary">{{ step.title }}</h3>
                </div>
              </div>
              <span class="text-sm font-semibold text-brand-700">0{{ step.index }}</span>
            </div>
            <p class="mt-4 text-sm leading-6 text-secondary">{{ step.description }}</p>
            <button
              type="button"
              class="analysis-toolbar__action analysis-toolbar__action--ghost mt-5"
              @click="router.push(step.route)"
            >
              <span>前往 {{ step.title }}</span>
              <ArrowRightIcon class="h-4 w-4" />
            </button>
          </article>
        </div>
      </AnalysisSectionCard>
    </section>

    <AnalysisSectionCard
      title="结果会产出什么"
      description="V1 以表格维护台为主，先把候选名单、样本和标签资产沉淀下来。"
      tone="soft"
    >
      <div class="grid gap-4 lg:grid-cols-2">
        <article class="card-surface px-5 py-5">
          <div class="flex items-center gap-3">
            <div class="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-surface text-brand-700">
              <TableCellsIcon class="h-5 w-5" />
            </div>
            <div>
              <h3 class="text-base font-semibold text-primary">专题候选列表</h3>
              <p class="text-sm text-secondary">按发布量排序查看候选媒体、样本标题和来源平台。</p>
            </div>
          </div>
          <ul class="mt-4 space-y-2 text-sm text-secondary">
            <li>字段固定：媒体名、发布量、命中字典、当前标签、样本数、最近发布时间、平台与样本。</li>
            <li>支持筛选“官方媒体 / 地方媒体 / 未标记”，先处理高频候选。</li>
            <li>单条和批量保存都只会写回本次专题范围内的识别结果。</li>
          </ul>
        </article>

        <article class="card-surface px-5 py-5">
          <div class="flex items-center gap-3">
            <div class="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-surface text-brand-700">
              <BookOpenIcon class="h-5 w-5" />
            </div>
            <div>
              <h3 class="text-base font-semibold text-primary">共享媒体字典</h3>
              <p class="text-sm text-secondary">统一维护正式名称、别名、标签和备注说明。</p>
            </div>
          </div>
          <ul class="mt-4 space-y-2 text-sm text-secondary">
            <li>识别阶段只做确定性匹配，不自动替你判断媒体属性。</li>
            <li>已确认的字典条目会持续复用到后续专题识别结果里。</li>
            <li>后续 tools 优先读取专题内已标记媒体，必要时再补查共享字典。</li>
          </ul>
        </article>
      </div>
    </AnalysisSectionCard>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  ArrowRightIcon,
  BookOpenIcon,
  CheckBadgeIcon,
  InformationCircleIcon,
  PlayIcon,
  Squares2X2Icon,
  TableCellsIcon,
  ViewfinderCircleIcon
} from '@heroicons/vue/24/solid'
import AnalysisSectionCard from '../../../components/analysis/AnalysisSectionCard.vue'

const router = useRouter()

const introTags = ['共享媒体字典', '专题级结果', '人工确认标签', '按发布量排序', 'tools 可直接消费']

const steps = [
  {
    index: 1,
    eyebrow: 'Overview',
    title: '流程概览',
    description: '先了解标签口径、结果结构和后续消费方式，再进入识别流程。',
    route: { name: 'analysis-media-tagging' },
    icon: Squares2X2Icon
  },
  {
    index: 2,
    eyebrow: 'Run',
    title: '运行识别',
    description: '选择专题与时间范围，启动后台任务，从原始语料里整理媒体候选。',
    route: { name: 'analysis-media-tagging-run' },
    icon: ViewfinderCircleIcon
  },
  {
    index: 3,
    eyebrow: 'Results',
    title: '查看结果',
    description: '默认按发布量排序维护候选列表，并把确认后的标签沉淀进共享字典。',
    route: { name: 'analysis-media-tagging-view' },
    icon: TableCellsIcon
  }
]

const scrollToWorkflow = () => {
  const section = document.getElementById('workflow-section')
  if (section) {
    section.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>
