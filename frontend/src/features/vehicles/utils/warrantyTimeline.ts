import type { Warranty } from '../types'

/** Ending within this many months shows as "Sắp hết hạn". */
export const ENDING_SOON_MONTHS = 6

export interface WarrantyTimeline {
  /** Share of the warranty period already used, 0–1; for the illustrative bar only. */
  usedRatio: number
  /** "Còn 5 năm 5 tháng", "Còn 5 tháng", "Còn 12 ngày", or "Đã hết hiệu lực". */
  remainingText: string
  tone: 'active' | 'ending' | 'ended'
}

/** Midnight (Vietnam) of a `YYYY-MM-DD…` string or of the Vietnam day an instant falls on. */
function dayStart(value: string | Date): number {
  if (typeof value === 'string') return new Date(`${value.slice(0, 10)}T00:00:00+07:00`).getTime()
  const shifted = value.getTime() + VN_OFFSET_MS
  return shifted - (shifted % 86_400_000) - VN_OFFSET_MS
}

const VN_OFFSET_MS = 7 * 3_600_000

/** Whole calendar months between two instants, counted on Vietnam dates whatever the device zone; never negative. */
function monthsBetween(fromMs: number, toMs: number): number {
  const from = new Date(fromMs + VN_OFFSET_MS)
  const to = new Date(toMs + VN_OFFSET_MS)
  const months = (to.getUTCFullYear() - from.getUTCFullYear()) * 12 + (to.getUTCMonth() - from.getUTCMonth())
  return Math.max(0, to.getUTCDate() < from.getUTCDate() ? months - 1 : months)
}

/**
 * Display-only timeline of one warranty line. `isActive` comes from the backend (it also covers the km
 * limit), so an inactive line reads as ended whatever its end date says.
 */
export function warrantyTimeline(warranty: Pick<Warranty, 'startDate' | 'endDate' | 'isActive'>, now: Date = new Date()): WarrantyTimeline {
  const start = dayStart(warranty.startDate)
  const end = dayStart(warranty.endDate)
  const today = dayStart(now)
  const span = end - start
  const usedRatio = span > 0 ? Math.min(1, Math.max(0, (today - start) / span)) : 1

  if (!warranty.isActive || today > end) return { usedRatio: 1, remainingText: 'Đã hết hiệu lực', tone: 'ended' }

  const months = monthsBetween(today, end)
  const years = Math.floor(months / 12)
  const restMonths = months % 12
  let remainingText: string
  if (months === 0) {
    const days = Math.max(0, Math.round((end - today) / 86_400_000))
    remainingText = days === 0 ? 'Hết hạn hôm nay' : `Còn ${days} ngày`
  } else if (years === 0) {
    remainingText = `Còn ${restMonths} tháng`
  } else {
    remainingText = restMonths ? `Còn ${years} năm ${restMonths} tháng` : `Còn ${years} năm`
  }
  return { usedRatio, remainingText, tone: months < ENDING_SOON_MONTHS ? 'ending' : 'active' }
}
