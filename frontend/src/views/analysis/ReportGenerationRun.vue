<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">运行报告</h2>
          <p class="text-sm text-secondary">这里会持续展示任务拆解、当前处理节点、待确认事项和结果摘要。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading" @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '刷新中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="historyState.loading || !reportForm.topic" @click="handleRefreshHistory">
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '读取中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[1.15fr,1fr,1fr,1fr,0.8fr]">
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
            <option value="fast">快速</option>
            <option value="research">深入</option>
          </select>
        </label>
      </div>

      <div class="grid gap-4 rounded-3xl border border-soft bg-surface-muted/60 p-4 xl:grid-cols-[1.3fr,1fr]">
        <div class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">本次范围</p>
          <p class="text-sm text-secondary">建议优先使用已有分析区间；如果缺少基础结果，任务会自动补齐必要资料。</p>
          <p class="text-xs text-muted">
            建议范围：{{ availableRange.start || '--' }} → {{ availableRange.end || '--' }}
            <span v-if="availableRange.loading" class="ml-2 animate-pulse">检查中…</span>
            <span v-else-if="availableRange.error" class="ml-2 text-danger">{{ availableRange.error }}</span>
            <span v-else-if="availableRange.notice" class="ml-2 text-warning">{{ availableRange.notice }}</span>
          </p>
        </div>
        <div class="flex flex-wrap items-end justify-start gap-2 xl:justify-end">
          <button type="button" class="btn-primary inline-flex items-center gap-2" :disabled="taskState.creating" @click="handleCreateTask">
            <SparklesIcon class="h-4 w-4" :class="taskState.creating ? 'animate-pulse' : ''" />
            {{ taskState.creating ? '提交中…' : primaryActionLabel }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!taskState.id" @click="handleRefreshTask">
            <ArrowPathIcon class="h-4 w-4" />
            刷新状态
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canCancelTask" @click="handleCancelTask">
            <StopIcon class="h-4 w-4" />
            取消任务
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canRetryTask" @click="handleRetryTask">
            <ArrowPathIcon class="h-4 w-4" />
            重新运行
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canOpenResults" @click="goToResultsPage">
            <DocumentTextIcon class="h-4 w-4" />
            查看结构化结果
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canOpenAiResults" @click="goToAiResultsPage">
            <DocumentDuplicateIcon class="h-4 w-4" />
            查看正式文稿
          </button>
        </div>
      </div>

      <div v-if="taskState.error || reportState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ taskState.error || reportState.error }}
      </div>
    </section>

    <section class="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
      <article class="card-surface space-y-4 p-6">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">当前状态</p>
            <h3 class="text-lg font-semibold text-primary">{{ statusHeadline }}</h3>
            <p class="text-sm text-secondary">{{ statusSubline }}</p>
          </div>
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="rounded-full border border-soft px-3 py-1 text-secondary">{{ statusLabel(taskState.status) }}</span>
            <span v-if="taskState.id" class="rounded-full border border-soft px-3 py-1 text-secondary">任务 {{ taskState.id }}</span>
            <span v-if="taskState.threadId" class="rounded-full border border-soft px-3 py-1 text-secondary">线程 {{ taskState.threadId }}</span>
            <span v-if="taskState.streaming" class="rounded-full border border-brand-soft bg-brand-soft px-3 py-1 text-brand">实时连接已建立</span>
            <span v-else-if="taskState.usingPollingFallback" class="rounded-full border border-soft px-3 py-1 text-secondary">自动刷新中</span>
            <span v-else-if="taskState.reconnecting" class="rounded-full border border-soft px-3 py-1 text-secondary">重连中</span>
          </div>
        </div>

        <div class="space-y-3">
          <div class="h-3 overflow-hidden rounded-full bg-base-soft">
            <div class="h-full rounded-full bg-gradient-brand transition-all duration-500" :style="{ width: `${progressPercent}%` }" />
          </div>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">当前阶段</p>
              <p class="mt-2 text-sm font-semibold text-primary">{{ phaseLabel(taskState.phase) }}</p>
              <p class="mt-1 text-xs text-muted">{{ taskState.updatedAt || '等待首次更新' }}</p>
            </article>
            <article class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">审批状态</p>
              <p class="mt-2 text-sm font-semibold text-primary">{{ approvalSummary }}</p>
              <p class="mt-1 text-xs text-muted">需要确认时会在本页直接处理</p>
            </article>
            <article class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">产物状态</p>
              <p class="mt-2 text-sm font-semibold text-primary">{{ artifactSummary }}</p>
              <p class="mt-1 text-xs text-muted">结构化结果与正式文稿会分别更新</p>
            </article>
            <article class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">置信信息</p>
              <p class="mt-2 text-sm font-semibold text-primary">{{ trustHeadline }}</p>
              <p class="mt-1 text-xs text-muted">{{ trustSubline }}</p>
            </article>
          </div>
        </div>
      </article>

      <article class="card-surface space-y-4 p-6">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">结果摘要</p>
          <h3 class="text-lg font-semibold text-primary">{{ digestHeadline }}</h3>
          <p class="text-sm text-secondary">{{ digestSubline }}</p>
        </div>

        <div v-if="hasStructuredDigest" class="space-y-4">
          <div class="grid gap-3 sm:grid-cols-2">
            <article v-for="card in digestCards" :key="card.label" class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ card.label }}</p>
              <p class="mt-2 text-xl font-semibold text-primary">{{ card.value }}</p>
            </article>
          </div>
          <div class="rounded-3xl border border-soft bg-base-soft px-4 py-4">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">摘要</p>
            <p class="mt-2 text-sm leading-7 text-secondary">{{ taskState.structuredResultDigest.summary || '结果生成后，这里会显示本次报告的结论摘要。' }}</p>
          </div>
          <div v-if="taskState.structuredResultDigest.key_findings?.length" class="space-y-2">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">核心发现</p>
            <ul class="space-y-2 text-sm text-secondary">
              <li v-for="item in taskState.structuredResultDigest.key_findings" :key="item" class="rounded-2xl border border-soft bg-surface px-3 py-3">
                {{ item }}
              </li>
            </ul>
          </div>
        </div>

        <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
          结构化结果生成后，这里会先给出结论摘要和关键计数，方便你先判断是否需要进一步查看。
        </div>
      </article>
    </section>

    <section class="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
      <article class="card-surface space-y-4 p-6">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">执行清单</p>
            <p class="text-sm text-secondary">总控代理会按这里的顺序推进，当前步骤会实时更新。</p>
          </div>
          <span class="text-xs text-muted">{{ completedTodoCount }}/{{ todoCards.length || 0 }} 已完成</span>
        </div>

        <div v-if="todoCards.length" class="grid gap-3 md:grid-cols-2">
          <article v-for="todo in todoCards" :key="todo.id" class="rounded-3xl border p-4" :class="todoClass(todo.status)">
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm font-semibold">{{ todo.label }}</p>
                <p class="mt-1 text-xs">{{ todo.statusText }}</p>
              </div>
              <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="todoBadgeClass(todo.status)">
                {{ todo.statusText }}
              </span>
            </div>
          </article>
        </div>

        <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
          创建任务后，这里会出现本次报告的执行清单。
        </div>
      </article>

      <article class="card-surface space-y-4 p-6">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">处理节点</p>
            <p class="text-sm text-secondary">这里只保留各子代理的最终状态和关键说明。</p>
          </div>
          <span class="text-xs text-muted">{{ subagentCards.length }} 个节点</span>
        </div>

        <div v-if="subagentCards.length" class="space-y-3">
          <article v-for="agent in subagentCards" :key="agent.id" class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">{{ agent.displayName }}</p>
                <p class="mt-1 text-xs text-secondary">{{ agent.message || '等待启动' }}</p>
              </div>
              <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="agentBadgeClass(agent.status)">
                {{ agentStatusLabel(agent.status) }}
              </span>
            </div>
            <div class="mt-3 flex flex-wrap gap-2 text-[11px] text-muted">
              <span v-if="agent.started_at" class="rounded-full border border-soft px-2.5 py-1">开始 {{ formatTime(agent.started_at) }}</span>
              <span v-if="agent.updated_at" class="rounded-full border border-soft px-2.5 py-1">更新 {{ formatTime(agent.updated_at) }}</span>
              <span v-if="agent.tool_result_count" class="rounded-full border border-soft px-2.5 py-1">回执 {{ agent.tool_result_count }}</span>
            </div>
          </article>
        </div>

        <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
          任务进入正式处理后，这里会显示检索、证据整理、时间线、传播解释等节点的状态。
        </div>
      </article>
    </section>

    <section class="card-surface space-y-5 p-6">
      <div class="flex items-center justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">人工确认</p>
          <p class="text-sm text-secondary">需要你确认的动作会集中显示在这里，处理后任务会继续往下执行。</p>
        </div>
        <span class="text-xs text-muted">{{ pendingApprovals.length }} 项待处理</span>
      </div>

      <div v-if="taskState.approvals.length" class="space-y-4">
        <article v-for="approval in taskState.approvals" :key="approval.approval_id" class="rounded-3xl border border-soft bg-surface-muted/40 p-5">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="space-y-1">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="text-base font-semibold text-primary">{{ approval.title || '待确认事项' }}</h3>
                <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="approvalBadgeClass(approval.status, approval.decision)">
                  {{ approvalStatusLabel(approval.status, approval.decision) }}
                </span>
              </div>
              <p class="text-sm text-secondary">{{ approval.summary || '请确认是否继续执行。' }}</p>
            </div>
            <div class="text-xs text-muted">
              <p v-if="approval.requested_at">提出于 {{ formatTime(approval.requested_at) }}</p>
              <p v-if="approval.resolved_at">处理于 {{ formatTime(approval.resolved_at) }}</p>
            </div>
          </div>

          <div v-if="approval.action?.markdown_preview" class="mt-4 rounded-3xl border border-soft bg-base-soft px-4 py-4">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">文稿预览</p>
            <pre class="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs leading-6 text-secondary">{{ approval.action.markdown_preview }}</pre>
          </div>

          <div v-if="canEditApproval(approval)" class="mt-4 space-y-2">
            <label class="space-y-2 text-secondary">
              <span class="text-xs font-semibold text-muted">如需改写，可在这里直接编辑文稿</span>
              <textarea
                v-model="approvalEdits[approval.approval_id]"
                class="input min-h-[220px] resize-y"
                :placeholder="approval.action?.markdown_preview || '输入调整后的文稿内容'"
              />
            </label>
          </div>

          <div v-if="approval.status !== 'resolved'" class="mt-4 flex flex-wrap gap-2">
            <button type="button" class="btn-primary" :disabled="processingApprovalId === approval.approval_id" @click="handleApproval(approval, 'approve')">
              {{ processingApprovalId === approval.approval_id ? '处理中…' : '确认继续' }}
            </button>
            <button
              v-if="canEditApproval(approval)"
              type="button"
              class="btn-secondary"
              :disabled="processingApprovalId === approval.approval_id || !approvalEdits[approval.approval_id]?.trim()"
              @click="handleApproval(approval, 'edit')"
            >
              提交修改
            </button>
            <button type="button" class="btn-secondary" :disabled="processingApprovalId === approval.approval_id" @click="handleApproval(approval, 'reject')">
              暂不继续
            </button>
          </div>
        </article>
      </div>

      <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
        当前没有需要你确认的动作。任务如果需要人工确认，会自动停在这里等待处理。
      </div>
    </section>

    <section class="grid gap-6 xl:grid-cols-[0.95fr,1.05fr]">
      <article class="card-surface space-y-4 p-6">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">产物状态</p>
            <p class="text-sm text-secondary">这里会显示结构化结果、正式文稿和其他中间产物是否已经就绪。</p>
          </div>
          <span class="text-xs text-muted">{{ artifactCards.length }} 项</span>
        </div>

        <div v-if="artifactCards.length" class="space-y-3">
          <article v-for="artifact in artifactCards" :key="artifact.key" class="rounded-3xl border border-soft bg-surface-muted/40 p-4">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">{{ artifact.label }}</p>
                <p class="mt-1 text-xs text-secondary">{{ artifact.description }}</p>
              </div>
              <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="artifact.ready ? 'bg-success-soft text-success' : 'bg-base-soft text-secondary'">
                {{ artifact.ready ? '已就绪' : '等待中' }}
              </span>
            </div>
          </article>
        </div>
      </article>

      <article class="card-surface space-y-4 p-6">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">事件流</p>
            <p class="text-sm text-secondary">这里只保留任务关键事件，帮助你快速定位任务停留在哪一步。</p>
          </div>
          <span class="text-xs text-muted">最近 {{ visibleEvents.length }} 条</span>
        </div>

        <div v-if="visibleEvents.length" class="space-y-3">
          <article v-for="event in visibleEvents" :key="`task-event-${event.event_id || event.ts}`" class="rounded-3xl border border-soft bg-surface-muted/40 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="eventTypeClass(event.type)">
                  {{ eventTypeLabel(event.type) }}
                </span>
                <span class="text-sm font-semibold text-primary">{{ event.title || event.message || '任务事件' }}</span>
              </div>
              <span class="text-[11px] text-muted">{{ formatTime(event.ts) }}</span>
            </div>
            <p v-if="event.message" class="mt-2 text-sm text-secondary">{{ event.message }}</p>
            <div v-if="event.payload && Object.keys(event.payload).length" class="mt-3 rounded-2xl border border-soft bg-base-soft px-3 py-3 text-xs text-secondary">
              <pre class="overflow-x-auto whitespace-pre-wrap break-words">{{ prettyPayload(event.payload) }}</pre>
            </div>
          </article>
        </div>

        <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
          创建任务后，这里会显示阶段推进、审批结果和产物更新。
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
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
const approvalEdits = reactive({})
const processingApprovalId = ref('')

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
  loadTopics,
  loadHistory,
  createReportTask,
  loadReportTask,
  cancelReportTask,
  retryReportTask,
  resolveReportApproval,
  applyHistorySelection
} = useReportGeneration()

