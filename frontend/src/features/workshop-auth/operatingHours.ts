import type { OperatingHour } from './types'

export const DAY_LABELS = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']

/** Default week: Mon–Sat 08:00–17:30, Sunday closed (US-009 FE §4.3, `[Đề xuất]`). */
export function defaultOperatingHours(): OperatingHour[] {
  return DAY_LABELS.map((_, index) => {
    const dayOfWeek = index + 1
    return dayOfWeek === 7
      ? { dayOfWeek, isClosed: true, openTime: null, closeTime: null }
      : { dayOfWeek, isClosed: false, openTime: '08:00', closeTime: '17:30' }
  })
}

/** Always 7 rows ordered by dayOfWeek 1..7, closed days carry null times. */
export function normalizeOperatingHours(hours: OperatingHour[]): OperatingHour[] {
  const byDay = new Map(hours.map(hour => [hour.dayOfWeek, hour]))
  return DAY_LABELS.map((_, index) => {
    const dayOfWeek = index + 1
    const hour = byDay.get(dayOfWeek)
    if (!hour || hour.isClosed) return { dayOfWeek, isClosed: true, openTime: null, closeTime: null }
    return { dayOfWeek, isClosed: false, openTime: hour.openTime, closeTime: hour.closeTime }
  })
}

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/

/** Errors keyed like the backend `details.field`, e.g. `operatingHours[5].closeTime`. */
export function validateOperatingHours(hours: OperatingHour[]): Record<string, string> {
  const errors: Record<string, string> = {}
  hours.forEach((hour, index) => {
    if (hour.isClosed) return
    const prefix = `operatingHours[${index}]`
    if (!hour.openTime || !TIME_RE.test(hour.openTime) || !hour.closeTime || !TIME_RE.test(hour.closeTime)) {
      errors[`${prefix}.openTime`] = 'Vui lòng nhập giờ mở và giờ đóng.'
      return
    }
    if (hour.closeTime <= hour.openTime) errors[`${prefix}.closeTime`] = 'Giờ đóng cửa phải sau giờ mở cửa.'
  })
  if (hours.every(hour => hour.isClosed)) errors.operatingHours = 'Xưởng phải mở cửa ít nhất 1 ngày trong tuần.'
  return errors
}

/** Error message for one day row (either time field). */
export function dayError(errors: Record<string, string>, index: number): string | undefined {
  return errors[`operatingHours[${index}].openTime`] ?? errors[`operatingHours[${index}].closeTime`]
}
