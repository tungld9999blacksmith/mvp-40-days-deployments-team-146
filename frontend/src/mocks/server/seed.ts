/**
 * Demo data created on the first mock request. Uses the owner's real vehicle and a real
 * nearby workshop when they are already known (learned from real responses). Demo mode seeds its
 * own workshops instead and leaves the owner empty until the onboarding links a vehicle.
 */
import { upcomingSlotsToday } from './board'
import { CONFIRM_DEADLINE_HOURS, demoPhone, SLOT_TIMES } from './bookings'
import { scheduleFollowUp } from './crm'
import { activeWorkshopAccount } from './workshopAccount'
import {
  addDays,
  bookingCode,
  getDb,
  isDemo,
  nowIso,
  save,
  todayVn,
  uuid,
  type BookingState,
  type MockBooking,
  type MockVehicle,
  type MockWorkshop,
  type Stage,
} from './db'

const DEMO_WORKSHOP: MockWorkshop = {
  workshopId: '5b0e2f6a-0d1c-4e7a-9a51-00000000d001',
  name: 'VinFast Smart City',
  address: 'Đại lộ Thăng Long, Nam Từ Liêm, Hà Nội',
  phone: '024 3999 8888',
  region: 'Hà Nội',
  active: true,
  isPreferred: false,
  demo: true,
}

/** Demo mode: the first one is the workshop of the demo Workshop Portal account. */
const DEMO_WORKSHOPS: MockWorkshop[] = [
  { ...DEMO_WORKSHOP, demo: false, lat: 21.0006, lng: 105.753 },
  { workshopId: '5b0e2f6a-0d1c-4e7a-9a51-00000000d002', name: 'VinFast Thanh Xuân', address: '235 Nguyễn Trãi, Thanh Xuân, Hà Nội', phone: '024 3555 6677', region: 'Hà Nội', active: true, isPreferred: false, lat: 20.9935, lng: 105.8077 },
  { workshopId: '5b0e2f6a-0d1c-4e7a-9a51-00000000d003', name: 'VinFast Cầu Giấy', address: '89 Trần Duy Hưng, Cầu Giấy, Hà Nội', phone: '024 3777 1122', region: 'Hà Nội', active: true, isPreferred: false, lat: 21.012, lng: 105.799 },
  { workshopId: '5b0e2f6a-0d1c-4e7a-9a51-00000000d004', name: 'VinFast Long Biên', address: '7 Nguyễn Văn Linh, Long Biên, Hà Nội', phone: '024 3888 2233', region: 'Hà Nội', active: true, isPreferred: false, lat: 21.045, lng: 105.892 },
  { workshopId: '5b0e2f6a-0d1c-4e7a-9a51-00000000d005', name: 'VinFast Thảo Điền', address: '12 Quốc Hương, Thủ Đức, TP. Hồ Chí Minh', phone: '028 3666 4455', region: 'TP. Hồ Chí Minh', active: true, isPreferred: false, lat: 10.803, lng: 106.735 },
  { workshopId: '5b0e2f6a-0d1c-4e7a-9a51-00000000d006', name: 'VinFast Quận 7', address: '1058 Nguyễn Văn Linh, Quận 7, TP. Hồ Chí Minh', phone: '028 3777 5566', region: 'TP. Hồ Chí Minh', active: true, isPreferred: false, lat: 10.729, lng: 106.709 },
  { workshopId: '5b0e2f6a-0d1c-4e7a-9a51-00000000d007', name: 'VinFast Đà Nẵng', address: '255 Nguyễn Văn Linh, Thanh Khê, Đà Nẵng', phone: '0236 3888 999', region: 'Đà Nẵng', active: true, isPreferred: false, lat: 16.059, lng: 108.208 },
]

const CUSTOMERS = [
  { fullName: 'Nguyễn Văn An', modelName: 'VinFast VF 8', licensePlate: '30G-456.78' },
  { fullName: 'Trần Thị Bình', modelName: 'VinFast VF e34', licensePlate: '51H-123.45' },
  { fullName: 'Lê Hoàng Cường', modelName: 'VinFast VF 6', licensePlate: '29A-888.66' },
  { fullName: 'Phạm Minh Đức', modelName: 'VinFast VF 5 Plus', licensePlate: '30K-246.80' },
  { fullName: 'Võ Thu Hà', modelName: 'VinFast VF 7', licensePlate: '43A-135.79' },
  { fullName: 'Đặng Quốc Huy', modelName: 'VinFast VF 9', licensePlate: '51K-999.01' },
  { fullName: 'Bùi Thanh Lan', modelName: 'VinFast VF 3', licensePlate: '30L-020.24' },
]

function hoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 3_600_000).toISOString()
}

