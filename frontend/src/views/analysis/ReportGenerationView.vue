<template>
  <section class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-3 text-sm text-secondary">
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-brand-600">
          <SparklesIcon class="h-4 w-4" />
          <span>报告解读</span>
        </span>
        <ChevronRightIcon class="h-4 w-4 text-muted" />
        <span class="text-secondary">九三阅兵舆情报告</span>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
          <ClockIcon class="h-4 w-4" />
          {{ reportMeta.rangeText }}
        </span>
        <span class="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
          <BoltIcon class="h-4 w-4" />
          AI生成分析
        </span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.3em] text-muted">专题</p>
          <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ reportMeta.title }}</h1>
          <p class="text-sm text-secondary">
            数据区间：{{ filters.start }} → {{ filters.end }} · 最近更新：{{ reportMeta.lastUpdated }}
          </p>
          <p class="text-sm text-slate-500">{{ reportMeta.subtitle }}</p>
        </div>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full border border-soft bg-white px-4 py-2 text-sm font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-700 focus-ring-accent"
            :disabled="loading"
            @click="handleRefresh"
          >
            <ArrowPathIcon class="h-4 w-4" :class="loading ? 'animate-spin text-brand-600' : ''" />
            <span>{{ loading ? '刷新中…' : '刷新数据' }}</span>
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-brand/90 focus-ring-accent"
            @click="handleRegenerate"
          >
            <SparklesIcon class="h-4 w-4" />
            <span>重新生成</span>
          </button>
        </div>
      </div>
      <div class="grid gap-4 lg:grid-cols-[1.2fr,1fr]">
        <label class="space-y-1 text-secondary">
          <span class="text-xs font-semibold text-muted">专题</span>
          <input v-model="filters.topic" type="text" class="input" placeholder="九三阅兵" />
        </label>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="space-y-1 text-secondary">
            <span class="text-xs font-semibold text-muted">开始日期</span>
            <input v-model="filters.start" type="date" class="input" />
          </label>
          <label class="space-y-1 text-secondary">
            <span class="text-xs font-semibold text-muted">结束日期</span>
            <input v-model="filters.end" type="date" class="input" />
          </label>
        </div>
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">分析概览</p>
          <h3 class="text-lg font-semibold text-primary">核心指标</h3>
        </div>
        <span class="text-xs text-muted">全渠道统计摘要</span>
      </header>
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article class="flex flex-col gap-3 rounded-2xl border border-soft bg-surface p-5 shadow-sm">
          <div class="flex items-start justify-between gap-2">
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">总声量</p>
            <span class="rounded-full bg-brand-soft px-2 py-1 text-xs font-semibold text-brand-700">全渠道</span>
          </div>
          <p class="text-3xl font-semibold text-primary">{{ kpiMetrics.totalVolume }}</p>
          <p class="text-sm text-secondary">覆盖全渠道有效数据</p>
        </article>

        <article class="flex flex-col gap-3 rounded-2xl border border-soft bg-surface p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">峰值</p>
          <div class="flex items-center gap-6">
            <div class="rounded-2xl bg-orange-50 px-3 py-2">
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-orange-600">峰值日</p>
              <p class="text-2xl font-semibold text-orange-700">{{ kpiMetrics.peakDate }}</p>
            </div>
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">峰值声量</p>
              <p class="text-3xl font-semibold text-primary">{{ kpiMetrics.peakValue }}</p>
            </div>
          </div>
          <p class="text-sm text-secondary">高潮爆发期</p>
        </article>

        <article class="flex flex-col gap-3 rounded-2xl border border-soft bg-surface p-5 shadow-sm">
          <div class="flex items-start justify-between gap-2">
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">情感</p>
            <span class="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">正向为主</span>
          </div>
          <p class="text-2xl font-semibold text-primary">{{ formatRate(kpiMetrics.positiveRate) }} 正向</p>
          <div class="flex flex-wrap gap-2 text-xs font-semibold">
            <span class="rounded-full bg-amber-50 px-2 py-1 text-amber-700">
              中性 {{ formatRate(kpiMetrics.neutralRate) }}
            </span>
            <span class="rounded-full bg-rose-50 px-2 py-1 text-rose-700">
              负面 {{ formatRate(kpiMetrics.negativeRate) }}
            </span>
          </div>
          <div class="flex h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div class="h-full bg-emerald-500" :style="{ width: `${kpiMetrics.positiveRate * 100}%` }"></div>
            <div class="h-full bg-amber-400" :style="{ width: `${kpiMetrics.neutralRate * 100}%` }"></div>
            <div class="h-full bg-rose-500" :style="{ width: `${kpiMetrics.negativeRate * 100}%` }"></div>
          </div>
        </article>

        <article class="flex flex-col gap-3 rounded-2xl border border-soft bg-surface p-5 shadow-sm">
          <div class="flex items-start justify-between gap-2">
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">内容结构</p>
            <span class="rounded-full bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700">报道为主</span>
          </div>
          <p class="text-2xl font-semibold text-primary">{{ formatRate(kpiMetrics.factualRatio) }} 报道</p>
          <div class="flex flex-wrap gap-2 text-xs font-semibold">
            <span class="rounded-full bg-sky-50 px-2 py-1 text-sky-700">
              报道 {{ formatRate(kpiMetrics.factualRatio) }}
            </span>
            <span class="rounded-full bg-indigo-50 px-2 py-1 text-indigo-700">
              评论观点 {{ formatRate(kpiMetrics.opinionRatio) }}
            </span>
          </div>
          <div class="flex h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div class="h-full bg-sky-500" :style="{ width: `${kpiMetrics.factualRatio * 100}%` }"></div>
            <div class="h-full bg-indigo-500" :style="{ width: `${kpiMetrics.opinionRatio * 100}%` }"></div>
          </div>
        </article>
      </div>
    </section>

    <section class="grid gap-6 xl:grid-cols-3">
      <AnalysisChartPanel
        title="渠道声量分布"
        description="全渠道声量覆盖：官方媒体定调，社交媒体扩散"
        :option="channelChartOption"
        :has-data="hasChannelData"
      />
      <AnalysisChartPanel
        title="情感态度"
        description="正向与中性情绪占比超九成"
        :option="sentimentChartOption"
        :has-data="hasSentimentData"
      />
      <AnalysisChartPanel
        title="内容结构"
        description="报道事实为主，评论观点补充引导"
        :option="contentSplitOption"
        :has-data="hasContentSplitData"
      />
    </section>

    <section class="grid gap-6 xl:grid-cols-[2fr,1fr]">
      <AnalysisChartPanel
        title="时间趋势"
        description="预热→爆发→余热的四阶段曲线"
        :option="trendChartOption"
        :has-data="hasTrendData"
      />
      <article class="card-surface space-y-4 p-5">
        <header class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand-700">
              <CalendarIcon class="h-5 w-5" />
            </div>
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">关键节点</p>
              <p class="text-base font-semibold text-primary">传播节奏</p>
            </div>
          </div>
          <span class="text-xs text-muted">按阶段拆分</span>
        </header>
        <ul class="space-y-3 text-sm text-secondary">
          <li
            v-for="stage in report.stageNotes"
            :key="stage.title"
            class="rounded-2xl border border-soft bg-surface p-3 shadow-sm"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <span class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-brand-600/10 text-brand-700">
                  {{ stage.badge }}
                </span>
                <div>
                  <p class="text-sm font-semibold text-primary">{{ stage.title }}</p>
                  <p class="text-xs text-muted">{{ stage.range }}</p>
                </div>
              </div>
              <span class="text-xs font-semibold text-brand-700">{{ stage.delta }}</span>
            </div>
            <p class="mt-1 text-secondary">{{ stage.highlight }}</p>
          </li>
        </ul>
      </article>
    </section>

    <section class="grid gap-6 xl:grid-cols-2">
      <AnalysisChartPanel
        title="关键词热度"
        description="事件主线、装备亮点与外交议题并行"
        :option="keywordChartOption"
        :has-data="hasKeywordData"
      />
      <AnalysisChartPanel
        title="主题分布"
        description="历史叙事与国际政治形成双核心"
        :option="themeChartOption"
        :has-data="hasThemeData"
      />
    </section>

    <section class="card-surface space-y-5 p-6">
      <header class="flex items-center justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">洞察解读</p>
          <h3 class="text-lg font-semibold text-primary">重点结论</h3>
        </div>
        <span class="text-xs text-muted">根据结构化数据生成</span>
      </header>
      <article class="relative overflow-hidden rounded-3xl border border-brand-soft bg-gradient-to-br from-brand-50 via-white to-white p-6">
        <div class="absolute -top-16 right-0 h-44 w-44 rounded-full bg-brand-200/40 blur-3xl"></div>
        <div class="relative space-y-3">
          <span class="inline-flex items-center rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-700">
            洞察亮点
          </span>
          <ul class="space-y-2 text-base text-secondary">
            <li class="flex gap-2">
              <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
              <span>整体呈现“官方媒体定调、社交平台扩散、视听平台赋能”的多级传播格局。</span>
            </li>
            <li class="flex gap-2">
              <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
              <span>声量高峰与关键节点高度耦合，体现精准传播节奏</span>
            </li>
            <li class="flex gap-2">
              <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
              <span>声量峰值与重大时间节点密切相关。</span>
            </li>
            <li class="flex gap-2">
              <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
              <span>整体实现“硬实力展示”与“软性情感动员”的有机平衡。</span>
            </li>
          </ul>
        </div>
      </article>
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="insight in report.insights"
          :key="insight.title"
          class="h-full rounded-2xl border border-soft bg-surface p-4 shadow-sm"
        >
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ insight.title }}</p>
          <p class="mt-2 text-base font-semibold text-primary">{{ insight.headline }}</p>
          <ul class="mt-3 space-y-2 text-sm text-secondary">
            <li
              v-for="(point, idx) in insight.points"
              :key="`${insight.title}-${idx}`"
              class="flex gap-2"
            >
              <span class="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
              <span class="leading-relaxed">{{ point }}</span>
            </li>
          </ul>
        </article>
      </div>
    </section>

    <section class="card-surface space-y-4 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">导出与归档</p>
          <h3 class="text-lg font-semibold text-primary">报告交付</h3>
          <p class="text-sm text-secondary">导出报告分析，分为可视化 HTML 版本和专业 DOCX 文档分析版本。</p>
        </div>
      </header>
      <div class="flex flex-wrap items-center justify-end gap-3">
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-soft bg-white px-4 py-2 text-sm font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-700 focus-ring-accent"
          @click="handleSaveTemplate"
        >
          <BookmarkIcon class="h-4 w-4" />
          <span>保存为模板</span>
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-soft bg-white px-4 py-2 text-sm font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-700 focus-ring-accent"
        >
          <DocumentTextIcon class="h-4 w-4" />
          <span>导出详细 DOCX 报告</span>
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-brand/90 focus-ring-accent"
          :disabled="exporting"
          @click="exportHtmlReport"
        >
          <ArrowDownTrayIcon class="h-4 w-4" />
          <span>{{ exporting ? '导出中…' : '导出 HTML 报告' }}</span>
        </button>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  BoltIcon,
  BookmarkIcon,
  CalendarIcon,
  ChevronRightIcon,
  ClockIcon,
  DocumentTextIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'
