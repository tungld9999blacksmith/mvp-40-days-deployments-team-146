import { describe, expect, it } from 'vitest'
import { formatRelativeDay, formatTimeDayMonth } from './format'

// Regression: FINDING-005 (/design-review 2026-10-05) — ICU's vi-VN day-month pattern printed "01-10".
describe('day-month formatting', () => {
  it('writes the day and month with a slash, in Vietnam time', () => {
    expect(formatTimeDayMonth('2026-10-01T05:35:00Z')).toBe('12:35 01/10')
  })

  it('uses the same day/month form for older relative days', () => {
    expect(formatRelativeDay('2026-09-28T02:00:00Z', new Date('2026-10-05T02:00:00Z'))).toBe('28/09')
  })
})
