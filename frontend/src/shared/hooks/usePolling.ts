import { useCallback, useEffect, useRef, useState } from 'react'

export type PollResult = 'continue' | 'stop'

interface PollingOptions {
  enabled: boolean
  /** Delay before the next poll, given the time elapsed since polling started. */
  intervalMs: (elapsedMs: number) => number
  /** Stop and report `timedOut` after this long. */
  maxDurationMs: number
  /** Resolve `stop` when the awaited state is reached. Throwing counts as an error. */
  poll: () => Promise<PollResult>
  /** Stop and report `failed` after this many errors in a row. */
  maxConsecutiveErrors?: number
}

/**
 * Polls while the tab is visible. Pauses on `visibilitychange → hidden`, polls
 * immediately when the tab becomes visible again (US-001 FE §4.4, US-009 FE §4.4).
 */
export function usePolling({ enabled, intervalMs, maxDurationMs, poll, maxConsecutiveErrors = 3 }: PollingOptions) {
  const [timedOut, setTimedOut] = useState(false)
  const [failed, setFailed] = useState(false)
  const [runId, setRunId] = useState(0)
  const pollRef = useRef(poll)
  const intervalRef = useRef(intervalMs)
  pollRef.current = poll
  intervalRef.current = intervalMs

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    let timer: number | undefined
    let errors = 0
    let running = false
    const startedAt = Date.now()

    const schedule = () => {
      if (cancelled) return
      const elapsed = Date.now() - startedAt
      if (elapsed >= maxDurationMs) {
        setTimedOut(true)
        return
      }
      timer = window.setTimeout(tick, intervalRef.current(elapsed))
    }

    const tick = async () => {
      if (cancelled || running) return
      if (document.visibilityState === 'hidden') return // resumed by the visibility listener
      running = true
      try {
        const result = await pollRef.current()
        errors = 0
        if (result === 'stop') {
          cancelled = true
          return
        }
      } catch {
        errors += 1
        if (errors >= maxConsecutiveErrors) {
          setFailed(true)
          cancelled = true
          return
        }
      } finally {
        running = false
      }
      schedule()
    }

    const onVisibility = () => {
      if (document.visibilityState !== 'visible' || cancelled) return
      window.clearTimeout(timer)
      void tick()
    }

    document.addEventListener('visibilitychange', onVisibility)
    schedule()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [enabled, maxDurationMs, maxConsecutiveErrors, runId])

  const restart = useCallback(() => {
    setTimedOut(false)
    setFailed(false)
    setRunId(id => id + 1)
  }, [])

  return { timedOut, failed, restart }
}
