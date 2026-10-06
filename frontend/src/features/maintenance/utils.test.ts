import { describe, expect, it } from 'vitest'
import type { ServiceRecord } from '@/features/vehicles/types'
import { matchesServiceRecord, serviceRecordCost, serviceRecordSource, serviceRecordTitle } from './utils'

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
