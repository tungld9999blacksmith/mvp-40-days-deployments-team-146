/**
 * Demo mode: the owner's vehicle (us-017 API-VEH-001/002/003/005). The vehicle is created when the
 * onboarding verification passes; its due status follows the ODO and the EV Care visits completed
 * on the Workshop Board, so completing a periodic booking moves the next milestone.
 */
import { hasRules, milestoneRuleItems } from './catalog'
import { fail, ok, route } from './core'
import {
  addDays,
  daysBetween,
  getDb,
  isDemo,
  todayVn,
  uuid,
  type MockBooking,
  type MockVehicle,
  type MockVehicleProfile,
} from './db'

const GROUP = 'vehicles'
const STEP_KM = 12_000
const MAX_MILESTONE_KM = 96_000
const DUE_SOON_KM = 1_000
const DUE_SOON_DAYS = 30
const OEM_SYNC_SOURCE = 'OEM_SYNC'

export const OWNER_VEHICLE_ID = 'demo-owner-vehicle'

export const VEHICLE_MODELS = [
  { modelId: 'VF3', modelName: 'VF 3', trim: null, batteryKwh: 18.64, motorKw: 32, color: 'Vàng chanh' },
  { modelId: 'VF5', modelName: 'VF 5', trim: 'Plus', batteryKwh: 37.23, motorKw: 100, color: 'Trắng' },
  { modelId: 'VF6', modelName: 'VF 6', trim: 'Plus', batteryKwh: 59.6, motorKw: 150, color: 'Xanh dương' },
  { modelId: 'VF7', modelName: 'VF 7', trim: 'Plus', batteryKwh: 75.3, motorKw: 260, color: 'Đỏ' },
  { modelId: 'VF8', modelName: 'VF 8', trim: 'Eco', batteryKwh: 87.7, motorKw: 260, color: 'Xám' },
  { modelId: 'VF9', modelName: 'VF 9', trim: 'Plus', batteryKwh: 123, motorKw: 300, color: 'Đen' },
  { modelId: 'VFE34', modelName: 'VF e34', trim: null, batteryKwh: 42, motorKw: 110, color: 'Trắng' },
] as const

export function modelById(modelId: string) {
  return VEHICLE_MODELS.find(model => model.modelId === modelId.toUpperCase()) ?? VEHICLE_MODELS[2]
}

/** `30A-123.45` → `30A12345` (the backend stores plates without separators). */
export function normalizePlate(plate: string): string {
  return plate.toUpperCase().replace(/[\s.-]/g, '')
}

const WARRANTY_TERMS = [
  { component: 'BATTERY', years: 8, kmLimit: 160_000 },
  { component: 'MOTOR', years: 8, kmLimit: 160_000 },
  { component: 'CHASSIS', years: 7, kmLimit: 160_000 },
  { component: 'ELECTRONICS', years: 3, kmLimit: 100_000 },
]

/**
 * Links a vehicle to the owner. `odoKm` and `firstDueDate` decide the opening due status; the
 * defaults give the "500 km / 12 days left" case of the us-061 spec.
 */
