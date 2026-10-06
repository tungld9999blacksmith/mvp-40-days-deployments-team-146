import type { ServiceRecord } from '@/features/vehicles/types'

/** What was done: the manufacturer / workshop note, else the kind of visit. */
export function serviceRecordTitle(record: Pick<ServiceRecord, 'itemsDone' | 'isPeriodic'>): string {
  const note = record.itemsDone?.trim()
  if (note) return note
  return record.isPeriodic ? 'Bảo dưỡng định kỳ' : 'Sửa chữa / kiểm tra'
}

export function serviceRecordSource(record: Pick<ServiceRecord, 'source'>): string {
  return record.source === 'EV_CARE' ? 'EV Care' : 'Hãng'
}

export type ServiceRecordFilter = 'ALL' | 'PERIODIC' | 'OTHER'

export function matchesServiceRecord(record: ServiceRecord, filter: ServiceRecordFilter, search: string): boolean {
  if (filter === 'PERIODIC' && !record.isPeriodic) return false
  if (filter === 'OTHER' && record.isPeriodic) return false
  const needle = search.trim().toLowerCase()
  if (!needle) return true
  return [record.itemsDone, record.workshop?.name, record.bookingCode]
    .some(value => value?.toLowerCase().includes(needle))
}

export function serviceRecordCost(record: Pick<ServiceRecord, 'actualCost'>): number | null {
  if (record.actualCost === null || record.actualCost === undefined) return null
  const value = typeof record.actualCost === 'string' ? Number(record.actualCost) : record.actualCost
  return Number.isFinite(value) ? value : null
}
