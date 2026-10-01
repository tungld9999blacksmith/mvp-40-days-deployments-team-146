import { formatNumber } from '@/shared/utils/format'
import type { MaintenanceStatus, NextMilestone } from '../types'

/** "Mốc 12.000 km / 12 tháng" — built from numbers, never from the English `label`. */
export function milestoneTitle(milestone: Pick<NextMilestone, 'odoMilestoneKm' | 'monthMilestone'>): string {
  return `Mốc ${formatNumber(milestone.odoMilestoneKm)} km / ${milestone.monthMilestone} tháng`
}

export interface RemainingPart {
  text: string
  /** This part is what caused DUE_SOON / OVERDUE (per `dueReason`). */
  emphasized: boolean
  kind: 'km' | 'days'
}

/**
 * Distance to the milestone, displayed exactly from backend numbers (US-017 FE §4.2):
 * "Còn 400 km · 17 ngày", "Quá 300 km", "Còn 4.000 km · quá 10 ngày", "Còn 17 ngày" (TIME_ONLY).
 * Negative values are kept negative in data and rendered as "Quá …".
 */
export function remainingParts(
  status: Pick<MaintenanceStatus, 'remainingKm' | 'remainingDays' | 'dueReason' | 'dueStatus'>,
): RemainingPart[] {
  const { remainingKm: km, remainingDays: days, dueReason, dueStatus } = status
  const alerting = dueStatus === 'DUE_SOON' || dueStatus === 'OVERDUE'
  const kmEmphasis = alerting && (dueReason === 'KM' || dueReason === 'BOTH')
  const daysEmphasis = alerting && (dueReason === 'TIME' || dueReason === 'BOTH')
  const parts: RemainingPart[] = []

  if (km !== null) {
    const text = km > 0 ? `Còn ${formatNumber(km)} km` : km === 0 ? 'Đến mốc km' : `Quá ${formatNumber(-km)} km`
    parts.push({ text, emphasized: kmEmphasis, kind: 'km' })
  }

  if (days !== null) {
    const leading = parts.length === 0
    const counting = km !== null && km > 0
    let text: string
    if (days > 0) text = counting ? `${formatNumber(days)} ngày` : `${leading ? 'Còn' : 'còn'} ${formatNumber(days)} ngày`
    else if (days === 0) text = leading ? 'Đúng mốc hôm nay' : 'đến hạn hôm nay'
    else text = `${leading ? 'Quá' : 'quá'} ${formatNumber(-days)} ngày`
    parts.push({ text, emphasized: daysEmphasis, kind: 'days' })
  }
  return parts
}

export const DUE_REASON_TEXT: Record<string, string> = {
  KM: 'Theo số km',
  TIME: 'Theo thời gian',
  BOTH: 'Theo số km và thời gian',
}

/**
 * Progress towards the next milestone for the illustrative bar only — never used to
 * decide the status (BR-008). Base is the last service km, or 0.
 */
export function milestoneProgress(status: Pick<MaintenanceStatus, 'odometer' | 'nextMilestone' | 'lastService'>): number | null {
  if (!status.odometer || !status.nextMilestone) return null
  const base = status.lastService?.odoKm ?? 0
  const span = status.nextMilestone.odoMilestoneKm - base
  if (span <= 0) return 1
  return Math.min(1, Math.max(0, (status.odometer.odoKm - base) / span))
}
