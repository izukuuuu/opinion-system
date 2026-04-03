<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">AI 完整报告</h2>
          <p class="text-sm text-secondary">基于当前结构化报告、知识库方法论和 reviewer 裁决，生成一份可导航的 Markdown 长报告。</p>
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
          <span class="text-xs font-semibold text-muted">专题 (Topic)</span>
          <select v-model="reportForm.topic" class="input" :disabled="topicsState.loading || !topicOptions.length" required>
            <option value="" disabled>请选择专题</option>
            <option v-for="option in topicOptions" :key="`full-report-topic-${option}`" :value="option">
              {{ option }}
            </option>
          </select>
          <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">历史记录</span>
          <select :value="selectedHistoryId" class="input" :disabled="historyState.loading || !reportHistory.length" @change="handleSelectHistory">
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
          <span v-else-if="availableRange.notice" class="ml-2 text-amber-600">{{ availableRange.notice }}</span>
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
            <h3 class="mt-2 text-lg font-semibold text-primary">{{ fullReport.title }}</h3>
            <p class="mt-2 text-sm text-secondary">{{ fullReport.subtitle || 'AI 完整报告视图' }}</p>
          </div>
          <div class="space-y-2 text-sm text-secondary">
            <p>{{ fullReport.rangeText }}</p>
            <p>最近更新：{{ fullReport.lastUpdated }}</p>
            <p v-if="fullReportState.lastLoaded">前端读取：{{ fullReportState.lastLoaded }}</p>
          </div>
          <div class="flex flex-wrap gap-2 text-xs">
            <span class="rounded-full border border-soft bg-surface px-3 py-1 text-secondary">
              brief {{ fullMeta.briefSource }}
            </span>
            <span class="rounded-full border border-soft bg-surface px-3 py-1 text-secondary">
              draft {{ fullMeta.draftSource }}
            </span>
            <span class="rounded-full border border-soft bg-surface px-3 py-1 text-secondary">
              revise {{ fullMeta.reviseSource }}
            </span>
          </div>
        </section>

        <section class="card-surface space-y-4 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">章节导航</p>
            <p class="mt-2 text-sm text-secondary">当前目录直接来自 Markdown 标题。</p>
          </div>
          <nav class="space-y-1.5">
            <a
              v-for="item in tocItems"
              :key="item.id"
              :href="`#${item.id}`"
              class="block rounded-xl px-3 py-2 text-sm transition hover:bg-brand-soft hover:text-brand-700"
              :class="item.level === 1 ? 'font-semibold text-primary' : (item.level === 2 ? 'pl-3 text-secondary' : 'pl-6 text-muted')"
            >
              {{ item.text }}
            </a>
          </nav>
        </section>

        <section class="card-surface space-y-4 p-5">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">复核裁决</p>
            <p class="mt-2 text-sm text-secondary">{{ reviewVerdict.verdict || '暂无 reviewer 裁决。' }}</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div class="rounded-2xl border border-soft bg-surface-muted/60 p-4">
              <p class="text-xs text-muted">状态</p>
              <p class="mt-1 text-lg font-semibold" :class="reviewVerdict.requiresManual ? 'text-amber-700' : 'text-emerald-700'">
                {{ reviewVerdict.statusText }}
              </p>
            </div>
            <div class="rounded-2xl border border-soft bg-surface-muted/60 p-4">
              <p class="text-xs text-muted">知识术语</p>
              <p class="mt-1 text-sm font-semibold text-primary">{{ knowledgeTermsText }}</p>
            </div>
          </div>
          <div v-if="reviewVerdict.focusAreas.length" class="space-y-2">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">人工复核重点</p>
            <div class="flex flex-wrap gap-2">
              <span v-for="item in reviewVerdict.focusAreas" :key="item" class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                {{ item }}
              </span>
            </div>
          </div>
        </section>
      </aside>

      <article class="card-surface overflow-hidden p-0">
        <div class="border-b border-soft px-6 py-5">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">Markdown Preview</p>
          <p class="mt-2 text-sm text-secondary">图片由系统根据结构化数据自动插入，导出 HTML 时会保持内嵌。</p>
        </div>
        <div class="ai-report-body px-6 py-8" v-html="renderedHtml"></div>
      </article>
    </section>

    <section v-else class="card-surface p-6 text-sm text-muted">
      请先选择专题与时间范围，然后点击“读取 AI 报告”。
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
import { useReportGeneration } from '../../composables/useReportGeneration'
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
const fullMeta = computed(() => ({
  briefSource: String(fullReport.value?.meta?.brief_source || 'fallback').trim(),
  draftSource: String(fullReport.value?.meta?.draft_source || 'fallback').trim(),
  reviseSource: String(fullReport.value?.meta?.revise_source || 'fallback').trim(),
  knowledgeTerms: Array.isArray(fullReport.value?.meta?.knowledge_terms)
    ? fullReport.value.meta.knowledge_terms.map((item) => String(item || '').trim()).filter(Boolean)
    : []
}))
const tocItems = computed(() => extractMarkdownToc(fullReport.value?.markdown || ''))
const renderedHtml = computed(() => renderAiReportMarkdown(fullReport.value?.markdown || '', { assets: fullReport.value?.assets || [] }))

