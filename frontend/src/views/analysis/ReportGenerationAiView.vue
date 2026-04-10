<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">AI 完整报告</h2>
          <p class="text-sm text-secondary">完整报告页不再依赖 markdown 排版，直接复用统一的结构化报告文档和图表目录。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading" @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '同步中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" @click="goToRunPage">
            <PlayCircleIcon class="h-4 w-4" />
            前往运行页
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="historyState.loading || !reportForm.topic" @click="handleRefreshHistory">
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '加载中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-[1.2fr,1fr,1fr,1fr]">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">专题</span>
          <AppSelect
            :options="topicSelectOptions"
            :value="reportForm.topic"
            :disabled="topicsState.loading || !topicOptions.length"
            @change="reportForm.topic = $event"
          />
          <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">历史记录</span>
          <AppSelect
            :options="historySelectOptions"
            :value="selectedHistoryId"
            :disabled="historyState.loading || !reportHistory.length"
            :placeholder="historyState.loading ? '加载历史中…' : reportHistory.length ? '选择历史记录' : '暂无历史记录'"
            @change="handleSelectHistory"
          />
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
          <span v-else-if="availableRange.notice" class="ml-2 text-warning">{{ availableRange.notice }}</span>
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="fullReportState.loading || fullReportState.regenerating" @click="handleLoad">
            <ArrowPathIcon class="h-4 w-4" :class="fullReportState.loading ? 'animate-spin' : ''" />
            {{ fullReportState.loading ? '读取中…' : '读取 AI 报告' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="fullReportState.loading || fullReportState.regenerating" @click="handleRegenerate">
            <SparklesIcon class="h-4 w-4" :class="fullReportState.regenerating ? 'animate-pulse' : ''" />
            {{ fullReportState.regenerating ? '重写中…' : '重新生成' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!fullReport" @click="exportMarkdown">
            <DocumentDuplicateIcon class="h-4 w-4" />
            导出 Markdown
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!fullReport" @click="exportHtml">
            <ArrowDownTrayIcon class="h-4 w-4" />
            导出 HTML
          </button>
        </div>
      </div>

      <div v-if="fullReportState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ fullReportState.error }}
      </div>
    </section>

    <section v-if="fullReport" class="grid gap-6 xl:grid-cols-[280px,minmax(0,1fr)]">
      <aside class="space-y-6 xl:sticky xl:top-24 xl:self-start">
        <section class="card-surface space-y-4 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">报告信息</p>
            <h3 class="mt-2 text-lg font-semibold text-primary">{{ reportTitle }}</h3>
            <p class="mt-2 text-sm text-secondary">{{ reportSubtitle }}</p>
          </div>
          <div class="space-y-2 text-sm text-secondary">
            <p>{{ fullReport.rangeText || reportRange }}</p>
            <p>图表位点：{{ chartCatalog.length }} 个</p>
            <p>引用索引：{{ citationCount }} 条</p>
            <p v-if="fullReportState.lastLoaded">读取时间：{{ fullReportState.lastLoaded }}</p>
          </div>
        </section>

        <section class="card-surface space-y-4 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">章节导航</p>
          </div>
          <nav class="space-y-1.5">
            <a
              v-for="item in tocItems"
              :key="item.id"
              :href="`#${item.id}`"
              class="block rounded-xl px-3 py-2 text-sm transition hover:bg-brand-soft hover:text-brand-700"
              :class="item.kind === 'appendix' ? 'font-semibold text-secondary' : 'font-semibold text-primary'"
            >
              {{ item.label }}
            </a>
          </nav>
        </section>

        <section v-if="hero.highlights?.length" class="card-surface space-y-3 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">核心发现</p>
          </div>
          <article v-for="item in hero.highlights" :key="item" class="rounded-3xl border border-soft bg-surface-muted/40 p-4">
            <p class="text-sm leading-7 text-primary">{{ item }}</p>
          </article>
        </section>
      </aside>

      <article class="card-surface space-y-6 overflow-hidden p-6">
        <div class="border-b border-soft pb-5">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">结构化文稿预览</p>
          <p class="mt-2 text-sm text-secondary">当前预览、结构化结果页和导出 HTML 都来自同一份 `report_document`，不再走独立的 markdown 模板。</p>
        </div>

        <ReportDocumentRenderer
          :document="reportDocument"
          :chart-catalog="chartCatalog"
          :report-data="reportBundle"
        />
      </article>
    </section>

    <section v-else class="card-surface p-6 text-sm text-muted">
      请先选择专题和时间范围，然后读取正式文稿。
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ClockIcon,
  DocumentDuplicateIcon,
  PlayCircleIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
import ReportDocumentRenderer from '../../components/report/ReportDocumentRenderer.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'
import { buildStandaloneReportHtml } from '../../utils/reportDocumentHtml'

const router = useRouter()

const {
  topicsState,
  topicOptions,
  reportForm,
  availableRange,
  historyState,
  reportHistory,
  selectedHistoryId,
  fullReportState,
  fullReportData,
  loadTopics,
  loadHistory,
  loadFullReport,
  createReportTask,
  applyHistorySelection
} = useReportGeneration()

const fullReport = computed(() => (fullReportData.value && typeof fullReportData.value === 'object' ? fullReportData.value : null))
const reportBundle = computed(() => (fullReport.value?.report_data && typeof fullReport.value.report_data === 'object' ? fullReport.value.report_data : fullReport.value || {}))
const reportDocument = computed(() => (fullReport.value?.report_document && typeof fullReport.value.report_document === 'object' ? fullReport.value.report_document : {}))
const chartCatalog = computed(() => (Array.isArray(fullReport.value?.chart_catalog) ? fullReport.value.chart_catalog : []))
const hero = computed(() => (reportDocument.value?.hero && typeof reportDocument.value.hero === 'object' ? reportDocument.value.hero : {}))
const task = computed(() => (reportBundle.value?.task && typeof reportBundle.value.task === 'object' ? reportBundle.value.task : {}))

const reportTitle = computed(() => fullReport.value?.title || hero.value.title || task.value.topic_label || task.value.topic_identifier || 'AI 完整报告')
const reportSubtitle = computed(() => fullReport.value?.subtitle || hero.value.subtitle || '统一结构化报告阅读视图')
const reportRange = computed(() => `${task.value.start || '--'} → ${task.value.end || '--'}`)
const citationCount = computed(() => (Array.isArray(reportBundle.value?.citations) ? reportBundle.value.citations.length : 0))

const tocItems = computed(() => {
  const sections = Array.isArray(reportDocument.value?.sections) ? reportDocument.value.sections : []
  const items = sections.map((section) => ({
    id: section.section_id,
    label: section.kicker || section.title || section.section_id,
    kind: 'section'
  }))
  if (reportDocument.value?.appendix?.blocks?.length) {
    items.push({
      id: 'report-appendix',
      label: reportDocument.value.appendix.title || '附录',
      kind: 'appendix'
    })
  }
  return items
})

const topicSelectOptions = computed(() => topicOptions.value.map((option) => ({ value: option, label: option })))
const historySelectOptions = computed(() =>
  reportHistory.value.map((record) => ({
    value: record.id,
    label: `${record.start} → ${record.end}`
  }))
)

const handleSelectHistory = (historyId) => {
  applyHistorySelection(historyId || '')
}

const handleRefreshHistory = async () => {
  await loadHistory(reportForm.topic)
}

const handleLoad = async () => {
  await loadFullReport()
}

const handleRegenerate = async () => {
  const taskRecord = await createReportTask()
  if (taskRecord?.id) {
    router.push({ name: 'report-generation-run' })
  }
}

const goToRunPage = () => router.push({ name: 'report-generation-run' })

const exportMarkdown = () => {
  if (!fullReport.value) return
  const markdown = String(fullReport.value.markdown || '').trim()
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  downloadBlob(blob, `${reportTitle.value || 'ai-report'}.md`)
}

const exportHtml = () => {
  if (!fullReport.value) return
  const html = buildStandaloneReportHtml(fullReport.value, { lastLoaded: fullReportState.lastLoaded })
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  downloadBlob(blob, `${reportTitle.value || 'ai-report'}.html`)
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
</script>