import AnalysisChartPanel from '../../components/AnalysisChartPanel.vue'

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '暂无'
  return new Intl.NumberFormat('zh-CN').format(Number(value))
}

const clampRate = (value) => {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return 0
  return Math.min(1, Math.max(0, numeric))
}

const formatRate = (value) => `${(clampRate(value) * 100).toFixed(1)}%`

const filters = reactive({
  topic: '九三阅兵',
  start: '2025-09-01',
  end: '2025-09-10'
})

const createMockReport = () => ({
  title: '九三阅兵舆情分析报告',
  subtitle: '重点解读：新闻、社交媒体与短视频多端联动，形成预热、爆发、余热的全周期传播。',
  rangeText: '2025-09-01 → 2025-09-10',
  lastUpdated: '2025-09-10 18:00',
  metrics: {
    totalVolume: 15498,
    peak: {
      value: 5908,
      date: '9月3日'
    },
    positiveRate: 0.461,
    neutralRate: 0.455,
    factualRatio: 0.575
  },
  channels: [
    { name: '新闻', value: 6487 },
    { name: '推特', value: 3540 },
    { name: '脸书', value: 2978 },
    { name: '油管', value: 1596 },
    { name: '照片墙', value: 400 },
    { name: 'TikTok', value: 377 },
    { name: 'Telegram', value: 120 }
  ],
  timeline: [
    { date: '9月1日', value: 459 },
    { date: '9月2日', value: 1687 },
    { date: '9月3日', value: 5908 },
    { date: '9月4日', value: 2669 },
    { date: '9月5日', value: 1900 },
    { date: '9月6日', value: 1400 },
    { date: '9月7日', value: 980 },
    { date: '9月8日', value: 709 },
    { date: '9月9日', value: 620 },
    { date: '9月10日', value: 515 }
  ],
  sentiment: {
    positive: 7152,
    neutral: 7053,
    negative: 1293
  },
  contentSplit: {
    factual: 8908,
    opinion: 6590
  },
  keywords: [
    { term: '九三閱兵', value: 16343 },
    { term: '九三阅兵', value: 8006 },
    { term: '阅兵', value: 5024 },
    { term: '东风', value: 1602 },
    { term: '2025', value: 1442 },
    { term: '金正恩', value: 1144 },
    { term: '9月3日', value: 1570 },
    { term: 'China', value: 922 },
    { term: '中共', value: 1529 }
  ],
  themes: [
    { name: '阅兵与历史叙事', value: 6351 },
    { name: '国际政治与外交', value: 3018 },
    { name: '社会治理与舆论', value: 602 },
    { name: '经济与市场反应', value: 104 },
    { name: '社会运动与抗议', value: 144 },
    { name: '军事技术与战略', value: 36 }
  ],
  stageNotes: [
    {
      title: '筹备预热期',
      range: '9月1日到9月2日',
      delta: '增幅达267%',
      highlight: '声量由459迅速攀升至1687，显示官方媒体提前释放信息（如阅兵预告、彩排画面、嘉宾名单等）有效激发公众期待。此阶段讨论聚焦于“历史意义回顾”“参演部队揭秘”和“外宾出席情况”，社交媒体出现话题标签如#九三阅兵倒计时#，形成初步议程引导。',
      badge: 'P1'
    },
    {
      title: '高潮爆发期',
      range: '9月3日',
      delta: '近40%峰值',
      highlight: '当日声量飙升至5908，为峰值，占全周期总声量的近40%，体现阅兵仪式当天的集中关注。这一峰值由多重关键事件叠加驱动：上午举行的正式阅兵式直播、领导人重要讲话、新型武器装备首次公开亮相、主流媒体同步推出重磅评论文章（如《人民日报》头版社论《铭记历史，开创未来》）。视频平台实时弹幕互动活跃，“东风-XX”“空中梯队压轴机型”等成为热搜词，形成现象级传播。',
      badge: 'P2'
    },
    {
      title: '总结回顾与余热期',
      range: '9月4日到9月10日',
      delta: '阶梯式回落',
      highlight: '声量自2669开始阶梯式回落，至9月10日稳定在515，约为峰值的8.7%。此阶段议题转向深度解读，包括专家分析军事战略意义、外媒报道汇总、民间“阅兵感动瞬间”图文集锦、青少年爱国主义教育延伸讨论。值得注意的是，9月8日出现小幅回升（709），可能与权威媒体发布完整版阅兵纪录片或重要人物专访有关，显示优质内容仍能激活次生传播。',
      badge: 'P3'
    }
  ],
  insights: [
    {
      title: '声量',
      headline: '主流媒体定调，社交平台扩散',
      points: [
        '新闻渠道 6487，占比 35.7%，形成权威议程设置。',
        '推特与脸书合计 6518，覆盖海外信息窗口。',
        '短视频（TikTok 377、照片墙 400）放大装备与情感瞬间。',
        '油管 1596 贡献长视频回放，支撑二次传播。',
        'Telegram 120 维持小众圈层聚合。'
      ]
    },
    {
      title: '趋势',
      headline: '预热、引爆、沉淀的全周期节奏',
      points: [
        '9月3日峰值占全周期近 40%，与重要仪式高度耦合。',
        '9月8日纪录片发布带来 709 的次高点，证明优质长尾内容的激活力。',
        '峰值后 7 天内声量回落 91.3%，节奏控制有效。'
      ]
    },
    {
      title: '态度',
      headline: '正向 46.1%，中性 45.5%，舆情稳定',
      points: [
        '正面情绪聚焦“强军形象”“历史记忆”，情感基调稳健。',
        '负面 8.4%，主要来自外部地缘政治猜疑与成本讨论。',
        '青年圈层触达度有限，短视频声量偏低需加强。'
      ]
    },
    {
      title: '关键词',
      headline: '历史符号与装备亮点并行',
      points: [
        '“九三阅兵”系列词汇总热度超 2.4 万，事件识别度极高。',
        '“东风”“金正恩”等词反映军事展示与外交关联的双重关注。',
        '“中共”出现次数多，话语呈现政治化。'
      ]
    },
    {
      title: '主题',
      headline: '历史叙事 + 国际政治构成双核心',
      points: [
        '历史叙事与国际政治占比约 76%，形成内外话语闭环。',
        '社会治理与舆论 602 体现公众参与与情绪表达的中腰部关注。',
        '边缘主题（经济、军技、抗议）体量小但敏感度高。'
      ]
    },
    {
      title: '建议',
      headline: '增强温度与外宣协同',
      points: [
        '增加老兵口述、家庭记忆等人文内容，补足情感侧。',
        '在海外社交平台设置“共同守护战后秩序”等议题框架。',
        '针对青年圈层推出二创素材包，提升短视频渗透。'
      ]
    }
  ]
})