const reviewVerdict = computed(() => {
  const payload = fullReport.value?.reviewVerdict || {}
  const focusAreas = Array.isArray(payload?.focus_areas || payload?.focusAreas)
    ? (payload.focus_areas || payload.focusAreas).map((item) => String(item || '').trim()).filter(Boolean)
    : []
  const requiresManual = Boolean(payload?.requires_manual_review || payload?.requiresManualReview || fullReport.value?.meta?.requires_manual_review)
  return {
    verdict: String(payload?.verdict || '').trim(),
    requiresManual,
    focusAreas,
    statusText: requiresManual ? '需要人工复核' : '可直接阅读'
  }
})

const knowledgeTermsText = computed(() => fullMeta.value.knowledgeTerms.length ? fullMeta.value.knowledgeTerms.join('、') : '暂无')

const handleSelectHistory = (event) => {
  applyHistorySelection(event?.target?.value || '')
}

const handleRefreshHistory = async () => {
  await loadHistory(reportForm.topic)
}

const handleLoad = async () => {
  await loadFullReport()
}

const handleRegenerate = async () => {
  const task = await createReportTask()
  if (task?.id) {
    router.push({ name: 'report-generation-run' })
  }
}

const goToRunPage = () => router.push({ name: 'report-generation-run' })

const exportMarkdown = () => {
  if (!fullReport.value) return
  const markdown = exportableAiMarkdown(fullReport.value.markdown || '', { assets: fullReport.value.assets || [] })
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  downloadBlob(blob, `${fullReport.value.title || 'ai-report'}.md`)
}

const exportHtml = () => {
  if (!fullReport.value) return
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(fullReport.value.title || 'AI 完整报告')}</title>
  <style>
    body { margin: 0; padding: 40px 24px; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; color: #0f172a; background: #f8fafc; }
    .shell { max-width: 980px; margin: 0 auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 24px; overflow: hidden; }
    .head { padding: 32px 36px; border-bottom: 1px solid #e2e8f0; background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%); }
    .head h1 { margin: 0; font-size: 32px; }
    .head p { margin: 10px 0 0; color: #475569; }
    .body { padding: 32px 36px 44px; }
    .body h1, .body h2, .body h3 { color: #0f172a; line-height: 1.3; }
    .body h1 { font-size: 30px; margin: 0 0 18px; }
    .body h2 { font-size: 24px; margin: 34px 0 14px; }
    .body h3 { font-size: 18px; margin: 24px 0 10px; }
    .body p, .body li { font-size: 15px; line-height: 1.9; color: #334155; }
    .body img { display: block; width: 100%; max-width: 920px; margin: 18px auto; border-radius: 20px; border: 1px solid #dbeafe; background: #f8fafc; }
    .body ul, .body ol { padding-left: 22px; }
    .body blockquote { margin: 20px 0; padding: 14px 18px; border-left: 4px solid #93c5fd; background: #eff6ff; color: #1e3a8a; }
    .body code { padding: 2px 6px; border-radius: 6px; background: #e2e8f0; }
  </style>
</head>
<body>
  <div class="shell">
    <header class="head">
      <h1>${escapeHtml(fullReport.value.title || 'AI 完整报告')}</h1>
      <p>${escapeHtml(fullReport.value.subtitle || fullReport.value.rangeText || '')}</p>
      <p>${escapeHtml(fullReport.value.lastUpdated || '')}</p>
    </header>
    <main class="body">${renderedHtml.value}</main>
  </div>
</body>
</html>`
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  downloadBlob(blob, `${fullReport.value.title || 'ai-report'}.html`)
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

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
</script>

<style scoped>
.ai-report-body :deep(.ai-report-heading) {
  scroll-margin-top: 100px;
  color: rgb(15 23 42);
  line-height: 1.3;
}

.ai-report-body :deep(.ai-report-heading-1) {
  margin: 0 0 1.25rem;
  font-size: 2rem;
  font-weight: 700;
}

.ai-report-body :deep(.ai-report-heading-2) {
  margin: 2rem 0 0.875rem;
  font-size: 1.45rem;
  font-weight: 700;
}

.ai-report-body :deep(.ai-report-heading-3) {
  margin: 1.5rem 0 0.75rem;
  font-size: 1.1rem;
  font-weight: 700;
}

.ai-report-body :deep(p),
.ai-report-body :deep(li) {
  color: rgb(51 65 85);
  font-size: 0.97rem;
  line-height: 1.9;
}

.ai-report-body :deep(ul),
.ai-report-body :deep(ol) {
  padding-left: 1.35rem;
}

.ai-report-body :deep(img) {
  display: block;
  width: 100%;
  max-width: 920px;
  margin: 1.25rem auto;
  border-radius: 1.25rem;
  border: 1px solid rgb(219 234 254);
  background: rgb(248 250 252);
  box-shadow: 0 18px 40px -30px rgba(15, 23, 42, 0.45);
}

.ai-report-body :deep(blockquote) {
  margin: 1.25rem 0;
  padding: 0.95rem 1rem;
  border-left: 4px solid rgb(147 197 253);
  background: rgb(239 246 255);
  color: rgb(30 64 175);
  border-radius: 0 1rem 1rem 0;
}

.ai-report-body :deep(code) {
  padding: 0.1rem 0.35rem;
  border-radius: 0.45rem;
  background: rgb(226 232 240);
  font-size: 0.92em;
}

.ai-report-body :deep(hr) {
  margin: 1.75rem 0;
  border: 0;
  border-top: 1px solid rgb(226 232 240);
}
</style>
