import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useReportRunStore } from './reportRun'

describe('reportRun store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('resets stale events when the same task is resumed with cleared history', () => {
    const store = useReportRunStore()

    store.applySnapshot({
      id: 'rp-1',
      recent_events: [
        { event_id: 1, type: 'phase.started' },
        { event_id: 2, type: 'phase.progress' },
        { event_id: 3, type: 'task.failed' }
      ],
      event_seq: 3
    })

    expect(store.lastEventId).toBe(3)
    expect(store.events).toHaveLength(3)

    store.applySnapshot({
      id: 'rp-1',
      status: 'queued',
      recent_events: [
        {
          event_id: 1,
          type: 'phase.progress',
          payload: { history_reset: true }
        }
      ],
      event_seq: 1
    })

    expect(store.lastEventId).toBe(1)
    expect(store.events).toHaveLength(1)
    expect(store.events[0].payload.history_reset).toBe(true)
  })

  it('keeps events when the same task snapshot only appends newer items', () => {
    const store = useReportRunStore()

    store.applySnapshot({
      id: 'rp-2',
      recent_events: [
        { event_id: 1, type: 'phase.started' },
        { event_id: 2, type: 'phase.progress' }
      ],
      event_seq: 2
    })

    store.applySnapshot({
      id: 'rp-2',
      recent_events: [
        { event_id: 2, type: 'phase.progress' },
        { event_id: 3, type: 'task.completed' }
      ],
      event_seq: 3
    })

    expect(store.lastEventId).toBe(3)
    expect(store.events.map((item) => item.event_id)).toEqual([1, 2, 3])
  })
})
