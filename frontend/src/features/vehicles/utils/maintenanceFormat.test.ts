import { describe, expect, it } from 'vitest'
import { milestoneProgress, milestoneTitle, remainingParts } from './maintenanceFormat'

const text = (parts: { text: string }[]) => parts.map(part => part.text).join(' · ')

describe('milestoneTitle', () => {
  it('builds the Vietnamese title from numbers', () => {
    expect(milestoneTitle({ odoMilestoneKm: 12000, monthMilestone: 12 })).toBe('Mốc 12.000 km / 12 tháng')
  })
})

describe('remainingParts', () => {
  it('AC-001: DUE_SOON by km → "Còn 400 km · 17 ngày", km emphasised', () => {
    const parts = remainingParts({ remainingKm: 400, remainingDays: 17, dueReason: 'KM', dueStatus: 'DUE_SOON' })
    expect(text(parts)).toBe('Còn 400 km · 17 ngày')
    expect(parts.map(part => part.emphasized)).toEqual([true, false])
  })

  it('AC-002: TIME_ONLY (no ODO) → days only', () => {
    expect(text(remainingParts({ remainingKm: null, remainingDays: 17, dueReason: null, dueStatus: 'NORMAL' }))).toBe('Còn 17 ngày')
  })

  it('AC-004: OVERDUE by time → days part emphasised, negative shown as "quá"', () => {
    const parts = remainingParts({ remainingKm: 4000, remainingDays: -10, dueReason: 'TIME', dueStatus: 'OVERDUE' })
    expect(text(parts)).toBe('Còn 4.000 km · quá 10 ngày')
    expect(parts.map(part => part.emphasized)).toEqual([false, true])
  })

  it('AC-003: over the km milestone → "Quá 300 km"', () => {
    expect(text(remainingParts({ remainingKm: -300, remainingDays: 20, dueReason: 'KM', dueStatus: 'OVERDUE' }))).toBe(
      'Quá 300 km · còn 20 ngày',
    )
  })

  it('exactly at the milestone', () => {
    expect(text(remainingParts({ remainingKm: null, remainingDays: 0, dueReason: 'TIME', dueStatus: 'DUE_SOON' }))).toBe(
      'Đúng mốc hôm nay',
    )
  })

  it('NORMAL never emphasises a part', () => {
    const parts = remainingParts({ remainingKm: 5000, remainingDays: 200, dueReason: null, dueStatus: 'NORMAL' })
    expect(parts.every(part => !part.emphasized)).toBe(true)
  })
})

describe('milestoneProgress (illustration only)', () => {
  const milestone = { odoMilestoneKm: 12000, monthMilestone: 12, label: '', dueDate: '2026-10-15', isRecurring: false, items: [] }
  const odometer = (odoKm: number) => ({ odoKm, recordedAt: '', isStale: false, dataSource: 'OEM' })

  it('is relative to the last service km', () => {
    expect(milestoneProgress({ odometer: odometer(9000), nextMilestone: milestone, lastService: { type: 'OEM', date: '', odoKm: 6000 } })).toBe(0.5)
  })

  it('is clamped to [0, 1] and null without ODO', () => {
    expect(milestoneProgress({ odometer: odometer(12300), nextMilestone: milestone, lastService: null })).toBe(1)
    expect(milestoneProgress({ odometer: null, nextMilestone: milestone, lastService: null })).toBeNull()
  })
})
