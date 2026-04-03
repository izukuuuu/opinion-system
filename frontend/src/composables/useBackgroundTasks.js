import { computed, reactive } from 'vue'
import { useApiBase } from './useApiBase'

const POLL_INTERVAL = 3000
const { callApi } = useApiBase()

const state = reactive({
  loading: false,
  error: '',
  tasks: [],
  workers: [],
  summary: {
    active_count: 0,
    running_count: 0,
    queued_count: 0,
    total_count: 0,
    updated_at: ''
  }
})

let consumerCount = 0
let pollTimer = null
let inFlight = null

export function useBackgroundTasks() {
  consumerCount += 1
  if (consumerCount === 1) {
    loadBackgroundTasks({ silent: true })
    scheduleNextPoll()
  }

  return {
    state,
    tasks: computed(() => state.tasks),
    workers: computed(() => state.workers),
    summary: computed(() => state.summary),
    activeCount: computed(() => Number(state.summary?.active_count || 0)),
    isQuiet: computed(() => Number(state.summary?.active_count || 0) === 0),
    refresh: () => loadBackgroundTasks(),
    release: releaseConsumer
  }
}

async function loadBackgroundTasks(options = {}) {
  if (inFlight) return inFlight
  const { silent = false } = options
  if (!silent) {
    state.loading = true
  }
  state.error = ''
  inFlight = callApi('/api/system/background-tasks?active_only=1&limit=12')
    .then((response) => {
      const payload = response?.data || {}
      state.tasks = Array.isArray(payload.tasks) ? payload.tasks : []
      state.workers = Array.isArray(payload.workers) ? payload.workers : []
      state.summary = payload.summary || {
        active_count: 0,
        running_count: 0,
        queued_count: 0,
        total_count: 0,
        updated_at: ''
      }
    })
    .catch((error) => {
      state.error = error instanceof Error ? error.message : String(error || '加载后台任务失败')
    })
    .finally(() => {
      state.loading = false
      inFlight = null
    })
  return inFlight
}

function scheduleNextPoll() {
  if (typeof window === 'undefined' || pollTimer) return
  pollTimer = window.setTimeout(async function poll() {
    pollTimer = null
    await loadBackgroundTasks({ silent: true })
    if (consumerCount > 0) {
      scheduleNextPoll()
    }
  }, POLL_INTERVAL)
}

function releaseConsumer() {
  consumerCount = Math.max(0, consumerCount - 1)
  if (consumerCount > 0) return
  if (typeof window !== 'undefined' && pollTimer) {
    window.clearTimeout(pollTimer)
  }
  pollTimer = null
}
