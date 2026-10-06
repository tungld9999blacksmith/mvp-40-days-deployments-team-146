import { describe, expect, it } from 'vitest'
import { createInFlightGuard } from './inFlightGuard'

describe('createInFlightGuard', () => {
  it('runs a key once while it is in flight (double click on "Xác nhận đặt lịch")', async () => {
    const guard = createInFlightGuard()
    let calls = 0
    let release: () => void = () => {}
    const task = () =>
      new Promise<string>(resolve => {
        calls += 1
        release = () => resolve('booked')
      })

    const first = guard.run('p-1', task)
    const second = guard.run('p-1', task)
    expect(calls).toBe(1)
    expect(guard.isRunning('p-1')).toBe(true)
    release()
    await expect(Promise.all([first, second])).resolves.toEqual(['booked', 'booked'])
    expect(guard.isRunning('p-1')).toBe(false)
  })

  it('lets another key, or the same key after it finished, run', async () => {
    const guard = createInFlightGuard()
    let calls = 0
    const task = async () => {
      calls += 1
    }
    await Promise.all([guard.run('a', task), guard.run('b', task)])
    await guard.run('a', task)
    expect(calls).toBe(3)
  })
})