const primaryActionLabel = computed(() => {
  if (taskState.id && ['queued', 'running', 'waiting_approval'].includes(taskState.status)) return '继续查看任务'
  return '创建任务'
})

const canCancelTask = computed(() => Boolean(taskState.id && ['queued', 'running', 'waiting_approval'].includes(taskState.status)))
const canRetryTask = computed(() => Boolean(taskState.id && ['failed', 'cancelled'].includes(taskState.status)))
const canOpenResults = computed(() => Boolean(
  taskState.artifacts?.report_ready ||
  taskState.structuredResultDigest?.summary ||
  (reportForm.topic && reportForm.start && (reportForm.end || reportForm.start))
))
const canOpenAiResults = computed(() => Boolean(
  taskState.artifacts?.full_report_ready ||
  (reportForm.topic && reportForm.start && (reportForm.end || reportForm.start))
))
const progressPercent = computed(() => Math.max(0, Math.min(100, Number(taskState.percentage || 0))))
const statusHeadline = computed(() => {
  if (!taskState.id) return '尚未创建任务'
  return taskState.message || '任务已创建'
})
const statusSubline = computed(() => {
  if (!taskState.id) return '提交后会先建立执行清单，再逐步推进检索、证据整理、写作和校验。'
  if (taskState.status === 'waiting_approval') return '任务已暂停，等待你确认后继续写入正式结果。'
  if (taskState.status === 'completed') return '结构化结果和正式文稿都已写好，可以直接查看。'
  if (taskState.status === 'failed') return '任务没有完成，你可以先查看事件流，再决定是否重试。'
  if (taskState.status === 'cancelled') return '任务已取消，当前快照和事件记录会保留。'
  return `当前正在处理：${phaseLabel(taskState.phase)}`
})
const hasStructuredDigest = computed(() => Boolean(taskState.structuredResultDigest && Object.keys(taskState.structuredResultDigest).length))
const digestHeadline = computed(() => hasStructuredDigest.value ? '已生成结构化摘要' : '等待结构化结果')
const digestSubline = computed(() => hasStructuredDigest.value
  ? '这里先展示结论摘要和关键计数，适合快速判断结果是否可用。'
  : '任务进入汇总阶段后，这里会优先更新结果摘要。')
