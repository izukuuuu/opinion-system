<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">查看语义报告</h2>
          <p class="text-sm text-secondary">这里展示 结构化报告，方便核对章节、图表位点、证据条目和引用索引。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading"
            @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '刷新中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" @click="goToRunPage">
            <PlayCircleIcon class="h-4 w-4" />
            前往运行页
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2"
            :disabled="historyState.loading || !reportForm.topic" @click="handleRefreshHistory">
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '读取中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-[1.2fr,1fr,1fr,1fr]">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">专题</span>
          <AppSelect :options="topicSelectOptions" :value="reportForm.topic"
            :disabled="topicsState.loading || !topicOptions.length" @change="reportForm.topic = $event" />
          <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">历史记录</span>
          <AppSelect :options="historySelectOptions" :value="selectedHistoryId"
            :disabled="historyState.loading || !reportHistory.length"
            :placeholder="historyState.loading ? '加载历史中…' : reportHistory.length ? '选择历史记录' : '暂无历史记录'"
            @change="handleSelectHistory" />
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
          <button type="button" class="btn-primary inline-flex items-center gap-2" :disabled="reportState.loading"
            @click="loadReport()">
            <ArrowPathIcon class="h-4 w-4" :class="reportState.loading ? 'animate-spin' : ''" />
            {{ reportState.loading ? '读取中…' : '读取结果' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!report"
            @click="exportJson">
            <ArrowDownTrayIcon class="h-4 w-4" />
            导出结果
          </button>
        </div>
      </div>

      <div v-if="reportState.error"
        class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ reportState.error }}
      </div>
    </section>

    <template v-if="report">
      <section class="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <article class="card-surface space-y-5 p-6">
          <div class="space-y-2">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">报告概览</p>
            <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ reportTitle }}</h1>
            <p class="text-sm text-secondary">区间：{{ reportRange }}<span v-if="reportState.lastLoaded"> · 读取时间：{{
              reportState.lastLoaded }}</span></p>
          </div>

          <div class="rounded-3xl border border-brand-soft bg-brand-soft/40 px-5 py-5">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">统一摘要</p>
            <p class="mt-3 text-sm leading-7 text-primary">{{ hero.summary || conclusion.executive_summary ||
              '当前结果没有独立摘要。' }}</p>
            <div v-if="hero.risks?.length || conclusion.key_risks?.length" class="mt-3 flex flex-wrap gap-2">
              <span v-for="risk in (hero.risks?.length ? hero.risks : conclusion.key_risks || [])" :key="risk"
                class="rounded-full bg-warning-soft px-3 py-1 text-xs text-warning">
                {{ risk }}
              </span>
            </div>
          </div>

          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article v-for="card in summaryCards" :key="card.label"
              class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ card.label }}</p>
              <p class="mt-2 text-2xl font-semibold text-primary">{{ card.value }}</p>
              <p v-if="card.detail" class="mt-1 text-xs text-muted">{{ card.detail }}</p>
            </article>
          </div>
        </article>

        <article class="card-surface space-y-4 p-6">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">阅读索引</p>
            <p class="text-sm text-secondary">这里保留语义章节和图表定位，正式 Markdown 报告请在正式文稿页查看。</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <a v-for="item in navItems" :key="item.id"
              class="inline-flex items-center rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:bg-surface-muted hover:text-primary"
              :href="`#${item.id}`">
              {{ item.label }}
            </a>
          </div>
          <div v-if="hero.highlights?.length || conclusion.key_findings?.length" class="space-y-3">
            <article v-for="item in (hero.highlights?.length ? hero.highlights : conclusion.key_findings || [])"
              :key="item" class="rounded-3xl border border-soft bg-surface-muted/40 p-4">
              <p class="text-sm leading-7 text-primary">{{ item }}</p>
            </article>
          </div>
        </article>
      </section>

      <section class="card-surface grid gap-3 p-6 md:grid-cols-5">
        <article class="rounded-3xl bg-base-soft px-4 py-4">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">线程</p>
          <p class="mt-2 text-sm font-semibold text-primary">{{ provenance.threadId }}</p>
        </article>
        <article class="rounded-3xl bg-base-soft px-4 py-4">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">语义报告</p>
          <p class="mt-2 text-sm font-semibold text-primary">{{ provenance.structuredStatus }}</p>
        </article>
        <article class="rounded-3xl bg-base-soft px-4 py-4">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">介入记录</p>
          <p class="mt-2 text-sm font-semibold text-primary">{{ provenance.approvalStatus }}</p>
        </article>
        <article class="rounded-3xl bg-base-soft px-4 py-4">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">回退重写</p>
          <p class="mt-2 text-sm font-semibold text-primary">{{ provenance.fallbackText }}</p>
        </article>
        <article class="rounded-3xl bg-base-soft px-4 py-4">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">放行判断</p>
          <p class="mt-2 text-sm font-semibold text-primary">{{ provenance.utilityDecision }}</p>
        </article>
      </section>

      <ReportDocumentRenderer
        :document="reportDocument"
        :report-ir="reportIr"
        :artifact-manifest="artifactManifest"
        :report-data="reportBundle"
        :show-hero="false"
      />
    </template>

    <section v-else class="card-surface p-6 text-sm text-secondary">
      请选择专题和时间范围，然后读取语义报告。
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDownTrayIcon, ArrowPathIcon, ClockIcon, PlayCircleIcon } from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
import ReportDocumentRenderer from '../../components/report/ReportDocumentRenderer.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'