const report = ref(createMockReport())
const loading = ref(false)
const exporting = ref(false)

const reportMeta = computed(() => ({
  title: report.value?.title || '报告',
  subtitle: report.value?.subtitle || '',
  rangeText: report.value?.rangeText || `${filters.start} → ${filters.end}`,
  lastUpdated: report.value?.lastUpdated || '未提供'
}))

const kpiMetrics = computed(() => {
  const metrics = report.value?.metrics || {}
  const peak = metrics.peak || { value: 0, date: '未提供' }
  const positiveRate = clampRate(metrics.positiveRate || 0)
  const neutralRate = clampRate(metrics.neutralRate || 0)
  const negativeRate = Math.max(0, 1 - positiveRate - neutralRate)
  const factualRatio = clampRate(metrics.factualRatio || 0)
  const opinionRatio = Math.max(0, 1 - factualRatio)
  return {
    totalVolume: formatNumber(metrics.totalVolume || 0),
    peakValue: formatNumber(peak.value || 0),
    peakDate: peak.date || '未提供',
    positiveRate,
    neutralRate,
    negativeRate,
    factualRatio,
    opinionRatio
  }
})

const hasChannelData = computed(() => Array.isArray(report.value.channels) && report.value.channels.length > 0)
const hasTrendData = computed(() => Array.isArray(report.value.timeline) && report.value.timeline.length > 0)
const hasSentimentData = computed(() => Boolean(report.value.sentiment))
const hasContentSplitData = computed(() => Boolean(report.value.contentSplit))
const hasKeywordData = computed(() => Array.isArray(report.value.keywords) && report.value.keywords.length > 0)
const hasThemeData = computed(() => Array.isArray(report.value.themes) && report.value.themes.length > 0)

