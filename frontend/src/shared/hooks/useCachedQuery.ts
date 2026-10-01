import { useCallback, useEffect, useSyncExternalStore } from 'react'
import type { ApiError } from '@/shared/api/client'
import { onSessionEnd } from '@/shared/session/sessionCache'

interface Entry<T> {
  data: T | null
  error: ApiError | null
  fetchedAt: number | null
  promise: Promise<void> | null
  listeners: Set<() => void>
  snapshot: QueryState<T>
}

export interface QueryState<T> {
  data: T | null
  error: ApiError | null
  /** A request is in flight (initial load or background refresh). */
  isFetching: boolean
  fetchedAt: number | null
}

const cache = new Map<string, Entry<unknown>>()

// Per-user data must not survive a logout (US-005 FE §19).
onSessionEnd(() => {
  const entries = [...cache.values()]
  cache.clear()
  entries.forEach(entry => entry.listeners.forEach(listener => listener()))
})

function getEntry<T>(key: string): Entry<T> {
  let entry = cache.get(key) as Entry<T> | undefined
  if (!entry) {
    entry = {
      data: null,
      error: null,
      fetchedAt: null,
      promise: null,
      listeners: new Set(),
      snapshot: { data: null, error: null, isFetching: false, fetchedAt: null },
    }
    cache.set(key, entry as Entry<unknown>)
  }
  return entry
}

function publish<T>(entry: Entry<T>) {
  entry.snapshot = { data: entry.data, error: entry.error, isFetching: entry.promise !== null, fetchedAt: entry.fetchedAt }
  entry.listeners.forEach(listener => listener())
}

function run<T>(key: string, fetcher: () => Promise<T>): Promise<void> {
  const entry = getEntry<T>(key)
  if (entry.promise) return entry.promise
  entry.promise = fetcher()
    .then(data => {
      entry.data = data
      entry.error = null
      entry.fetchedAt = Date.now()
    })
    .catch((error: ApiError) => {
      entry.error = error
    })
    .finally(() => {
      entry.promise = null
      publish(entry)
    })
  publish(entry)
  return entry.promise
}

/** Replaces cached data after a successful mutation (e.g. PUT returns the new settings). */
export function setQueryData<T>(key: string, data: T): void {
  const entry = getEntry<T>(key)
  entry.data = data
  entry.error = null
  entry.fetchedAt = Date.now()
  publish(entry)
}

/** Drops a cached query so the next mount refetches it. */
export function invalidateQuery(key: string): void {
  const entry = cache.get(key)
  if (!entry) return
  entry.data = null
  entry.error = null
  entry.fetchedAt = null
  publish(entry)
}

const EMPTY: QueryState<never> = { data: null, error: null, isFetching: false, fetchedAt: null }

/**
 * In-memory cache shared between screens: cached data shows immediately, a background
 * refresh runs when it is older than `staleMs` (on mount and when the tab is focused).
 */
export function useCachedQuery<T>(key: string | null, fetcher: () => Promise<T>, staleMs = 5 * 60 * 1000) {
  const subscribe = useCallback(
    (listener: () => void) => {
      if (!key) return () => {}
      const entry = getEntry<T>(key)
      entry.listeners.add(listener)
      return () => entry.listeners.delete(listener)
    },
    [key],
  )
  const state = useSyncExternalStore(subscribe, () => (key ? getEntry<T>(key).snapshot : (EMPTY as QueryState<T>)))

  const refetch = useCallback(() => (key ? run(key, fetcher) : Promise.resolve()), [key, fetcher])

  useEffect(() => {
    if (!key) return
    const entry = getEntry<T>(key)
    const stale = entry.fetchedAt === null || Date.now() - entry.fetchedAt >= staleMs
    if (stale) void run(key, fetcher)

    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      const current = getEntry<T>(key)
      if (current.fetchedAt !== null && Date.now() - current.fetchedAt >= staleMs) void run(key, fetcher)
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
    // `fetcher` is expected to be stable per key, so it is not a dependency.
  }, [key, staleMs])

  return { ...state, refetch, isLoading: state.data === null && state.error === null }
}
