<template>
  <div class="space-y-4">
    <section class="rounded-3xl border border-soft bg-gradient-to-br from-white to-surface-muted/40 p-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="space-y-1.5">
          <div class="flex flex-wrap items-center gap-2">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">执行状态</p>
            <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="workerToneClass">
              {{ workerLabel }}
            </span>
          </div>
          <p :class="['text-lg font-semibold', summaryToneClass]">{{ summaryTitle }}</p>
          <p class="text-xs text-secondary">{{ summaryDetail }}</p>
        </div>
        <div class="text-right">
          <p class="text-3xl font-semibold text-primary">{{ summaryPercent }}%</p>
          <p class="text-xs text-muted">共 {{ safeTasks.length }} 项</p>
        </div>
      </div>

        <div class="mt-4 h-2 overflow-hidden rounded-full bg-soft/60">
          <div
            class="h-full rounded-full transition-all duration-500"
            :style="{ ...summaryBarStyle, width: `${summaryPercent}%` }"
          />
        </div>

      <div class="mt-4 grid gap-2 sm:grid-cols-4">
        <div class="rounded-2xl border border-soft bg-white/80 px-3 py-3">
          <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">已完成</p>
          <p class="mt-1 text-lg font-semibold text-primary">{{ completedCount }} / {{ safeTasks.length }}</p>
        </div>
        <div class="rounded-2xl border border-soft bg-white/80 px-3 py-3">
          <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">执行中</p>
          <p class="mt-1 text-lg font-semibold text-primary">{{ runningCount }}</p>
        </div>
        <div class="rounded-2xl border border-soft bg-white/80 px-3 py-3">
          <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">排队中</p>
          <p class="mt-1 text-lg font-semibold text-primary">{{ queuedCount }}</p>
        </div>
        <div class="rounded-2xl border border-soft bg-white/80 px-3 py-3">
          <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">失败</p>
          <p class="mt-1 text-lg font-semibold text-primary">{{ failedCount }}</p>
        </div>
      </div>
    </section>

    <section v-if="notice" class="rounded-2xl border border-brand-soft bg-brand-soft-muted px-4 py-3 text-sm text-secondary">
      {{ notice }}
    </section>

    <section v-if="error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
      {{ error }}
    </section>

    <section v-if="safeTasks.length" class="space-y-3">
      <article
        v-for="task in safeTasks"
        :key="task.id"
        class="rounded-3xl border border-soft bg-white/90 px-4 py-4"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="text-sm font-semibold text-primary">{{ task.label }}</h3>
              <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="statusTone(task.status)">
                {{ statusLabel(task.status) }}
              </span>
              <span class="inline-flex items-center rounded-full border border-soft bg-surface-muted px-2.5 py-1 text-[11px] font-medium text-secondary">
                {{ phaseLabel(task.phase) }}
              </span>
            </div>
            <p class="text-sm leading-6 text-secondary">{{ task.message || '等待状态更新。' }}</p>
            <p v-if="task.currentTarget" class="text-xs text-muted">当前范围：{{ task.currentTarget }}</p>
            <p
              v-if="task.sentimentTotal > 0 && task.status === 'running'"
              class="text-xs text-muted"
            >
              情感分类：{{ task.sentimentProcessed }} / {{ task.sentimentTotal }}，已判定 {{ task.sentimentClassified }} 条
            </p>
          </div>
          <div class="text-right">
            <p class="text-2xl font-semibold text-primary">{{ task.percentage }}%</p>
            <p class="text-xs text-muted">{{ task.updatedAt || '等待更新' }}</p>
          </div>
        </div>

        <div class="mt-3 h-2 overflow-hidden rounded-full bg-soft/60">
          <div
            class="h-full rounded-full transition-all duration-500"
            :style="{ ...progressBarStyle(task.status), width: `${task.percentage}%` }"
          />
        </div>
      </article>
    </section>

    <p v-else class="text-xs text-muted">
      {{ loading ? '正在同步任务状态…' : emptyLabel }}
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tasks: {
    type: Array,
    default: () => []
  },
  worker: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  },
  notice: {
    type: String,
    default: ''
  },
  emptyLabel: {
    type: String,
    default: '当前范围还没有执行记录。'
  }
})

const safeTasks = computed(() => (Array.isArray(props.tasks) ? props.tasks : []))

