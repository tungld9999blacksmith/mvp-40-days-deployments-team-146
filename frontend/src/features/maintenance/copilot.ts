import type { MaintenanceStatus } from '@/features/vehicles/types'
import { milestoneTitle, remainingParts } from '@/features/vehicles/utils/maintenanceFormat'

export interface HistoryCopilot {
  /** Plain sentence; `figures` are the parts the line sets in the bright ink colour. */
  lead: string
  figures: string
  tail: string
  action: { to: string; label: string }
}

/**
 * The copilot line on Lịch sử dịch vụ: speaks only while the next milestone is due (DUE_SOON / OVERDUE)
 * and the backend lists its items, so every figure is real. Otherwise nothing.
 */
export function historyCopilot(
  status: Pick<MaintenanceStatus, 'dueStatus' | 'dueReason' | 'remainingKm' | 'remainingDays' | 'nextMilestone'> | null | undefined,
): HistoryCopilot | null {
  if (!status || (status.dueStatus !== 'DUE_SOON' && status.dueStatus !== 'OVERDUE')) return null
  const milestone = status.nextMilestone
  if (!milestone || milestone.items.length === 0) return null

  const remaining = remainingParts(status).map(part => part.text).join(' · ')
  const covered = milestone.items.filter(item => item.isCoveredByWarranty).length
  const count = milestone.items.length
  return {
    lead: `${milestoneTitle(milestone)}${remaining ? ` (${remaining.charAt(0).toLowerCase()}${remaining.slice(1)})` : ''} gồm `,
    figures: covered > 0 ? `${count} hạng mục, ${covered} được bảo hành` : `${count} hạng mục`,
    tail: '. Xem chi phí dự kiến trước khi đặt lịch.',
    action: { to: `/estimate?odoMilestone=${milestone.odoMilestoneKm}`, label: 'Xem chi phí dự kiến' },
  }
}
