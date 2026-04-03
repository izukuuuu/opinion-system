<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">运行报告</h2>
          <p class="text-sm text-secondary">创建持久任务，实时查看多 Agent 公开备忘录、工具轨迹和复核裁决。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading" @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '同步中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="historyState.loading || !reportForm.topic" @click="handleRefreshHistory">
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '加载中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[1.1fr,1fr,1fr,1fr,0.8fr]">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">专题</span>
          <select v-model="reportForm.topic" class="input" :disabled="topicsState.loading || !topicOptions.length">
            <option value="" disabled>请选择专题</option>
            <option v-for="option in topicOptions" :key="`report-run-topic-${option}`" :value="option">{{ option }}</option>
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

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">模式</span>
          <select v-model="reportForm.mode" class="input">
            <option value="fast">fast</option>
            <option value="research">research</option>
          </select>
        </label>
      </div>

      <div class="grid gap-3 rounded-3xl border border-soft bg-surface-muted/60 p-4 lg:grid-cols-[1.4fr,1fr]">
        <div class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">运行说明</p>
          <p class="text-sm text-secondary">
            系统只展示公开工作备忘录、工具调用和 reviewer 裁决，不直接暴露原始 chain-of-thought。
          </p>
          <p class="text-xs text-muted">
            建议范围：{{ availableRange.start || '--' }} → {{ availableRange.end || '--' }}
            <span v-if="availableRange.loading" class="ml-2 animate-pulse">检查中…</span>
            <span v-else-if="availableRange.error" class="ml-2 text-danger">{{ availableRange.error }}</span>
            <span v-else-if="availableRange.notice" class="ml-2 text-amber-600">{{ availableRange.notice }}</span>
          </p>
        </div>
        <div class="flex flex-wrap items-end justify-start gap-2 lg:justify-end">
          <button type="button" class="btn-primary inline-flex items-center gap-2" :disabled="taskState.creating" @click="handleCreateTask">
            <SparklesIcon class="h-4 w-4" :class="taskState.creating ? 'animate-pulse' : ''" />
            {{ taskState.creating ? '提交中…' : (taskState.id && ['queued', 'running'].includes(taskState.status) ? '继续运行' : '创建任务') }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!taskState.id" @click="handleRefreshTask">
            <ArrowPathIcon class="h-4 w-4" />
            刷新快照
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canCancelTask" @click="handleCancelTask">
            <StopIcon class="h-4 w-4" />
            取消
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canRetryTask" @click="handleRetryTask">
            <ArrowPathIcon class="h-4 w-4" />
            重试
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canOpenResults" @click="goToResultsPage">
            <DocumentTextIcon class="h-4 w-4" />
            查看结果
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canOpenAiResults" @click="goToAiResultsPage">
            <DocumentDuplicateIcon class="h-4 w-4" />
            查看 AI 报告
          </button>
        </div>
      </div>

      <div v-if="taskState.error || reportState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ taskState.error || reportState.error }}
      </div>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">阶段进度</p>
          <h3 class="text-lg font-semibold text-primary">{{ progressHeadline }}</h3>
          <p class="text-sm text-secondary">{{ progressSubline }}</p>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-xs text-muted">
          <span v-if="taskState.id" class="rounded-full border border-soft px-3 py-1">Task {{ taskState.id }}</span>
          <span v-if="taskState.streaming" class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">SSE 已连接</span>
          <span v-else-if="taskState.usingPollingFallback" class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">轮询保活</span>
          <span v-else-if="taskState.reconnecting" class="rounded-full border border-soft px-3 py-1">重连中</span>
          <span v-if="taskState.updatedAt" class="rounded-full border border-soft px-3 py-1">最近更新 {{ taskState.updatedAt }}</span>
        </div>
      </div>

      <div class="space-y-3">
        <div class="h-3 overflow-hidden rounded-full bg-slate-100">
          <div class="h-full rounded-full bg-gradient-to-r from-cyan-500 via-sky-500 to-emerald-500 transition-all duration-500" :style="{ width: `${progressPercent}%` }" />
        </div>
        <div class="grid gap-3 md:grid-cols-7">
          <div
            v-for="stage in taskStageList"
            :key="stage.id"
            class="rounded-2xl border px-3 py-3 text-xs transition"
            :class="stageClass(stage.id)"
          >
            <p class="font-semibold">{{ stage.label }}</p>
            <p class="mt-1 text-[11px] text-muted">{{ stageMeta(stage.id) }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="grid gap-6 xl:grid-cols-[1.6fr,1fr]">
      <div class="card-surface space-y-4 p-6">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">实时事件流</p>
            <p class="text-sm text-secondary">这里只展示真实发生的任务事件、工具回执和公开 memo。</p>
          </div>
          <span class="text-xs text-muted">最近 {{ visibleEvents.length }} 条</span>
        </div>

        <div v-if="visibleEvents.length" class="space-y-3">
          <article
            v-for="event in visibleEvents"
            :key="`task-event-${event.event_id || event.ts}`"
            class="rounded-3xl border border-soft bg-surface-muted/50 p-4"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="eventTypeClass(event.type)">{{ eventTypeLabel(event.type) }}</span>
                <span class="text-sm font-semibold text-primary">{{ event.title || event.message || '任务事件' }}</span>
              </div>
              <span class="text-[11px] text-muted">{{ event.ts || '' }}</span>
            </div>
            <p v-if="event.message" class="mt-2 text-sm text-secondary">{{ event.message }}</p>
            <p v-if="event.delta" class="mt-2 rounded-2xl bg-white/70 px-3 py-2 text-xs text-secondary">{{ event.delta }}</p>
            <div v-if="event.payload && Object.keys(event.payload).length" class="mt-3 rounded-2xl bg-slate-950/[0.03] px-3 py-3 text-xs text-secondary">
              <pre class="overflow-x-auto whitespace-pre-wrap break-words">{{ prettyPayload(event.payload) }}</pre>
            </div>
          </article>
        </div>

        <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
          当前还没有事件。创建任务后，这里会实时显示阶段推进、工具回执和 reviewer 裁决。
        </div>
      </div>

      <div class="space-y-6">
        <section class="card-surface space-y-4 p-6">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">Agent Room</p>
            <p class="text-sm text-secondary">默认折叠原始推理，只保留 agent 的公开工作痕迹。</p>
          </div>
          <div class="space-y-3">
            <article v-for="agent in agentCards" :key="agent.id" class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">{{ agent.name }}</p>
                  <p class="text-xs text-muted">{{ agent.message || '等待启动' }}</p>
                </div>
                <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="agentStatusClass(agent.status)">{{ agentStatusLabel(agent.status) }}</span>
              </div>
              <div class="mt-3 flex flex-wrap gap-2 text-[11px] text-muted">
                <span class="rounded-full border border-soft px-2.5 py-1">tool calls {{ agent.tool_call_count || 0 }}</span>
                <span class="rounded-full border border-soft px-2.5 py-1">tool results {{ agent.tool_result_count || 0 }}</span>
              </div>
              <div v-if="agent.memos?.length" class="mt-3 space-y-2">
                <p v-for="memo in agent.memos.slice(-2)" :key="`${agent.id}-${memo.ts}`" class="rounded-2xl bg-white/80 px-3 py-2 text-xs text-secondary">
                  {{ memo.text }}
                </p>
              </div>
            </article>
          </div>
        </section>

        <section class="card-surface space-y-4 p-6">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">可信度面板</p>
            <p class="text-sm text-secondary">信服度来自工具轨迹、覆盖情况和 reviewer 的真实裁决。</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="rounded-2xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs text-muted">Confidence</p>
              <p class="mt-1 text-lg font-semibold text-primary">{{ trustConfidence }}</p>
            </div>
            <div class="rounded-2xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs text-muted">Manual Review</p>
              <p class="mt-1 text-lg font-semibold" :class="trustManualClass">{{ trustManualText }}</p>
            </div>
            <div class="rounded-2xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs text-muted">Evidence Coverage</p>
              <p class="mt-1 text-lg font-semibold text-primary">{{ trustCoverage }}</p>
            </div>
            <div class="rounded-2xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs text-muted">Issues</p>
              <p class="mt-1 text-lg font-semibold text-primary">{{ trustIssueCount }}</p>
            </div>
          </div>
          <div class="rounded-3xl border border-soft bg-surface-muted/60 p-4">
            <p class="text-sm font-semibold text-primary">Reviewer Verdict</p>
            <p class="mt-2 text-sm text-secondary">{{ trustVerdict }}</p>
          </div>
          <div v-if="trustIssues.length" class="space-y-2">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">需要关注</p>
            <div class="flex flex-wrap gap-2">
              <span v-for="issue in trustIssues" :key="issue" class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                {{ issue }}
              </span>
            </div>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowPathIcon,
  ClockIcon,
  DocumentDuplicateIcon,
  DocumentTextIcon,
  SparklesIcon,
  StopIcon
} from '@heroicons/vue/24/outline'
import { useReportGeneration } from '../../composables/useReportGeneration'

const router = useRouter()
const {
  topicsState,
  topicOptions,
  reportForm,
  availableRange,
  reportState,
  historyState,
  taskState,
  reportHistory,
  selectedHistoryId,
  taskEvents,
  taskStageList,
  loadTopics,
  loadHistory,
  createReportTask,
  loadReportTask,
  cancelReportTask,
  retryReportTask,
  applyHistorySelection
} = useReportGeneration()

const canCancelTask = computed(() => Boolean(taskState.id && ['queued', 'running'].includes(taskState.status)))
const canRetryTask = computed(() => Boolean(taskState.id && ['failed', 'cancelled'].includes(taskState.status)))
const canOpenResults = computed(() => Boolean(
  (taskState.artifacts?.report_ready && taskState.topic && taskState.start && taskState.end) ||
  (reportForm.topic && reportForm.start && (reportForm.end || reportForm.start))
))
const canOpenAiResults = computed(() => Boolean(
  (taskState.artifacts?.full_report_ready && taskState.topic && taskState.start && taskState.end) ||
  (reportForm.topic && reportForm.start && (reportForm.end || reportForm.start))
))
const progressPercent = computed(() => {
  if (taskState.id) return Math.max(0, Math.min(100, Number(taskState.percentage || 0)))
  return 0
})
const progressHeadline = computed(() => {
  if (!taskState.id) return '尚未创建任务'
  return taskState.message || '任务已创建'
})
const progressSubline = computed(() => {
  if (!taskState.id) return '创建任务后，系统会在这里持续展示阶段进度和 agent 事件。'
  if (taskState.status === 'completed') return '报告产物已写入，可直接进入查看页。'
  if (taskState.status === 'failed') return '任务执行失败，可查看事件流并按需重试。'
  if (taskState.status === 'cancelled') return '任务已取消，快照和事件仍会保留。'
  return `当前阶段：${stageLabel(taskState.phase)}`
})
const visibleEvents = computed(() => (Array.isArray(taskEvents.value) ? taskEvents.value.slice(-40).reverse() : []))
const agentCards = computed(() => Array.isArray(taskState.agents) ? taskState.agents : [])
const trust = computed(() => taskState.trust && typeof taskState.trust === 'object' ? taskState.trust : {})
const trustConfidence = computed(() => String(trust.value.confidence_label || '待评估'))
const trustIssueCount = computed(() => Number(trust.value.issue_count || (Array.isArray(trust.value.issues) ? trust.value.issues.length : 0) || 0))
const trustVerdict = computed(() => String(trust.value.verdict || 'Reviewer 尚未给出裁决。'))
const trustIssues = computed(() => Array.isArray(trust.value.issues) ? trust.value.issues : [])
const trustCoverage = computed(() => `${Math.round(Number(trust.value.evidence_coverage || 0) * 100)}%`)
const trustManualText = computed(() => (trust.value.requires_manual_review ? '需要人工复核' : '可直接交付'))
const trustManualClass = computed(() => trust.value.requires_manual_review ? 'text-amber-700' : 'text-emerald-700')

function stageLabel(phase) {
  const item = taskStageList.find((entry) => entry.id === phase)
  return item?.label || '等待中'
}

function stageClass(stageId) {
  if (!taskState.id) return 'border-soft bg-surface-muted/40 text-secondary'
  const currentIndex = taskStageList.findIndex((item) => item.id === taskState.phase)
  const targetIndex = taskStageList.findIndex((item) => item.id === stageId)
  if (targetIndex < currentIndex) return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (stageId === taskState.phase) return 'border-cyan-200 bg-cyan-50 text-cyan-700'
  return 'border-soft bg-surface-muted/40 text-secondary'
}

function stageMeta(stageId) {
  if (stageId === taskState.phase) return taskState.message || '执行中'
  if (!taskState.id) return '等待'
  const currentIndex = taskStageList.findIndex((item) => item.id === taskState.phase)
  const targetIndex = taskStageList.findIndex((item) => item.id === stageId)
  return targetIndex < currentIndex ? '已完成' : '待进入'
}

function eventTypeLabel(type) {
  const mapping = {
    'task.created': '创建',
    'phase.started': '阶段启动',
    'phase.progress': '阶段进度',
    'agent.started': 'Agent 启动',
    'agent.memo': '公开备忘录',
    'tool.called': '工具调用',
    'tool.result': '工具回执',
    'review.verdict': '复核裁决',
    'artifact.ready': '产物就绪',
    heartbeat: '保活心跳',
    'task.completed': '任务完成',
    'task.failed': '任务失败',
    'task.cancelled': '任务取消'
  }
  return mapping[type] || type || '事件'
}

function eventTypeClass(type) {
  if (['task.failed'].includes(type)) return 'bg-rose-50 text-rose-700'
  if (['task.completed', 'artifact.ready'].includes(type)) return 'bg-emerald-50 text-emerald-700'
  if (['review.verdict', 'tool.result'].includes(type)) return 'bg-amber-50 text-amber-700'
  return 'bg-cyan-50 text-cyan-700'
}

function agentStatusLabel(status) {
  const mapping = { idle: '待命', running: '运行中', done: '已完成', failed: '失败' }
  return mapping[status] || '待命'
}

function agentStatusClass(status) {
  if (status === 'done') return 'bg-emerald-50 text-emerald-700'
  if (status === 'running') return 'bg-cyan-50 text-cyan-700'
  if (status === 'failed') return 'bg-rose-50 text-rose-700'
  return 'bg-slate-100 text-slate-600'
}

function prettyPayload(payload) {
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload || '')
  }
}

async function handleCreateTask() {
  await createReportTask()
}

async function handleRefreshHistory() {
  const topic = String(reportForm.topic || '').trim()
  if (!topic) return
  await loadHistory(topic)
}

async function handleRefreshTask() {
  if (taskState.id) {
    await loadReportTask(taskState.id)
  }
}

async function handleCancelTask() {
  await cancelReportTask()
}

async function handleRetryTask() {
  await retryReportTask()
}

async function handleSelectHistory(event) {
  const historyId = String(event.target.value || '').trim()
  if (!historyId) return
  await applyHistorySelection(historyId, { shouldLoad: false })
}

function goToResultsPage() {
  if (!canOpenResults.value) return
  router.push({ name: 'report-generation-view' })
}

function goToAiResultsPage() {
  if (!canOpenAiResults.value) return
  router.push({ name: 'report-generation-ai' })
}
</script>
