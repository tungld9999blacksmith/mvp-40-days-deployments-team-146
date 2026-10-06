/** us-037 API-WB-01 → 08 (Workshop Board) and us-057 API-PG-01/02 (progress, portal side). */
import { bodyOf, fail, ok, route } from './core'
import {
  addDays,
  appointmentAt,
  getDb,
  isDemo,
  nowIso,
  save,
  todayVn,
  uuid,
  type BookingState,
  type MockBooking,
  type Stage,
} from './db'
import {
  apptOf,
  blockOf,
  CAPACITY_BASE,
  confirmDeadlineOf,
  costOf,
  currentStageOf,
  EMERGENCY_SLOTS,
  isClosedDay,
  nextStagesOf,
  NO_SHOW_GRACE_MINUTES,
  occupiedCount,
  progressView,
  pushEvent,
  SLOT_TIMES,
  TOTAL_TECHNICIANS,
  upper,
  visibleCode,
} from './bookings'
import { scheduleFollowUp } from './crm'

const GROUP = 'board'
const HISTORY_DAYS = 30
const MAX_RANGE_DAYS = 7
const BLOCK_MAX_DAYS_AHEAD = 30
const STATUSES = ['PENDING', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED']
const REJECT_REASONS = ['FULLY_BOOKED', 'NOT_SUPPORTED_SERVICE', 'WORKSHOP_UNAVAILABLE', 'OTHER']
const CANCEL_REASONS = ['NO_SHOW', 'WORKSHOP_UNAVAILABLE', 'CUSTOMER_REQUEST', 'OTHER']
const BLOCK_REASONS = ['PHONE_BOOKING', 'WALK_IN', 'MAINTENANCE', 'OTHER']
const OWNER_NAME = 'Chủ xưởng'

/**
 * Check-in is only allowed on the appointment day (us-037). Demo mode lifts that rule so the whole
 * flow (book → confirm → check in → complete) can be shown in one sitting.
 */
function isCheckInDay(booking: MockBooking): boolean {
  return isDemo() || booking.bookingDate === todayVn()
}

function boardActions(booking: MockBooking): string[] {
  const now = Date.now()
  switch (booking.status) {
    case 'pending': {
      const deadline = confirmDeadlineOf(booking)
      const canAccept = (!deadline || now <= new Date(deadline).getTime()) && now < new Date(apptOf(booking)).getTime()
      return canAccept ? ['ACCEPT', 'REJECT'] : ['REJECT']
    }
    case 'confirmed':
      return isCheckInDay(booking) ? ['CHECK_IN', 'CANCEL'] : ['CANCEL']
    case 'checked_in':
      return ['START']
    case 'in_progress':
      return ['COMPLETE']
    default:
      return []
  }
}

function boardItem(booking: MockBooking) {
  return {
    bookingId: booking.bookingId,
    bookingCode: visibleCode(booking),
    status: upper(booking.status),
    bookingDate: booking.bookingDate,
    timeSlot: booking.timeSlot,
    customer: booking.customer,
    vehicle: booking.vehicle,
    milestoneLabel: booking.odoMilestone ? `Mốc ${new Intl.NumberFormat('vi-VN').format(booking.odoMilestone)} km` : null,
    estimatedCost: costOf(booking).amount,
    attendanceConfirmedAt: booking.attendanceConfirmedAt,
    confirmDeadline: confirmDeadlineOf(booking),
    allowedActions: boardActions(booking),
  }
}

function boardDetail(booking: MockBooking) {
  return {
    ...boardItem(booking),
    actualCost: booking.actualCost,
    note: booking.note,
    checkedInAt: booking.checkedInAt,
    currentStage: currentStageOf(booking),
    statusHistory: booking.events,
  }
}

function find(id: string): MockBooking | null {
  return getDb().bookings.find(booking => booking.bookingId === id) ?? null
}

const notFound = () => fail(404, 'BOOKING_NOT_FOUND', 'Không tìm thấy lịch hẹn.')

function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
}

const TRANSITIONS: Record<string, { from: BookingState; to: BookingState }> = {
  ACCEPT: { from: 'pending', to: 'confirmed' },
  REJECT: { from: 'pending', to: 'cancelled' },
  CHECK_IN: { from: 'confirmed', to: 'checked_in' },
  START: { from: 'checked_in', to: 'in_progress' },
  COMPLETE: { from: 'in_progress', to: 'completed' },
  CANCEL: { from: 'confirmed', to: 'cancelled' },
}

function addProgress(booking: MockBooking, stage: Stage, actorType: 'SYSTEM' | 'WORKSHOP_OWNER', note: string | null = null) {
  booking.progress.push({ stage, note, actorType, actorName: actorType === 'SYSTEM' ? null : OWNER_NAME, createdAt: nowIso() })
}