function at(date: string, slot: string, minutesAfter = 0): string {
  return new Date(new Date(`${date}T${slot}:00+07:00`).getTime() + minutesAfter * 60_000).toISOString()
}

const STAGES: Stage[] = ['CHECKED_IN', 'INSPECTING', 'SERVICING', 'QUALITY_CHECK', 'READY_FOR_PICKUP']

function makeBooking(options: {
  workshopId: string
  status: BookingState
  date: string
  slot: string
  customer: { fullName: string; phone: string }
  vehicle: { modelName: string; licensePlate: string }
  userVehicleId?: string | null
  ownerSelf?: boolean
  odoMilestone?: number | null
  createdHoursAgo?: number
  mode?: 'AUTO' | 'MANUAL'
  attendance?: boolean
  stages?: Stage[]
  cancel?: { actor: 'VEHICLE_OWNER' | 'WORKSHOP_OWNER' | 'SYSTEM'; source: string; reason: string | null; note?: string }
  actualCost?: number | null
  note?: string | null
}): MockBooking {
  const createdAt = hoursAgo(options.createdHoursAgo ?? 48)
  const mode = options.mode ?? 'MANUAL'
  const events: MockBooking['events'] = [
    { fromStatus: null, toStatus: 'PENDING', actorType: 'VEHICLE_OWNER', source: 'APP', reasonCode: null, note: null, at: createdAt },
  ]
  const reached = (state: BookingState) => {
    const order: BookingState[] = ['pending', 'confirmed', 'checked_in', 'in_progress', 'completed']
    return order.indexOf(options.status) >= order.indexOf(state)
  }
  const confirmedAt = new Date(new Date(createdAt).getTime() + 40 * 60_000).toISOString()
  if (reached('confirmed') || (options.status === 'cancelled' && options.cancel?.actor !== 'SYSTEM' && options.cancel?.reason !== 'FULLY_BOOKED')) {
    events.push({
      fromStatus: 'PENDING',
      toStatus: 'CONFIRMED',
      actorType: mode === 'AUTO' ? 'SYSTEM' : 'WORKSHOP_OWNER',
      source: mode === 'AUTO' ? 'AUTO_CONFIRM' : 'BOARD',
      reasonCode: null,
      note: null,
      at: confirmedAt,
    })
  }
  const progress: MockBooking['progress'] = []
  if (reached('checked_in')) {
    events.push({ fromStatus: 'CONFIRMED', toStatus: 'CHECKED_IN', actorType: 'WORKSHOP_OWNER', source: 'QR_SCAN', reasonCode: null, note: null, at: at(options.date, options.slot, -5) })
  }
  if (reached('in_progress')) {
    events.push({ fromStatus: 'CHECKED_IN', toStatus: 'IN_PROGRESS', actorType: 'WORKSHOP_OWNER', source: 'BOARD', reasonCode: null, note: null, at: at(options.date, options.slot, 5) })
  }
  ;(options.stages ?? []).forEach((stage, index) => {
    progress.push({
      stage,
      note: stage === 'WAITING_PARTS' ? 'Chờ má phanh trước, dự kiến có lúc 14:00' : null,
      actorType: index < 2 ? 'SYSTEM' : 'WORKSHOP_OWNER',
      actorName: index < 2 ? null : 'Chủ xưởng',
      createdAt: at(options.date, options.slot, index * 25 - 5),
    })
  })
  if (options.status === 'completed') {
    events.push({ fromStatus: 'IN_PROGRESS', toStatus: 'COMPLETED', actorType: 'WORKSHOP_OWNER', source: 'BOARD', reasonCode: null, note: null, at: at(options.date, options.slot, 150) })
  }
  if (options.status === 'cancelled' && options.cancel) {
    const from = events[events.length - 1].toStatus
    events.push({
      fromStatus: from,
      toStatus: 'CANCELLED',
      actorType: options.cancel.actor,
      source: options.cancel.source,
      reasonCode: options.cancel.reason,
      note: options.cancel.note ?? null,
      at: hoursAgo(Math.max((options.createdHoursAgo ?? 48) - 6, 1)),
    })
  }
  return {
    bookingId: uuid(),
    bookingCode: bookingCode(),
    status: options.status,
    workshopId: options.workshopId,
    userVehicleId: options.userVehicleId ?? null,
    vehicle: options.vehicle,
    customer: options.customer,
    ownerSelf: options.ownerSelf ?? false,
    real: false,
    bookingDate: options.date,
    timeSlot: options.slot,
    createdAt,
    holdExpiresAt: options.status === 'pending' ? new Date(new Date(createdAt).getTime() + CONFIRM_DEADLINE_HOURS * 3_600_000).toISOString() : null,
    ownerCancelableUntil: new Date(new Date(createdAt).getTime() + 10 * 60_000).toISOString(),
    confirmationMode: mode,
    odoMilestone: options.odoMilestone === undefined ? 12_000 : options.odoMilestone,
    estimatedCost: null,
    actualCost: options.actualCost ?? null,
    note: options.note ?? null,
    attendanceConfirmedAt: options.attendance ? hoursAgo(3) : null,
    rescheduleCount: 0,
    checkedInAt: reached('checked_in') ? at(options.date, options.slot, -5) : null,
    events,
    reschedules: [],
    progress,
  }
}