const buildBarColors = ['#6366f1', '#8b5cf6', '#0ea5e9', '#22c55e', '#f97316', '#e11d48', '#334155']

const channelChartOption = computed(() => {
  const sorted = [...(report.value.channels || [])].sort((a, b) => b.value - a.value)
  return {
    color: buildBarColors,
    tooltip: { trigger: 'axis' },
    grid: { left: 80, right: 20, bottom: 20, top: 20 },
    xAxis: { type: 'value', axisLabel: { color: '#475569' } },
    yAxis: {
      type: 'category',
      data: sorted.map((item) => item.name),
      inverse: true,
      axisLabel: { color: '#475569' }
    },
    series: [
      {
        type: 'bar',
        data: sorted.map((item) => item.value),
        barWidth: 20,
        itemStyle: { borderRadius: [6, 6, 6, 6] },
        label: { show: true, position: 'right', color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const trendChartOption = computed(() => ({
  color: ['#6366f1'],
  tooltip: { trigger: 'axis' },
  grid: { left: 60, right: 30, bottom: 40, top: 20 },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: (report.value.timeline || []).map((item) => item.date),
    axisLabel: { color: '#475569' }
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#475569' },
    splitLine: { lineStyle: { color: '#e2e8f0' } }
  },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      data: (report.value.timeline || []).map((item) => item.value),
      areaStyle: { color: 'rgba(99,102,241,0.12)' },
      lineStyle: { width: 3 }
    }
  ]
}))

const sentimentChartOption = computed(() => ({
  color: ['#22c55e', '#f97316', '#e11d48'],
  tooltip: { trigger: 'item' },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      label: { formatter: '{b}\n{d}%' },
      data: [
        { name: '正面', value: report.value.sentiment?.positive ?? 0 },
        { name: '中性', value: report.value.sentiment?.neutral ?? 0 },
        { name: '负面', value: report.value.sentiment?.negative ?? 0 }
      ]
    }
  ]
}))

const contentSplitOption = computed(() => ({
  color: ['#0ea5e9', '#6366f1'],
  tooltip: { trigger: 'item' },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      label: { formatter: '{b}\n{d}%' },
      data: [
        { name: '报道事实', value: report.value.contentSplit?.factual ?? 0 },
        { name: '评论观点', value: report.value.contentSplit?.opinion ?? 0 }
      ]
    }
  ]
}))

