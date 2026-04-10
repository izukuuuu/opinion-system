import { describe, expect, it } from 'vitest'
import { buildLifecycleSnapshotInput, createReportRunLifecycleActor } from './reportRunMachine'

describe('reportRunMachine', () => {
  it('moves through running, waiting approval, and completed', () => {
    const actor = createReportRunLifecycleActor()

    actor.send({ type: 'SNAPSHOT', taskStatus: 'running', hasPendingApproval: false, connectionMode: 'streaming' })
    expect(String(actor.getSnapshot().value)).toBe('running')

    actor.send({ type: 'SNAPSHOT', taskStatus: 'waiting_approval', hasPendingApproval: true, connectionMode: 'streaming' })
    expect(String(actor.getSnapshot().value)).toBe('waitingApproval')

    actor.send({ type: 'SNAPSHOT', taskStatus: 'completed', hasPendingApproval: false, connectionMode: 'streaming' })
    expect(String(actor.getSnapshot().value)).toBe('completed')
  })

  it('tracks reconnecting stream mode without losing task state', () => {
    const actor = createReportRunLifecycleActor()
    actor.send({ type: 'SNAPSHOT', taskStatus: 'running', hasPendingApproval: false, connectionMode: 'streaming' })
    actor.send({ type: 'STREAM_RECONNECTING' })

    const snapshot = actor.getSnapshot()
    expect(String(snapshot.value)).toBe('running')
    expect(snapshot.context.connectionMode).toBe('reconnecting')
  })

  it('derives snapshot input from task state', () => {
    const input = buildLifecycleSnapshotInput({
      status: 'waiting_approval',
      approvals: [{ approval_id: 'a1', status: 'pending' }]
    }, 'streaming')

    expect(input).toEqual({
      taskStatus: 'waiting_approval',
      hasPendingApproval: true,
      connectionMode: 'streaming'
    })
  })
})
