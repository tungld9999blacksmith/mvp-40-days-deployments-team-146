/**
 * Runs at most one task per key at a time: a second call while the first is running
 * returns the same promise instead of starting again (double click on "Xác nhận đặt lịch").
 */
export function createInFlightGuard() {
  const running = new Map<string, Promise<unknown>>()
  return {
    run<T>(key: string, task: () => Promise<T>): Promise<T> {
      const current = running.get(key)
      if (current) return current as Promise<T>
      const promise = task().finally(() => running.delete(key))
      running.set(key, promise)
      return promise
    },
    isRunning(key: string): boolean {
      return running.has(key)
    },
  }
}
