/**
 * Learns reference data from real backend responses so mock screens reuse real ids and names:
 * the owner, their vehicle, nearby workshops, and bookings the real API-BK-03 creates.
 */
import { observe } from './core'
import {
  getDb,
  hash01,
  nowIso,
  save,
  type BookingState,
  type MockBooking,
  type MockVehicle,
} from './db'

const GROUP = 'learn'

function modelIdOf(modelName: string | null | undefined): string {
  const match = /VF\s?(e?\d+)/i.exec(modelName ?? '')
  return match ? `VF${match[1].toUpperCase()}` : 'VF'
}

function upsertVehicle(id: string, patch: Partial<MockVehicle>) {
  const db = getDb()
  let vehicle = db.vehicles.find(item => item.userVehicleId === id)
  if (!vehicle) {
    vehicle = {
      userVehicleId: id,
      modelId: 'VF',
      modelName: 'Xe của bạn',
      licensePlate: '',
      nextOdoMilestone: null,
      nextItems: [],
      warrantyStatus: 'UNKNOWN',
    }
    db.vehicles.push(vehicle)
  }
  Object.assign(vehicle, patch)
  save()
}

export function registerLearners() {
  observe(GROUP, 'POST', '/oauth/sign-in', (_req, data) => {
    const user = (data as { user?: { fullName?: string | null; displayName?: string | null } } | null)?.user
    const name = user?.fullName || user?.displayName
    if (name) {
      getDb().owner.fullName = name
      save()
    }
  })

  observe(GROUP, 'GET', '/user-vehicles', (_req, data) => {
    if (!Array.isArray(data)) return
    for (const item of data as { userVehicleId: string; modelName: string | null; trim: string | null; licensePlate: string }[]) {
      upsertVehicle(item.userVehicleId, {
        modelName: [item.modelName, item.trim].filter(Boolean).join(' ') || 'Xe của bạn',
        modelId: modelIdOf(item.modelName),
        licensePlate: item.licensePlate,
      })
    }
  })

  observe(GROUP, 'GET', '/user-vehicles/:id', (req, data) => {
    const profile = data as {
      modelId: string | null
      modelName: string | null
      trim: string | null
      licensePlate: string
      warranties: { component: string; isActive: boolean }[]
    } | null
    if (!profile) return
    const chassis = profile.warranties?.find(item => item.component.toLowerCase() === 'chassis')
    upsertVehicle(req.params.id, {
      modelId: profile.modelId ? modelIdOf(profile.modelId) : modelIdOf(profile.modelName),
      modelName: [profile.modelName, profile.trim].filter(Boolean).join(' ') || 'Xe của bạn',
      licensePlate: profile.licensePlate,
      warrantyStatus: chassis ? (chassis.isActive ? 'ACTIVE' : 'EXPIRED') : profile.warranties?.length ? 'ACTIVE' : 'UNKNOWN',
    })
  })

  observe(GROUP, 'GET', '/user-vehicles/:id/maintenance-status', (req, data) => {
    const next = (data as {
      nextMilestone: { odoMilestoneKm: number; items: { itemCode: string; itemName: string; isCoveredByWarranty: boolean }[] } | null
    } | null)?.nextMilestone
    upsertVehicle(req.params.id, {
      nextOdoMilestone: next?.odoMilestoneKm ?? null,
      nextItems: next?.items.map(item => ({ itemCode: item.itemCode, itemName: item.itemName, covered: item.isCoveredByWarranty })) ?? [],
    })
  })

  observe(GROUP, 'GET', '/workshops/nearby', (_req, data) => {
    const list = (data as { workshops?: { workshopId: string; name: string; address: string; region: string; isPreferred: boolean }[] } | null)
      ?.workshops
    if (!Array.isArray(list)) return
    const db = getDb()
    for (const item of list) {
      const known = db.workshops.find(workshop => workshop.workshopId === item.workshopId)
      const phone = `024 3${Math.floor(100 + hash01(item.workshopId) * 899)} ${Math.floor(1000 + hash01(`${item.workshopId}p`) * 8999)}`
      if (known) Object.assign(known, { name: item.name, address: item.address, region: item.region, isPreferred: item.isPreferred, active: true })
      else db.workshops.push({ ...item, phone, active: true })
    }
    save()
  })

  observe(GROUP, 'POST', '/bookings', (req, data) => {
    const booking = data as {
      bookingId: string
      status: string
      confirmationMode: string
      workshopId: string
      workshopName: string | null
      bookingDate: string
      timeSlot: string
      holdExpiresAt: string | null
      ownerCancelableUntil: string | null
      bookingCode: string | null
      estimatedCost: string | number | null
      note?: string | null
    } | null
    if (!booking?.bookingId) return
    const db = getDb()
    const body = (req.body ?? {}) as { userVehicleId?: string; milestoneRef?: string; note?: string }
    const vehicle = db.vehicles.find(item => item.userVehicleId === body.userVehicleId) ?? null
    if (!db.workshops.some(item => item.workshopId === booking.workshopId)) {
      db.workshops.push({
        workshopId: booking.workshopId,
        name: booking.workshopName ?? 'Xưởng dịch vụ',
        address: '',
        phone: '',
        region: '',
        active: true,
        isPreferred: false,
      })
    }
    const status = booking.status.toLowerCase() as BookingState
    const odoMilestone = body.milestoneRef && /^\d+$/.test(body.milestoneRef) ? Number(body.milestoneRef) : null
    const now = nowIso()
    const shadow: MockBooking = {
      bookingId: booking.bookingId,
      bookingCode: booking.bookingCode ?? `EVC-${booking.bookingId.replace(/-/g, '').slice(0, 8).toUpperCase()}`,
      status,
      workshopId: booking.workshopId,
      userVehicleId: body.userVehicleId ?? null,
      vehicle: { modelName: vehicle?.modelName ?? 'Xe của bạn', licensePlate: vehicle?.licensePlate ?? '' },
      customer: { ...db.owner },
      ownerSelf: true,
      real: true,
      bookingDate: booking.bookingDate,
      timeSlot: booking.timeSlot.slice(0, 5),
      createdAt: now,
      holdExpiresAt: booking.holdExpiresAt,
      ownerCancelableUntil: booking.ownerCancelableUntil,
      confirmationMode: booking.confirmationMode.toUpperCase() === 'AUTO' ? 'AUTO' : 'MANUAL',
      odoMilestone,
      estimatedCost: booking.estimatedCost === null ? null : Number(booking.estimatedCost),
      actualCost: null,
      note: body.note ?? null,
      attendanceConfirmedAt: null,
      rescheduleCount: 0,
      checkedInAt: null,
      events: [
        { fromStatus: null, toStatus: 'PENDING', actorType: 'VEHICLE_OWNER', source: 'APP', reasonCode: null, note: null, at: now },
        ...(status === 'confirmed'
          ? [{ fromStatus: 'PENDING', toStatus: 'CONFIRMED', actorType: 'SYSTEM' as const, source: 'AUTO_CONFIRM', reasonCode: null, note: null, at: now }]
          : []),
      ],
      reschedules: [],
      progress: [],
    }
    db.bookings = db.bookings.filter(item => item.bookingId !== shadow.bookingId)
    db.bookings.push(shadow)
    save()
  })

  observe(GROUP, 'DELETE', '/bookings/:id/hold', req => {
    const booking = getDb().bookings.find(item => item.bookingId === req.params.id)
    if (!booking || booking.status !== 'pending') return
    booking.events.push({
      fromStatus: 'PENDING',
      toStatus: 'CANCELLED',
      actorType: 'VEHICLE_OWNER',
      source: 'APP',
      reasonCode: 'HOLD_CANCELLED',
      note: null,
      at: nowIso(),
    })
    booking.status = 'cancelled'
    save()
  })
}