const digestCards = computed(() => {
  const counts = taskState.structuredResultDigest?.counts || {}
  return [
    { label: '时间线节点', value: Number(counts.timeline || 0) },
    { label: '主体数量', value: Number(counts.subjects || 0) },
    { label: '证据数量', value: Number(counts.evidence || 0) },
    { label: '引用数量', value: Number(counts.citations || 0) }
  ]
})
const todoCards = computed(() => (Array.isArray(taskState.todos) ? taskState.todos : []).map((item) => ({
  ...item,
  statusText: todoStatusLabel(item?.status)
})))
const completedTodoCount = computed(() => todoCards.value.filter((item) => item.status === 'completed').length)
const subagentCards = computed(() => (Array.isArray(taskState.subagents) ? taskState.subagents : [])
  .filter((item) => item && item.id)
  .map((item) => ({
    ...item,
    displayName: subagentLabel(item.id)
  }))
  .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || ''))))
const pendingApprovals = computed(() => (Array.isArray(taskState.approvals) ? taskState.approvals : [])
  .filter((item) => String(item?.status || '').trim() !== 'resolved'))
const approvalSummary = computed(() => {
  if (!taskState.approvals.length) return '当前无需确认'
  if (!pendingApprovals.value.length) return '已全部处理'
  return `待处理 ${pendingApprovals.value.length} 项`
})
const artifactCards = computed(() => [
  {
    key: 'report_ready',
    label: '结构化结果',
    description: '供查看页展示的结构化对象。',
    ready: Boolean(taskState.artifacts?.report_ready)
  },
  {
    key: 'full_report_ready',
    label: '正式文稿',
    description: '供 AI 报告页展示的完整文稿。',
    ready: Boolean(taskState.artifacts?.full_report_ready)
  },
  {
    key: 'report_runtime_artifact',
    label: '运行时草稿',
    description: '审批通过后保存的本次文稿版本。',
    ready: Boolean(taskState.artifacts?.report_runtime_artifact)
  }
])
const artifactSummary = computed(() => {
  const readyCount = artifactCards.value.filter((item) => item.ready).length
  return readyCount ? `已就绪 ${readyCount} 项` : '暂无已就绪产物'
})
const visibleEvents = computed(() => (Array.isArray(taskEvents.value) ? taskEvents.value.slice(-24).reverse() : []))
const trustHeadline = computed(() => {
  const value = String(taskState.trust?.confidence_label || '').trim()
  return value || '待评估'
})
const trustSubline = computed(() => {
  const evidenceCoverage = Number(taskState.trust?.evidence_coverage || 0)
  if (!evidenceCoverage) return '证据覆盖率会在结果汇总后更新'
  return `证据覆盖率 ${(evidenceCoverage * 100).toFixed(0)}%`
})

