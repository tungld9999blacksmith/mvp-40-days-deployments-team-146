import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { addDays, getDb, isDemo, resetDb, todayVn } from './db'
import { demoProgress, DEMO_SAMPLE, openFollowUpNow, restartWorkshopOnboarding, skipOwnerOnboarding } from './demo'
import { configure, handleRequest } from './index'

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

async function call(method: Method, path: string, body?: unknown, headers: Record<string, string> = {}) {
  const response = await handleRequest({ method, path, body, headers: new Headers(headers) })
  if (!response) return { status: 0, data: null as never, error: null as never }
  const text = await response.text()
  const json = text ? JSON.parse(text) : null
  return { status: response.status, data: json?.data, error: json?.error }
}

const later = (ms: number) => vi.setSystemTime(Date.now() + ms)

/** Next open day (the mock workshops close on Sundays), at least `from` days ahead. */
function openDay(from = 1): string {
  let day = addDays(todayVn(), from)
  if (new Date(`${day}T12:00:00+07:00`).getUTCDay() === 0) day = addDays(day, 1)
  return day
}

async function onboardOwner() {
  const { owner, vehicle } = DEMO_SAMPLE
  await call('POST', '/oauth/sign-in')
  await call('PUT', '/onboarding/profile', {
    fullName: owner.fullName,
    phoneNumber: owner.phoneNumber,
    nationalId: owner.nationalId,
    dateOfBirth: owner.dateOfBirth,
    location: { addressLine: owner.addressLine, ward: null, district: owner.district, province: owner.province, source: 'MANUAL' },
    personalDataConsent: { granted: true, policyVersion: '2026-09' },
  })
  const submit = await call('POST', '/onboarding/vehicle-verification', {
    vin: vehicle.vin,
    licensePlate: vehicle.licensePlate,
    modelId: vehicle.modelId,
    manufactureYear: vehicle.manufactureYear,
    oemDataSharingConsent: { granted: true, policyVersion: '2026-09' },
  }, { 'Idempotency-Key': 'k-1' })
  later(3_000)
  return submit
}

async function bookFirstSlot(date = openDay()) {
  const workshop = getDb().workshops[0]
  const availability = await call('GET', `/workshops/${workshop.workshopId}/availability?date=${date}&timeSlot=09:00`)
  return call('POST', '/bookings', {
    confirmationToken: availability.data.requested.confirmationToken,
    userVehicleId: 'demo-owner-vehicle',
    milestoneRef: '12000',
  }, { 'Idempotency-Key': `book-${date}` })
}

beforeEach(() => {
  // Monday 09:00 in Vietnam: every slot of the next days is in the future.
  vi.useFakeTimers({ now: new Date('2026-10-05T02:00:00Z'), toFake: ['Date'] })
  resetDb()
  configure('demo')
})

afterEach(() => {
  vi.useRealTimers()
})

describe('demo mode — owner onboarding', () => {
  it('starts as a new account and is locked out of vehicle screens', async () => {
    expect(isDemo()).toBe(true)
    const signIn = await call('POST', '/oauth/sign-in')
    expect(signIn.status).toBe(201)
    expect(signIn.data.isNewUser).toBe(true)
    expect(signIn.data.onboarding.nextStep).toBe('PROFILE')
    const vehicles = await call('GET', '/user-vehicles')
    expect(vehicles.error.code).toBe('ONBOARDING_REQUIRED')
  })

  it('verifies the vehicle with the manufacturer, then links it with a due-soon status', async () => {
    const submit = await onboardOwner()
    expect(submit.status).toBe(200)
    expect(submit.data.verification.status).toBe('VERIFIED')
    expect(submit.data.vehicle.spec.modelName).toBe('VF 6')

    const snapshot = await call('GET', '/onboarding')
    expect(snapshot.data.onboarding.nextStep).toBe('HOME')
    expect(snapshot.data.vehicle.verificationStatus).toBe('VERIFIED')
    expect(snapshot.data.warranties.length).toBeGreaterThan(0)

    const [vehicle] = (await call('GET', '/user-vehicles')).data
    expect(vehicle.modelName).toBe('VF 6')
    const status = (await call('GET', `/user-vehicles/${vehicle.userVehicleId}/maintenance-status`)).data
    expect(status.dueStatus).toBe('DUE_SOON')
    expect(status.dueReason).toBe('BOTH')
    expect(status.nextMilestone.odoMilestoneKm).toBe(12_000)
    expect(status.remainingKm).toBe(500)
    expect(status.remainingDays).toBe(12)
  })

  it('fails the verification for a VIN the manufacturer does not know', async () => {
    await call('POST', '/oauth/sign-in')
    await call('PUT', '/onboarding/profile', {
      fullName: 'Lê Văn Bình', phoneNumber: '0912345678', nationalId: '001092012345', dateOfBirth: null,
      location: { addressLine: '1 Phố Huế', ward: null, district: null, province: 'Hà Nội', source: 'MANUAL' },
      personalDataConsent: { granted: true, policyVersion: '2026-09' },
    })
    await call('POST', '/onboarding/vehicle-verification', {
      vin: DEMO_SAMPLE.failingVin, licensePlate: '30A12345', modelId: 'VF5', manufactureYear: null,
      oemDataSharingConsent: { granted: true, policyVersion: '2026-09' },
    })
    later(3_000)
    const snapshot = await call('GET', '/onboarding')
    expect(snapshot.data.onboarding.status).toBe('VERIFICATION_FAILED')
    expect(snapshot.data.latestVerification.failureReason).toBe('VIN_NOT_FOUND')
    expect(snapshot.data.remainingAttempts).toBe(4)
  })
})

