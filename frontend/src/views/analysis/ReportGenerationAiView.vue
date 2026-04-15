<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">正式文稿</h2>
          <p class="text-sm text-secondary">这里展示舆情分析 Markdown 文稿，语义底稿和运行信息保留在其它视图查看。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading"
            @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '同步中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" @click="goToRunPage">
            <PlayCircleIcon class="h-4 w-4" />
            前往运行页
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2"
            :disabled="historyState.loading || !reportForm.topic" @click="handleRefreshHistory">
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '加载中…' : '刷新记录' }}
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
          <button type="button" class="btn-secondary inline-flex items-center gap-2"
            :disabled="fullReportState.loading || fullReportState.regenerating" @click="handleLoad">
            <ArrowPathIcon class="h-4 w-4" :class="fullReportState.loading ? 'animate-spin' : ''" />
            {{ fullReportState.loading ? '读取中…' : '读取 AI 报告' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2"
            :disabled="fullReportState.loading || fullReportState.regenerating" @click="handleRegenerate">
            <SparklesIcon class="h-4 w-4" :class="fullReportState.regenerating ? 'animate-pulse' : ''" />
            {{ fullReportState.regenerating ? '重写中…' : '重新生成' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!fullReport"
            @click="exportMarkdown">
            <DocumentDuplicateIcon class="h-4 w-4" />
            导出 Markdown
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!fullReport"
            @click="exportHtml">
            <ArrowDownTrayIcon class="h-4 w-4" />
            导出 HTML
          </button>
        </div>
      </div>

      <div v-if="fullReportState.error"
        class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
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
            <p v-if="sceneLabel">场景：{{ sceneLabel }}</p>
            <p v-if="templateName">模板：{{ templateName }}</p>
            <p>插图资源：{{ assetsCount }} 个</p>
            <p v-if="fullReportState.lastLoaded">读取时间：{{ fullReportState.lastLoaded }}</p>
          </div>
        </section>

        <section class="card-surface space-y-4 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">章节导航</p>
          </div>
          <nav class="space-y-1.5">
            <a v-for="item in tocItems" :key="item.id" :href="`#${item.id}`"
              class="block rounded-xl px-3 py-2 text-sm font-semibold text-primary transition hover:bg-brand-soft hover:text-brand-700">
              {{ item.text }}
            </a>
            <p v-if="!tocItems.length" class="rounded-2xl bg-base-soft px-3 py-3 text-sm text-secondary">正文还没有可用目录。</p>
          </nav>
        </section>
      </aside>

      <article class="card-surface overflow-hidden p-6">
        <div class="border-b border-soft pb-5">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">正式文稿</p>
        </div>

        <div v-if="reportHtml" class="ai-report-markdown mt-6" v-html="reportHtml" />
        <div v-else class="mt-6 rounded-3xl bg-base-soft px-4 py-6 text-sm text-secondary">当前没有可展示的正式文稿。</div>
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
import { useReportGeneration } from '../../composables/useReportGeneration'
import { buildStandaloneAiReportHtml } from '../../utils/aiReportHtml'
import { exportableAiMarkdown, extractMarkdownToc, renderAiReportMarkdown } from '../../utils/aiReportMarkdown'

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
const meta = computed(() => (fullReport.value?.meta && typeof fullReport.value.meta === 'object' ? fullReport.value.meta : {}))
const markdown = computed(() => String(fullReport.value?.markdown || '').trim())
const reportIr = computed(() => (fullReport.value?.report_ir && typeof fullReport.value.report_ir === 'object' ? fullReport.value.report_ir : {}))
const artifactManifest = computed(() => (fullReport.value?.artifact_manifest && typeof fullReport.value.artifact_manifest === 'object' ? fullReport.value.artifact_manifest : {}))
const reportTitle = computed(() => fullReport.value?.title || '正式文稿')
const reportSubtitle = computed(() => fullReport.value?.subtitle || '正式 Markdown 报告')
const reportRange = computed(() => fullReport.value?.rangeText || '-- → --')
const sceneLabel = computed(() => String(meta.value.scene_label || '').trim())
const templateName = computed(() => String(meta.value.template_name || '').trim())
const assetsCount = computed(() => (Array.isArray(fullReport.value?.assets) ? fullReport.value.assets.length : 0))
const reportHtml = computed(() => renderAiReportMarkdown(markdown.value, {
  assets: fullReport.value?.assets || [],
  reportIr: reportIr.value,
  artifactManifest: artifactManifest.value
}))
const tocItems = computed(() => extractMarkdownToc(markdown.value))

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
  const exportText = exportableAiMarkdown(markdown.value, { assets: fullReport.value.assets || [] })
  const blob = new Blob([exportText], { type: 'text/markdown;charset=utf-8' })
  downloadBlob(blob, `${reportTitle.value || 'ai-report'}.md`)
}

const exportHtml = () => {
  if (!fullReport.value) return
  const html = buildStandaloneAiReportHtml(fullReport.value, { lastLoaded: fullReportState.lastLoaded })
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

<style scoped>
.ai-report-markdown {
  color: var(--color-text-primary);
}

.ai-report-markdown :deep(.ai-report-heading) {
  scroll-margin-top: 96px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.ai-report-markdown :deep(.ai-report-heading-1) {
  margin: 0 0 1.5rem;
  font-size: clamp(1.9rem, 1.4rem + 1.4vw, 2.6rem);
  line-height: 1.12;
}

.ai-report-markdown :deep(.ai-report-heading-2) {
  margin: 2.2rem 0 1rem;
  font-size: clamp(1.35rem, 1.1rem + 0.8vw, 1.8rem);
  line-height: 1.22;
}

.ai-report-markdown :deep(.ai-report-heading-3) {
  margin: 1.5rem 0 0.7rem;
  font-size: 1.1rem;
  line-height: 1.35;
}

.ai-report-markdown :deep(p),
.ai-report-markdown :deep(li),
.ai-report-markdown :deep(blockquote) {
  line-height: 1.9;
  color: var(--color-text-primary);
}

.ai-report-markdown :deep(p),
.ai-report-markdown :deep(ul),
.ai-report-markdown :deep(ol),
.ai-report-markdown :deep(table),
.ai-report-markdown :deep(blockquote) {
  margin: 0 0 1rem;
}

.ai-report-markdown :deep(ul),
.ai-report-markdown :deep(ol) {
  padding-left: 1.35rem;
}

.ai-report-markdown :deep(blockquote) {
  border-left: 4px solid rgba(20, 93, 160, 0.26);
  background: rgba(232, 241, 250, 0.52);
  border-radius: 0 1rem 1rem 0;
  padding: 0.9rem 1rem;
  color: var(--color-text-secondary);
}

.ai-report-markdown :deep(table) {
  width: 100%;
  overflow: hidden;
  border-collapse: collapse;
  border: 1px solid var(--color-border-soft);
  border-radius: 1rem;
}

.ai-report-markdown :deep(th),
.ai-report-markdown :deep(td) {
  padding: 0.8rem 0.9rem;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--color-border-soft);
}

.ai-report-markdown :deep(thead th) {
  color: var(--color-text-secondary);
  background: var(--color-surface-muted);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.ai-report-markdown :deep(img) {
  display: block;
  max-width: 100%;
  margin: 1.25rem auto;
  border-radius: 1.25rem;
  border: 1px solid var(--color-border-soft);
  background: #fff;
}

.ai-report-markdown :deep(code) {
  padding: 0.12rem 0.42rem;
  border-radius: 0.5rem;
  background: rgba(15, 23, 42, 0.06);
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 0.84em;
}
</style>
