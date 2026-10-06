/**
 * Demo mode: us-029 API-BK-01 → 03 — nearby workshops, slot availability with a confirmation token,
 * and the booking itself (pending for a MANUAL workshop, confirmed at once for AUTO). Capacity uses
 * the same BR-005 formula as the Board, so a booking made here shows up there immediately.
 */
import { estimate } from './catalog'
import { bodyOf, fail, ok, rememberIdempotent, replayIdempotent, route, type MockRequest } from './core'
import {
  addDays,
  appointmentAt,
  bookingCode,
  distanceKm,
  fold,
  getDb,
  hoursFromNow,
  nowIso,
  save,
  todayVn,
  uuid,
  type MockBooking,
  type MockWorkshop,
} from './db'
import { CONFIRM_DEADLINE_HOURS, isClosedDay, remainingOf, SLOT_TIMES, visibleCode } from './bookings'

const GROUP = 'slots'
const TOKEN_TTL_MS = 600_000
const OWNER_CANCEL_WINDOW_MINUTES = 10
/** BK-02 accepts days this far ahead (wizard: 7, us-061 windows up to 60). */
const MAX_DAYS_AHEAD = 60
const NEARBY_LIMIT = 5
const OPEN_STATES = ['pending', 'confirmed', 'checked_in', 'in_progress']

function activeWorkshops(): MockWorkshop[] {
  return getDb().workshops.filter(workshop => workshop.active)
}

function workshopById(id: string): MockWorkshop | null {
  return activeWorkshops().find(workshop => workshop.workshopId === id) ?? null
}

function hms(slot: string): string {
  return `${slot.slice(0, 5)}:00`
}

function started(date: string, slot: string): boolean {
  return new Date(appointmentAt(date, slot)).getTime() <= Date.now()
}

/** Every slot of an open day; started or full slots are not available. */
export function daySlots(date: string) {
  if (isClosedDay(date)) return []
  return SLOT_TIMES.map(slot => {
    const remaining = started(date, slot) ? 0 : remainingOf(date, slot)
    return { timeSlot: hms(slot), available: remaining > 0, remaining }
  })
}

function issueToken(workshopId: string, date: string, slot: string): string {
  const token = `cft_${uuid().replace(/-/g, '')}`
  const db = getDb()
  db.holdTokens = db.holdTokens.filter(item => !item.used && item.expiresAt > Date.now())
  db.holdTokens.push({ token, workshopId, date, timeSlot: slot.slice(0, 5), expiresAt: Date.now() + TOKEN_TTL_MS, used: false })
  save()
  return token
}

/** BR-008 — same workshop same day (closest first), then the next days, then other workshops of the area. */
function alternatives(workshop: MockWorkshop, date: string, slot: string) {
  const result: { workshopId: string; name: string; date: string; timeSlot: string; remaining: number }[] = []
  const minutes = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5))
  const push = (target: MockWorkshop, day: string, time: string, remaining: number) => {
    if (result.length < 3) result.push({ workshopId: target.workshopId, name: target.name, date: day, timeSlot: time, remaining })
  }
  const sameDay = daySlots(date)
    .filter(item => item.available && item.timeSlot.slice(0, 5) !== slot)
    .sort((a, b) => Math.abs(minutes(a.timeSlot) - minutes(slot)) - Math.abs(minutes(b.timeSlot) - minutes(slot)))
  for (const item of sameDay.slice(0, 2)) push(workshop, date, item.timeSlot, item.remaining)
  for (let offset = 1; offset <= 7 && result.length < 2; offset += 1) {
    const day = addDays(date, offset)
    const free = daySlots(day).find(item => item.available)
    if (free) push(workshop, day, free.timeSlot, free.remaining)
  }
  for (const other of activeWorkshops()) {
    if (other.workshopId === workshop.workshopId || fold(other.region) !== fold(workshop.region)) continue
    if (!isClosedDay(date) && SLOT_TIMES.includes(slot) && !started(date, slot) && remainingOf(date, slot) > 0) {
      push(other, date, hms(slot), remainingOf(date, slot))
    }
  }
  return result
}

function operatingHoursToday() {
  const closed = isClosedDay(todayVn())
  return { isClosed: closed, openTime: closed ? null : '08:00:00', closeTime: closed ? null : '17:00:00' }
}