function phaseLabel(phase) {
  const mapping = {
    prepare: '范围确认',
    analyze: '基础分析',
    explain: '总体解读',
    interpret: '结构分析',
    write: '文稿生成',
    review: '质量校验',
    persist: '审批与落盘'
  }
  return mapping[String(phase || '').trim()] || '等待中'
}

function statusLabel(status) {
  const mapping = {
    idle: '未开始',
    queued: '排队中',
    running: '进行中',
    waiting_approval: '待确认',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return mapping[String(status || '').trim()] || '处理中'
}

function todoStatusLabel(status) {
  const mapping = {
    pending: '等待开始',
    running: '处理中',
    completed: '已完成',
    failed: '未通过'
  }
  return mapping[String(status || '').trim()] || '等待开始'
}

function todoClass(status) {
  if (status === 'completed') return 'border-brand-soft bg-brand-soft/40 text-primary'
  if (status === 'running') return 'border-brand bg-brand-soft/60 text-primary'
  if (status === 'failed') return 'border-danger/40 bg-danger-soft text-primary'
  return 'border-soft bg-surface-muted/40 text-secondary'
}

function todoBadgeClass(status) {
  if (status === 'completed') return 'bg-success-soft text-success'
  if (status === 'running') return 'bg-brand-soft text-brand'
  if (status === 'failed') return 'bg-danger-soft text-danger'
  return 'bg-base-soft text-secondary'
}

function subagentLabel(id) {
  const mapping = {
    retrieval_router: '检索路由',
    evidence_organizer: '证据整理',
    timeline_analyst: '时间线与因果',
    stance_conflict: '主体与立场',
    propagation_analyst: '传播结构',
    report_coordinator: '总控汇总'
  }
  return mapping[String(id || '').trim()] || String(id || '处理节点')
}

function agentStatusLabel(status) {
  const mapping = { idle: '待命', running: '处理中', done: '已完成', failed: '失败' }
  return mapping[String(status || '').trim()] || '处理中'
}

function agentBadgeClass(status) {
  if (status === 'done') return 'bg-success-soft text-success'
  if (status === 'running') return 'bg-brand-soft text-brand'
  if (status === 'failed') return 'bg-danger-soft text-danger'
  return 'bg-base-soft text-secondary'
}

function approvalStatusLabel(status, decision) {
  if (status === 'resolved' && decision === 'approve') return '已确认'
  if (status === 'resolved' && decision === 'edit') return '已修改'
  if (status === 'resolved' && decision === 'reject') return '已拒绝'
  return '待处理'
}

function approvalBadgeClass(status, decision) {
  if (status === 'resolved' && decision === 'approve') return 'bg-success-soft text-success'
  if (status === 'resolved' && decision === 'edit') return 'bg-brand-soft text-brand'
  if (status === 'resolved' && decision === 'reject') return 'bg-danger-soft text-danger'
  return 'bg-warning-soft text-warning'
}

function eventTypeLabel(type) {
  const mapping = {
    'task.created': '任务创建',
    'phase.started': '阶段开始',
    'phase.progress': '阶段推进',
    'agent.started': '节点启动',
    'agent.memo': '节点说明',
    'tool.called': '调用动作',
    'tool.result': '动作回执',
    'artifact.ready': '产物就绪',
    'artifact.updated': '产物更新',
    'todo.updated': '清单更新',
    'subagent.started': '子代理启动',
    'subagent.completed': '子代理完成',
    'approval.required': '等待确认',
    'approval.resolved': '确认完成',
    'task.completed': '任务完成',
    'task.failed': '任务失败',
    'task.cancelled': '任务取消',
    heartbeat: '状态同步'
  }
  return mapping[String(type || '').trim()] || '任务事件'
}

function eventTypeClass(type) {
  if (['task.failed', 'task.cancelled'].includes(type)) return 'bg-danger-soft text-danger'
  if (['task.completed', 'artifact.ready', 'subagent.completed', 'approval.resolved'].includes(type)) return 'bg-success-soft text-success'
  if (['approval.required'].includes(type)) return 'bg-warning-soft text-warning'
  return 'bg-brand-soft text-brand'
}

function canEditApproval(approval) {
  return String(approval?.tool_name || '').trim() === 'write_final_report'
}

async function handleApproval(approval, decision) {
  if (!taskState.id || !approval?.approval_id) return
  const payload = { decision }
  const edited = String(approvalEdits[approval.approval_id] || '').trim()
  if (decision === 'edit' && canEditApproval(approval) && edited) {
    payload.edited_action = { markdown: edited }
  }
  processingApprovalId.value = approval.approval_id
  try {
    await resolveReportApproval(taskState.id, approval.approval_id, payload)
  } finally {
    processingApprovalId.value = ''
  }
}

function formatTime(value) {
  return String(value || '').trim() || ''
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
  if (taskState.id) await loadReportTask(taskState.id)
}

async function handleCancelTask() {
  await cancelReportTask()
}

async function handleRetryTask() {
  await retryReportTask()
}

async function handleSelectHistory(event) {
  const historyId = String(event?.target?.value || '').trim()
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