export function createOwnerVehicle(input: {
  vin: string
  licensePlate: string
  modelId: string
  productionYear: number | null
  odoKm?: number
  deliveredDaysAgo?: number
  firstDueInDays?: number
  oemRecords?: MockVehicleProfile['oemRecords']
}): MockVehicle {
  const db = getDb()
  const model = modelById(input.modelId)
  const today = todayVn()
  const deliveredAt = addDays(today, -(input.deliveredDaysAgo ?? 353))
  const productionYear = input.productionYear ?? Number(deliveredAt.slice(0, 4))
  const vehicle: MockVehicle = {
    userVehicleId: OWNER_VEHICLE_ID,
    modelId: model.modelId,
    modelName: `VinFast ${[model.modelName, model.trim].filter(Boolean).join(' ')}`,
    licensePlate: normalizePlate(input.licensePlate),
    nextOdoMilestone: null,
    nextItems: [],
    warrantyStatus: 'ACTIVE',
    profile: {
      vin: input.vin.toUpperCase(),
      modelName: model.modelName,
      trim: model.trim,
      color: model.color,
      productionYear,
      manufactureDate: `${productionYear}-03-15`,
      batteryCapacityKwh: model.batteryKwh,
      motorPowerKw: model.motorKw,
      odoKm: input.odoKm ?? 11_500,
      odoRecordedAt: new Date(Date.now() - 3 * 3_600_000).toISOString(),
      deliveredAt,
      firstDueDate: addDays(today, input.firstDueInDays ?? 12),
      oemRecords: input.oemRecords ?? [
        {
          recordId: uuid(),
          serviceDate: deliveredAt,
          odoKm: 8,
          isPeriodic: false,
          itemsDone: 'Kiểm tra trước giao xe (PDI)',
          centerName: 'VinFast Smart City',
        },
      ],
    },
  }
  db.vehicles = db.vehicles.filter(item => item.userVehicleId !== vehicle.userVehicleId)
  db.vehicles.push(vehicle)
  syncNextMilestone(vehicle)
  return vehicle
}

export function ownerVehicle(): MockVehicle | null {
  return getDb().vehicles.find(item => item.profile) ?? null
}

function completedAt(booking: MockBooking): string | null {
  return booking.events.find(event => event.toStatus === 'COMPLETED')?.at ?? null
}

function vnDay(iso: string): string {
  return todayVn(new Date(iso))
}

/** Latest periodic service: an EV Care visit with a milestone, else a manufacturer record. */
function lastPeriodic(vehicle: MockVehicle): { milestone: number; day: string; viaEvCare: boolean } | null {
  const visits = getDb()
    .bookings.filter(booking => booking.userVehicleId === vehicle.userVehicleId && booking.status === 'completed' && booking.odoMilestone)
    .map(booking => ({ milestone: booking.odoMilestone!, day: vnDay(completedAt(booking) ?? booking.createdAt), viaEvCare: true }))
  const oem = (vehicle.profile?.oemRecords ?? [])
    .filter(record => record.isPeriodic && record.odoKm !== null)
    .map(record => ({ milestone: Math.round(record.odoKm! / STEP_KM) * STEP_KM, day: record.serviceDate, viaEvCare: false }))
  return [...visits, ...oem].sort((a, b) => b.milestone - a.milestone)[0] ?? null
}

export interface DueState {
  dueStatus: 'NORMAL' | 'DUE_SOON' | 'OVERDUE' | 'UNKNOWN'
  dueReason: 'KM' | 'TIME' | 'BOTH' | null
  unknownReason: 'NO_MAINTENANCE_RULE' | null
  nextKm: number | null
  dueDate: string | null
  remainingKm: number | null
  remainingDays: number | null
}

export function dueOf(vehicle: MockVehicle): DueState {
  const profile = vehicle.profile
  if (!profile || !hasRules(vehicle)) {
    return { dueStatus: 'UNKNOWN', dueReason: null, unknownReason: 'NO_MAINTENANCE_RULE', nextKm: null, dueDate: null, remainingKm: null, remainingDays: null }
  }
  const last = lastPeriodic(vehicle)
  const nextKm = Math.min((last?.milestone ?? 0) + STEP_KM, MAX_MILESTONE_KM)
  // After an EV Care visit the next milestone is due a year later; before, the manufacturer schedule applies.
  const dueDate = last?.viaEvCare ? addDays(last.day, 365) : profile.firstDueDate
  const remainingKm = nextKm - profile.odoKm
  const remainingDays = daysBetween(todayVn(), dueDate)
  const kmHit = remainingKm <= DUE_SOON_KM
  const timeHit = remainingDays <= DUE_SOON_DAYS
  const overdue = remainingKm <= 0 || remainingDays < 0
  return {
    dueStatus: overdue ? 'OVERDUE' : kmHit || timeHit ? 'DUE_SOON' : 'NORMAL',
    dueReason: kmHit && timeHit ? 'BOTH' : kmHit ? 'KM' : timeHit ? 'TIME' : null,
    unknownReason: null,
    nextKm,
    dueDate,
    remainingKm,
    remainingDays,
  }
}

