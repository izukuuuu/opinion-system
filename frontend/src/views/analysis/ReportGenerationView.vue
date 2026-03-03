<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-xl font-semibold text-primary">报告解读</h2>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="topicsState.loading"
            @click="loadTopics"
          >
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '同步中…' : '刷新专题' }}
          </button>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="historyState.loading || !reportForm.topic"
            @click="handleRefreshHistory"
          >
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '加载中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-[1.2fr,1fr,1fr,1fr]">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">专题 (Topic)</span>
          <select
            v-model="reportForm.topic"
            class="input"
            :disabled="topicsState.loading || !topicOptions.length"
            required
          >
            <option value="" disabled>请选择专题</option>
            <option v-for="option in topicOptions" :key="`report-topic-${option}`" :value="option">
              {{ option }}
            </option>
          </select>
          <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">历史记录</span>
          <select
            :value="selectedHistoryId"
            class="input"
            :disabled="historyState.loading || !reportHistory.length"
            @change="handleSelectHistory"
          >
            <option value="" disabled>
              {{ historyState.loading ? '加载历史中…' : reportHistory.length ? '选择历史记录' : '暂无历史记录' }}
            </option>
            <option v-for="record in reportHistory" :key="record.id" :value="record.id">
              {{ record.start }} → {{ record.end }}
            </option>
          </select>
          <p v-if="historyState.error" class="text-xs text-muted">{{ historyState.error }}</p>
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">开始日期</span>
          <input v-model="reportForm.start" type="date" class="input" />
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">结束日期</span>
          <input v-model="reportForm.end" type="date" class="input" />
        </label>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-soft pt-4">
        <p class="text-xs text-muted">
          建议范围：{{ availableRange.start || '--' }} → {{ availableRange.end || '--' }}
          <span v-if="availableRange.loading" class="ml-2 animate-pulse">检查中…</span>
          <span v-else-if="availableRange.error" class="ml-2 text-danger">{{ availableRange.error }}</span>
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="reportState.loading || reportState.regenerating"
            @click="loadReport"
          >
            <ArrowPathIcon class="h-4 w-4" :class="reportState.loading ? 'animate-spin' : ''" />
            {{ reportState.loading ? '读取中…' : '读取报告' }}
          </button>
          <button
            type="button"
            class="btn-primary inline-flex items-center gap-2"
            :disabled="reportState.loading || reportState.regenerating"
            @click="regenerateReport"
          >
            <SparklesIcon class="h-4 w-4" :class="reportState.regenerating ? 'animate-pulse' : ''" />
            {{ reportState.regenerating ? '生成中…' : '重新生成' }}
          </button>
        </div>
      </div>

      <div v-if="reportState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ reportState.error }}
      </div>
    </section>

    <section v-if="report" class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">报告概览</p>
        <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ reportMeta.title }}</h1>
        <p class="text-sm text-secondary">{{ reportMeta.subtitle }}</p>
        <p class="text-xs text-muted">
          {{ reportMeta.rangeText }} · 最近更新：{{ reportMeta.lastUpdated }}
          <span v-if="reportState.lastLoaded"> · 前端读取：{{ reportState.lastLoaded }}</span>
        </p>
      </header>

      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">总声量</p>
          <p class="mt-2 text-3xl font-semibold text-primary">{{ formatNumber(metrics.totalVolume) }}</p>
        </article>

        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">峰值</p>
          <p class="mt-2 text-xl font-semibold text-primary">{{ formatNumber(metrics.peak.value) }}</p>
          <p class="text-sm text-secondary">{{ metrics.peak.date || '未提供' }}</p>
        </article>

        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">情感结构</p>
          <p class="mt-2 text-base font-semibold text-primary">正向 {{ formatRate(metrics.positiveRate) }}</p>
          <p class="text-sm text-secondary">中性 {{ formatRate(metrics.neutralRate) }} · 负向 {{ formatRate(metrics.negativeRate) }}</p>
        </article>

        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">内容结构</p>
          <p class="mt-2 text-base font-semibold text-primary">报道 {{ formatRate(metrics.factualRatio) }}</p>
          <p class="text-sm text-secondary">观点 {{ formatRate(metrics.opinionRatio) }}</p>
        </article>
      </div>
    </section>

    <template v-if="report">
      <section class="grid gap-6 xl:grid-cols-3">
        <AnalysisChartPanel title="渠道分布" :option="channelChartOption" :has-data="hasChannelData" />
        <AnalysisChartPanel title="情感态度" :option="sentimentChartOption" :has-data="hasSentimentData" />
        <AnalysisChartPanel title="内容结构" :option="contentSplitOption" :has-data="hasContentSplitData" />
      </section>

      <section class="grid gap-6 xl:grid-cols-[2fr,1fr]">
        <AnalysisChartPanel title="时间趋势" :option="trendChartOption" :has-data="hasTrendData" />
        <article class="card-surface space-y-3 p-5">
          <header>
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">传播阶段</p>
            <h3 class="text-lg font-semibold text-primary">节奏拆解</h3>
          </header>
          <ul v-if="stageNotes.length" class="space-y-3 text-sm text-secondary">
            <li v-for="stage in stageNotes" :key="`${stage.badge}-${stage.title}`" class="rounded-2xl border border-soft bg-surface p-3">
              <div class="flex items-center justify-between gap-2">
                <p class="font-semibold text-primary">{{ stage.title }}</p>
                <span class="text-xs font-semibold text-brand-600">{{ stage.badge || '-' }}</span>
              </div>
              <p class="mt-1 text-xs text-muted">{{ stage.range }} · {{ stage.delta }}</p>
              <p class="mt-2 leading-relaxed">{{ stage.highlight }}</p>
            </li>
          </ul>
          <p v-else class="text-sm text-muted">暂无阶段说明。</p>

          <div class="border-t border-soft pt-3">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">BERTopic 时间节点（AI再分类）</p>
            <ul v-if="bertopicTimeNodes.length" class="mt-2 space-y-2 text-sm text-secondary">
              <li
                v-for="node in bertopicTimeNodes"
                :key="`bertopic-node-${node.date}-${node.topTheme}`"
                class="rounded-xl border border-soft bg-surface p-3"
              >
                <div class="flex items-center justify-between gap-2">
                  <p class="font-semibold text-primary">{{ node.label }}</p>
                  <span class="text-xs text-muted">样本 {{ formatNumber(node.total) }}</span>
                </div>
                <p class="mt-1 text-xs text-secondary">主主题：{{ node.topTheme }}（{{ formatNumber(node.topValue) }}）</p>
                <p v-if="node.tailThemes" class="mt-1 text-xs text-muted">次级主题：{{ node.tailThemes }}</p>
              </li>
            </ul>
            <p v-else class="mt-2 text-sm text-muted">暂无 BERTopic 时间节点数据。</p>
          </div>
        </article>
      </section>

      <section class="grid gap-6 xl:grid-cols-2">
        <AnalysisChartPanel title="关键词热度" :option="keywordChartOption" :has-data="hasKeywordData" />
        <AnalysisChartPanel title="主题分布" :option="themeChartOption" :has-data="hasThemeData" />
      </section>

      <section class="card-surface space-y-4 p-6">
        <header class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">洞察亮点</p>
            <h3 class="text-lg font-semibold text-primary">重点结论</h3>
          </div>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="exporting"
            @click="exportHtmlReport"
          >
            <ArrowDownTrayIcon class="h-4 w-4" />
            {{ exporting ? '导出中…' : '导出 HTML' }}
          </button>
        </header>

        <ul v-if="highlightPoints.length" class="space-y-2 rounded-2xl border border-brand-soft bg-brand-soft/20 p-4 text-sm text-secondary">
          <li v-for="(point, index) in highlightPoints" :key="`highlight-${index}`" class="flex gap-2">
            <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
            <span>{{ point }}</span>
          </li>
        </ul>

        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="insight in insightCards" :key="insight.title" class="rounded-2xl border border-soft bg-surface p-4">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ insight.title }}</p>
            <p class="mt-2 text-base font-semibold text-primary">{{ insight.headline }}</p>
            <ul class="mt-3 space-y-2 text-sm text-secondary">
              <li v-for="(point, idx) in insight.points" :key="`${insight.title}-${idx}`" class="flex gap-2">
                <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
                <span>{{ point }}</span>
              </li>
            </ul>
          </article>
        </div>
      </section>
    </template>

    <section v-else class="card-surface p-6 text-sm text-muted">
      请先选择专题与时间范围，然后点击“读取报告”或“重新生成”。
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ClockIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'
import AnalysisChartPanel from '../../components/AnalysisChartPanel.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'

