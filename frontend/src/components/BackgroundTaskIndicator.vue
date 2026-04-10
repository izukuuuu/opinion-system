<template>
  <div ref="rootEl" class="relative">
    <button
      type="button"
      :class="buttonClass"
      aria-label="查看后台任务"
      :aria-expanded="open"
      @click="toggleOpen"
    >
      <span :class="ringClass">
        <svg
          viewBox="0 0 64 64"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          class="task-indicator-ring__svg"
          :class="{ 'task-indicator-ring__svg--active animate-spin': activeCount > 0 }"
          aria-hidden="true"
        >
          <path
            class="task-indicator-ring__track"
            d="M32 3C35.8083 3 39.5794 3.75011 43.0978 5.20749C46.6163 6.66488 49.8132 8.80101 52.5061 11.4939C55.199 14.1868 57.3351 17.3837 58.7925 20.9022C60.2499 24.4206 61 28.1917 61 32C61 35.8083 60.2499 39.5794 58.7925 43.0978C57.3351 46.6163 55.199 49.8132 52.5061 52.5061C49.8132 55.199 46.6163 57.3351 43.0978 58.7925C39.5794 60.2499 35.8083 61 32 61C28.1917 61 24.4206 60.2499 20.9022 58.7925C17.3837 57.3351 14.1868 55.199 11.4939 52.5061C8.801 49.8132 6.66487 46.6163 5.20749 43.0978C3.7501 39.5794 3 35.8083 3 32C3 28.1917 3.75011 24.4206 5.2075 20.9022C6.66489 17.3837 8.80101 14.1868 11.4939 11.4939C14.1868 8.80099 17.3838 6.66487 20.9022 5.20749C24.4206 3.7501 28.1917 3 32 3Z"
            pathLength="100"
          />
          <path
            class="task-indicator-ring__arc"
            :class="{ 'task-indicator-ring__arc--active': activeCount > 0 }"
            d="M32 3C36.5778 3 41.0906 4.08374 45.1692 6.16256C49.2477 8.24138 52.7762 11.2562 55.466 14.9605C58.1558 18.6647 59.9304 22.9531 60.6448 27.4748C61.3591 31.9965 60.9928 36.6232 59.5759 40.9762"
          />
        </svg>
        <span :class="countClass">{{ activeCount }}</span>
      </span>
    </button>

    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="translate-y-1 opacity-0"
        enter-to-class="translate-y-0 opacity-100"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="translate-y-0 opacity-100"
        leave-to-class="translate-y-1 opacity-0"
      >
        <div
          v-if="open"
          ref="popupEl"
          class="background-task-popup fixed z-[80] w-[22rem] overflow-hidden rounded-3xl border border-soft shadow-2xl sm:w-[25rem]"
          :style="popupStyle"
        >
          <div class="background-task-popup__header border-b border-soft px-4 py-3">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">后台任务</p>
                <p class="mt-0.5 text-xs text-secondary">
                  {{ activeCount > 0 ? `${summary.running_count || 0} 个运行中，${summary.queued_count || 0} 个排队中` : '当前没有运行中的后台任务' }}
                </p>
              </div>
              <button
                type="button"
                class="background-task-popup__refresh rounded-lg border border-soft px-2 py-1 text-[11px] text-secondary transition hover:border-brand-soft hover:text-primary"
                @click="refresh"
              >
                刷新
              </button>
            </div>
            <p v-if="state.error" class="mt-2 text-xs text-rose-600">{{ state.error }}</p>
          </div>

          <div v-if="tasks.length" class="flex max-h-[24rem] flex-col gap-2 overflow-y-auto px-3 py-3">
            <div
              v-for="task in tasks"
              :key="task.id"
              class="background-task-popup__card rounded-2xl border border-soft px-3 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="truncate text-sm font-semibold text-primary">{{ task.title }}</p>
                  <p class="mt-0.5 truncate text-xs text-secondary">
                    {{ task.source_label }}<span v-if="task.phase_label"> · {{ task.phase_label }}</span>
                  </p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <button
                    v-if="canCancel(task.status)"
                    type="button"
                    class="rounded-md bg-rose-50 px-2 py-1 text-[10px] font-medium text-rose-600 transition hover:bg-rose-100"
                    :disabled="cancellingIds.has(task.id)"
                    @click.stop="cancelTask(task)"
                  >
                    {{ cancellingIds.has(task.id) ? '取消中...' : '终止' }}
                  </button>
                  <span
                    class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="statusBadgeClass(task.status)"
                  >
                    {{ statusLabel(task.status) }}
                  </span>
                </div>
              </div>

              <p v-if="task.scope" class="mt-2 truncate text-[11px] text-muted">{{ task.scope }}</p>
              <p class="mt-2 text-xs leading-5 text-secondary">{{ task.message }}</p>

              <!-- 情感分析进度详情 -->
              <div v-if="hasSentimentProgress(task)" class="mt-2 flex items-center gap-2 text-[11px]">
                <span class="rounded px-1.5 py-0.5 bg-blue-50 text-blue-600">AI 情感分类</span>
                <span class="text-secondary">
                  {{ task.progress?.sentiment_processed || 0 }}/{{ task.progress?.sentiment_total || 0 }}
                </span>
                <span v-if="task.progress?.sentiment_classified" class="text-emerald-600">
                  (成功 {{ task.progress.sentiment_classified }})
                </span>
              </div>

              <div class="mt-3">
                <div class="flex items-center justify-between gap-3 text-[11px] text-secondary">
                  <span class="truncate">{{ task.detail_text || task.progress_text }}</span>
                  <span class="shrink-0 font-medium text-primary">{{ Math.max(0, Math.min(100, Number(task.percentage || 0))) }}%</span>
                </div>
                <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100/85">
                  <div
                    class="h-full rounded-full transition-all duration-500"
                    :class="progressClass(task.status)"
                    :style="{ width: `${Math.max(0, Math.min(100, Number(task.percentage || 0)))}%` }"
                  />
                </div>
                <div class="mt-2 flex items-center justify-between gap-3 text-[11px] text-muted">
                  <span class="truncate">{{ task.progress_text }}</span>
                  <span class="shrink-0">{{ formatRelativeTime(task.updated_at) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="px-4 py-8 text-center">
            <div class="background-task-popup__empty-indicator mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-soft text-muted">
              0
            </div>
            <p class="mt-3 text-sm font-semibold text-primary">后台静默</p>
            <p class="mt-1 text-xs text-secondary">当前没有需要跟踪的后台任务。</p>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useBackgroundTasks } from '../composables/useBackgroundTasks'
import { useApiBase } from '../composables/useApiBase'

const props = defineProps({
  compact: {
    type: Boolean,
    default: false
  }
})

const { state, tasks, summary, activeCount, refresh, release } = useBackgroundTasks()
const { callApi } = useApiBase()

const open = ref(false)
const rootEl = ref(null)
const popupEl = ref(null)
const cancellingIds = ref(new Set())
const popupPosition = ref({
  top: 0,
  right: 16
})

const buttonClass = computed(() => [
  'flex items-center justify-center rounded-lg border border-soft text-secondary shadow-sm transition hover:border-brand-soft hover:text-primary focus-ring-accent',
  props.compact ? 'h-8 w-8 bg-surface/50' : 'h-9 w-9 bg-surface',
  activeCount.value > 0 ? 'border-brand-soft text-primary' : ''
])

const ringClass = computed(() => [
  'task-indicator-ring',
  props.compact ? 'task-indicator-ring--compact' : '',
  activeCount.value > 0 ? 'task-indicator-ring--active' : ''
])

const countClass = computed(() => [
  'relative z-[1] text-[11px] leading-none font-extrabold',
  activeCount.value > 0 ? 'text-brand-700' : 'text-muted'
])

const popupStyle = computed(() => ({
  top: `${popupPosition.value.top}px`,
  right: `${popupPosition.value.right}px`
}))

const toggleOpen = async () => {
  open.value = !open.value
  if (open.value) {
    await nextTick()
    updatePopupPosition()
    await refresh()
  }
}

const handleDocumentPointerDown = (event) => {
  const root = rootEl.value
  const popup = popupEl.value
  if ((root && root.contains(event.target)) || (popup && popup.contains(event.target))) return
  open.value = false
}

const handleEscape = (event) => {
  if (event.key === 'Escape') {
    open.value = false
  }
}

onMounted(() => {
  if (typeof document === 'undefined') return
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleEscape)
  window.addEventListener('resize', updatePopupPosition)
  window.addEventListener('scroll', updatePopupPosition, true)
})

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('pointerdown', handleDocumentPointerDown)
    document.removeEventListener('keydown', handleEscape)
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', updatePopupPosition)
    window.removeEventListener('scroll', updatePopupPosition, true)
  }
  release()
})