export function ensureSeeded() {
  const db = getDb()
  if (db.seededAt) return
  if (isDemo()) {
    seedDemo()
    return
  }
  if (!db.workshops.some(item => item.workshopId === DEMO_WORKSHOP.workshopId)) db.workshops.push({ ...DEMO_WORKSHOP })
  const real = db.workshops.filter(item => !item.demo && item.active)
  const workshop = real.find(item => item.isPreferred) ?? real[0] ?? DEMO_WORKSHOP
  const today = todayVn()
  const ownerVehicle: MockVehicle =
    db.vehicles[0] ?? {
      userVehicleId: 'demo-owner-vehicle',
      modelId: 'VF5',
      modelName: 'VinFast VF 5 Plus',
      licensePlate: '30A-123.45',
      nextOdoMilestone: 12_000,
      nextItems: [],
      warrantyStatus: 'ACTIVE',
    }
  const owner = { fullName: db.owner.fullName, phone: db.owner.phone }
  const mine = { customer: owner, vehicle: { modelName: ownerVehicle.modelName, licensePlate: ownerVehicle.licensePlate }, userVehicleId: ownerVehicle.userVehicleId, ownerSelf: true }
  const milestone = ownerVehicle.nextOdoMilestone ?? 12_000

  // ---------------------------------------------------------- owner: bookings
  const upcomingSlot = SLOT_TIMES[1]
  // Workshops close on Sundays in the mock: keep demo appointments on open days.
  const openDay = (offset: number) => {
    const day = addDays(today, offset)
    return new Date(`${day}T12:00:00+07:00`).getUTCDay() === 0 ? addDays(day, 1) : day
  }
  const upcoming = makeBooking({ ...mine, workshopId: workshop.workshopId, status: 'confirmed', date: openDay(3), slot: upcomingSlot, odoMilestone: milestone, createdHoursAgo: 50 })

  const done = makeBooking({
    ...mine,
    workshopId: workshop.workshopId,
    status: 'completed',
    date: addDays(today, -2),
    slot: '10:00',
    odoMilestone: Math.max(milestone - 12_000, 12_000),
    createdHoursAgo: 120,
    stages: STAGES,
    actualCost: 1_250_000,
  })
  const cancelled = makeBooking({
    ...mine,
    workshopId: workshop.workshopId,
    status: 'cancelled',
    date: addDays(today, -20),
    slot: '14:00',
    createdHoursAgo: 520,
    cancel: { actor: 'WORKSHOP_OWNER', source: 'BOARD', reason: 'WORKSHOP_UNAVAILABLE' },
  })

  db.bookings.push(upcoming, done, cancelled)
  ownFollowUp(done)
  seedBoard(workshop)
  db.seededAt = nowIso()
  save()
}

/** Survey of the owner's completed booking, already sent (answerable now). */
function ownFollowUp(done: MockBooking) {
  const followUp = scheduleFollowUp(done, 0)
  followUp.scheduledAt = hoursAgo(20)
}

