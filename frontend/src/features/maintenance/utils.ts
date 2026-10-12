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

/** What was done as a list: the note split on commas, semicolons and new lines. */
export function serviceRecordItems(record: Pick<ServiceRecord, 'itemsDone' | 'isPeriodic'>): string[] {
  const parts = (record.itemsDone ?? '')
    .split(/[,;\n]+/)
    .map(part => part.trim())
    .filter(Boolean)
  return parts.length > 0 ? parts : [serviceRecordTitle(record)]
}

export interface ServiceHistorySummary {
  periodicCount: number
  /** Earliest periodic visit (ISO day), for "từ 06/2025". */
  firstPeriodicDate: string | null
  latest: ServiceRecord | null
  /** Final costs of EV Care visits; manufacturer records carry no price. */
  evCareCost: { total: number; count: number }
}

/** Figures of the strip above the history table, from the records alone (no extra request). */
export function serviceHistorySummary(records: ServiceRecord[]): ServiceHistorySummary {
  let periodicCount = 0
  let firstPeriodicDate: string | null = null
  let latest: ServiceRecord | null = null
  let total = 0
  let count = 0
  for (const record of records) {
    if (record.isPeriodic) {
      periodicCount += 1
      if (firstPeriodicDate === null || record.serviceDate < firstPeriodicDate) firstPeriodicDate = record.serviceDate
    }
    if (latest === null || record.serviceDate > latest.serviceDate) latest = record
    const cost = record.source === 'EV_CARE' ? serviceRecordCost(record) : null
    if (cost !== null) {
      total += cost
      count += 1
    }
  }
  return { periodicCount, firstPeriodicDate, latest, evCareCost: { total, count } }
}