const router = useRouter()
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
  taskState,
  loadTopics,
  loadHistory,
  loadReport,
  applyHistorySelection
} = useReportGeneration()

const report = computed(() => (reportData.value && typeof reportData.value === 'object' ? reportData.value : null))
const reportBundle = computed(() => (report.value?.report_data && typeof report.value.report_data === 'object' ? report.value.report_data : report.value || {}))
const reportDocument = computed(() => (report.value?.report_document && typeof report.value.report_document === 'object' ? report.value.report_document : {}))
const reportIr = computed(() => (report.value?.report_ir && typeof report.value.report_ir === 'object' ? report.value.report_ir : {}))
const artifactManifest = computed(() => (report.value?.artifact_manifest && typeof report.value.artifact_manifest === 'object' ? report.value.artifact_manifest : {}))
const hero = computed(() => (reportDocument.value?.hero && typeof reportDocument.value.hero === 'object' ? reportDocument.value.hero : {}))
const task = computed(() => (reportBundle.value?.task && typeof reportBundle.value.task === 'object' ? reportBundle.value.task : {}))
const conclusion = computed(() => (reportBundle.value?.conclusion && typeof reportBundle.value.conclusion === 'object' ? reportBundle.value.conclusion : {}))

const reportTitle = computed(() => hero.value.title || task.value.topic_label || task.value.topic_identifier || '语义报告')
const reportRange = computed(() => `${task.value.start || '--'} → ${task.value.end || '--'}`)
const provenance = computed(() => {
  const manifest = taskState.artifactManifest && typeof taskState.artifactManifest === 'object' ? taskState.artifactManifest : {}
  const approvalStatus = manifest.approval_records?.status === 'ready'
    ? '已记录'
    : (Array.isArray(taskState.approvals) && taskState.approvals.some((item) => String(item?.status || '').trim() !== 'resolved') ? '待处理' : '未触发')
  const fallbackCount = Number(taskState.reportIrSummary?.fallback_trace_count || taskState.structuredResultDigest?.fallback_trace_count || 0)
  return {
    threadId: taskState.threadId || '未绑定',
    structuredStatus: manifest.structured_projection?.status === 'ready' ? '已生成' : '未就绪',
    approvalStatus,
    fallbackText: fallbackCount > 0 ? `已回退 ${fallbackCount} 次` : '未触发',
    utilityDecision: String(taskState.reportIrSummary?.utility_assessment?.decision || taskState.structuredResultDigest?.utility_assessment?.decision || 'pending').trim() || 'pending'
  }
})

const topicSelectOptions = computed(() => topicOptions.value.map((option) => ({ value: option, label: option })))
const historySelectOptions = computed(() =>
  reportHistory.value.map((record) => ({
    value: record.id,
    label: `${record.start} → ${record.end}`
  }))
)

const summaryCards = computed(() => {
  if (Array.isArray(hero.value.metrics) && hero.value.metrics.length) {
    return hero.value.metrics.map((metric) => ({
      label: metric.label || '--',
      value: metric.value || '--',
      detail: metric.detail || ''
    }))
  }
  return [
    { label: '章节数量', value: String(Array.isArray(reportDocument.value?.sections) ? reportDocument.value.sections.length : 0), detail: '统一文档层' },
    { label: '图表位点', value: String(Array.isArray(reportIr.value?.figures) ? reportIr.value.figures.length : 0), detail: '来自图表 artifact contract' },
    { label: '证据数量', value: String(Array.isArray(reportBundle.value?.key_evidence) ? reportBundle.value.key_evidence.length : 0), detail: '结构化证据条目' },
    { label: '引用数量', value: String(Array.isArray(reportBundle.value?.citations) ? reportBundle.value.citations.length : 0), detail: '可回链来源' }
  ]
})

const navItems = computed(() => {
  const sections = Array.isArray(reportDocument.value?.sections) ? reportDocument.value.sections : []
  return sections.map((section) => ({
    id: section.section_id,
    label: section.kicker || section.title || section.section_id
  }))
})

const handleSelectHistory = (historyId) => {
  applyHistorySelection(historyId || '')
}

const handleRefreshHistory = async () => {
  await loadHistory(reportForm.topic)
}

const goToRunPage = () => router.push({ name: 'report-generation-run' })

const exportJson = () => {
  if (!report.value) return
  const blob = new Blob([JSON.stringify(report.value, null, 2)], { type: 'application/json;charset=utf-8' })
  downloadBlob(blob, `${reportTitle.value || 'structured-report'}.json`)
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
