/** Vietnamese number / date formatting. Display timezone is always Asia/Ho_Chi_Minh. */

const TIME_ZONE = 'Asia/Ho_Chi_Minh'
const numberFormat = new Intl.NumberFormat('vi-VN')

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

export function formatKm(value: number): string {
  return `${formatNumber(value)} km`
}

function toDate(value: string | Date): Date {
  // A bare `YYYY-MM-DD` is a calendar date in Vietnam time, not UTC midnight.
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Date(`${value}T00:00:00+07:00`)
  }
  return value instanceof Date ? value : new Date(value)
}

/** 28/09/2026 */
export function formatDate(value: string | Date): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(toDate(value))
}

/** "28/09" — built from parts because ICU's vi-VN day-month pattern prints "28-09". */
function formatDayMonth(date: Date): string {
  const parts = new Intl.DateTimeFormat('vi-VN', { timeZone: TIME_ZONE, day: '2-digit', month: '2-digit' }).formatToParts(date)
  const part = (type: string) => parts.find(item => item.type === type)?.value ?? ''
  return `${part('day')}/${part('month')}`
}

/** 09:00 28/09 */
export function formatTimeDayMonth(value: string | Date): string {
  const date = toDate(value)
  const time = new Intl.DateTimeFormat('vi-VN', {
    timeZone: TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
  return `${time} ${formatDayMonth(date)}`
}

/** 09:14 */
export function formatTime(value: string | Date): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(toDate(value))
}

function dayKey(date: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE }).format(date)
}

/** "Hôm nay 09:14" · "Hôm qua" · "28/09" */
export function formatRelativeDay(value: string | Date, now: Date = new Date()): string {
  const date = toDate(value)
  const today = dayKey(now)
  const yesterday = dayKey(new Date(now.getTime() - 86_400_000))
  const key = dayKey(date)
  if (key === today) return `Hôm nay ${formatTime(date)}`
  if (key === yesterday) return 'Hôm qua'
  return formatDayMonth(date)
}

/** 5400 → "1 giờ 30 phút"; 40 → "1 phút" (rounded up). */
export function formatDuration(seconds: number): string {
  const totalMinutes = Math.max(1, Math.ceil(seconds / 60))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours && minutes) return `${hours} giờ ${minutes} phút`
  if (hours) return `${hours} giờ`
  return `${minutes} phút`
}

/** 40 → "00:40" */
export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

/** `30A12345` → `30A-123.45`; `30A1234` → `30A-1234`. Display only. */
export function formatLicensePlate(plate: string): string {
  const match = /^(\d{2}[A-Z]{1,2}\d?)(\d{3})(\d{2})$/.exec(plate)
  if (match) return `${match[1]}-${match[2]}.${match[3]}`
  const four = /^(\d{2}[A-Z]{1,2}\d?)(\d{4})$/.exec(plate)
  if (four) return `${four[1]}-${four[2]}`
  return plate
}
