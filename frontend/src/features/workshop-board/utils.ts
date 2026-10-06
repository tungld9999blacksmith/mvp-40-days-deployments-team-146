/** Pure helpers of the Workshop Board (us-037 FE). */

/** The ticket QR holds `{APP_BASE_URL}/c/{code}` or the bare code (§4.9) — returns the upper-case code. */
export function codeFromQr(content: string): string {
  const text = content.trim()
  const match = /\/c\/([A-Za-z0-9-]+)\/?$/.exec(text)
  return (match ? match[1] : text).toUpperCase()
}

/** UTC ISO of a booking day + `HH:mm[:ss]` in Vietnam time (bookingDate/timeSlot are local). */
export function appointmentIso(date: string, timeSlot: string): string {
  return new Date(`${date}T${timeSlot.slice(0, 5)}:00+07:00`).toISOString()
}

/** Manual code input rule (§8.1). */
export const BOOKING_CODE_PATTERN = /^[A-Z0-9-]{4,20}$/

/** Capacity cell state: a slot with no seats and nothing booked or locked does not take bookings; it is not "full". */
export function capacitySlotState(slot: { occupied: number; blocked: number; remaining: number }): 'open' | 'full' | 'closed' {
  if (slot.remaining > 0) return 'open'
  return slot.occupied === 0 && slot.blocked === 0 ? 'closed' : 'full'
}
