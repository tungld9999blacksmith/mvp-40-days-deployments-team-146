import type { MaintenanceStatus, Odometer, ServiceRecord, Warranty } from '@/features/vehicles/types'
import type { MyBookingItem } from '@/features/bookings/types'
import { isConfirmedStatus, isPendingStatus, slotLabel } from '@/features/bookings/utils'
import { serviceRecordCost } from '@/features/maintenance/utils'
import { QUICK_BOOKING_ENTRY_PATH } from '@/features/assistant/quickBooking/entry'
import { ASK_AI_QUESTION } from '@/features/vehicles/components/MaintenanceStatusCard'
import { milestoneTitle, remainingParts } from '@/features/vehicles/utils/maintenanceFormat'
import { warrantyTimeline } from '@/features/vehicles/utils/warrantyTimeline'
import { formatDate, formatNumber } from '@/shared/utils/format'

/** Lamp colours on ink (DESIGN.md "Tell-tales"): green fine, amber needs you, red overdue, off nothing to report. */
export type LampTone = 'green' | 'amber' | 'red' | 'off'

type StatusFields = Pick<
  MaintenanceStatus,
  'dueStatus' | 'dueReason' | 'remainingKm' | 'remainingDays' | 'nextMilestone'
>

export interface GaugeModel {
  /** Share of the interval used, 0–1, for the arc only; null draws an empty track. */
  fraction: number | null
  /** Figure in the centre; null renders "—". */
  value: string | null
  unit: string
  caption: string
  ends: [string, string] | null
  tone: LampTone
}

const DAY_MS = 86_400_000

/** Midnight (Vietnam) of a `YYYY-MM-DD…` string or of the Vietnam day an instant falls on. */
function vnDay(value: string | Date): number {
  if (typeof value === 'string') return Date.parse(`${value.slice(0, 10)}T00:00:00+07:00`)
  const shifted = value.getTime() + 7 * 3_600_000
  return shifted - (shifted % DAY_MS) - 7 * 3_600_000
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, value))

/** "17/10" from an ISO day. */
function dayMonth(day: string): string {
  return formatDate(day).slice(0, 5)
}

/** "24/10/25": the gauge ends can be a year apart on the same day and month. */
function shortDate(day: string): string {
  const full = formatDate(day)
  return `${full.slice(0, 6)}${full.slice(8)}`
}

function known(status: StatusFields | null | undefined): status is StatusFields {
  return !!status && status.dueStatus !== 'UNKNOWN'
}

/**
 * Colour of one gauge, from the backend's due status (BR-008: the arc length never decides it).
 * Red once that axis is past the milestone; amber when that axis is what made it DUE_SOON / OVERDUE.
 */
export function gaugeTone(status: StatusFields | null | undefined, axis: 'km' | 'time'): LampTone {
  if (!known(status)) return 'off'
  const remaining = axis === 'km' ? status.remainingKm : status.remainingDays
  if (remaining === null) return 'off'
  if (remaining < 0) return 'red'
  const alerting = status.dueStatus === 'DUE_SOON' || status.dueStatus === 'OVERDUE'
  const caused = status.dueReason === 'BOTH' || status.dueReason === (axis === 'km' ? 'KM' : 'TIME')
  return alerting && caused ? 'amber' : 'green'
}

const EMPTY_CAPTION = 'Chưa đủ dữ liệu'

type PeriodicVisit = Pick<ServiceRecord, 'serviceDate' | 'odoKm'>

/**
 * The latest periodic maintenance: where both gauges start. `status.lastService` is any record, a repair
 * included, so it is not the start of the maintenance interval.
 */
export function lastPeriodicService<T extends Pick<ServiceRecord, 'serviceDate' | 'odoKm' | 'isPeriodic'>>(records: T[]): T | null {
  return records.filter(record => record.isPeriodic).sort((a, b) => b.serviceDate.localeCompare(a.serviceDate))[0] ?? null
}

