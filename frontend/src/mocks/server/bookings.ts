/**
 * Owner-side booking APIs: ticket (API-BR-01 + us-053 fields), attendance (BR-02), cancel (BR-03),
 * "Lịch của tôi" (BT-01), QR (BT-02), by-code (BT-03), reschedule availability (BK-02 extension)
 * and reschedule (BT-04), owner progress (PG-03). Views shared with the Board live here too.
 */
import QRCode from 'qrcode'
import { milestoneItems } from './catalog'
import { bodyOf, fail, ok, rememberIdempotent as remember, replayIdempotent as replay, route } from './core'
import {
  addDays,
  appointmentAt,
  getDb,
  hash01,
  hoursFromNow,
  isoMinus,
  maskPlate,
  nowIso,
  save,
  todayVn,
  uuid,
  type BookingState,
  type MockBooking,
  type Stage,
} from './db'

export const RESCHEDULE_MIN_LEAD_MINUTES = 60
export const RESCHEDULE_MAX_COUNT = 2
export const CONFIRM_DEADLINE_HOURS = 12
export const NO_SHOW_GRACE_MINUTES = 30
const HORIZON_DAYS = 7
const PAST_DAYS = 90
const TOKEN_TTL_SECONDS = 600
export const DOCUMENTS_TO_BRING = ['Giấy đăng ký xe', 'Sổ bảo hành / sổ bảo dưỡng (nếu có)', 'Mã lịch hẹn hoặc QR này']
export const SLOT_TIMES = ['08:00', '09:00', '10:00', '11:00', '13:00', '14:00', '15:00', '16:00']
export const TOTAL_TECHNICIANS = 4
export const EMERGENCY_SLOTS = 1
export const CAPACITY_BASE = TOTAL_TECHNICIANS - EMERGENCY_SLOTS
const OPEN_STATES: BookingState[] = ['pending', 'confirmed', 'checked_in', 'in_progress']

const GROUP = 'bookings'

/** `APP_BASE_URL` of the QR payload (BR-1203) — the current origin in the browser. */
function appBaseUrl(): string {
  return typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173'
}

// ---------------------------------------------------------------- shared helpers

export function upper(status: string): string {
  return status.toUpperCase()
}

export function apptOf(booking: MockBooking): string {
  return appointmentAt(booking.bookingDate, booking.timeSlot)
}

export function isClosedDay(date: string): boolean {
  return new Date(`${date}T12:00:00+07:00`).getUTCDay() === 0
}

export function workshopOf(workshopId: string) {
  return (
    getDb().workshops.find(item => item.workshopId === workshopId) ?? {
      workshopId,
      name: 'Xưởng dịch vụ',
      address: '',
      phone: '',
      region: '',
      active: true,
      isPreferred: false,
    }
  )
}

export function confirmDeadlineOf(booking: MockBooking): string | null {
  if (booking.status !== 'pending' || booking.confirmationMode !== 'MANUAL') return null
  const deadline = Math.min(
    new Date(booking.createdAt).getTime() + CONFIRM_DEADLINE_HOURS * 3_600_000,
    new Date(apptOf(booking)).getTime(),
  )
  return new Date(deadline).toISOString()
}

function wasConfirmed(booking: MockBooking): boolean {
  return booking.events.some(event => event.toStatus === 'CONFIRMED')
}

/** The code is generated at creation but only shown once the booking was confirmed (HOOK-BT-01). */
export function visibleCode(booking: MockBooking): string | null {
  return booking.status !== 'pending' && wasConfirmed(booking) ? booking.bookingCode : null
}

export function pushEvent(
  booking: MockBooking,
  toStatus: BookingState,
  actorType: 'VEHICLE_OWNER' | 'WORKSHOP_OWNER' | 'SYSTEM',
  source: string,
  reasonCode: string | null = null,
  note: string | null = null,
) {
  booking.events.push({ fromStatus: upper(booking.status), toStatus: upper(toStatus), actorType, source, reasonCode, note, at: nowIso() })
  booking.status = toStatus
}

/** Booking `pending` past the workshop deadline is cancelled by the system (us-029 BR-015). */
export function reconcileBookings() {
  let changed = false
  const now = Date.now()
  for (const booking of getDb().bookings) {
    const deadline = confirmDeadlineOf(booking)
    if (deadline && now > new Date(deadline).getTime()) {
      pushEvent(booking, 'cancelled', 'SYSTEM', 'CONFIRM_DEADLINE', 'CONFIRM_DEADLINE_PASSED')
      changed = true
    }
  }
  if (changed) save()
}

