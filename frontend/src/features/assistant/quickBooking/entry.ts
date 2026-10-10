/** Deep link used by Home to open AI Assistant and start one quick-booking proposal. */
export const QUICK_BOOKING_INTENT = 'quick-booking'

export const QUICK_BOOKING_ENTRY_PATH = `/ai/new?intent=${QUICK_BOOKING_INTENT}`

/** Returns the remaining query parameters when the quick-booking intent is present. */
export function consumeQuickBookingIntent(searchParams: URLSearchParams): URLSearchParams | null {
  if (searchParams.get('intent') !== QUICK_BOOKING_INTENT) return null
  const remaining = new URLSearchParams(searchParams)
  remaining.delete('intent')
  return remaining
}
