import { describe, expect, it } from 'vitest'
import { warrantyTimeline } from './warrantyTimeline'

const NOW = new Date('2026-10-08T10:00:00+07:00')

describe('warrantyTimeline', () => {
  it('counts years and months left on a long warranty', () => {
    const line = warrantyTimeline({ startDate: '2024-03-15', endDate: '2032-03-13', isActive: true }, NOW)
    expect(line.remainingText).toBe('Còn 5 năm 5 tháng')
    expect(line.tone).toBe('active')
    expect(line.usedRatio).toBeCloseTo(0.32, 2)
  })

  it('marks a warranty ending within six months', () => {
    const line = warrantyTimeline({ startDate: '2024-03-15', endDate: '2027-03-15', isActive: true }, NOW)
    expect(line.remainingText).toBe('Còn 5 tháng')
    expect(line.tone).toBe('ending')
  })

  it('switches to days in the last month', () => {
    expect(warrantyTimeline({ startDate: '2023-10-20', endDate: '2026-10-20', isActive: true }, NOW).remainingText).toBe('Còn 12 ngày')
  })

  it('trusts the backend when the line is no longer active', () => {
    const line = warrantyTimeline({ startDate: '2024-03-15', endDate: '2032-03-13', isActive: false }, NOW)
    expect(line).toEqual({ usedRatio: 1, remainingText: 'Đã hết hiệu lực', tone: 'ended' })
  })
})
