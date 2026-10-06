/** Pure helpers of the booking flow (US-029 FE). Dates are calendar days in Asia/Ho_Chi_Minh. */

const TIME_ZONE = 'Asia/Ho_Chi_Minh'
const WEEKDAYS = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
const WEEKDAYS_LONG = ['Chủ nhật', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7']

/** Confirmation token lifetime (backend `BOOKING_CONFIRMATION_TOKEN_TTL_SECONDS`, not returned by BK-02). */
export const TOKEN_TTL_SECONDS = 600
/** Booking window shown in the day strip (backend `BOOKING_SEARCH_HORIZON_DAYS`). */
export const SEARCH_HORIZON_DAYS = 7
export const NOTE_MAX_LENGTH = 500

/** `YYYY-MM-DD` of `now` in Vietnam time. */
export function todayVn(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE }).format(now)
}

function parseDay(day: string): Date {
  return new Date(`${day}T00:00:00+07:00`)
}

export function addDays(day: string, amount: number): string {
  return todayVn(new Date(parseDay(day).getTime() + amount * 86_400_000))
}

/** Today plus the next `SEARCH_HORIZON_DAYS - 1` days. */
export function bookableDays(now: Date = new Date()): string[] {
  const today = todayVn(now)
  return Array.from({ length: SEARCH_HORIZON_DAYS }, (_, index) => addDays(today, index))
}

export function isBookableDay(day: string, now: Date = new Date()): boolean {
  return bookableDays(now).includes(day)
}

function weekdayIndex(day: string): number {
  // Noon avoids any DST/offset edge; the day itself is already a Vietnam date.
  return new Date(`${day}T12:00:00+07:00`).getUTCDay()
}

/** `2026-10-04` → `{ weekday: 'T7', dayMonth: '04/10' }` */
export function dayChip(day: string): { weekday: string; dayMonth: string } {
  const [, month, date] = day.split('-')
  return { weekday: WEEKDAYS[weekdayIndex(day)], dayMonth: `${date}/${month}` }
}

/** `2026-10-04` → `Thứ 7, 04/10/2026` */
export function formatLongDay(day: string): string {
  const [year, month, date] = day.split('-')
  return `${WEEKDAYS_LONG[weekdayIndex(day)]}, ${date}/${month}/${year}`
}

/** Backend times are `HH:mm:ss`; the UI and query strings use `HH:mm`. */
export function slotLabel(timeSlot: string): string {
  return timeSlot.slice(0, 5)
}

/** Slot already started today (Vietnam time) — hidden even if the backend still lists it. */
export function isPastSlot(day: string, timeSlot: string, now: Date = new Date()): boolean {
  const start = new Date(`${day}T${slotLabel(timeSlot)}:00+07:00`)
  return start.getTime() <= now.getTime()
}

/**
 * Earliest day that can still be booked. Stops at a day still loading, so the
 * selection does not jump to a later day whose answer happened to arrive first.
 */
export function pickDefaultDay(days: string[], states: Record<string, string>): string | null {
  for (const day of days) {
    const state = states[day] ?? 'loading'
    if (state === 'open' || state === 'loading') return day
  }
  return null
}

/** Token expiry estimated from the moment BK-02 answered (the API does not return it). */
export function tokenExpiry(issuedAt: number, ttlSeconds: number = TOKEN_TTL_SECONDS): number {
  return issuedAt + ttlSeconds * 1000
}

export function secondsLeft(until: number | string | null, now: number = Date.now()): number {
  if (until === null) return 0
  const target = typeof until === 'number' ? until : new Date(until).getTime()
  return Math.max(0, Math.ceil((target - now) / 1000))
}

/** 3.4 → "3,4 km"; `null` → "Cùng khu vực" (ranked by region, FE §4.2). */
export function formatDistance(distanceKm: number | null): string {
  if (distanceKm === null) return 'Cùng khu vực'
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(distanceKm)} km`
}

/** "Còn 2 chỗ" only when few remain (FE §3.4); `null` when there is no need to show it. */
export function remainingLabel(remaining: number, available: boolean): string | null {
  if (!available || remaining <= 0) return 'Hết chỗ'
  return remaining <= 3 ? `Còn ${remaining} chỗ` : null
}

export function isPendingStatus(status: string): boolean {
  return status.toLowerCase() === 'pending'
}

export function isConfirmedStatus(status: string): boolean {
  return status.toLowerCase() === 'confirmed'
}

/** Error code → owner-facing message (FE §7). `null` ⇒ the caller shows a generic error. */
export function bookingErrorMessage(code: string): string | null {
  switch (code) {
    case 'LOCATION_ANCHOR_REQUIRED':
      return 'Cho mình biết bạn muốn đặt gần đâu nhé.'
    case 'WORKSHOP_NOT_FOUND':
    case 'NO_WORKSHOP_AVAILABLE':
      return 'Chưa có xưởng khả dụng gần vị trí này.'
    case 'SLOT_OUT_OF_HOURS':
      return 'Khung giờ này nằm ngoài giờ hoạt động của xưởng, bạn chọn khung khác nhé.'
    case 'SLOT_FULL':
      return 'Khung giờ này vừa hết chỗ.'
    case 'HOLD_EXPIRED':
    case 'INVALID_CONFIRMATION_TOKEN':
      return 'Thẻ đặt lịch đã hết hiệu lực, mình kiểm tra lại giúp bạn.'
    case 'OPEN_BOOKING_EXISTS':
      return 'Xe của bạn đang có một lịch hẹn chưa hoàn tất.'
    case 'HOLD_WINDOW_CLOSED':
      return 'Đã quá thời gian tự huỷ giữ chỗ, lịch hẹn đang chờ xưởng xác nhận.'
    case 'SERVICE_UNAVAILABLE':
      return 'Tạm thời chưa đặt được, bạn thử lại giúp mình.'
    default:
      return null
  }
}
