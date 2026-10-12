import { beforeEach, describe, expect, it, vi } from 'vitest'

const hooks = vi.hoisted(() => ({ effects: [] as (() => unknown)[] }))
vi.mock('react', async () => ({
  ...await vi.importActual('react'),
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => unknown) => { hooks.effects.push(effect) },
  useSyncExternalStore: (_subscribe: unknown, snapshot: () => unknown) => snapshot(),
}))

import { invalidateQueries, setQueryData, useCachedQuery } from './useCachedQuery'

beforeEach(() => {
  hooks.effects.length = 0
  vi.stubGlobal('document', { addEventListener: vi.fn(), removeEventListener: vi.fn() })
})

describe('cached reads after personalization changes', () => {
  it('discards an in-flight forecast after erasure and accepts a fresh read', async () => {
    const key = 'maintenance:erasure-test'
    let resolve!: (value: string) => void
    const fetcher = vi.fn(() => new Promise<string>(done => { resolve = done }))
    const query = useCachedQuery(key, fetcher)
    const pending = query.refetch()
    invalidateQueries('maintenance:', 'reminder:')
    resolve('private old forecast')
    await pending
    expect(useCachedQuery(key, fetcher).data).toBeNull()
    const current = query.refetch()
    resolve('personalization disabled')
    await current
    expect(useCachedQuery(key, fetcher).data).toBe('personalization disabled')
  })

  it('keeps settings returned by a mutation when an older GET completes', async () => {
    const key = 'notification-settings:mutation-test'
    let resolve!: (value: boolean) => void
    const fetcher = () => new Promise<boolean>(done => { resolve = done })
    const pending = useCachedQuery(key, fetcher).refetch()
    setQueryData(key, false)
    resolve(true)
    await pending
    expect(useCachedQuery(key, fetcher).data).toBe(false)
  })
})
