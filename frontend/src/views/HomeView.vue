<template>
  <div class="mx-auto flex max-w-6xl flex-col gap-28 px-6 pb-24 pt-16 sm:px-10 lg:px-12">
    <section class="rounded-[40px] bg-surface px-10 py-20 text-center shadow-[0_40px_80px_rgba(15,23,42,0.12)]">
      <div class="mx-auto flex max-w-3xl flex-col items-center gap-8">
        <span class="text-xs font-semibold uppercase tracking-[0.35em] text-muted">OpinionSystem</span>
        <h1 class="text-4xl font-semibold tracking-tight text-primary sm:text-5xl md:text-6xl md:leading-tight">
          全链路舆情分析，
          <span class="text-transparent bg-gradient-to-r from-brand-500 via-brand-600 to-brand-400 bg-clip-text">
            一站式分析
          </span>
        </h1>
        <p class="text-lg leading-8 text-secondary">
          从数据采集、智能筛选到多维分析与解读，OpinionSystem 以全功能体验，
          帮助团队快速洞察舆情脉络，沉淀可复用的决策资产。
        </p>
        <div class="flex flex-col gap-4 sm:flex-row">
          <RouterLink
            :to="{ name: 'topic-create-overview' }"
            class="inline-flex items-center justify-center rounded-full bg-primary px-8 py-3 text-sm font-semibold text-surface transition hover:bg-primary/90 focus-ring-accent"
          >
            开始创建专题
          </RouterLink>
          <RouterLink
            :to="{ name: 'project-data' }"
            class="inline-flex items-center justify-center rounded-full border border-soft px-8 py-3 text-sm font-semibold text-primary transition hover:border-brand-soft hover:text-brand-600 focus-ring-accent"
          >
            探索平台能力
          </RouterLink>
        </div>
      </div>
      <div class="mt-16 grid gap-6 sm:grid-cols-3">
        <div
          v-for="stat in stats"
          :key="stat.label"
          class="rounded-[28px] border border-soft/80 bg-surface px-6 py-6 text-left shadow-sm"
        >
          <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">{{ stat.label }}</p>
          <p class="mt-4 text-2xl font-semibold text-primary">{{ stat.value }}</p>
          <p class="mt-2 text-sm text-secondary">{{ stat.detail }}</p>
        </div>
      </div>
    </section>

    <section class="space-y-12">
      <header class="text-center">
        <h2 class="text-3xl font-semibold tracking-tight text-primary sm:text-4xl">
          轻盈界面背后的硬核能力
        </h2>
        <p class="mt-4 text-base leading-7 text-secondary">
          一体化的舆情工作台，覆盖采集、处理、分析、检索与报告输出，每个环节都保持极简界面与可靠的工程能力。
        </p>
      </header>
      <div class="grid gap-10 sm:grid-cols-2">
        <article
          v-for="feature in coreFeatures"
          :key="feature.title"
          class="flex flex-col gap-5 rounded-[32px] bg-base/60 px-8 py-10 shadow-[0_20px_60px_rgba(15,23,42,0.06)] backdrop-blur"
        >
          <component :is="feature.icon" class="h-8 w-8 text-primary" aria-hidden="true" />
          <div class="space-y-3">
            <h3 class="text-xl font-semibold text-primary">{{ feature.title }}</h3>
            <p class="text-sm leading-7 text-secondary">{{ feature.description }}</p>
          </div>
        </article>
      </div>
    </section>

    <section class="space-y-16">
      <header class="text-center">
        <h2 class="text-3xl font-semibold tracking-tight text-primary sm:text-4xl">内容分析 · 精准到字段</h2>
        <p class="mt-4 text-base leading-7 text-secondary">
          内容编码分析引擎以 Qwen-Plus 为核心，支持动态字段建模，自动适配不同专题的数据结构。
        </p>
      </header>
      <div class="grid gap-10 lg:grid-cols-[1.2fr_0.8fr]">
        <div class="space-y-10 rounded-[36px] border border-soft/70 bg-surface px-10 py-12 shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
          <h3 class="text-sm font-semibold uppercase tracking-[0.28em] text-muted">功能亮点</h3>
          <ul class="space-y-4 text-sm leading-7 text-secondary">
            <li
              v-for="feature in contentFeatures"
              :key="feature"
              class="flex items-start gap-3"
            >
              <span class="mt-2 h-1.5 w-1.5 rounded-full bg-primary"></span>
              <span>{{ feature }}</span>
            </li>
          </ul>
          <div class="rounded-[28px] bg-base/70 px-8 py-8">
            <h4 class="text-sm font-semibold uppercase tracking-[0.25em] text-muted">处理流程</h4>
            <div class="mt-6 grid gap-6 sm:grid-cols-2">
              <div
                v-for="step in pipeline"
                :key="step.title"
                class="rounded-[24px] bg-surface px-5 py-5 shadow-sm"
              >
                <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ step.step }}</p>
                <p class="mt-2 text-base font-semibold text-primary">{{ step.title }}</p>
                <p class="mt-2 text-xs leading-6 text-secondary">{{ step.description }}</p>
              </div>
            </div>
          </div>
        </div>
        <aside class="space-y-8 rounded-[36px] border border-soft/70 bg-gradient-to-b from-base/80 via-surface to-base px-10 py-12 shadow-[0_24px_60px_rgba(15,23,42,0.06)]">
          <h3 class="text-sm font-semibold uppercase tracking-[0.28em] text-muted">控烟专题示例</h3>
          <ul class="space-y-3 text-sm leading-7 text-secondary">
            <li
              v-for="dimension in contentDimensions"
              :key="dimension"
              class="flex items-start gap-3"
            >
              <span class="mt-1 flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                ✓
              </span>
              <span>{{ dimension }}</span>
            </li>
          </ul>
        </aside>
      </div>
    </section>

    <section class="space-y-16">
      <header class="text-center">
        <h2 class="text-3xl font-semibold tracking-tight text-primary sm:text-4xl">智能解读 · AI 级洞察官</h2>
        <p class="mt-4 text-base leading-7 text-secondary">
          将 Qwen-Plus 与 TagRAG 知识库深度融合，为每个专题输出可信赖的专业分析报告。
        </p>
      </header>
      <div class="grid gap-10 lg:grid-cols-[1.1fr_0.9fr]">
        <div class="space-y-8 rounded-[36px] border border-soft/70 bg-surface px-10 py-12 shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
          <h3 class="text-sm font-semibold uppercase tracking-[0.28em] text-muted">系统特性</h3>
          <div class="grid gap-6 sm:grid-cols-2">
            <article
              v-for="feature in interpretationFeatures"
              :key="feature.title"
              class="rounded-[28px] bg-base/70 px-6 py-6 shadow-sm"
            >
              <h4 class="text-base font-semibold text-primary">{{ feature.title }}</h4>
              <p class="mt-3 text-sm leading-7 text-secondary">{{ feature.description }}</p>
            </article>
          </div>
        </div>
        <aside class="space-y-6 rounded-[36px] border border-soft/70 bg-base/70 px-10 py-12 shadow-[0_24px_60px_rgba(15,23,42,0.06)]">
          <h3 class="text-sm font-semibold uppercase tracking-[0.28em] text-muted">解读维度</h3>
          <ul class="grid gap-3 sm:grid-cols-2">
            <li
              v-for="dimension in interpretationDimensions"
              :key="dimension"
              class="rounded-[24px] bg-surface px-4 py-3 text-sm text-secondary shadow-sm"
            >
              {{ dimension }}
            </li>
          </ul>
        </aside>
      </div>
    </section>
  </div>
