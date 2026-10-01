import { describe, expect, it } from 'vitest'
import {
  addDays,
  bookableDays,
  bookingErrorMessage,
  dayChip,
  formatDistance,
  formatLongDay,
  isBookableDay,
  isPastSlot,
  isPendingStatus,
  pickDefaultDay,
  remainingLabel,
  secondsLeft,
  slotLabel,
  todayVn,
  tokenExpiry,
} from './utils'

// 2026-10-03 23:30 in Vietnam = 16:30 UTC.
const LATE_EVENING = new Date('2026-10-03T16:30:00Z')

describe('Vietnam calendar days', () => {
  it('uses the Vietnam date, not UTC', () => {
    expect(todayVn(new Date('2026-10-03T17:30:00Z'))).toBe('2026-10-04')
    expect(todayVn(LATE_EVENING)).toBe('2026-10-03')
  })

  it('lists today plus six days and crosses month ends', () => {
    const days = bookableDays(new Date('2026-09-28T03:00:00Z'))
    expect(days).toHaveLength(7)
    expect(days[0]).toBe('2026-09-28')
    expect(days[6]).toBe('2026-10-04')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
  })

  it('checks the booking window', () => {
    expect(isBookableDay('2026-10-03', LATE_EVENING)).toBe(true)
    expect(isBookableDay('2026-10-10', LATE_EVENING)).toBe(false)
    expect(isBookableDay('2026-10-02', LATE_EVENING)).toBe(false)
  })

  it('formats day chips and long days', () => {
    expect(dayChip('2026-10-04')).toEqual({ weekday: 'CN', dayMonth: '04/10' })
    expect(dayChip('2026-10-03')).toEqual({ weekday: 'T7', dayMonth: '03/10' })
    expect(formatLongDay('2026-10-03')).toBe('Thứ 7, 03/10/2026')
  })
})

describe('slots', () => {
  it('trims seconds', () => {
    expect(slotLabel('09:00:00')).toBe('09:00')
    expect(slotLabel('14:30')).toBe('14:30')
  })

  it('hides slots that already started in Vietnam time', () => {
    const now = new Date('2026-10-03T02:15:00Z') // 09:15 VN
    expect(isPastSlot('2026-10-03', '09:00:00', now)).toBe(true)
    expect(isPastSlot('2026-10-03', '10:00:00', now)).toBe(false)
    expect(isPastSlot('2026-10-04', '08:00:00', now)).toBe(false)
  })

  it('shows remaining seats only when few are left', () => {
    expect(remainingLabel(5, true)).toBeNull()
    expect(remainingLabel(2, true)).toBe('Còn 2 chỗ')
    expect(remainingLabel(0, false)).toBe('Hết chỗ')
  })
})

describe('default day', () => {
  const days = ['d1', 'd2', 'd3']

  it('skips closed, past and full days', () => {
    expect(pickDefaultDay(days, { d1: 'past', d2: 'closed', d3: 'open' })).toBe('d3')
    expect(pickDefaultDay(days, { d1: 'full', d2: 'open', d3: 'open' })).toBe('d2')
  })

  it('waits for an earlier day that is still loading', () => {
    expect(pickDefaultDay(days, { d1: 'past', d3: 'open' })).toBe('d2')
  })

  it('returns null when nothing is bookable', () => {
    expect(pickDefaultDay(days, { d1: 'closed', d2: 'full', d3: 'past' })).toBeNull()
  })
})

describe('token timer', () => {
  it('estimates expiry from the issue time', () => {
    expect(tokenExpiry(1_000, 600)).toBe(601_000)
  })

  it('counts seconds left and never goes negative', () => {
    expect(secondsLeft(10_500, 1_000)).toBe(10)
    expect(secondsLeft(500, 1_000)).toBe(0)
    expect(secondsLeft(null)).toBe(0)
  })
})

describe('labels', () => {
  it('formats distance or the region fallback', () => {
    expect(formatDistance(3.44)).toBe('3,4 km')
    expect(formatDistance(null)).toBe('Cùng khu vực')
  })

  it('reads backend status case-insensitively', () => {
    expect(isPendingStatus('pending')).toBe(true)
    expect(isPendingStatus('PENDING')).toBe(true)
    expect(isPendingStatus('confirmed')).toBe(false)
  })

  it('maps known error codes and leaves others to the caller', () => {
    expect(bookingErrorMessage('SLOT_FULL')).toBe('Khung giờ này vừa hết chỗ.')
    expect(bookingErrorMessage('WORKSHOP_NOT_FOUND')).toContain('Chưa có xưởng')
    expect(bookingErrorMessage('SOMETHING_ELSE')).toBeNull()
  })
})