export function occupiedCount(date: string, timeSlot: string, excludeId: string | null = null): number {
  return getDb().bookings.filter(
    booking =>
      booking.bookingDate === date && booking.timeSlot === timeSlot && booking.bookingId !== excludeId && OPEN_STATES.includes(booking.status),
  ).length
}

export function blockOf(date: string, timeSlot: string) {
  return getDb().slotBlocks.find(block => block.date === date && block.timeSlot === timeSlot) ?? null
}

export function remainingOf(date: string, timeSlot: string, excludeId: string | null = null): number {
  return Math.max(CAPACITY_BASE - (blockOf(date, timeSlot)?.blockedCount ?? 0) - occupiedCount(date, timeSlot, excludeId), 0)
}

function itemsOf(booking: MockBooking): { itemName: string; covered: boolean }[] {
  const vehicle = getDb().vehicles.find(item => item.userVehicleId === booking.userVehicleId) ?? null
  return milestoneItems(vehicle, booking.odoMilestone)
}

export function costOf(booking: MockBooking): { amount: number | null; label: 'ESTIMATE' | 'NONE' } {
  if (booking.estimatedCost !== null) return { amount: booking.estimatedCost, label: 'ESTIMATE' }
  return { amount: null, label: 'NONE' }
}

// ---------------------------------------------------------------- progress (us-057)

const NEXT_STAGES: Record<Stage, Stage[]> = {
  CHECKED_IN: [],
  INSPECTING: ['SERVICING'],
  SERVICING: ['WAITING_PARTS', 'QUALITY_CHECK'],
  WAITING_PARTS: ['SERVICING'],
  QUALITY_CHECK: ['READY_FOR_PICKUP', 'SERVICING'],
  READY_FOR_PICKUP: [],
}

export function currentStageOf(booking: MockBooking): Stage | null {
  const last = booking.progress[booking.progress.length - 1]
  if (last) return last.stage
  // Checked in before the feature was enabled (FF EDGE-1304).
  if (booking.status === 'checked_in') return 'CHECKED_IN'
  if (booking.status === 'in_progress' || booking.status === 'completed') return 'INSPECTING'
  return null
}

export function nextStagesOf(booking: MockBooking): Stage[] {
  if (booking.status !== 'in_progress') return []
  const current = currentStageOf(booking)
  return current ? NEXT_STAGES[current] : []
}

export function progressView(booking: MockBooking, forPortal: boolean) {
  return {
    bookingId: booking.bookingId,
    bookingStatus: upper(booking.status),
    currentStage: currentStageOf(booking),
    isFrozen: booking.status === 'completed' || booking.status === 'cancelled',
    ...(forPortal ? { nextStages: nextStagesOf(booking) } : {}),
    entries: booking.progress.map(entry => ({
      stage: entry.stage,
      note: entry.note,
      actorType: entry.actorType,
      ...(forPortal ? { actorName: entry.actorType === 'SYSTEM' ? null : entry.actorName } : {}),
      createdAt: entry.createdAt,
    })),
  }
}

// ---------------------------------------------------------------- owner views

function ownerActions(booking: MockBooking): { allowedActions: string[]; rescheduleBlockedReason: string | null } {
  const now = Date.now()
  const appt = new Date(apptOf(booking)).getTime()
  const actions: string[] = []
  let reason: string | null = null
  if (booking.status === 'pending') {
    if (booking.ownerCancelableUntil && now <= new Date(booking.ownerCancelableUntil).getTime()) actions.push('CANCEL_HOLD')
    reason = 'NOT_CONFIRMED'
  } else if (booking.status === 'confirmed' && now < appt) {
    if (!booking.attendanceConfirmedAt) actions.push('CONFIRM_ATTENDANCE')
    if (now >= appt - RESCHEDULE_MIN_LEAD_MINUTES * 60_000) reason = 'TOO_CLOSE_TO_APPOINTMENT'
    else if (booking.rescheduleCount >= RESCHEDULE_MAX_COUNT) reason = 'MAX_RESCHEDULES_REACHED'
    else actions.push('RESCHEDULE')
    actions.push('CANCEL')
  } else if (booking.status === 'confirmed') {
    reason = 'TOO_CLOSE_TO_APPOINTMENT'
  }
  return { allowedActions: actions, rescheduleBlockedReason: actions.includes('RESCHEDULE') ? null : reason }
}

