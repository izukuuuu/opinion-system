import { assign, createActor, createMachine } from 'xstate'

function normalizeConnectionMode(value) {
  return String(value || 'idle').trim() || 'idle'
}

function normalizeSnapshotInput(input = {}) {
  return {
    taskStatus: String(input.taskStatus || 'idle').trim() || 'idle',
    hasPendingApproval: Boolean(input.hasPendingApproval),
    connectionMode: normalizeConnectionMode(input.connectionMode)
  }
}

function targetStateForSnapshot(input = {}) {
  const snapshot = normalizeSnapshotInput(input)
  if (snapshot.taskStatus === 'waiting_approval' || snapshot.hasPendingApproval) return 'waitingApproval'
  if (snapshot.taskStatus === 'completed') return 'completed'
  if (snapshot.taskStatus === 'failed') return 'failed'
  if (snapshot.taskStatus === 'cancelled') return 'cancelled'
  if (['queued', 'running'].includes(snapshot.taskStatus)) return snapshot.taskStatus === 'queued' ? 'bootstrapping' : 'running'
  return 'idle'
}

export const reportRunMachine = createMachine({
  id: 'reportRunLifecycle',
  initial: 'idle',
  context: {
    taskStatus: 'idle',
    hasPendingApproval: false,
    connectionMode: 'idle'
  },
  on: {
    RESET: {
      target: '.idle',
      actions: assign(() => ({
        taskStatus: 'idle',
        hasPendingApproval: false,
        connectionMode: 'idle'
      }))
    },
    SNAPSHOT: [
      { guard: ({ event }) => targetStateForSnapshot(event) === 'waitingApproval', target: '.waitingApproval', actions: 'assignSnapshot' },
      { guard: ({ event }) => targetStateForSnapshot(event) === 'completed', target: '.completed', actions: 'assignSnapshot' },
      { guard: ({ event }) => targetStateForSnapshot(event) === 'failed', target: '.failed', actions: 'assignSnapshot' },
      { guard: ({ event }) => targetStateForSnapshot(event) === 'cancelled', target: '.cancelled', actions: 'assignSnapshot' },
      { guard: ({ event }) => targetStateForSnapshot(event) === 'running', target: '.running', actions: 'assignSnapshot' },
      { guard: ({ event }) => targetStateForSnapshot(event) === 'bootstrapping', target: '.bootstrapping', actions: 'assignSnapshot' },
      { target: '.idle', actions: 'assignSnapshot' }
    ],
    STREAM_OPENED: {
      actions: assign(({ context }) => ({
        connectionMode: context.connectionMode === 'polling_fallback' ? 'polling_fallback' : 'streaming'
      }))
    },
    STREAM_RECONNECTING: {
      actions: assign(() => ({
        connectionMode: 'reconnecting'
      }))
    },
    STREAM_POLLING: {
      actions: assign(() => ({
        connectionMode: 'polling_fallback'
      }))
    },
    STREAM_CLOSED: {
      actions: assign(({ context }) => ({
        connectionMode: context.connectionMode === 'polling_fallback' ? 'polling_fallback' : 'idle'
      }))
    }
  },
  states: {
    idle: {},
    bootstrapping: {},
    running: {},
    waitingApproval: {},
    completed: {},
    failed: {},
    cancelled: {}
  }
}, {
  actions: {
    assignSnapshot: assign(({ event }) => normalizeSnapshotInput(event))
  }
})

export function createReportRunLifecycleActor(options = {}) {
  const actor = createActor(reportRunMachine, options)
  actor.start()
  return actor
}

export function buildLifecycleSnapshotInput(taskState = {}, connectionMode = 'idle') {
  const approvals = Array.isArray(taskState.approvals) ? taskState.approvals : []
  return {
    taskStatus: String(taskState.status || 'idle').trim() || 'idle',
    hasPendingApproval: approvals.some((item) => String(item?.status || '').trim() !== 'resolved'),
    connectionMode: normalizeConnectionMode(connectionMode)
  }
}