function number(value: string | null): number | null {
  if (value === null || value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** BR-002 → BR-004: coordinates rank by distance; text and the profile province rank by area. */
function rankNearby(req: MockRequest) {
  const lat = number(req.query.get('lat'))
  const lng = number(req.query.get('lng'))
  const text = (req.query.get('query') ?? req.query.get('province') ?? '').trim()
  const active = activeWorkshops()

  if (lat !== null && lng !== null) {
    const ranked = active
      .map(workshop => ({
        workshop,
        distance: workshop.lat !== undefined && workshop.lng !== undefined ? distanceKm({ lat, lng }, { lat: workshop.lat, lng: workshop.lng }) : null,
      }))
      .sort((a, b) => (a.distance ?? Number.POSITIVE_INFINITY) - (b.distance ?? Number.POSITIVE_INFINITY))
    return { anchor: { source: 'SPECIFIED', province: null, lat, lng, query: null, rankedBy: 'DISTANCE' }, ranked }
  }

  if (text) {
    const tokens = fold(text)
      .split(/[,;]/)
      .map(token => token.trim())
      .filter(Boolean)
    const scored = active
      .map(workshop => {
        const place = fold(`${workshop.name} ${workshop.address}`)
        const region = fold(workshop.region)
        const score = tokens.filter(token => place.includes(token)).length * 2 + (tokens.some(token => region.includes(token) || token.includes(region)) ? 1 : 0)
        return { workshop, distance: null, score }
      })
      .filter(item => item.score > 0)
      .sort((a, b) => b.score - a.score)
    const province = scored[0] && tokens.some(token => fold(scored[0].workshop.region).includes(token)) ? scored[0].workshop.region : null
    return { anchor: { source: 'SPECIFIED', province, lat: null, lng: null, query: text, rankedBy: 'REGION' }, ranked: scored }
  }

  const province = getDb().account.location?.province ?? null
  if (!province) return null
  const ranked = active.filter(workshop => fold(workshop.region) === fold(province)).map(workshop => ({ workshop, distance: null }))
  return { anchor: { source: 'PROFILE', province, lat: null, lng: null, query: null, rankedBy: 'REGION' }, ranked }
}

function bookingResponse(booking: MockBooking) {
  const workshop = getDb().workshops.find(item => item.workshopId === booking.workshopId)
  const confirmed = booking.status === 'confirmed'
  return {
    bookingId: booking.bookingId,
    status: booking.status,
    confirmationMode: booking.confirmationMode,
    workshopId: booking.workshopId,
    workshopName: workshop?.name ?? null,
    bookingDate: booking.bookingDate,
    timeSlot: hms(booking.timeSlot),
    holdExpiresAt: booking.holdExpiresAt,
    ownerCancelableUntil: booking.ownerCancelableUntil,
    bookingCode: visibleCode(booking),
    qrUrl: confirmed ? `/api/v1/bookings/${booking.bookingId}/qr` : null,
    estimatedCost: booking.estimatedCost,
    estimateLabel: 'Chi phí ước tính',
  }
}

export function registerSlotRoutes() {
  route(GROUP, 'GET', '/workshops/nearby', req => {
    const result = rankNearby(req)
    if (!result) return fail(422, 'LOCATION_ANCHOR_REQUIRED', 'Chưa xác định được vị trí để tìm xưởng.')
    const limit = Math.min(Math.max(Number(req.query.get('limit') ?? NEARBY_LIMIT) || NEARBY_LIMIT, 1), 10)
    const date = req.query.get('date')
    const slot = req.query.get('timeSlot')?.slice(0, 5) ?? null
    const ranked = [...result.ranked].sort((a, b) => Number(b.workshop.isPreferred) - Number(a.workshop.isPreferred)).slice(0, limit)
    return ok({
      anchor: result.anchor,
      workshops: ranked.map(({ workshop, distance }) => {
        let availability = null
        if (date && slot) {
          const open = !isClosedDay(date) && SLOT_TIMES.includes(slot) && !started(date, slot)
          const remaining = open ? remainingOf(date, slot) : 0
          availability = {
            date,
            timeSlot: hms(slot),
            available: remaining > 0,
            remaining,
            confirmationToken: remaining > 0 ? issueToken(workshop.workshopId, date, slot) : null,
          }
        }
        return {
          workshopId: workshop.workshopId,
          name: workshop.name,
          address: workshop.address,
          region: workshop.region,
          distanceKm: distance === null ? null : Math.round(distance * 100) / 100,
          isPreferred: workshop.isPreferred,
          operatingHoursToday: operatingHoursToday(),
          availability,
        }
      }),
    })
  })

  // Without `rescheduleBookingId` (the `bookings` group answers the reschedule variant).
  route(GROUP, 'GET', '/workshops/:workshopId/availability', req => {
    if (req.query.get('rescheduleBookingId')) return undefined
    const workshop = workshopById(req.params.workshopId)
    if (!workshop) return fail(404, 'WORKSHOP_NOT_FOUND', 'Xưởng hiện không nhận khách.')
    const today = todayVn()
    const date = req.query.get('date') ?? today
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < today || date > addDays(today, MAX_DAYS_AHEAD)) {
      return fail(400, 'INVALID_REQUEST', 'Ngày nằm ngoài khoảng đặt lịch.', { field: 'date' })
    }
    const slot = req.query.get('timeSlot')?.slice(0, 5) ?? null
    let requested = null
    let alternativesList: ReturnType<typeof alternatives> = []
    if (slot) {
      if (isClosedDay(date) || !SLOT_TIMES.includes(slot)) {
        return fail(422, 'SLOT_OUT_OF_HOURS', 'Khung giờ nằm ngoài giờ hoạt động của xưởng.')
      }
      const remaining = started(date, slot) ? 0 : remainingOf(date, slot)
      const token = remaining > 0 ? issueToken(workshop.workshopId, date, slot) : null
      if (!token && req.query.get('withAlternatives') !== 'false') alternativesList = alternatives(workshop, date, slot)
      requested = { timeSlot: hms(slot), available: remaining > 0, remaining, confirmationToken: token }
    }
    return ok({ workshopId: workshop.workshopId, date, requested, slots: daySlots(date), alternatives: alternativesList })
  })

  route(GROUP, 'POST', '/bookings', req => {
    const stored = replayIdempotent(req)
    if (stored) return stored
    const db = getDb()
    const body = bodyOf<{ confirmationToken: string; userVehicleId: string; milestoneRef: string; note: string }>(req)
    if (!body.confirmationToken || !body.userVehicleId) return fail(400, 'INVALID_REQUEST', 'Thiếu thông tin đặt lịch.')
    if ((body.note ?? '').length > 500) return fail(400, 'INVALID_REQUEST', 'Ghi chú tối đa 500 ký tự.', { field: 'note' })
    const token = db.holdTokens.find(item => item.token === body.confirmationToken)
    if (!token || token.used) return fail(409, 'INVALID_CONFIRMATION_TOKEN', 'Thẻ đặt lịch không hợp lệ.')
    if (Date.now() > token.expiresAt) return fail(409, 'HOLD_EXPIRED', 'Thẻ đặt lịch đã hết hạn.')
    const vehicle = db.vehicles.find(item => item.userVehicleId === body.userVehicleId && item.profile)
    if (!vehicle || db.account.status !== 'ACTIVE') return fail(403, 'FORBIDDEN', 'Xe không thuộc tài khoản.')
    const workshop = workshopById(token.workshopId)
    if (!workshop) return fail(404, 'WORKSHOP_NOT_FOUND', 'Xưởng hiện không nhận khách.')
    const open = db.bookings.find(item => item.userVehicleId === vehicle.userVehicleId && OPEN_STATES.includes(item.status))
    if (open) return fail(409, 'OPEN_BOOKING_EXISTS', 'Xe đã có lịch hẹn đang mở.', { bookingId: open.bookingId })
    if (started(token.date, token.timeSlot) || remainingOf(token.date, token.timeSlot) <= 0) {
      token.used = true
      save()
      return fail(409, 'SLOT_FULL', 'Khung giờ vừa hết chỗ.', { alternatives: alternatives(workshop, token.date, token.timeSlot) })
    }

    const milestone = body.milestoneRef && /^\d+$/.test(body.milestoneRef) ? Number(body.milestoneRef) : null
    const cost = milestone ? estimate(vehicle, milestone, workshop, 'REQUEST') : null
    const mode = db.confirmationMode
    const now = nowIso()
    const booking: MockBooking = {
      bookingId: uuid(),
      bookingCode: bookingCode(),
      status: mode === 'AUTO' ? 'confirmed' : 'pending',
      workshopId: workshop.workshopId,
      userVehicleId: vehicle.userVehicleId,
      vehicle: { modelName: vehicle.modelName, licensePlate: vehicle.licensePlate },
      customer: { ...db.owner },
      ownerSelf: true,
      real: false,
      live: true,
      bookingDate: token.date,
      timeSlot: token.timeSlot,
      createdAt: now,
      holdExpiresAt: mode === 'AUTO' ? null : hoursFromNow(CONFIRM_DEADLINE_HOURS),
      ownerCancelableUntil: hoursFromNow(OWNER_CANCEL_WINDOW_MINUTES / 60),
      confirmationMode: mode,
      odoMilestone: milestone,
      estimatedCost: cost?.chargeableTotal ?? null,
      actualCost: null,
      note: body.note?.trim() || null,
      attendanceConfirmedAt: null,
      rescheduleCount: 0,
      checkedInAt: null,
      events: [
        { fromStatus: null, toStatus: 'PENDING', actorType: 'VEHICLE_OWNER', source: 'APP', reasonCode: null, note: null, at: now },
        ...(mode === 'AUTO'
          ? [{ fromStatus: 'PENDING', toStatus: 'CONFIRMED', actorType: 'SYSTEM' as const, source: 'AUTO_CONFIRM', reasonCode: null, note: null, at: now }]
          : []),
      ],
      reschedules: [],
      progress: [],
    }
    token.used = true
    db.bookings.push(booking)
    return rememberIdempotent(req, ok(bookingResponse(booking), 201))
  })
}
