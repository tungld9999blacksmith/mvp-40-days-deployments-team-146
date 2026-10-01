import { describe, expect, it } from 'vitest'
import { formatCountdown, formatDate, formatDuration, formatKm, formatLicensePlate } from './format'

describe('format helpers (vi-VN, Asia/Ho_Chi_Minh)', () => {
  it('km with Vietnamese grouping', () => {
    expect(formatKm(11600)).toBe('11.600 km')
  })

  it('a bare calendar date is not shifted by the timezone', () => {
    expect(formatDate('2026-10-15')).toBe('15/10/2026')
  })

  it('Retry-After seconds as a readable duration (AC-FE-208)', () => {
    expect(formatDuration(5400)).toBe('1 giờ 30 phút')
    expect(formatDuration(40)).toBe('1 phút')
    expect(formatDuration(7200)).toBe('2 giờ')
  })

  it('countdown mm:ss', () => {
    expect(formatCountdown(40)).toBe('00:40')
    expect(formatCountdown(125)).toBe('02:05')
  })

  it('licence plate display only', () => {
    expect(formatLicensePlate('30A12345')).toBe('30A-123.45')
    expect(formatLicensePlate('30A1234')).toBe('30A-1234')
  })
})