const {
  topicsState,
  topicOptions,
  reportForm,
  availableRange,
  reportState,
  historyState,
  reportHistory,
  selectedHistoryId,
  reportData,
  loadTopics,
  loadHistory,
  loadReport,
  regenerateReport,
  applyHistorySelection
} = useReportGeneration()

const exporting = ref(false)

const clampRate = (value) => {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return 0
  return Math.max(0, Math.min(1, numeric))
}

const formatRate = (value) => `${(clampRate(value) * 100).toFixed(1)}%`

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '0'
  return new Intl.NumberFormat('zh-CN').format(Number(value))
}

const report = computed(() => (reportData.value && typeof reportData.value === 'object' ? reportData.value : null))

const reportMeta = computed(() => ({
  title: report.value?.title || `${reportForm.topic || '专题'}舆情分析报告`,
  subtitle: report.value?.subtitle || '基于分析结果自动生成',
  rangeText: report.value?.rangeText || `${reportForm.start || '--'} → ${reportForm.end || '--'}`,
  lastUpdated: report.value?.lastUpdated || '未提供'
}))

const metrics = computed(() => {
  const data = report.value?.metrics || {}
  const positiveRate = clampRate(data.positiveRate || 0)
  const neutralRate = clampRate(data.neutralRate || 0)
  const negativeRate = clampRate(1 - positiveRate - neutralRate)
  const factualRatio = clampRate(data.factualRatio || 0)
  const opinionRatio = clampRate(1 - factualRatio)
  return {
    totalVolume: Number(data.totalVolume || 0),
    peak: {
      value: Number(data?.peak?.value || 0),
      date: String(data?.peak?.date || '')
    },
    positiveRate,
    neutralRate,
    negativeRate,
    factualRatio,
    opinionRatio
  }
})