</template>

<script setup>
import {
  BoltIcon,
  ChartBarIcon,
  CloudArrowUpIcon,
  CpuChipIcon,
  DocumentChartBarIcon,
  MagnifyingGlassCircleIcon
} from '@heroicons/vue/24/outline'
import { RouterLink } from 'vue-router'

const stats = [
  { label: 'THROUGHPUT', value: '舆论流体力学', detail: '传播趋势洞察' },
  { label: 'RETRIEVAL', value: 'GraphRAG + Vector', detail: '双引擎智能检索' },
  { label: 'PROJECTS', value: '10+ 专题', detail: '多专题并行调度' }
]

const coreFeatures = [
  {
    title: '自动化数据流水线',
    description: '采集、清洗、入库全流程自动化，保障数据质量与时效性。',
    icon: CloudArrowUpIcon
  },
  {
    title: 'AI 智能筛选',
    description: 'Qwen 驱动的相关度筛选与内容分类，替你过滤噪声信息。',
    icon: CpuChipIcon
  },
  {
    title: '多维度分析',
    description: '情感、地域、趋势、关键词等多维指标一站式呈现。',
    icon: ChartBarIcon
  },
  {
    title: '可视化洞察输出',
    description: '自动生成高层可读的图表与摘要报告，支持导出复用。',
    icon: DocumentChartBarIcon
  },
  {
    title: '智能解读引擎',
    description: 'TagRAG 背景知识结合大模型，为舆情团队提供深度观点。',
    icon: BoltIcon
  },
  {
    title: '多形态智能检索',
    description: 'GraphRAG 与向量检索协同，精准定位关键内容与证据。',
    icon: MagnifyingGlassCircleIcon
  }
]

const contentFeatures = [
  '动态字段适配，自动识别不同专题的 JSON 结构',
  '基于 Qwen-Plus 的高准确度内容编码',
  '支持 50 QPS 的批量处理吞吐，为新闻热点实时赋码',
  'Excel 与 JSON 双形态输出，方便复盘与二次建模'
]

const pipeline = [
  {
    step: '01',
    title: '多源接入',
    description: '对接社交媒体、新闻站点与行业数据库，实时聚合舆情。'
  },
  {
    step: '02',
    title: '结构化清洗',
    description: '字段规范、去重、噪声剔除，保持数据纯净度。'
  },
  {
    step: '03',
    title: '智能编码',
    description: 'Qwen-Plus 自动完成内容标签化与维度映射。'
  },
  {
    step: '04',
    title: '指标渲染',
    description: '生成多维指标，为下一步解读与检索打好基础。'
  }
]

const contentDimensions = [
  '信息类别：控烟立场 / 烟草立场 / 其他',
  '议题编码：1-1 烟草与健康、1-2 无烟立法等',
  '信源编码：卫生部门、媒体自采、意见领袖等',
  '报道体裁：事实性报道、观点性报道、深度综合',
  '诉求方式：恐怖诉求、人性诉求、行动呼吁等'
]

const interpretationFeatures = [
  {
    title: 'AI 深度解读',
    description: '多角度洞察舆情变化，自动生成结构化结论。'
  },
  {
    title: 'TagRAG 背景召回',
    description: '召回权威资料与历史案例，构建可信赖的分析上下文。'
  },
  {
    title: '高并发处理',
    description: '支持 50 并发解读请求，多专题同步推进无压力。'
  },
  {
    title: '全链路追踪',
    description: '内置质量监控与日志记录，确保结论可追溯、可复盘。'
  }
]

const interpretationDimensions = [
  '情感分析（attitude）',
  '话题分类（classification）',
  '地域分析（geography）',
  '关键词分析（keywords）',
  '发布者分析（publishers）',
  '趋势分析（trends）',
  '声量分析（volume）',
  '内容分析（contentanalyze）'
]
</script>
