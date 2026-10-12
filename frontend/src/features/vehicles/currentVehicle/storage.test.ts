import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearSessionCaches } from '@/shared/session/sessionCache'
import { forgetAllVehicles, readRememberedVehicle, rememberVehicle } from './storage'

function memoryStorage(): Storage {
  const items = new Map<string, string>()
  return {
    get length() {
      return items.size
    },
    key: index => [...items.keys()][index] ?? null,
    getItem: key => items.get(key) ?? null,
    setItem: (key, value) => void items.set(key, value),
    removeItem: key => void items.delete(key),
    clear: () => items.clear(),
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('current vehicle storage', () => {
  it('remembers the pick per user', () => {
    vi.stubGlobal('localStorage', memoryStorage())
    rememberVehicle(1, 'v2')
    rememberVehicle(2, 'v9')
    expect(readRememberedVehicle(1)).toBe('v2')
    expect(readRememberedVehicle(2)).toBe('v9')
    rememberVehicle(1, null)
    expect(readRememberedVehicle(1)).toBeNull()
  })

  it('treats blocked storage as nothing remembered', () => {
    const throwing = memoryStorage()
    throwing.getItem = () => {
      throw new Error('SecurityError')
    }
    throwing.setItem = () => {
      throw new Error('QuotaExceededError')
    }
    vi.stubGlobal('localStorage', throwing)
    expect(() => rememberVehicle(1, 'v2')).not.toThrow()
    expect(readRememberedVehicle(1)).toBeNull()
    expect(() => forgetAllVehicles()).not.toThrow()
  })

  it('forgets every pick when the session ends and keeps other keys', () => {
    const store = memoryStorage()
    vi.stubGlobal('localStorage', store)
    store.setItem('theme', 'dark')
    rememberVehicle(1, 'v2')
    rememberVehicle(2, 'v9')
    clearSessionCaches()
    expect(readRememberedVehicle(1)).toBeNull()
    expect(readRememberedVehicle(2)).toBeNull()
    expect(store.getItem('theme')).toBe('dark')
  })
})