/** Left gauge: km from the last periodic service (or delivery, 0 km) to the next milestone, to scale. */
export function kmGauge(status: StatusFields | null | undefined, lastPeriodic: PeriodicVisit | null = null): GaugeModel {
  const km = known(status) ? status.remainingKm : null
  if (!known(status) || km === null || !status.nextMilestone) {
    return { fraction: null, value: null, unit: 'km', caption: EMPTY_CAPTION, ends: null, tone: 'off' }
  }
  const end = status.nextMilestone.odoMilestoneKm
  const lastKm = lastPeriodic?.odoKm ?? null
  const start = lastKm !== null && lastKm < end ? lastKm : 0
  // Current km from the backend's own remaining figure, so the arc and the number never disagree.
  const fraction = km < 0 ? 1 : clamp01((end - km - start) / (end - start))
  return {
    fraction,
    value: formatNumber(Math.abs(km)),
    unit: km < 0 ? 'km quá mốc' : 'km tới mốc',
    caption: `Mốc ${formatNumber(end)} km`,
    ends: [formatNumber(start), formatNumber(end)],
    tone: gaugeTone(status, 'km'),
  }
}

/** Right gauge: days from the last periodic service to the milestone's due date. Without one the arc stays empty. */
export function daysGauge(
  status: StatusFields | null | undefined,
  lastPeriodic: PeriodicVisit | null = null,
  now: Date = new Date(),
): GaugeModel {
  const days = known(status) ? status.remainingDays : null
  if (!known(status) || days === null || !status.nextMilestone) {
    return { fraction: null, value: null, unit: 'ngày', caption: EMPTY_CAPTION, ends: null, tone: 'off' }
  }
  const due = status.nextMilestone.dueDate
  const startDay = lastPeriodic && lastPeriodic.serviceDate < due ? lastPeriodic.serviceDate : null
  let fraction: number | null = null
  if (days < 0) fraction = 1
  else if (startDay) {
    const span = vnDay(due) - vnDay(startDay)
    fraction = span > 0 ? clamp01((vnDay(now) - vnDay(startDay)) / span) : 1
  }
  return {
    fraction,
    value: formatNumber(Math.abs(days)),
    unit: days < 0 ? 'ngày quá hạn' : 'ngày tới hạn',
    caption: `Hạn ${formatDate(due)}`,
    ends: startDay ? [shortDate(startDay), shortDate(due)] : null,
    tone: gaugeTone(status, 'time'),
  }
}

export interface Lamp {
  id: 'maintenance' | 'quotes' | 'booking' | 'warranty' | 'odo'
  tone: LampTone
  label: string
  to: string
}

/**
 * Tell-tale row of the Home cluster. Each lamp is a state EV Care knows; a lamp whose source is not
 * loaded (or switched off) is left out rather than shown as fine.
 */
export function tellTales({
  status,
  odometer,
  nextBooking,
  unseenQuotes,
  quotesEnabled,
  warranties,
  now = new Date(),
}: {
  status: StatusFields | null | undefined
  odometer: Odometer | null | undefined
  nextBooking: Pick<MyBookingItem, 'bookingId' | 'status'> | null
  unseenQuotes: number
  quotesEnabled: boolean
  warranties: Pick<Warranty, 'startDate' | 'endDate' | 'isActive'>[] | null
  now?: Date
}): Lamp[] {
  const lamps: Lamp[] = []

  if (!known(status)) lamps.push({ id: 'maintenance', tone: 'off', label: 'Chưa rõ hạn bảo dưỡng', to: '/vehicle' })
  else if (status.dueStatus === 'OVERDUE') lamps.push({ id: 'maintenance', tone: 'red', label: 'Đã quá hạn bảo dưỡng', to: '/vehicle' })
  else if (status.dueStatus === 'DUE_SOON') lamps.push({ id: 'maintenance', tone: 'amber', label: 'Sắp tới hạn bảo dưỡng', to: '/vehicle' })
  else lamps.push({ id: 'maintenance', tone: 'green', label: 'Bảo dưỡng đúng hạn', to: '/vehicle' })

  if (quotesEnabled) {
    lamps.push(
      unseenQuotes > 0
        ? { id: 'quotes', tone: 'amber', label: `${unseenQuotes} báo giá có kết quả`, to: '/quotes?unseenResult=true' }
        : { id: 'quotes', tone: 'off', label: 'Không có báo giá mới', to: '/quotes' },
    )
  }

  if (!nextBooking) lamps.push({ id: 'booking', tone: 'off', label: 'Chưa có lịch hẹn', to: '/booking' })
  else {
    const to = `/bookings/${encodeURIComponent(nextBooking.bookingId)}?src=APP`
    if (isPendingStatus(nextBooking.status)) lamps.push({ id: 'booking', tone: 'amber', label: 'Lịch hẹn chờ xưởng xác nhận', to })
    else lamps.push({ id: 'booking', tone: isConfirmedStatus(nextBooking.status) ? 'green' : 'off', label: 'Có lịch hẹn sắp tới', to })
  }

  if (warranties && warranties.length > 0) {
    const tones = warranties.map(warranty => warrantyTimeline(warranty, now).tone)
    if (tones.includes('ending')) lamps.push({ id: 'warranty', tone: 'amber', label: 'Bảo hành sắp hết', to: '/vehicle' })
    else if (tones.includes('active')) lamps.push({ id: 'warranty', tone: 'green', label: 'Bảo hành còn hiệu lực', to: '/vehicle' })
    else lamps.push({ id: 'warranty', tone: 'off', label: 'Hết bảo hành', to: '/vehicle' })
  }

  if (odometer) {
    lamps.push(
      odometer.isStale
        ? { id: 'odo', tone: 'amber', label: 'ODO chưa được cập nhật', to: '/vehicle' }
        : { id: 'odo', tone: 'off', label: 'ODO mới cập nhật', to: '/vehicle' },
    )
  }
  return lamps
}

