import type { MaintenanceStatus } from '@/features/vehicles/types'
import { QUICK_BOOKING_ENTRY_PATH } from '@/features/assistant/quickBooking/entry'

export type HomeSlideKind = 'maintenance' | 'booking' | 'assistant'

/**
 * Which banner slides Home shows, in order. Only real data or real features:
 * - maintenance: the vehicle has a known next milestone;
 * - booking: the selected vehicle has no upcoming appointment yet (with one, HomeHighlights already shows it, and BR-013 allows one open booking per vehicle);
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

/**
 * Primary button of the maintenance slide. With an open booking BR-013 rejects a second one, so the
 * slide leads to that appointment instead of quick booking.
 */
export function maintenanceSlideAction(openBookingId: string | null): { kind: 'book' | 'view'; to: string; label: string } {
  if (openBookingId) {
    return { kind: 'view', to: `/bookings/${encodeURIComponent(openBookingId)}?src=APP`, label: 'Xem lịch hẹn' }
  }
  return { kind: 'book', to: QUICK_BOOKING_ENTRY_PATH, label: 'Đặt lịch bảo dưỡng nhanh' }
}