function historyOf(booking: MockBooking) {
  const status = booking.events.map(event => ({ kind: 'STATUS' as const, ...event }))
  const moves = booking.reschedules.map(move => ({ kind: 'RESCHEDULE' as const, ...move }))
  return [...status, ...moves].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 20)
}

export function ticketView(booking: MockBooking) {
  const workshop = workshopOf(booking.workshopId)
  const confirmed = booking.status === 'confirmed'
  const code = visibleCode(booking)
  const cost = costOf(booking)
  const cancel = booking.status === 'cancelled' ? [...booking.events].reverse().find(event => event.toStatus === 'CANCELLED') ?? null : null
  const followUp = getDb().followUps.find(item => item.bookingId === booking.bookingId) ?? null
  return {
    bookingId: booking.bookingId,
    bookingCode: code,
    status: upper(booking.status),
    bookingDate: booking.bookingDate,
    timeSlot: booking.timeSlot,
    appointmentAt: apptOf(booking),
    workshop: { workshopId: workshop.workshopId, name: workshop.name, address: workshop.address || null, phone: workshop.phone || null },
    vehicle: { userVehicleId: booking.userVehicleId, modelName: booking.vehicle.modelName, plateMasked: maskPlate(booking.vehicle.licensePlate) },
    estimatedCost: cost.amount,
    estimateLabel: 'Chi phí ước tính',
    qrUrl: confirmed ? `/api/v1/bookings/${booking.bookingId}/qr` : null,
    qrPayload: confirmed && code ? `${appBaseUrl()}/c/${code}` : null,
    attendanceConfirmedAt: booking.attendanceConfirmedAt,
    ...ownerActions(booking),
    rescheduleMode: 'F6B',
    odoMilestone: booking.odoMilestone,
    items: itemsOf(booking),
    cost,
    documentsToBring: DOCUMENTS_TO_BRING,
    rescheduleCount: booking.rescheduleCount,
    rescheduleDeadline: confirmed ? isoMinus(apptOf(booking), RESCHEDULE_MIN_LEAD_MINUTES) : null,
    holdExpiresAt: booking.holdExpiresAt,
    ownerCancelableUntil: booking.ownerCancelableUntil,
    cancelledAt: cancel?.at ?? null,
    cancelledBy: cancel?.actorType ?? null,
    cancelReason: cancel?.reasonCode ?? null,
    completedAt: booking.events.find(event => event.toStatus === 'COMPLETED')?.at ?? null,
    history: historyOf(booking),
    followUp:
      booking.status === 'completed' && followUp
        ? { followUpId: followUp.followUpId, canRespond: followUp.status === 'sent' }
        : null,
  }
}

function listItem(booking: MockBooking) {
  const workshop = workshopOf(booking.workshopId)
  const cost = costOf(booking)
  return {
    bookingId: booking.bookingId,
    bookingCode: visibleCode(booking),
    status: upper(booking.status),
    appointmentAt: apptOf(booking),
    bookingDate: booking.bookingDate,
    timeSlot: booking.timeSlot,
    workshop: { workshopId: workshop.workshopId, name: workshop.name },
    cost: { amount: cost.amount, label: cost.label },
    allowedActions: ownerActions(booking).allowedActions,
  }
}

function ownBooking(id: string): MockBooking | null {
  return getDb().bookings.find(booking => booking.bookingId === id && booking.ownerSelf) ?? null
}

const notFound = () => fail(404, 'BOOKING_NOT_FOUND', 'Không tìm thấy lịch hẹn.')

// ---------------------------------------------------------------- reschedule availability

/** Every slot of an open day (like API-BK-02); started slots are not available. */
function slotsOf(date: string, excludeId: string | null) {
  if (isClosedDay(date)) return []
  const now = Date.now()
  return SLOT_TIMES.map(slot => {
    const remaining = remainingOf(date, slot, excludeId)
    const started = new Date(appointmentAt(date, slot)).getTime() <= now
    return { timeSlot: `${slot}:00`, available: !started && remaining > 0, remaining: started ? 0 : remaining }
  })
}

