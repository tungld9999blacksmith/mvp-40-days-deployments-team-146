import { describe, expect, it } from 'vitest'
import { capacitySlotState } from './utils'

// Regression: FINDING-002 (/design-review 2026-10-05) — slots with zero capacity read "Hết chỗ" in error red.
describe('capacitySlotState', () => {
  it('treats a slot without seats, bookings or locks as not taking bookings', () => {
    expect(capacitySlotState({ occupied: 0, blocked: 0, remaining: 0 })).toBe('closed')
  })

  it('is full only when bookings or locks used the seats', () => {
    expect(capacitySlotState({ occupied: 1, blocked: 0, remaining: 0 })).toBe('full')
    expect(capacitySlotState({ occupied: 0, blocked: 2, remaining: 0 })).toBe('full')
  })

  it('is open while seats remain', () => {
    expect(capacitySlotState({ occupied: 1, blocked: 0, remaining: 1 })).toBe('open')
  })
})