watch(open, async (value) => {
  if (!value) return
  await nextTick()
  updatePopupPosition()
})

const statusLabel = (status) => {
  const value = String(status || '').trim()
  if (value === 'running') return '运行中'
  if (value === 'queued') return '排队中'
  if (value === 'completed') return '已完成'
  if (value === 'failed' || value === 'error') return '异常'
  if (value === 'cancelled') return '已取消'
  return '处理中'
}

const statusBadgeClass = (status) => {
  const value = String(status || '').trim()
  if (value === 'running') return 'bg-brand-soft text-brand-700'
  if (value === 'queued') return 'bg-amber-100 text-amber-700'
  if (value === 'completed') return 'bg-emerald-100 text-emerald-700'
  if (value === 'failed' || value === 'error') return 'bg-rose-100 text-rose-700'
  if (value === 'cancelled') return 'bg-slate-100 text-slate-600'
  return 'bg-slate-100 text-slate-700'
}

const progressClass = (status) => {
  const value = String(status || '').trim()
  if (value === 'running') return 'bg-brand'
  if (value === 'queued') return 'bg-amber-400'
  if (value === 'completed') return 'bg-emerald-500'
  if (value === 'failed' || value === 'error') return 'bg-rose-500'
  if (value === 'cancelled') return 'bg-slate-400'
  return 'bg-slate-400'
}