/** The estimate and booking mocks read `nextOdoMilestone`; keep it on the computed milestone. */
export function syncNextMilestone(vehicle: MockVehicle) {
  vehicle.nextOdoMilestone = dueOf(vehicle).nextKm
}

export function reconcileVehicles() {
  if (!isDemo()) return
  for (const vehicle of getDb().vehicles) if (vehicle.profile) syncNextMilestone(vehicle)
}

function warranties(vehicle: MockVehicle) {
  const profile = vehicle.profile!
  const today = todayVn()
  return WARRANTY_TERMS.map(term => {
    const endDate = addDays(profile.deliveredAt, term.years * 365)
    return {
      component: term.component,
      startDate: profile.deliveredAt,
      endDate,
      kmLimit: term.kmLimit,
      durationMonths: term.years * 12,
      isActive: endDate >= today && profile.odoKm < term.kmLimit,
    }
  })
}

/** Onboarding shape of the warranties (API-002 / API-005). */
export function onboardingWarranties(vehicle: MockVehicle) {
  return warranties(vehicle).map(item => ({
    component: item.component,
    startDate: item.startDate,
    endDate: item.endDate,
    kmLimit: item.kmLimit,
    durationMonths: item.durationMonths,
    status: item.isActive ? 'ACTIVE' : 'EXPIRED',
    termsDescription: `${item.durationMonths / 12} năm hoặc ${new Intl.NumberFormat('vi-VN').format(item.kmLimit)} km, tuỳ điều kiện nào đến trước`,
  }))
}

export function vehicleSpec(vehicle: MockVehicle) {
  const profile = vehicle.profile!
  return {
    modelId: vehicle.modelId,
    modelName: profile.modelName,
    trim: profile.trim,
    color: profile.color,
    manufactureDate: profile.manufactureDate,
    productionYear: profile.productionYear,
    batteryCapacityKwh: profile.batteryCapacityKwh,
    motorPowerKw: profile.motorPowerKw,
  }
}

function serviceRecords(vehicle: MockVehicle) {
  const db = getDb()
  const evCare = db.bookings
    .filter(booking => booking.userVehicleId === vehicle.userVehicleId && booking.ownerSelf && booking.status === 'completed')
    .map(booking => {
      const workshop = db.workshops.find(item => item.workshopId === booking.workshopId)
      return {
        recordId: `ev-${booking.bookingId}`,
        source: 'EV_CARE' as const,
        serviceDate: vnDay(completedAt(booking) ?? booking.createdAt),
        odoKm: booking.odoMilestone ? vehicle.profile!.odoKm : null,
        isPeriodic: booking.odoMilestone !== null,
        itemsDone: booking.odoMilestone ? `Bảo dưỡng định kỳ mốc ${new Intl.NumberFormat('vi-VN').format(booking.odoMilestone)} km` : booking.note,
        workshop: { workshopId: booking.workshopId, name: workshop?.name ?? 'Xưởng dịch vụ' },
        bookingId: booking.bookingId,
        bookingCode: booking.bookingCode,
        actualCost: booking.actualCost,
      }
    })
  const oem = vehicle.profile!.oemRecords.map(record => ({
    recordId: record.recordId,
    source: 'OEM' as const,
    serviceDate: record.serviceDate,
    odoKm: record.odoKm,
    isPeriodic: record.isPeriodic,
    itemsDone: record.itemsDone,
    workshop: { workshopId: null, name: record.centerName },
    bookingId: null,
    bookingCode: null,
    actualCost: null,
  }))
  return [...evCare, ...oem].sort((a, b) => b.serviceDate.localeCompare(a.serviceDate))
}