function alternativesFor(booking: MockBooking, date: string, timeSlot: string) {
  const workshop = workshopOf(booking.workshopId)
  const result: { workshopId: string; name: string; date: string; timeSlot: string; remaining: number }[] = []
  const today = todayVn()
  for (let offset = 0; offset < HORIZON_DAYS && result.length < 3; offset += 1) {
    const day = addDays(date, offset)
    if (day < today || day > addDays(today, HORIZON_DAYS - 1)) continue
    const slots = slotsOf(day, booking.bookingId)
      .filter(slot => slot.available && !(day === booking.bookingDate && slot.timeSlot.startsWith(booking.timeSlot)))
      .filter(slot => !(day === date && slot.timeSlot.startsWith(timeSlot)))
    // Same day: closest slots to the requested time first (FF AF-1203).
    slots.sort((a, b) => Math.abs(minutes(a.timeSlot) - minutes(timeSlot)) - Math.abs(minutes(b.timeSlot) - minutes(timeSlot)))
    for (const slot of slots) {
      if (result.length >= 3) break
      result.push({ workshopId: workshop.workshopId, name: workshop.name, date: day, timeSlot: slot.timeSlot, remaining: slot.remaining })
    }
  }
  return result
}

function minutes(timeSlot: string): number {
  const [h, m] = timeSlot.split(':').map(Number)
  return h * 60 + m
}

function rescheduleBlock(booking: MockBooking): string | null {
  if (booking.status !== 'confirmed') return 'NOT_CONFIRMED'
  const appt = new Date(apptOf(booking)).getTime()
  if (Date.now() >= appt - RESCHEDULE_MIN_LEAD_MINUTES * 60_000) return 'TOO_CLOSE_TO_APPOINTMENT'
  if (booking.rescheduleCount >= RESCHEDULE_MAX_COUNT) return 'MAX_RESCHEDULES_REACHED'
  return null
}

// ---------------------------------------------------------------- routes

