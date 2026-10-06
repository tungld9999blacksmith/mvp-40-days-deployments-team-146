import { describe, expect, it } from 'vitest'
import { formatVnd, milestoneLabel, readNumberParam, validMilestone } from './utils'

describe('estimate utils', () => {
  it('formats money the Vietnamese way and never rounds it', () => {
    expect(formatVnd(1_300_000)).toBe('1.300.000 ₫')
    expect(formatVnd(0)).toBe('0 ₫')
  })

  it('labels a milestone with km and months', () => {
    expect(milestoneLabel(12_000, 12)).toBe('Mốc 12.000 km / 12 tháng')
  })

  it('drops a query milestone that is not in API-EST-01 (FE §8)', () => {
    expect(validMilestone(24_000, [12_000, 24_000])).toBe(24_000)
    expect(validMilestone(13_000, [12_000, 24_000])).toBeNull()
    expect(validMilestone(null, [12_000])).toBeNull()
  })

  it('only reads whole positive numbers from the query', () => {
    expect(readNumberParam('12000')).toBe(12_000)
    expect(readNumberParam('12k')).toBeNull()
    expect(readNumberParam(null)).toBeNull()
  })
})