function maintenanceStatus(vehicle: MockVehicle) {
  const due = dueOf(vehicle)
  const profile = vehicle.profile!
  const records = serviceRecords(vehicle)
  const last = records[0] ?? null
  const now = new Date().toISOString()
  return {
    userVehicleId: vehicle.userVehicleId,
    dueStatus: due.dueStatus,
    dueReason: due.dueReason,
    calculationBasis: due.dueStatus === 'UNKNOWN' ? null : 'KM_AND_TIME',
    unknownReason: due.unknownReason,
    nextMilestone:
      due.nextKm && due.dueDate
        ? {
            odoMilestoneKm: due.nextKm,
            monthMilestone: due.nextKm / 1000,
            label: `${new Intl.NumberFormat('en-US').format(due.nextKm)} km / ${due.nextKm / 1000} months`,
            dueDate: due.dueDate,
            isRecurring: true,
            items: milestoneRuleItems(vehicle, due.nextKm),
          }
        : null,
    remainingKm: due.remainingKm,
    remainingDays: due.remainingDays,
    odometer: { odoKm: profile.odoKm, recordedAt: profile.odoRecordedAt, isStale: false, dataSource: OEM_SYNC_SOURCE },
    lastService: last ? { type: last.source, date: last.serviceDate, odoKm: last.odoKm } : null,
    thresholds: { dueSoonKm: DUE_SOON_KM, dueSoonDays: DUE_SOON_DAYS },
    oemSyncedAt: profile.odoRecordedAt,
    calculatedAt: now,
  }
}

function vehicleProfile(vehicle: MockVehicle) {
  const profile = vehicle.profile!
  const last = serviceRecords(vehicle)[0] ?? null
  return {
    userVehicleId: vehicle.userVehicleId,
    vinMasked: `${profile.vin.slice(0, 3)}***********${profile.vin.slice(-3)}`,
    licensePlate: vehicle.licensePlate,
    modelId: vehicle.modelId,
    modelName: profile.modelName,
    trim: profile.trim,
    color: profile.color,
    productionYear: profile.productionYear,
    manufactureDate: profile.manufactureDate,
    batteryCapacityKwh: profile.batteryCapacityKwh,
    motorPowerKw: profile.motorPowerKw,
    warranties: warranties(vehicle).map(({ durationMonths: _months, ...item }) => item),
    odometer: { odoKm: profile.odoKm, recordedAt: profile.odoRecordedAt, isStale: false, dataSource: OEM_SYNC_SOURCE },
    lastService: last ? { serviceDate: last.serviceDate, odoKm: last.odoKm, source: last.source, centerName: last.workshop.name } : null,
    oemSyncedAt: profile.odoRecordedAt,
  }
}

function owned(id: string): MockVehicle | null {
  return getDb().vehicles.find(item => item.userVehicleId === id && item.profile) ?? null
}

const notFound = () => fail(404, 'VEHICLE_NOT_FOUND', 'Không tìm thấy xe.')
const onboardingRequired = () => fail(403, 'ONBOARDING_REQUIRED', 'Cần hoàn tất đăng ký trước.')

export function registerVehicleRoutes() {
  route(GROUP, 'GET', '/user-vehicles', () => {
    if (getDb().account.status !== 'ACTIVE') return onboardingRequired()
    return ok(
      getDb()
        .vehicles.filter(vehicle => vehicle.profile)
        .map(vehicle => ({
          userVehicleId: vehicle.userVehicleId,
          modelName: vehicle.profile!.modelName,
          trim: vehicle.profile!.trim,
          licensePlate: vehicle.licensePlate,
          color: vehicle.profile!.color,
        })),
    )
  })

  route(GROUP, 'GET', '/user-vehicles/:id', req => {
    const vehicle = owned(req.params.id)
    return vehicle ? ok(vehicleProfile(vehicle)) : notFound()
  })

  route(GROUP, 'GET', '/user-vehicles/:id/maintenance-status', req => {
    const vehicle = owned(req.params.id)
    return vehicle ? ok(maintenanceStatus(vehicle)) : notFound()
  })

  route(GROUP, 'GET', '/user-vehicles/:id/service-records', req => {
    const vehicle = owned(req.params.id)
    return vehicle ? ok({ items: serviceRecords(vehicle) }) : notFound()
  })
}