const hasSentimentProgress = (task) => {
  const progress = task?.progress
  if (!progress) return false
  const phase = String(progress.sentiment_phase || '').trim()
  const total = Number(progress.sentiment_total || 0)
  // 有情感分析阶段或总数大于0时显示
  return phase !== '' || total > 0
}

const formatRelativeTime = (value) => {
  const text = String(value || '').trim()
  if (!text) return ''
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return ''
  const diffSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000))
  if (diffSeconds < 10) return '刚刚'
  if (diffSeconds < 60) return `${diffSeconds} 秒前`
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} 分钟前`
  return `${Math.floor(diffSeconds / 3600)} 小时前`
}

const canCancel = (status) => {
  const value = String(status || '').trim().toLowerCase()
  return value === 'running' || value === 'queued'
}

const cancelTask = async (task) => {
  const taskId = task?.id
  if (!taskId || cancellingIds.value.has(taskId)) return

  cancellingIds.value.add(taskId)
  try {
    await callApi(`/api/system/background-tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' })
    await refresh()
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error || '取消任务失败')
    alert(`取消任务失败: ${message}`)
  } finally {
    cancellingIds.value.delete(taskId)
  }
}

function updatePopupPosition() {
  if (!open.value || typeof window === 'undefined') return
  const root = rootEl.value
  if (!root) return
  const rect = root.getBoundingClientRect()
  popupPosition.value = {
    top: Math.max(12, Math.round(rect.bottom + 12)),
    right: Math.max(16, Math.round(window.innerWidth - rect.right))
  }
}
</script>

<style scoped>
.task-indicator-ring {
  position: relative;
  display: inline-flex;
  height: 1.75rem;
  width: 1.75rem;
  align-items: center;
  justify-content: center;
}

.task-indicator-ring--compact {
  height: 1.5rem;
  width: 1.5rem;
}

.task-indicator-ring__svg {
  position: absolute;
  inset: 0;
  height: 100%;
  width: 100%;
  overflow: visible;
  color: rgb(var(--color-brand-300) / 0.72);
}

.task-indicator-ring__track {
  stroke: color-mix(in srgb, var(--color-surface-muted) 88%, transparent);
  stroke-width: 5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.task-indicator-ring__arc {
  stroke: color-mix(in srgb, var(--color-surface-muted) 76%, transparent);
  stroke-width: 5;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: stroke 0.2s ease, opacity 0.2s ease;
}

.task-indicator-ring__svg--active {
  color: rgb(var(--color-brand-300) / 0.9);
}

.task-indicator-ring__arc--active {
  stroke: rgb(var(--color-brand-700) / 0.98);
}

.task-indicator-ring--active .task-indicator-ring__track {
  stroke: rgb(var(--color-brand-300) / 0.9);
}

.background-task-popup {
  backdrop-filter: blur(24px) saturate(145%);
  background-color: color-mix(in srgb, var(--color-surface) 88%, transparent);
}

.background-task-popup__header {
  background-color: color-mix(in srgb, var(--color-surface) 62%, transparent);
}

.background-task-popup__refresh {
  background-color: color-mix(in srgb, var(--color-surface) 78%, transparent);
}

.background-task-popup__card {
  background-color: color-mix(in srgb, var(--color-surface) 72%, transparent);
}

.background-task-popup__empty-indicator {
  background-color: color-mix(in srgb, var(--color-surface) 78%, transparent);
}
</style>
