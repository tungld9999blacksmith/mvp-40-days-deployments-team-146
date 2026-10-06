import type { MaintenanceStatus } from '@/features/vehicles/types'

export type HomeSlideKind = 'maintenance' | 'booking' | 'assistant'

/**
 * Which banner slides Home shows, in order. Only real data or real features:
 * - maintenance: the vehicle has a known next milestone;
 * - booking: no upcoming appointment yet (with one, HomeHighlights already shows it, and BR-013 allows one open booking);
 * - assistant: always.
 */
export function homeSlideKinds({ status, hasUpcomingBooking }: {
  status: Pick<MaintenanceStatus, 'dueStatus' | 'nextMilestone'> | null
  hasUpcomingBooking: boolean
}): HomeSlideKind[] {
  const kinds: HomeSlideKind[] = []
  if (status && status.dueStatus !== 'UNKNOWN' && status.nextMilestone) kinds.push('maintenance')
  if (!hasUpcomingBooking) kinds.push('booking')
  kinds.push('assistant')
  return kinds
}