const channels = computed(() => (Array.isArray(report.value?.channels) ? report.value.channels : []))
const timeline = computed(() => (Array.isArray(report.value?.timeline) ? report.value.timeline : []))
const keywords = computed(() => (Array.isArray(report.value?.keywords) ? report.value.keywords : []))
const themes = computed(() => (Array.isArray(report.value?.themes) ? report.value.themes : []))
const sentiment = computed(() => report.value?.sentiment || { positive: 0, neutral: 0, negative: 0 })
const contentSplit = computed(() => report.value?.contentSplit || { factual: 0, opinion: 0 })

const stageNotes = computed(() => (Array.isArray(report.value?.stageNotes) ? report.value.stageNotes : []))
const bertopicTimeNodes = computed(() => {
  const rows = Array.isArray(report.value?.bertopicTimeNodes) ? report.value.bertopicTimeNodes : []
  return rows
    .map((item) => {
      const date = String(item?.date || '').trim()
      const label = String(item?.label || date).trim()
      const topTheme = String(item?.topTheme || '').trim()
      const topValue = Number(item?.topValue || 0)
      const total = Number(item?.total || 0)
      const themes = Array.isArray(item?.themes)
        ? item.themes
          .map((theme) => ({
            name: String(theme?.name || '').trim(),
            value: Number(theme?.value || 0)
          }))
          .filter((theme) => theme.name)
        : []
      const tailThemes = themes
        .slice(1, 3)
        .map((theme) => `${theme.name}(${formatNumber(theme.value)})`)
        .join('、')
      return {
        date,
        label: label || date,
        topTheme,
        topValue,
        total,
        themes,
        tailThemes
      }
    })
    .filter((item) => item.date && item.topTheme)
    .sort((a, b) => b.total - a.total)
    .slice(0, 8)
})
const highlightPoints = computed(() => (Array.isArray(report.value?.highlightPoints) ? report.value.highlightPoints : []))
const insightCards = computed(() => (Array.isArray(report.value?.insights) ? report.value.insights : []))

const hasChannelData = computed(() => channels.value.length > 0)
const hasTrendData = computed(() => timeline.value.length > 0)
const hasSentimentData = computed(() => Boolean(sentiment.value))
const hasContentSplitData = computed(() => Boolean(contentSplit.value))
const hasKeywordData = computed(() => keywords.value.length > 0)
const hasThemeData = computed(() => themes.value.length > 0)

