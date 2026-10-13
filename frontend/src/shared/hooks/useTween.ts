import { useEffect, useRef, useState } from 'react'

/** Ease-out cubic between `from` and `to` at progress `p` (0–1, clamped). */
export function tweenValue(from: number, to: number, p: number): number {
  const t = Math.min(1, Math.max(0, p))
  return from + (to - from) * (1 - (1 - t) ** 3)
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

/**
 * The value shown while `target` changes: it eases from what is on screen to the new target over
 * `durationMs`. Starts at `initial` (default: the target, so nothing moves on mount). Jumps straight to
 * the target under prefers-reduced-motion.
 */
export function useTween(target: number, durationMs = 700, initial: number = target): number {
  const [shown, setShown] = useState(initial)
  const shownRef = useRef(initial)

  useEffect(() => {
    if (prefersReducedMotion() || shownRef.current === target) {
      shownRef.current = target
      setShown(target)
      return
    }
    const from = shownRef.current
    let frame = 0
    let start: number | null = null
    const step = (now: number) => {
      if (start === null) start = now
      const value = tweenValue(from, target, (now - start) / durationMs)
      shownRef.current = value
      setShown(value)
      if (now - start < durationMs) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  return shown
}
