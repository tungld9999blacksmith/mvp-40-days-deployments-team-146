import { describe, expect, it } from 'vitest'
import type { ServiceRecord } from '@/features/vehicles/types'
import {
  matchesServiceRecord,
  serviceHistorySummary,
  serviceRecordCost,
  serviceRecordItems,
  serviceRecordSource,
  serviceRecordTitle,
} from './utils'

const record = (overrides: Partial<ServiceRecord> = {}): ServiceRecord => ({
  recordId: 'r1',
  source: 'OEM',
  serviceDate: '2026-04-12',
  odoKm: 10_000,
  isPeriodic: true,
  itemsDone: null,
  workshop: { workshopId: null, name: 'VinFast Hà Nội' },
  bookingId: null,
  bookingCode: null,
  actualCost: null,
  ...overrides,
})

describe('service record helpers', () => {
  it('titles a record by its note, else by the kind of visit', () => {
    expect(serviceRecordTitle(record({ itemsDone: ' Thay lọc gió ' }))).toBe('Thay lọc gió')
    expect(serviceRecordTitle(record())).toBe('Bảo dưỡng định kỳ')
    expect(serviceRecordTitle(record({ isPeriodic: false }))).toBe('Sửa chữa / kiểm tra')
  })

  it('names the source', () => {
    expect(serviceRecordSource(record())).toBe('Hãng')
    expect(serviceRecordSource(record({ source: 'EV_CARE' }))).toBe('EV Care')
  })

  it('filters by kind and searches note, workshop and booking code', () => {
    const repair = record({ isPeriodic: false, itemsDone: 'Thay cảm biến', bookingCode: 'EVC-7K2M' })
    expect(matchesServiceRecord(repair, 'PERIODIC', '')).toBe(false)
    expect(matchesServiceRecord(repair, 'OTHER', 'cảm biến')).toBe(true)
    expect(matchesServiceRecord(repair, 'ALL', 'evc-7k2m')).toBe(true)
    expect(matchesServiceRecord(repair, 'ALL', 'hà nội')).toBe(true)
    expect(matchesServiceRecord(repair, 'ALL', 'đà nẵng')).toBe(false)
  })

  it('reads the decimal cost the backend sends as a string', () => {
    expect(serviceRecordCost(record({ actualCost: '1250000.00' }))).toBe(1_250_000)
    expect(serviceRecordCost(record({ actualCost: 800_000 }))).toBe(800_000)
    expect(serviceRecordCost(record())).toBeNull()
  })
})

describe('serviceRecordItems', () => {
  it('splits the note into items', () => {
    expect(serviceRecordItems(record({ itemsDone: 'Thay lọc gió, kiểm tra phanh;\nĐảo lốp ' }))).toEqual(['Thay lọc gió', 'kiểm tra phanh', 'Đảo lốp'])
  })

  it('falls back to the kind of visit without a note', () => {
    expect(serviceRecordItems(record({ itemsDone: ' ' }))).toEqual(['Bảo dưỡng định kỳ'])
  })
})

describe('serviceHistorySummary', () => {
  it('counts periodic visits, finds the latest and adds up EV Care costs only', () => {
    const records = [
      record({ recordId: 'a', serviceDate: '2025-06-10', isPeriodic: true }),
      record({ recordId: 'b', serviceDate: '2026-06-12', isPeriodic: true, source: 'EV_CARE', actualCost: '1420000.00' }),
      record({ recordId: 'c', serviceDate: '2026-04-02', isPeriodic: false, source: 'EV_CARE', actualCost: 380_000 }),
      record({ recordId: 'd', serviceDate: '2025-12-20', isPeriodic: false, source: 'EV_CARE', actualCost: null }),
      record({ recordId: 'e', serviceDate: '2025-09-15', isPeriodic: false, actualCost: 999 }),
    ]
    const summary = serviceHistorySummary(records)
    expect(summary.periodicCount).toBe(2)
    expect(summary.firstPeriodicDate).toBe('2025-06-10')
    expect(summary.latest?.recordId).toBe('b')
    expect(summary.evCareCost).toEqual({ total: 1_800_000, count: 2 })
  })

  it('is empty for no records', () => {
    expect(serviceHistorySummary([])).toEqual({ periodicCount: 0, firstPeriodicDate: null, latest: null, evCareCost: { total: 0, count: 0 } })
  })
})