const channelChartOption = computed(() => {
  const sorted = [...channels.value]
    .map((item) => ({
      name: String(item?.name || ''),
      value: Number(item?.value || 0)
    }))
    .filter((item) => item.name)
    .sort((a, b) => b.value - a.value)

  return {
    color: ['#2563eb', '#0ea5e9', '#10b981', '#f97316', '#8b5cf6', '#ef4444'],
    tooltip: { trigger: 'axis' },
    grid: { left: 72, right: 24, top: 24, bottom: 24 },
    xAxis: { type: 'value', axisLabel: { color: '#475569' } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: sorted.map((item) => item.name),
      axisLabel: { color: '#475569' }
    },
    series: [
      {
        type: 'bar',
        barWidth: 18,
        data: sorted.map((item) => item.value),
        itemStyle: { borderRadius: [8, 8, 8, 8] },
        label: { show: true, position: 'right', color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const trendChartOption = computed(() => {
  const rows = timeline.value.map((item) => ({
    date: String(item?.date || ''),
    value: Number(item?.value || 0)
  }))
  const interval = rows.length > 40 ? Math.ceil(rows.length / 12) : 0

  return {
    color: ['#2563eb'],
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 20, top: 24, bottom: rows.length > 40 ? 72 : 34 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: rows.map((item) => item.date),
      axisLabel: { color: '#475569', interval }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#475569' },
      splitLine: { lineStyle: { color: '#e2e8f0' } }
    },
    dataZoom: rows.length > 40
      ? [
          { type: 'inside', start: 0, end: 100 },
          { type: 'slider', start: 0, end: 100, height: 20, bottom: 18 }
        ]
      : [],
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: rows.map((item) => item.value),
        areaStyle: { color: 'rgba(37,99,235,0.12)' },
        lineStyle: { width: 2.5 }
      }
    ]
  }
})

const sentimentChartOption = computed(() => ({
  color: ['#22c55e', '#f59e0b', '#ef4444'],
  tooltip: { trigger: 'item' },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      label: { formatter: '{b}\n{d}%' },
      data: [
        { name: '正向', value: Number(sentiment.value.positive || 0) },
        { name: '中性', value: Number(sentiment.value.neutral || 0) },
        { name: '负向', value: Number(sentiment.value.negative || 0) }
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
        { name: '报道事实', value: Number(contentSplit.value.factual || 0) },
        { name: '评论观点', value: Number(contentSplit.value.opinion || 0) }
      ]
    }
  ]
}))

const keywordChartOption = computed(() => {
  const rows = [...keywords.value]
    .map((item) => ({ term: String(item?.term || ''), value: Number(item?.value || 0) }))
    .filter((item) => item.term)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  return {
    color: ['#2563eb'],
    tooltip: { trigger: 'axis' },
    grid: { left: 120, right: 24, top: 24, bottom: 24 },
    xAxis: { type: 'value', axisLabel: { color: '#475569' } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((item) => item.term),
      axisLabel: { color: '#475569' }
    },
    series: [
      {
        type: 'bar',
        barWidth: 16,
        data: rows.map((item) => item.value),
        itemStyle: { borderRadius: [6, 6, 6, 6] },
        label: { show: true, position: 'right', color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const themeChartOption = computed(() => {
  const rows = [...themes.value]
    .map((item) => ({ name: String(item?.name || ''), value: Number(item?.value || 0) }))
    .filter((item) => item.name)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  return {
    color: ['#8b5cf6'],
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 24, top: 24, bottom: 48 },
    xAxis: {
      type: 'category',
      data: rows.map((item) => item.name),
      axisLabel: { color: '#475569', interval: 0, rotate: rows.length > 6 ? 20 : 0 }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#475569' },
      splitLine: { lineStyle: { color: '#e2e8f0' } }
    },
    series: [
      {
        type: 'bar',
        barWidth: 20,
        data: rows.map((item) => item.value),
        itemStyle: { borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const handleSelectHistory = async (event) => {
  const historyId = String(event.target.value || '').trim()
  if (!historyId) return
  await applyHistorySelection(historyId, { shouldLoad: true })
}

const handleRefreshHistory = async () => {
  const topic = String(reportForm.topic || '').trim()
  if (!topic) return
  await loadHistory(topic)
}

const escapeHtml = (value) => String(value || '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const buildHtmlDocument = () => {
  const payload = report.value
  if (!payload) return ''

  const insightHtml = insightCards.value
    .map((insight) => {
      const points = Array.isArray(insight.points) ? insight.points : []
      return `
        <article class="card">
          <h3>${escapeHtml(insight.title)}</h3>
          <p class="headline">${escapeHtml(insight.headline)}</p>
          <ul>${points.map((point) => `<li>${escapeHtml(point)}</li>`).join('')}</ul>
        </article>
      `
    })
    .join('')

  const highlightHtml = highlightPoints.value
    .map((point) => `<li>${escapeHtml(point)}</li>`)
    .join('')

  const bertopicNodeHtml = bertopicTimeNodes.value
    .map((node) => {
      const tailText = node.tailThemes ? `<p class="meta">次级主题：${escapeHtml(node.tailThemes)}</p>` : ''
      return `
        <li>
          <strong>${escapeHtml(node.label)}</strong>
          <span class="meta">主主题：${escapeHtml(node.topTheme)}（${escapeHtml(formatNumber(node.topValue))}） · 样本 ${escapeHtml(formatNumber(node.total))}</span>
          ${tailText}
        </li>
      `
    })
    .join('')

  const charts = {
    channel: channelChartOption.value,
    sentiment: sentimentChartOption.value,
    contentSplit: contentSplitOption.value,
    trend: trendChartOption.value,
    keyword: keywordChartOption.value,
    theme: themeChartOption.value
  }

  const chartJson = JSON.stringify(charts)
  const closeScript = '</scr' + 'ipt>'

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(reportMeta.value.title)}</title>
  <style>
    body { margin: 0; padding: 20px; background: #f8fafc; color: #0f172a; font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }
    h1, h2, h3 { margin: 0; }
    .panel { background: #fff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 16px; margin-bottom: 14px; }
    .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
    .chart { height: 300px; }
    .card { border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; background: #fff; }
    .headline { margin: 8px 0; color: #1e293b; font-weight: 600; }
    ul { margin: 6px 0 0; padding-left: 18px; color: #334155; }
    .meta { color: #64748b; font-size: 13px; margin-top: 6px; }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js">${closeScript}
</head>
<body>
  <section class="panel">
    <h1>${escapeHtml(reportMeta.value.title)}</h1>
    <p class="meta">${escapeHtml(reportMeta.value.subtitle)}</p>
    <p class="meta">${escapeHtml(reportMeta.value.rangeText)} · 更新于 ${escapeHtml(reportMeta.value.lastUpdated)}</p>
  </section>

  <section class="panel">
    <h2>洞察亮点</h2>
    <ul>${highlightHtml}</ul>
  </section>

  <section class="panel">
    <h2>BERTopic 时间节点（AI再分类）</h2>
    <ul>${bertopicNodeHtml || '<li>暂无 BERTopic 时间节点数据</li>'}</ul>
  </section>

  <section class="panel">
    <h2>图表</h2>
    <div class="grid">
      <div><h3>渠道分布</h3><div id="chart-channel" class="chart"></div></div>
      <div><h3>情感态度</h3><div id="chart-sentiment" class="chart"></div></div>
      <div><h3>内容结构</h3><div id="chart-content" class="chart"></div></div>
      <div><h3>时间趋势</h3><div id="chart-trend" class="chart"></div></div>
      <div><h3>关键词热度</h3><div id="chart-keyword" class="chart"></div></div>
      <div><h3>主题分布</h3><div id="chart-theme" class="chart"></div></div>
    </div>
  </section>

  <section class="panel">
    <h2>重点结论</h2>
    <div class="grid">${insightHtml}</div>
  </section>

  <script>
    const chartOptions = ${chartJson};
    const map = [
      ['chart-channel', chartOptions.channel],
      ['chart-sentiment', chartOptions.sentiment],
      ['chart-content', chartOptions.contentSplit],
      ['chart-trend', chartOptions.trend],
      ['chart-keyword', chartOptions.keyword],
      ['chart-theme', chartOptions.theme]
    ];
    map.forEach(([id, option]) => {
      const el = document.getElementById(id);
      if (!el || !option) return;
      const chart = echarts.init(el);
      chart.setOption(option);
      window.addEventListener('resize', () => chart.resize());
    });
  ${closeScript}
</body>
</html>`
}

const exportHtmlReport = async () => {
  if (!report.value) return
  exporting.value = true
  try {
    const html = buildHtmlDocument()
    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${reportMeta.value.title || 'report'}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } finally {
    exporting.value = false
  }
}
</script>
