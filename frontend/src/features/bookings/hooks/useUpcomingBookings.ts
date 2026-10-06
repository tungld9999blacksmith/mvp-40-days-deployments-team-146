import { invalidateQuery, useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { listMyBookings } from '../api'

/** Cache of "Lịch của tôi — Sắp tới" (API-BT-01) shown on Home. */
export const UPCOMING_BOOKINGS_KEY = 'bookings:upcoming'

const fetchUpcoming = () => listMyBookings('UPCOMING')

export function useUpcomingBookings() {
  return useCachedQuery(UPCOMING_BOOKINGS_KEY, fetchUpcoming, 60_000)
}

/** Call after any booking mutation (create, cancel, reschedule) so Home shows fresh data. */
export function invalidateUpcomingBookings() {
  invalidateQuery(UPCOMING_BOOKINGS_KEY)
}