describe('demo mode — booking to completion', () => {
  beforeEach(async () => {
    await onboardOwner()
    await call('GET', '/onboarding')
  })

  it('ranks workshops by the profile province, or by distance from coordinates', async () => {
    const byProfile = (await call('GET', '/workshops/nearby')).data
    expect(byProfile.anchor.source).toBe('PROFILE')
    expect(byProfile.workshops.every((item: { region: string }) => item.region === 'Hà Nội')).toBe(true)
    // Next to "VinFast Thanh Xuân".
    const byDistance = (await call('GET', '/workshops/nearby?lat=20.994&lng=105.808')).data
    expect(byDistance.anchor.rankedBy).toBe('DISTANCE')
    expect(byDistance.workshops[0].name).toBe('VinFast Thanh Xuân')
    expect(byDistance.workshops[0].distanceKm).toBeLessThan(1)
  })

  it('creates a pending booking that the Board confirms, checks in, progresses and completes', async () => {
    const created = await bookFirstSlot()
    expect(created.status).toBe(201)
    expect(created.data.status).toBe('pending')
    expect(created.data.bookingCode).toBeNull()
    expect(created.data.estimatedCost).toBeGreaterThan(0)
    const id = created.data.bookingId

    const again = await bookFirstSlot(openDay(2))
    expect(again.error.code).toBe('OPEN_BOOKING_EXISTS')

    const step = async (action: string, expectedStatus: string, extra: Record<string, unknown> = {}) =>
      call('POST', `/workshop-owner/bookings/${id}/transitions`, { action, expectedStatus, ...extra })
    expect((await step('ACCEPT', 'PENDING')).data.status).toBe('CONFIRMED')
    // Demo mode allows the check-in before the appointment day.
    expect((await step('CHECK_IN', 'CONFIRMED', { source: 'QR_SCAN' })).data.status).toBe('CHECKED_IN')
    expect((await step('START', 'CHECKED_IN')).data.status).toBe('IN_PROGRESS')
    for (const [stage, expectedCurrentStage] of [['SERVICING', 'INSPECTING'], ['QUALITY_CHECK', 'SERVICING'], ['READY_FOR_PICKUP', 'QUALITY_CHECK']]) {
      const progress = await call('POST', `/workshop-owner/bookings/${id}/progress`, { stage, expectedCurrentStage })
      expect(progress.status).toBe(201)
    }
    const completed = await step('COMPLETE', 'IN_PROGRESS', { actualCost: 1_100_000 })
    expect(completed.data.status).toBe('COMPLETED')

    // The periodic visit moves the next milestone.
    const status = (await call('GET', '/user-vehicles/demo-owner-vehicle/maintenance-status')).data
    expect(status.nextMilestone.odoMilestoneKm).toBe(24_000)
    expect(status.dueStatus).toBe('NORMAL')
    const records = (await call('GET', '/user-vehicles/demo-owner-vehicle/service-records')).data.items
    expect(records[0]).toMatchObject({ source: 'EV_CARE', bookingId: id, actualCost: 1_100_000 })

    const progress = demoProgress()
    expect(progress.booking?.reached('completed')).toBe(true)
    expect(progress.followUp?.open).toBe(false)
    openFollowUpNow(id)
    const feed = (await call('GET', '/notifications')).data
    const kinds = feed.items.map((item: { kind: string }) => item.kind)
    expect(kinds).toContain('FOLLOW_UP')
    expect(feed.items.filter((item: { booking: { status: string } | null }) => item.booking).map((item: { booking: { status: string } }) => item.booking.status)).toEqual(
      expect.arrayContaining(['CONFIRMED', 'COMPLETED']),
    )
    expect(feed.unreadCount).toBe(1)
  })

  it('confirms at once when the workshop is in AUTO mode', async () => {
    await call('PUT', '/workshop-owner/booking-settings', { confirmationMode: 'AUTO' })
    const created = await bookFirstSlot()
    expect(created.data.status).toBe('confirmed')
    expect(created.data.bookingCode).toMatch(/^EVC-/)
  })

  it('spends the confirmation token once', async () => {
    const workshop = getDb().workshops[0]
    const availability = await call('GET', `/workshops/${workshop.workshopId}/availability?date=${openDay()}&timeSlot=10:00`)
    const body = { confirmationToken: availability.data.requested.confirmationToken, userVehicleId: 'demo-owner-vehicle' }
    expect((await call('POST', '/bookings', body)).status).toBe(201)
    expect((await call('POST', '/bookings', body)).error.code).toBe('INVALID_CONFIRMATION_TOKEN')
  })
})