/** Other customers of the workshop: today's Board, requests to confirm, answered surveys. */
function seedBoard(workshop: MockWorkshop) {
  const db = getDb()
  const today = todayVn()
  const openDay = (offset: number) => {
    const day = addDays(today, offset)
    return new Date(`${day}T12:00:00+07:00`).getUTCDay() === 0 ? addDays(day, 1) : day
  }
  const person = (index: number) => {
    const customer = CUSTOMERS[index % CUSTOMERS.length]
    return { customer: { fullName: customer.fullName, phone: demoPhone(customer.fullName) }, vehicle: { modelName: customer.modelName, licensePlate: customer.licensePlate } }
  }
  const later = upcomingSlotsToday()
  const board: MockBooking[] = [
    makeBooking({ ...person(0), workshopId: workshop.workshopId, status: 'in_progress', date: today, slot: '08:00', createdHoursAgo: 30, stages: ['CHECKED_IN', 'INSPECTING', 'SERVICING', 'WAITING_PARTS'], attendance: true }),
    makeBooking({ ...person(1), workshopId: workshop.workshopId, status: 'checked_in', date: today, slot: '08:00', createdHoursAgo: 26, stages: ['CHECKED_IN'] }),
    makeBooking({ ...person(2), workshopId: workshop.workshopId, status: 'completed', date: today, slot: '08:00', createdHoursAgo: 72, stages: STAGES, actualCost: 980_000 }),
    makeBooking({ ...person(3), workshopId: workshop.workshopId, status: 'confirmed', date: today, slot: later[0] ?? '16:00', createdHoursAgo: 40, attendance: true }),
    // A request still waiting for the workshop: today when a slot is left, otherwise tomorrow.
    makeBooking({ ...person(4), workshopId: workshop.workshopId, status: 'pending', date: later.length > 1 ? today : openDay(1), slot: later.length > 1 ? later[1] : '10:00', createdHoursAgo: 1, mode: 'MANUAL' }),
    makeBooking({ ...person(5), workshopId: workshop.workshopId, status: 'cancelled', date: today, slot: '11:00', createdHoursAgo: 30, cancel: { actor: 'VEHICLE_OWNER', source: 'REMINDER_24H', reason: null, note: 'Bận việc đột xuất' } }),
    makeBooking({ ...person(6), workshopId: workshop.workshopId, status: 'confirmed', date: openDay(1), slot: '09:00', createdHoursAgo: 20 }),
    makeBooking({ ...person(0), workshopId: workshop.workshopId, status: 'pending', date: openDay(2), slot: '13:00', createdHoursAgo: 3, mode: 'MANUAL' }),
  ]
  // Past completed bookings whose follow-ups were answered.
  const pastA = makeBooking({ ...person(3), workshopId: workshop.workshopId, status: 'completed', date: addDays(today, -1), slot: '09:00', createdHoursAgo: 60, stages: STAGES, actualCost: 1_420_000 })
  const pastB = makeBooking({ ...person(4), workshopId: workshop.workshopId, status: 'completed', date: addDays(today, -3), slot: '14:00', createdHoursAgo: 110, stages: STAGES, actualCost: 760_000 })
  const pastC = makeBooking({ ...person(5), workshopId: workshop.workshopId, status: 'completed', date: addDays(today, -6), slot: '10:00', createdHoursAgo: 180, stages: STAGES, actualCost: 1_150_000 })

  db.bookings.push(...board, pastA, pastB, pastC)

  for (const [booking, rating, comment, safety] of [
    [pastA, 2, 'Về nhà thấy phanh trước kêu khi dừng, hơi rung ở tốc độ thấp.', true],
    [pastB, 3, 'Chờ nhận xe hơi lâu so với hẹn, nhân viên vẫn nhiệt tình.', false],
    [pastC, 2, 'Đèn báo lỗi điều hoà vẫn còn sau khi bảo dưỡng.', false],
  ] as const) {
    const followUp = scheduleFollowUp(booking, 0)
    const respondedAt = hoursAgo(booking === pastA ? 2 : booking === pastB ? 30 : 100)
    followUp.status = 'closed'
    followUp.closedReason = 'PROCESSED'
    followUp.sentAt = hoursAgo(booking === pastA ? 4 : booking === pastB ? 40 : 120)
    followUp.response = { rating, comment, respondedAt }
    followUp.outcome = { hasIssue: true, safetyAdvice: safety }
  }
}

/** Demo mode: workshops, the activated Workshop Portal account and the Board; the owner starts empty. */
function seedDemo() {
  const db = getDb()
  db.workshops = DEMO_WORKSHOPS.map(workshop => ({ ...workshop }))
  db.workshopAccount = activeWorkshopAccount(db.workshops[0])
  seedBoard(db.workshops[0])
  db.seededAt = nowIso()
  save()
}

/**
 * Demo "returning owner": a repair visit two days ago whose survey is open, and a booking the
 * workshop cancelled. No open booking, so a new one can be made right away.
 */
export function seedOwnerHistory(vehicle: MockVehicle) {
  const db = getDb()
  const workshop = db.workshops[0] ?? DEMO_WORKSHOP
  const today = todayVn()
  const mine = {
    customer: { ...db.owner },
    vehicle: { modelName: vehicle.modelName, licensePlate: vehicle.licensePlate },
    userVehicleId: vehicle.userVehicleId,
    ownerSelf: true,
    workshopId: workshop.workshopId,
  }
  const done = makeBooking({
    ...mine,
    status: 'completed',
    date: addDays(today, -2),
    slot: '10:00',
    odoMilestone: null,
    note: 'Kiểm tra tiếng kêu ở gầm xe khi qua gờ giảm tốc',
    createdHoursAgo: 120,
    stages: STAGES,
    actualCost: 450_000,
  })
  const cancelled = makeBooking({
    ...mine,
    status: 'cancelled',
    date: addDays(today, -20),
    slot: '14:00',
    createdHoursAgo: 520,
    cancel: { actor: 'WORKSHOP_OWNER', source: 'BOARD', reason: 'WORKSHOP_UNAVAILABLE' },
  })
  db.bookings.push(done, cancelled)
  ownFollowUp(done)
}