export type VoicePrompt =
  | { kind: 'proposal'; text: string; actionLabel: string; to: string }
  | { kind: 'question'; question: string; to: string }

/**
 * What the assistant says in the cluster's voice bar. It speaks first only with real figures: the milestone
 * is due and nothing is booked yet. With an open booking BR-013 rejects a second one, so it asks instead.
 */
export function voicePrompt({ status, hasUpcomingBooking }: {
  status: StatusFields | null | undefined
  hasUpcomingBooking: boolean
}): VoicePrompt {
  const alerting = known(status) && (status.dueStatus === 'DUE_SOON' || status.dueStatus === 'OVERDUE')
  if (alerting && status.nextMilestone && !hasUpcomingBooking) {
    const remaining = remainingParts(status).map(part => part.text).join(' · ')
    const lead = remaining ? `${milestoneTitle(status.nextMilestone)}: ${remaining.charAt(0).toLowerCase()}${remaining.slice(1)}.` : `${milestoneTitle(status.nextMilestone)}.`
    return { kind: 'proposal', text: `${lead} Mình tìm xưởng và giờ trống gần bạn nhé?`, actionLabel: 'Đặt lịch nhanh', to: QUICK_BOOKING_ENTRY_PATH }
  }
  return { kind: 'question', question: ASK_AI_QUESTION, to: `/ai?q=${encodeURIComponent(ASK_AI_QUESTION)}` }
}

export interface MonthSpend {
  /** `YYYY-MM` */
  key: string
  /** Month number shown under the bar. */
  label: string
  total: number
}

/** EV Care spend per month over the last 12 months (current month last), from recorded final costs only. */
export function monthlySpend(records: Pick<ServiceRecord, 'serviceDate' | 'actualCost'>[], now: Date = new Date()): {
  months: MonthSpend[]
  total: number
  max: number
} {
  const today = new Date(vnDay(now) + 7 * 3_600_000)
  const months: MonthSpend[] = []
  for (let back = 11; back >= 0; back--) {
    const date = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - back, 1))
    const month = date.getUTCMonth() + 1
    months.push({ key: `${date.getUTCFullYear()}-${String(month).padStart(2, '0')}`, label: String(month), total: 0 })
  }
  const byKey = new Map(months.map(month => [month.key, month]))
  for (const record of records) {
    const cost = serviceRecordCost(record)
    const bucket = byKey.get(record.serviceDate.slice(0, 7))
    if (cost !== null && bucket) bucket.total += cost
  }
  const total = months.reduce((sum, month) => sum + month.total, 0)
  return { months, total, max: Math.max(0, ...months.map(month => month.total)) }
}

/** "9:00 · T7 17/10" style label for the next appointment card. */
export function bookingWhen(booking: Pick<MyBookingItem, 'timeSlot' | 'bookingDate'>): string {
  return `${slotLabel(booking.timeSlot)} · ${dayMonth(booking.bookingDate)}`
}