describe('demo mode — panel shortcuts', () => {
  it('skips the onboarding into a returning owner with history and an open survey', async () => {
    skipOwnerOnboarding()
    const signIn = await call('POST', '/oauth/sign-in')
    expect(signIn.data.onboarding.nextStep).toBe('HOME')
    const status = (await call('GET', '/user-vehicles/demo-owner-vehicle/maintenance-status')).data
    expect(status.nextMilestone.odoMilestoneKm).toBe(24_000)
    expect(status.dueStatus).toBe('DUE_SOON')
    const past = (await call('GET', '/bookings?scope=PAST')).data.items
    expect(past).toHaveLength(2)
    const upcoming = (await call('GET', '/bookings?scope=UPCOMING')).data.items
    expect(upcoming).toHaveLength(0)
    const feed = (await call('GET', '/notifications')).data
    expect(feed.unreadCount).toBe(1)
  })

  it('starts with an activated workshop owner, and can replay the workshop onboarding', async () => {
    const active = await call('POST', '/workshop-owner/oauth/sign-in')
    expect(active.data.onboarding.nextStep).toBe('DASHBOARD')
    expect(active.data.workshop.name).toBe('VinFast Smart City')

    restartWorkshopOnboarding()
    expect((await call('GET', '/workshop-owner/oauth/session')).error.code).toBe('WORKSHOP_OWNER_NOT_REGISTERED')
    const fresh = await call('POST', '/workshop-owner/oauth/sign-in')
    expect(fresh.data.isNewOwner).toBe(true)
    expect(fresh.data.onboarding.nextStep).toBe('PROFILE')
    await call('PUT', '/workshop-owner/onboarding/profile', {
      fullName: 'Nguyễn Hoàng Nam', phoneNumber: '0987654321', nationalId: '001085005678',
      personalDataConsent: { granted: true, policyVersion: 'WS-2026-09' },
    })
    const submit = await call('POST', '/workshop-owner/onboarding/workshop-verification', {
      address: 'Đại lộ Thăng Long', hotline: '02439998888', totalTechnicians: 4, emergencySlotsReserved: 1,
      operatingHours: [], oemDataSharingConsent: { granted: true, policyVersion: 'WS-2026-09' },
    })
    expect(submit.status).toBe(200)
    expect(submit.data.verification.status).toBe('VERIFIED')
    const snapshot = (await call('GET', '/workshop-owner/onboarding')).data
    expect(snapshot.onboarding.nextStep).toBe('DASHBOARD')
    expect(snapshot.workshop.workshopId).toBe(getDb().workshops[0].workshopId)
  })

  it('answers unknown endpoints as not mocked instead of reaching for a backend', async () => {
    expect(await handleRequest({ method: 'GET', path: '/not-a-route', body: undefined, headers: new Headers() })).toBeNull()
  })
})
