<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">HTML 报告</h2>
          <p class="text-sm text-secondary">这里预览可交付网页报告。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading" @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '同步中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" @click="goToMarkdownPage">
            <DocumentTextIcon class="h-4 w-4" />
            Markdown 文稿
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" @click="goToRunPage">
            <PlayCircleIcon class="h-4 w-4" />
            前往运行页
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
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="htmlPreview.loading" @click="handleLoad">
            <ArrowPathIcon class="h-4 w-4" :class="htmlPreview.loading ? 'animate-spin' : ''" />
            {{ htmlPreview.loading ? '读取中…' : '读取 HTML' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!hasHtmlPreview" @click="openHtmlInNewTab">
            <ArrowTopRightOnSquareIcon class="h-4 w-4" />
            新窗口打开
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!hasHtmlPreview" @click="exportHtml">
            <ArrowDownTrayIcon class="h-4 w-4" />
            导出 HTML
          </button>
        </div>
      </div>

      <div v-if="htmlPreview.error"
        class="rounded-2xl border border-warning/40 bg-warning-soft px-4 py-3 text-sm text-warning">
        {{ htmlPreview.error }}
      </div>
    </section>

    <section v-if="hasHtmlPreview" class="card-surface overflow-hidden">
      <div class="border-b border-soft px-5 py-4">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">网页报告</p>
        <p class="mt-1 text-sm text-secondary">已读取网页版本，可直接核对最终版式。</p>
      </div>
      <iframe
        class="html-report-frame"
        title="HTML 报告预览"
        sandbox="allow-scripts allow-same-origin"
        :srcdoc="htmlPreview.srcdoc"
      />
    </section>

    <section v-else class="card-surface p-6 text-sm text-muted">
      请先选择专题和时间范围，然后读取 HTML 报告。
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ArrowTopRightOnSquareIcon,
  DocumentTextIcon,
  PlayCircleIcon
} from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'

const router = useRouter()

const {
  topicsState,
  topicOptions,
  reportForm,
  availableRange,
  historyState,
  reportHistory,
  selectedHistoryId,
  loadTopics,
  loadFullReportHtml,
  applyHistorySelection
} = useReportGeneration()

const htmlPreview = ref({
  loading: false,
  error: '',
  srcdoc: ''
})

const hasHtmlPreview = computed(() => Boolean(String(htmlPreview.value.srcdoc || '').trim()))
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

const handleLoad = async () => {
  htmlPreview.value = { loading: true, error: '', srcdoc: '' }
  try {
    const html = await loadFullReportHtml({
      topic: reportForm.topic,
      start: reportForm.start,
      end: reportForm.end
    })
    htmlPreview.value = { loading: false, error: '', srcdoc: html }
  } catch (error) {
    htmlPreview.value = {
      loading: false,
      error: error instanceof Error ? error.message : String(error),
      srcdoc: ''
    }
  }
}

const exportHtml = () => {
  if (!hasHtmlPreview.value) return
  const blob = new Blob([htmlPreview.value.srcdoc], { type: 'text/html;charset=utf-8' })
  downloadBlob(blob, 'html-report.html')
}

const openHtmlInNewTab = () => {
  if (!hasHtmlPreview.value) return
  const blob = new Blob([htmlPreview.value.srcdoc], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(url), 30000)
}

const goToRunPage = () => router.push({ name: 'report-generation-run' })
const goToMarkdownPage = () => router.push({ name: 'report-generation-ai' })

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
.html-report-frame {
  display: block;
  width: 100%;
  min-height: calc(100vh - 15rem);
  border: 0;
  background: var(--color-surface);
}
</style>