export function registerBookingRoutes() {
  route(GROUP, 'GET', '/bookings', req => {
    const scope = (req.query.get('scope') ?? 'UPCOMING').toUpperCase()
    const limit = Math.min(Math.max(Number(req.query.get('limit') ?? 20) || 20, 1), 50)
    const offset = Number(req.query.get('cursor') ?? 0) || 0
    const today = todayVn()
    let list = getDb().bookings.filter(booking => booking.ownerSelf)
    if (scope === 'PAST') {
      list = list
        .filter(booking => (booking.status === 'completed' || booking.status === 'cancelled') && booking.bookingDate >= addDays(today, -PAST_DAYS))
        .sort((a, b) => apptOf(b).localeCompare(apptOf(a)))
    } else {
      list = list.filter(booking => OPEN_STATES.includes(booking.status)).sort((a, b) => apptOf(a).localeCompare(apptOf(b)))
    }
    const page = list.slice(offset, offset + limit)
    return ok({ items: page.map(listItem), nextCursor: offset + limit < list.length ? String(offset + limit) : null })
  })

  route(GROUP, 'GET', '/bookings/by-code/:code', req => {
    const code = req.params.code.toUpperCase()
    if (!/^EVC-[0-9A-F]{8}$/.test(code) && !/^[A-Z0-9-]{4,20}$/.test(code)) return notFound()
    const booking = getDb().bookings.find(item => item.ownerSelf && visibleCode(item) === code)
    return booking ? ok({ bookingId: booking.bookingId }) : notFound()
  })

  route(GROUP, 'GET', '/bookings/:id', req => {
    const booking = ownBooking(req.params.id)
    return booking ? ok(ticketView(booking)) : notFound()
  })

  route(GROUP, 'GET', '/bookings/:id/progress', req => {
    const booking = ownBooking(req.params.id)
    return booking ? ok(progressView(booking, false)) : notFound()
  })

  route(GROUP, 'GET', '/bookings/:id/qr', async req => {
    const booking = ownBooking(req.params.id)
    if (!booking) return notFound()
    const code = visibleCode(booking)
    if (booking.status !== 'confirmed' || !code) return fail(409, 'QR_NOT_AVAILABLE', 'Mã QR chỉ có khi lịch hẹn đã được xác nhận.')
    const dataUrl = await QRCode.toDataURL(`${appBaseUrl()}/c/${code}`, { errorCorrectionLevel: 'M', width: 512, margin: 2 })
    const blob = await (await fetch(dataUrl)).blob()
    return { status: 200, raw: blob, contentType: 'image/png', headers: { 'Cache-Control': 'private, max-age=3600' } }
  })

  route(GROUP, 'POST', '/bookings/:id/attendance-confirmation', req => {
    const booking = ownBooking(req.params.id)
    if (!booking) return notFound()
    if (booking.attendanceConfirmedAt && booking.status === 'confirmed') {
      return ok({ bookingId: booking.bookingId, status: 'CONFIRMED', attendanceConfirmedAt: booking.attendanceConfirmedAt })
    }
    if (booking.status !== 'confirmed') {
      return fail(409, 'BOOKING_NOT_CONFIRMED', 'Lịch hẹn không ở trạng thái đã xác nhận.', { currentStatus: upper(booking.status) })
    }
    if (Date.now() >= new Date(apptOf(booking)).getTime()) return fail(409, 'APPOINTMENT_STARTED', 'Đã tới giờ hẹn.')
    booking.attendanceConfirmedAt = nowIso()
    save()
    return ok({ bookingId: booking.bookingId, status: 'CONFIRMED', attendanceConfirmedAt: booking.attendanceConfirmedAt })
  })

  route(GROUP, 'POST', '/bookings/:id/cancel', req => {
    const stored = replay(req)
    if (stored) return stored
    const booking = ownBooking(req.params.id)
    if (!booking) return notFound()
    const body = bodyOf<{ source: string; reason: string }>(req)
    const source = body.source ?? 'APP'
    const reason = typeof body.reason === 'string' ? body.reason.trim() : ''
    if (!['APP', 'REMINDER_24H'].includes(source) || reason.length > 255) {
      return fail(400, 'INVALID_REQUEST', 'Lý do tối đa 255 ký tự.', { field: 'reason' })
    }
    const last = [...booking.events].reverse().find(event => event.toStatus === 'CANCELLED')
    if (booking.status === 'cancelled' && last?.actorType === 'VEHICLE_OWNER') {
      return ok({ bookingId: booking.bookingId, status: 'CANCELLED', cancelledAt: last.at, cancelledBy: 'VEHICLE_OWNER', source: last.source })
    }
    if (booking.status !== 'confirmed') {
      return fail(409, 'BOOKING_NOT_CONFIRMED', 'Lịch hẹn không còn ở trạng thái đã xác nhận.', { currentStatus: upper(booking.status) })
    }
    if (Date.now() >= new Date(apptOf(booking)).getTime()) {
      return fail(409, 'APPOINTMENT_STARTED', 'Đã tới giờ hẹn, không thể huỷ. Vui lòng liên hệ xưởng.')
    }
    pushEvent(booking, 'cancelled', 'VEHICLE_OWNER', source, null, reason || null)
    save()
    const at = booking.events[booking.events.length - 1].at
    return remember(req, ok({ bookingId: booking.bookingId, status: 'CANCELLED', cancelledAt: at, cancelledBy: 'VEHICLE_OWNER', source }))
  })

  // us-029 API-BK-04 for bookings that only exist in the mock (seeded); real holds pass through.
  route(GROUP, 'DELETE', '/bookings/:id/hold', req => {
    const booking = getDb().bookings.find(item => item.bookingId === req.params.id)
    if (!booking || booking.real) return undefined
    if (booking.status !== 'pending' || !booking.ownerCancelableUntil || Date.now() > new Date(booking.ownerCancelableUntil).getTime()) {
      return fail(409, 'HOLD_WINDOW_CLOSED', 'Đã quá thời gian tự huỷ giữ chỗ.')
    }
    pushEvent(booking, 'cancelled', 'VEHICLE_OWNER', 'APP', 'HOLD_CANCELLED')
    save()
    return ok({ bookingId: booking.bookingId, status: 'cancelled' })
  })

  // API-BK-02 with `rescheduleBookingId` (us-053 §7); without it the real backend answers.
  route(GROUP, 'GET', '/workshops/:workshopId/availability', req => {
    const bookingId = req.query.get('rescheduleBookingId')
    if (!bookingId) return undefined
    const booking = ownBooking(bookingId)
    if (!booking) return notFound()
    const blocked = rescheduleBlock(booking)
    if (blocked) return fail(409, 'RESCHEDULE_NOT_ALLOWED', 'Lịch hẹn này không đổi được nữa.', { reason: blocked })
    if (req.params.workshopId !== booking.workshopId) {
      return fail(422, 'RESCHEDULE_WORKSHOP_MISMATCH', 'Chỉ đổi lịch trong cùng xưởng.')
    }
    const date = req.query.get('date') ?? todayVn()
    const today = todayVn()
    if (date < today || date > addDays(today, HORIZON_DAYS - 1)) {
      return fail(400, 'INVALID_REQUEST', 'Ngày nằm ngoài khoảng đặt lịch.', { field: 'date' })
    }
    const timeSlot = req.query.get('timeSlot')?.slice(0, 5) ?? null
    const slots = slotsOf(date, booking.bookingId)
    let requested = null
    let alternatives: ReturnType<typeof alternativesFor> = []
    if (timeSlot) {
      if (date === booking.bookingDate && timeSlot === booking.timeSlot) {
        return fail(422, 'RESCHEDULE_SAME_SLOT', 'Đây là giờ hẹn hiện tại của bạn.')
      }
      if (isClosedDay(date) || !SLOT_TIMES.includes(timeSlot)) {
        return fail(422, 'SLOT_OUT_OF_HOURS', 'Khung giờ nằm ngoài giờ hoạt động của xưởng.')
      }
      const remaining = remainingOf(date, timeSlot, booking.bookingId)
      let token: string | null = null
      if (remaining > 0) {
        token = `cft_r_${uuid().replace(/-/g, '')}`
        getDb().tokens.push({
          token,
          bookingId: booking.bookingId,
          date,
          timeSlot,
          from: { date: booking.bookingDate, timeSlot: booking.timeSlot },
          expiresAt: Date.now() + TOKEN_TTL_SECONDS * 1000,
          used: false,
        })
        save()
      } else if (req.query.get('withAlternatives') !== 'false') {
        alternatives = alternativesFor(booking, date, timeSlot)
      }
      requested = { timeSlot: `${timeSlot}:00`, available: remaining > 0, remaining, confirmationToken: token }
    }
    return ok({ workshopId: booking.workshopId, date, requested, slots, alternatives })
  })

  route(GROUP, 'POST', '/bookings/:id/reschedule', req => {
    const stored = replay(req)
    if (stored) return stored
    const booking = ownBooking(req.params.id)
    if (!booking) return notFound()
    const { confirmationToken, source = 'APP' } = bodyOf<{ confirmationToken: string; source: string }>(req)
    const token = getDb().tokens.find(item => item.token === confirmationToken)
    if (!token || token.used || token.bookingId !== booking.bookingId) {
      return fail(409, 'INVALID_CONFIRMATION_TOKEN', 'Thẻ đổi lịch không hợp lệ.')
    }
    if (Date.now() > token.expiresAt) return fail(409, 'CONFIRMATION_TOKEN_EXPIRED', 'Thẻ đổi lịch đã hết hạn.')
    if (booking.status !== 'confirmed') {
      return fail(409, 'BOOKING_NOT_CONFIRMED', 'Lịch hẹn không còn ở trạng thái đã xác nhận.', { currentStatus: upper(booking.status) })
    }
    const blocked = rescheduleBlock(booking)
    if (blocked === 'TOO_CLOSE_TO_APPOINTMENT') return fail(409, 'RESCHEDULE_TOO_LATE', 'Đã quá hạn đổi lịch.')
    if (blocked === 'MAX_RESCHEDULES_REACHED') return fail(409, 'RESCHEDULE_LIMIT_REACHED', 'Đã đổi lịch tối đa số lần.')
    if (token.from.date !== booking.bookingDate || token.from.timeSlot !== booking.timeSlot) {
      return fail(409, 'BOOKING_CHANGED', 'Lịch hẹn vừa được đổi từ nơi khác.')
    }
    if (remainingOf(token.date, token.timeSlot, booking.bookingId) <= 0) {
      return fail(409, 'SLOT_FULL', 'Khung giờ vừa hết chỗ.', { alternatives: alternativesFor(booking, token.date, token.timeSlot) })
    }
    booking.reschedules.push({
      from: { date: booking.bookingDate, timeSlot: booking.timeSlot },
      to: { date: token.date, timeSlot: token.timeSlot },
      source,
      at: nowIso(),
    })
    booking.bookingDate = token.date
    booking.timeSlot = token.timeSlot
    booking.rescheduleCount += 1
    booking.attendanceConfirmedAt = null
    token.used = true
    save()
    return remember(req, ok(ticketView(booking)))
  })
}

/** Mock-only pending hold of the owner (seed) — owner-cancel window like us-029 BR-010. */
export function newHoldWindow() {
  return { holdExpiresAt: hoursFromNow(CONFIRM_DEADLINE_HOURS), ownerCancelableUntil: hoursFromNow(10 / 60) }
}

/** Stable pseudo phone for seeded customers. */
export function demoPhone(seed: string): string {
  return `09${Math.floor(10_000_000 + hash01(seed) * 89_999_999)}`
}