const keywordChartOption = computed(() => {
  const sorted = [...(report.value.keywords || [])].sort((a, b) => b.value - a.value).slice(0, 8)
  return {
    color: ['#6366f1'],
    tooltip: { trigger: 'axis' },
    grid: { left: 120, right: 40, bottom: 20, top: 20 },
    xAxis: { type: 'value', axisLabel: { color: '#475569' } },
    yAxis: {
      type: 'category',
      data: sorted.map((item) => item.term),
      inverse: true,
      axisLabel: { color: '#475569' }
    },
    series: [
      {
        type: 'bar',
        data: sorted.map((item) => item.value),
        barWidth: 16,
        itemStyle: { borderRadius: [6, 6, 6, 6] },
        label: { show: true, position: 'right', color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const themeChartOption = computed(() => ({
  color: ['#8b5cf6'],
  tooltip: { trigger: 'axis' },
  grid: { left: 60, right: 20, bottom: 40, top: 20 },
  xAxis: {
    type: 'category',
    data: (report.value.themes || []).map((item) => item.name),
    axisLabel: { color: '#475569', interval: 0, rotate: 18 }
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#475569' },
    splitLine: { lineStyle: { color: '#e2e8f0' } }
  },
  series: [
    {
      type: 'bar',
      data: (report.value.themes || []).map((item) => item.value),
      barWidth: 22,
      itemStyle: { borderRadius: [6, 6, 6, 6] },
      label: { show: true, position: 'top', color: '#0f172a', fontWeight: 600 }
    }
  ]
}))

const integrationHooks = {
  fetchReport: null,
  regenerateReport: null,
  exportReport: null
}

const handleRefresh = async () => {
  loading.value = true
  try {
    if (typeof integrationHooks.fetchReport === 'function') {
      const nextReport = await integrationHooks.fetchReport({ ...filters })
      if (nextReport) {
        report.value = nextReport
      }
    } else {
      report.value = createMockReport()
    }
  } finally {
    loading.value = false
  }
}

const handleRegenerate = async () => {
  if (typeof integrationHooks.regenerateReport === 'function') {
    await integrationHooks.regenerateReport({ ...filters })
  } else {
    await handleRefresh()
  }
}

const handleSaveTemplate = () => {
  if (typeof integrationHooks.exportReport === 'function') {
    integrationHooks.exportReport({ type: 'template', report: report.value })
  }
}

const buildHtmlDocument = (payload) => {
  const { reportData, charts } = payload
  const safeInsights = Array.isArray(reportData.insights) ? reportData.insights : []
  const safeStages = Array.isArray(reportData.stageNotes) ? reportData.stageNotes : []
  const insightHtml = safeInsights
    .map((insight) => {
      const points = Array.isArray(insight.points) ? insight.points : []
      return `
        <div>
          <strong>${insight.headline}</strong>
          <ul class="list">
            ${points.map((p) => `<li>${p}</li>`).join('')}
          </ul>
        </div>
      `
    })
    .join('')
  const stageChips = safeStages
    .map((stage) => `<span class="chip">${stage.title} · ${stage.range} · ${stage.delta}</span>`)
    .join('')
  const encodedCharts = JSON.stringify(charts)
  const encodedReport = JSON.stringify(reportData)
  const closingScriptTag = '</scr' + 'ipt>'
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${reportData.title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <style>
    body { font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; }
    .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 18px; margin-bottom: 18px; box-shadow: 0 10px 30px rgba(15,23,42,0.08); }
    h1 { margin: 0 0 4px; font-size: 26px; }
    h2 { margin: 16px 0 8px; font-size: 18px; }
    .kpis { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); }
    .kpi { padding: 12px; background: #f8fafc; border-radius: 14px; border: 1px solid #e2e8f0; }
    .kpi span { display: block; color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em; }
    .kpi strong { display: block; margin-top: 6px; font-size: 20px; }
    .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
    .list { list-style: disc; padding-left: 18px; color: #1e293b; }
    .chips { display: flex; flex-wrap: wrap; gap: 10px; }
    .chip { padding: 6px 10px; border-radius: 999px; background: #eef2ff; color: #4338ca; font-size: 13px; border: 1px solid #c7d2fe; }
    .chart { height: 280px; }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js">${closingScriptTag}
</head>
<body>
  <div class="card">
    <h1>${reportData.title}</h1>
    <div>${reportData.rangeText} · 更新于 ${reportData.lastUpdated}</div>
    <div style="color:#475569;margin-top:6px;">${reportData.subtitle}</div>
  </div>
  <div class="card">
    <h2>核心指标</h2>
    <div class="kpis">
      <div class="kpi"><span>总声量</span><strong>${formatNumber(reportData.metrics.totalVolume)}</strong><div>覆盖全渠道有效数据</div></div>
      <div class="kpi"><span>峰值</span><strong>${formatNumber(reportData.metrics.peak.value)} · ${reportData.metrics.peak.date}</strong><div>高潮爆发期</div></div>
      <div class="kpi"><span>情感</span><strong>${(reportData.metrics.positiveRate * 100).toFixed(1)}% 正向</strong><div>中性 ${(reportData.metrics.neutralRate * 100).toFixed(1)}%</div></div>
      <div class="kpi"><span>内容结构</span><strong>${(reportData.metrics.factualRatio * 100).toFixed(1)}% 报道</strong><div>其余为评论观点</div></div>
    </div>
  </div>
  <div class="card">
    <h2>可视化</h2>
    <div class="grid">
      <div><h3>渠道声量</h3><div id="channel-chart" class="chart"></div></div>
      <div><h3>情感态度</h3><div id="sentiment-chart" class="chart"></div></div>
      <div><h3>内容结构</h3><div id="content-chart" class="chart"></div></div>
      <div style="grid-column:1/-1;"><h3>时间趋势</h3><div id="trend-chart" class="chart"></div></div>
      <div><h3>关键词热度</h3><div id="keyword-chart" class="chart"></div></div>
      <div><h3>主题分布</h3><div id="theme-chart" class="chart"></div></div>
    </div>
  </div>
  <div class="card">
    <h2>洞察解读</h2>
    <div class="grid">
      ${insightHtml}
    </div>
  </div>
  <div class="card">
    <h2>关键节点</h2>
    <div class="chips">
      ${stageChips}
    </div>
  </div>
  <script>
    const chartOptions = ${encodedCharts};
    const reportPayload = ${encodedReport};
    const instances = [
      ['channel-chart', chartOptions.channel],
      ['sentiment-chart', chartOptions.sentiment],
      ['content-chart', chartOptions.contentSplit],
      ['trend-chart', chartOptions.trend],
      ['keyword-chart', chartOptions.keyword],
      ['theme-chart', chartOptions.theme]
    ];
    instances.forEach(([id, option]) => {
      const el = document.getElementById(id);
      if (!el || !option) return;
      const chart = echarts.init(el);
      chart.setOption(option);
      window.addEventListener('resize', () => chart.resize());
    });
  ${closingScriptTag}
</body>
</html>`
}

const exportHtmlReport = async () => {
  exporting.value = true
  try {
    const html = buildHtmlDocument({
      reportData: report.value,
      charts: {
        channel: channelChartOption.value,
        sentiment: sentimentChartOption.value,
        contentSplit: contentSplitOption.value,
        trend: trendChartOption.value,
        keyword: keywordChartOption.value,
        theme: themeChartOption.value
      }
    })
    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${report.value.title || 'report'}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    if (typeof integrationHooks.exportReport === 'function') {
      integrationHooks.exportReport({ type: 'html', report: report.value })
    }
  } finally {
    exporting.value = false
  }
}
</script>