function capacitySlot(date: string, timeSlot: string) {
  const occupied = occupiedCount(date, timeSlot)
  const block = blockOf(date, timeSlot)
  const blocked = block?.blockedCount ?? 0
  return {
    timeSlot,
    occupied,
    blocked,
    remaining: Math.max(CAPACITY_BASE - blocked - occupied, 0),
    maxBlock: Math.max(CAPACITY_BASE - occupied, 0),
    blockReason: block?.reason ?? null,
    blockNote: block?.note ?? null,
  }
}

export function registerBoardRoutes() {
  route(GROUP, 'GET', '/workshop-owner/bookings', req => {
    const today = todayVn()
    const from = req.query.get('from') || today
    const to = req.query.get('to') || from
    const statuses = req.query.getAll('status').map(item => item.toUpperCase())
    const q = (req.query.get('q') ?? '').trim()
    if (from > to || to > addDays(from, MAX_RANGE_DAYS - 1) || from < addDays(today, -HISTORY_DAYS)) {
      return fail(400, 'INVALID_REQUEST', 'Khoảng ngày không hợp lệ.', { field: 'from' })
    }
    if (statuses.some(status => !STATUSES.includes(status))) return fail(400, 'INVALID_REQUEST', 'Trạng thái không hợp lệ.')
    if (q && (q.length < 2 || q.length > 20)) return fail(400, 'INVALID_REQUEST', 'Từ khoá 2–20 ký tự.', { field: 'q' })
    const inRange = getDb()
      .bookings.filter(booking => booking.bookingDate >= from && booking.bookingDate <= to)
      .sort((a, b) => a.bookingDate.localeCompare(b.bookingDate) || a.timeSlot.localeCompare(b.timeSlot) || a.createdAt.localeCompare(b.createdAt))
    const summary = Object.fromEntries(STATUSES.map(status => [status, 0])) as Record<string, number>
    for (const booking of inRange) summary[upper(booking.status)] += 1
    const needle = normalize(q)
    const items = inRange
      .filter(booking => statuses.length === 0 || statuses.includes(upper(booking.status)))
      .filter(
        booking =>
          !needle || normalize(visibleCode(booking) ?? '').includes(needle) || normalize(booking.vehicle.licensePlate).includes(needle),
      )
    return ok({ workshopId: items[0]?.workshopId ?? null, confirmationMode: getDb().confirmationMode, from, to, summary, items: items.map(boardItem) })
  })

  route(GROUP, 'GET', '/workshop-owner/bookings/by-code/:code', req => {
    const code = req.params.code.toUpperCase()
    if (!/^[A-Z0-9-]{4,20}$/.test(code)) return fail(400, 'INVALID_REQUEST', 'Mã lịch hẹn không hợp lệ.')
    const booking = getDb().bookings.find(item => item.bookingCode === code && item.status !== 'pending')
    if (!booking) return notFound()
    const eligibility =
      booking.status === 'confirmed'
        ? isCheckInDay(booking)
          ? 'ELIGIBLE'
          : 'NOT_TODAY'
        : ['checked_in', 'in_progress', 'completed'].includes(booking.status)
          ? 'ALREADY_CHECKED_IN'
          : 'NOT_CONFIRMED'
    return ok({ ...boardItem(booking), checkInEligibility: eligibility, checkedInAt: booking.checkedInAt })
  })

  route(GROUP, 'GET', '/workshop-owner/bookings/:id', req => {
    const booking = find(req.params.id)
    return booking ? ok(boardDetail(booking)) : notFound()
  })

  route(GROUP, 'POST', '/workshop-owner/bookings/:id/transitions', req => {
    const booking = find(req.params.id)
    if (!booking) return notFound()
    const body = bodyOf<{ action: string; expectedStatus: string; reasonCode: string; note: string; actualCost: number; source: string }>(req)
    const transition = body.action ? TRANSITIONS[body.action] : undefined
    if (!transition) return fail(400, 'INVALID_REQUEST', 'Hành động không hợp lệ.', { field: 'action' })
    const note = body.note?.trim() || null
    // Same action already applied by the workshop (e.g. QR scanned twice) ⇒ idempotent 200 (EDGE-805).
    const last = booking.events[booking.events.length - 1]
    if (booking.status === transition.to && last?.actorType === 'WORKSHOP_OWNER' && last.toStatus === upper(transition.to)) {
      return ok({ ...boardDetail(booking), effects: null })
    }
    if (booking.status !== transition.from || upper(body.expectedStatus ?? '') !== upper(transition.from)) {
      return fail(409, 'INVALID_STATUS_TRANSITION', 'Lịch hẹn vừa được cập nhật.', {
        currentStatus: upper(booking.status),
        allowedActions: boardActions(booking),
      })
    }
    const reasons = body.action === 'REJECT' ? REJECT_REASONS : body.action === 'CANCEL' ? CANCEL_REASONS : null
    if (reasons) {
      if (!body.reasonCode || !reasons.includes(body.reasonCode)) return fail(400, 'REASON_REQUIRED', 'Vui lòng chọn lý do.', { field: 'reasonCode' })
      if (body.reasonCode === 'OTHER' && !note) return fail(400, 'REASON_REQUIRED', 'Vui lòng ghi rõ lý do.', { field: 'note' })
      if (note && note.length > 255) return fail(400, 'INVALID_REQUEST', 'Ghi chú tối đa 255 ký tự.', { field: 'note' })
    }
    const now = Date.now()
    const appt = new Date(apptOf(booking)).getTime()
    if (body.action === 'ACCEPT') {
      const deadline = confirmDeadlineOf(booking)
      if ((deadline && now > new Date(deadline).getTime()) || now >= appt) {
        pushEvent(booking, 'cancelled', 'SYSTEM', 'CONFIRM_DEADLINE', 'CONFIRM_DEADLINE_PASSED')
        save()
        return fail(409, 'CONFIRM_DEADLINE_PASSED', 'Yêu cầu đã quá hạn xác nhận.')
      }
    }
    if (body.action === 'CHECK_IN' && !isCheckInDay(booking)) {
      return fail(409, 'CHECK_IN_NOT_TODAY', 'Lịch hẹn không phải hôm nay.', { bookingDate: booking.bookingDate })
    }
    if (body.action === 'CANCEL' && body.reasonCode === 'NO_SHOW' && now < appt + NO_SHOW_GRACE_MINUTES * 60_000) {
      return fail(409, 'NO_SHOW_TOO_EARLY', 'Chưa thể đánh dấu khách không đến.', {
        availableAt: new Date(appt + NO_SHOW_GRACE_MINUTES * 60_000).toISOString(),
      })
    }
    let actualCost: number | null = null
    if (body.action === 'COMPLETE' && body.actualCost !== undefined && body.actualCost !== null) {
      if (typeof body.actualCost !== 'number' || body.actualCost < 0 || body.actualCost > 999_999_999) {
        return fail(400, 'INVALID_REQUEST', 'Chi phí không hợp lệ.', { field: 'actualCost' })
      }
      actualCost = body.actualCost
    }

    const source = body.action === 'CHECK_IN' && body.source === 'QR_SCAN' ? 'QR_SCAN' : 'BOARD'
    pushEvent(booking, transition.to, 'WORKSHOP_OWNER', source, reasons ? body.reasonCode ?? null : null, reasons ? note : null)
    let effects: Record<string, unknown> | null = null
    if (body.action === 'ACCEPT') effects = { reminderScheduled: true }
    if (body.action === 'CHECK_IN') {
      booking.checkedInAt = nowIso()
      addProgress(booking, 'CHECKED_IN', 'SYSTEM')
    }
    if (body.action === 'START') addProgress(booking, 'INSPECTING', 'SYSTEM')
    if (body.action === 'COMPLETE') {
      booking.actualCost = actualCost
      const followUp = scheduleFollowUp(booking)
      effects = { serviceRecordId: uuid(), followUpId: followUp.followUpId, followUpScheduledAt: followUp.scheduledAt }
    }
    save()
    return ok({ ...boardDetail(booking), effects })
  })

  route(GROUP, 'GET', '/workshop-owner/bookings/:id/progress', req => {
    const booking = find(req.params.id)
    return booking ? ok(progressView(booking, true)) : notFound()
  })

  route(GROUP, 'POST', '/workshop-owner/bookings/:id/progress', req => {
    const booking = find(req.params.id)
    if (!booking) return notFound()
    const { stage, note, expectedCurrentStage } = bodyOf<{ stage: Stage; note: string; expectedCurrentStage: Stage }>(req)
    if (booking.status !== 'in_progress') return fail(409, 'BOOKING_NOT_IN_PROGRESS', 'Lịch hẹn không ở trạng thái đang làm.')
    const current = currentStageOf(booking)
    if (current !== expectedCurrentStage) {
      return fail(409, 'PROGRESS_CHANGED', 'Tiến độ vừa được cập nhật.', { currentStage: current })
    }
    const next = nextStagesOf(booking)
    if (!stage || !next.includes(stage)) return fail(422, 'INVALID_STAGE_TRANSITION', 'Mốc không hợp lệ.', { nextStages: next })
    const text = note?.trim() ?? ''
    if (stage === 'WAITING_PARTS' && (text.length < 10 || text.length > 500)) {
      return fail(422, 'NOTE_REQUIRED', 'Ghi chú chờ phụ tùng cần 10–500 ký tự.', { field: 'note' })
    }
    if (text.length > 500) return fail(400, 'INVALID_REQUEST', 'Ghi chú tối đa 500 ký tự.', { field: 'note' })
    addProgress(booking, stage, 'WORKSHOP_OWNER', text || null)
    save()
    return ok(progressView(booking, true), 201)
  })

  route(GROUP, 'GET', '/workshop-owner/capacity', req => {
    const from = req.query.get('from') || todayVn()
    const days = Math.min(Math.max(Number(req.query.get('days') ?? 7) || 7, 1), 7)
    if (from < todayVn()) return fail(400, 'INVALID_REQUEST', 'Ngày bắt đầu không hợp lệ.', { field: 'from' })
    return ok({
      totalTechnicians: TOTAL_TECHNICIANS,
      emergencySlotsReserved: EMERGENCY_SLOTS,
      days: Array.from({ length: days }, (_, index) => {
        const date = addDays(from, index)
        const closed = isClosedDay(date)
        return {
          date,
          isClosed: closed,
          openTime: closed ? null : '08:00',
          closeTime: closed ? null : '17:00',
          slots: closed ? [] : SLOT_TIMES.map(slot => capacitySlot(date, slot)),
        }
      }),
    })
  })

  route(GROUP, 'PUT', '/workshop-owner/slot-blocks', req => {
    const body = bodyOf<{ date: string; timeSlot: string; blockedCount: number; reason: string; note: string }>(req)
    const today = todayVn()
    const timeSlot = (body.timeSlot ?? '').slice(0, 5)
    if (!body.date || body.date < today || body.date > addDays(today, BLOCK_MAX_DAYS_AHEAD)) {
      return fail(422, 'BLOCK_DATE_OUT_OF_RANGE', 'Ngày khoá nằm ngoài phạm vi.')
    }
    if (isClosedDay(body.date) || !SLOT_TIMES.includes(timeSlot)) return fail(422, 'SLOT_OUT_OF_HOURS', 'Khung ngoài giờ hoạt động.')
    const count = body.blockedCount
    if (typeof count !== 'number' || !Number.isInteger(count) || count < 0) {
      return fail(400, 'INVALID_REQUEST', 'Số chỗ khoá không hợp lệ.', { field: 'blockedCount' })
    }
    const reason = body.reason ?? ''
    if (count > 0 && !BLOCK_REASONS.includes(reason)) return fail(400, 'INVALID_REQUEST', 'Vui lòng chọn lý do khoá.', { field: 'reason' })
    if (count > 0 && reason === 'OTHER' && !body.note?.trim()) {
      return fail(400, 'INVALID_REQUEST', 'Vui lòng ghi chú lý do khoá.', { field: 'note' })
    }
    const slot = capacitySlot(body.date, timeSlot)
    if (count > slot.maxBlock) {
      return fail(409, 'BLOCK_EXCEEDS_FREE_CAPACITY', `Chỉ còn ${slot.maxBlock} chỗ trống để khoá.`, { maxBlock: slot.maxBlock })
    }
    const db = getDb()
    db.slotBlocks = db.slotBlocks.filter(block => !(block.date === body.date && block.timeSlot === timeSlot))
    if (count > 0) db.slotBlocks.push({ date: body.date, timeSlot, blockedCount: count, reason, note: body.note?.trim() || null })
    save()
    const after = capacitySlot(body.date, timeSlot)
    return ok({ date: body.date, timeSlot, blocked: after.blocked, occupied: after.occupied, remaining: after.remaining, maxBlock: after.maxBlock })
  })

  route(GROUP, 'GET', '/workshop-owner/booking-settings', () => {
    const db = getDb()
    return ok({
      confirmationMode: db.confirmationMode,
      wsConfirmDeadlineHours: 12,
      pendingCount: db.bookings.filter(booking => booking.status === 'pending').length,
    })
  })

  route(GROUP, 'PUT', '/workshop-owner/booking-settings', req => {
    const mode = bodyOf<{ confirmationMode: string }>(req).confirmationMode
    if (mode !== 'AUTO' && mode !== 'MANUAL') return fail(400, 'INVALID_REQUEST', 'Chế độ không hợp lệ.', { field: 'confirmationMode' })
    const db = getDb()
    db.confirmationMode = mode
    save()
    return ok({
      confirmationMode: mode,
      wsConfirmDeadlineHours: 12,
      pendingCount: db.bookings.filter(booking => booking.status === 'pending').length,
    })
  })
}

/** Today's slots in `HH:mm` that have not started yet (used by seeds). */
export function upcomingSlotsToday(): string[] {
  const now = Date.now()
  return SLOT_TIMES.filter(slot => new Date(appointmentAt(todayVn(), slot)).getTime() > now)
}