const completedCount = computed(() => safeTasks.value.filter((task) => task.status === 'completed').length)
const runningCount = computed(() => safeTasks.value.filter((task) => task.status === 'running').length)
const queuedCount = computed(() => safeTasks.value.filter((task) => task.status === 'queued').length)
const failedCount = computed(() => safeTasks.value.filter((task) => ['failed', 'cancelled'].includes(task.status)).length)

const summaryPercent = computed(() => {
  if (!safeTasks.value.length) return 0
  const total = safeTasks.value.reduce((sum, task) => sum + Math.max(0, Math.min(100, Number(task.percentage || 0))), 0)
  return Math.round(total / safeTasks.value.length)
})

const summaryTitle = computed(() => {
  if (!safeTasks.value.length) return props.loading ? '正在同步任务状态' : '等待执行'
  if (runningCount.value) return `正在执行 ${runningCount.value} 项`
  if (queuedCount.value) return `排队中 ${queuedCount.value} 项`
  if (failedCount.value && completedCount.value) return '部分任务未完成'
  if (failedCount.value) return '任务执行失败'
  return '全部任务已完成'
})

const runningLabels = computed(() => safeTasks.value.filter((task) => task.status === 'running').map((task) => task.label))
const queuedLabels = computed(() => safeTasks.value.filter((task) => task.status === 'queued').map((task) => task.label))

const summaryDetail = computed(() => {
  if (runningLabels.value.length) return `当前执行：${runningLabels.value.join('、')}`
  if (queuedLabels.value.length) return `等待调度：${queuedLabels.value.join('、')}`
  if (failedCount.value) return '存在失败项，先查看任务卡片里的错误信息。'
  if (safeTasks.value.length) return '最近一次提交的后台任务都已结束。'
  return '提交任务后，这里会展示真实 worker 状态与阶段进度。'
})

const summaryToneClass = computed(() => {
  if (failedCount.value && !runningCount.value && !queuedCount.value) return 'text-danger'
  if (runningCount.value || queuedCount.value) return 'text-brand'
  return 'text-success'
})

const summaryBarStyle = computed(() => {
  if (failedCount.value && !runningCount.value && !queuedCount.value) {
    return { backgroundColor: 'rgb(var(--color-danger-500) / 1)' }
  }
  if (runningCount.value || queuedCount.value) {
    return { backgroundColor: 'rgb(var(--color-brand-500) / 1)' }
  }
  return { backgroundColor: 'rgb(var(--color-success-500) / 1)' }
})

const workerLabel = computed(() => {
  const status = String(props.worker?.status || '').trim()
  const activeCount = Number(props.worker?.active_count || 0)
  if (status === 'running') return activeCount > 0 ? `Worker 运行中 · ${activeCount} 项` : 'Worker 运行中'
  if (status === 'idle') return 'Worker 待命'
  if (status === 'starting') return 'Worker 启动中'
  return 'Worker 未运行'
})

const workerToneClass = computed(() => {
  const status = String(props.worker?.status || '').trim()
  if (status === 'running') return 'bg-brand-50 text-brand-700'
  if (status === 'idle') return 'bg-success-soft text-success'
  if (status === 'starting') return 'bg-amber-50 text-amber-700'
  return 'bg-base-soft text-secondary'
})

const statusLabel = (status) => {
  const mapping = {
    queued: '排队中',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return mapping[String(status || '').trim()] || '等待中'
}

const phaseLabel = (phase) => {
  const mapping = {
    queued: '等待调度',
    prepare: '准备数据',
    analyze: '运行分析',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return mapping[String(phase || '').trim()] || '处理中'
}

const statusTone = (status) => {
  if (status === 'completed') return 'bg-success-soft text-success'
  if (status === 'failed' || status === 'cancelled') return 'bg-danger-soft text-danger'
  if (status === 'running') return 'bg-brand-50 text-brand-700'
  if (status === 'queued') return 'bg-amber-50 text-amber-700'
  return 'bg-base-soft text-secondary'
}

const progressBarStyle = (status) => {
  if (status === 'completed') return { backgroundColor: 'rgb(var(--color-success-500) / 1)' }
  if (status === 'failed' || status === 'cancelled') return { backgroundColor: 'rgb(var(--color-danger-500) / 1)' }
  if (status === 'running') return { backgroundColor: 'rgb(var(--color-brand-500) / 1)' }
  if (status === 'queued') return { backgroundColor: 'rgb(var(--color-warning-400) / 1)' }
  return { backgroundColor: 'rgb(var(--color-brand-200) / 1)' }
}
</script>
