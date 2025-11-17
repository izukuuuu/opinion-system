<template>
  <div>
    <div v-if="safeLogs.length" class="space-y-4">
      <section class="rounded-3xl border border-soft bg-gradient-to-br from-white to-surface-muted/40 p-4 shadow-inner">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">分析进度</p>
            <p :class="['text-lg font-semibold', summaryToneClass]">{{ summaryTitle }}</p>
            <p class="text-xs text-secondary">{{ summaryDetail }}</p>
          </div>
          <div class="text-right">
            <p class="text-3xl font-semibold text-primary">{{ summaryPercent }}%</p>
            <p class="text-xs text-muted">共 {{ safeLogs.length }} 项</p>
          </div>
        </div>
        <div class="mt-4 h-2 overflow-hidden rounded-full bg-soft/60">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="summaryBarClass"
            :style="{ width: `${summaryPercent}%` }"
          />
        </div>
      </section>

      <section class="rounded-3xl border border-dashed border-soft bg-white/70 p-4 text-sm text-secondary">
        <p class="text-sm font-semibold text-primary">
          {{ detailHeadline }}
        </p>
        <p v-if="queuedLabels.length" class="mt-1 text-xs text-muted">
          排队中：{{ queuedLabels.join('、') }}
        </p>
        <div class="mt-3 flex flex-wrap gap-2 text-[11px] font-semibold">
          <span class="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
            成功 {{ completedCount }} / {{ summaryFlags.total }}
          </span>
          <span
            v-if="statusCounts.running"
            class="inline-flex items-center rounded-full bg-brand-50 px-3 py-1 text-brand-700"
          >
            执行中 {{ statusCounts.running }}
          </span>
          <span
            v-if="statusCounts.queued"
            class="inline-flex items-center rounded-full bg-amber-50 px-3 py-1 text-amber-700"
          >
            排队 {{ statusCounts.queued }}
          </span>
          <span
            v-if="statusCounts.error"
            class="inline-flex items-center rounded-full bg-rose-50 px-3 py-1 text-rose-700"
          >
            失败 {{ statusCounts.error }}
          </span>
        </div>
      </section>
    </div>
    <p v-else class="text-xs text-muted">{{ emptyLabel }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  logs: {
    type: Array,
    default: () => []
  },
  emptyLabel: {
    type: String,
    default: ''
  }
})

const STATUS_CONFIG = {
  ok: {
    text: '已完成',
    percent: 100,
    bar: 'bg-emerald-500',
    chip: 'bg-emerald-50 text-emerald-700'
  },
  error: {
    text: '执行失败',
    percent: 100,
    bar: 'bg-rose-500',
    chip: 'bg-rose-50 text-rose-700'
  },
  running: {
    text: '执行中',
    percent: 80,
    bar: 'bg-brand-500',
    chip: 'bg-brand-50 text-brand-700'
  },
  queued: {
    text: '排队中',
    percent: 20,
    bar: 'bg-amber-400',
    chip: 'bg-amber-50 text-amber-700'
  },
  pending: {
    text: '处理中',
    percent: 60,
    bar: 'bg-amber-400',
    chip: 'bg-amber-50 text-amber-700'
  }
}

const statusMeta = (status = 'pending') => {
  return STATUS_CONFIG[status] || STATUS_CONFIG.pending
}

const progressPercent = (log) => {
  if (typeof log?.progress === 'number') {
    const value = Math.max(0, Math.min(100, log.progress))
    return Math.round(value)
  }
  return statusMeta(log?.status).percent
}

const safeLogs = computed(() => props.logs ?? [])

const averagePercent = computed(() => {
  if (!safeLogs.value.length) return 0
  const total = safeLogs.value.reduce((sum, log) => sum + progressPercent(log), 0)
  return Math.round(total / safeLogs.value.length)
})

const completedCount = computed(() => safeLogs.value.filter((log) => log.status === 'ok').length)

const summaryFlags = computed(() => {
  const logs = safeLogs.value
  return {
    hasError: logs.some((log) => log.status === 'error'),
    inProgress: logs.some((log) => log.status !== 'ok'),
    total: logs.length
  }
})

const summaryPercent = computed(() => (safeLogs.value.length ? averagePercent.value : 0))

const summaryTitle = computed(() => {
  if (!safeLogs.value.length) return '等待执行'
  if (summaryFlags.value.hasError) return '部分失败，请查看日志'
  if (!summaryFlags.value.inProgress) return '全部完成'
  return '处理中'
})

const summaryDetail = computed(() => {
  if (!safeLogs.value.length) return '暂无历史执行记录'
  if (currentRunningLabel.value) return `当前执行：${currentRunningLabel.value}`
  if (queuedLabels.value.length) return `排队中 ${queuedLabels.value.length} 项`
  return `${completedCount.value}/${summaryFlags.value.total} 已完成`
})

const summaryToneClass = computed(() => {
  if (summaryFlags.value.hasError) return 'text-rose-600'
  if (summaryFlags.value.inProgress) return 'text-brand-600'
  return 'text-emerald-600'
})

const summaryBarClass = computed(() => {
  if (summaryFlags.value.hasError) return 'bg-rose-500'
  if (summaryFlags.value.inProgress) return 'bg-brand-500'
  return 'bg-emerald-500'
})

const currentRunningLabel = computed(() => {
  const runningEntry = safeLogs.value.find((log) => log.status === 'running')
  return runningEntry?.label || ''
})

const queuedLabels = computed(() =>
  safeLogs.value.filter((log) => log.status === 'queued').map((log) => log.label)
)

const statusCounts = computed(() =>
  safeLogs.value.reduce(
    (acc, log) => {
      const key = log.status || 'pending'
      acc[key] = (acc[key] || 0) + 1
      return acc
    },
    { ok: 0, running: 0, queued: 0, error: 0 }
  )
)

const detailHeadline = computed(() => {
  if (currentRunningLabel.value) return `当前执行：${currentRunningLabel.value}`
  if (queuedLabels.value.length) return `排队中 ${queuedLabels.value.length} 项，等待调度`
  if (summaryFlags.value.hasError) return '已完成部分任务，请处理失败项后重试'
  return summaryFlags.value.inProgress ? '系统正在排队执行所选分析' : '最近一次执行已全部完成'
})
</script>
