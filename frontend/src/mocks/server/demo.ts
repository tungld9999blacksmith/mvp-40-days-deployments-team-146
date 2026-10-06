/**
 * Controls of the demo panel (src/demo): reset, skip the owner onboarding, fast-forward the survey,
 * and the progress of the scripted flow read from the mock data. Demo mode only.
 */
import { visibleCode } from './bookings'
import { scheduleFollowUp } from './crm'
import { getDb, newWorkshopAccount, nowIso, resetDb, save, setDemo, uuid, type BookingState } from './db'
import { ensureSeeded, seedOwnerHistory } from './seed'
import { createOwnerVehicle } from './vehicles'

/** Sample input for the onboarding forms (shown with copy buttons in the panel). */
export const DEMO_SAMPLE = {
  owner: {
    fullName: 'Nguyễn Minh Anh',
    phoneNumber: '0912345678',
    nationalId: '001092012345',
    dateOfBirth: '1992-05-14',
    addressLine: '25 Trần Duy Hưng',
    district: 'Cầu Giấy',
    province: 'Hà Nội',
  },
  vehicle: {
    vin: 'RLLV6PLUS24000123',
    licensePlate: '30A-123.45',
    modelId: 'VF6',
    modelLabel: 'VF 6 Plus',
    manufactureYear: 2024,
  },
  /** A VIN with `FAIL` is not found by the mock manufacturer (failed verification path). */
  failingVin: 'RLLFAIL0000000001',
  workshopOwner: { fullName: 'Nguyễn Hoàng Nam', phoneNumber: '0987654321', nationalId: '001085005678', hotline: '02439998888' },
} as const

/** Clears every mock record; the next request seeds a fresh demo. */
export function resetDemo() {
  setDemo(true)
  resetDb()
}

/** "Returning owner": activated account with a linked vehicle and some history. */
export function skipOwnerOnboarding() {
  setDemo(true)
  ensureSeeded()
  const db = getDb()
  if (db.account.status === 'ACTIVE') return
  const { owner, vehicle } = DEMO_SAMPLE
  const now = nowIso()
  const policy = { granted: true, policyVersion: '2026-09' }
  const acc = db.account
  acc.createdAt ??= now
  acc.status = 'ACTIVE'
  acc.profile = { fullName: owner.fullName, phoneNumber: owner.phoneNumber, nationalIdMasked: `********${owner.nationalId.slice(-4)}`, dateOfBirth: owner.dateOfBirth }
  acc.profileCompletedAt = now
  acc.completedAt = now
  acc.location = { addressLine: owner.addressLine, ward: null, district: owner.district, province: owner.province, latitude: null, longitude: null, source: 'MANUAL' }
  acc.consents = { personalDataProcessing: policy, oemDataSharing: policy }
  acc.vehicleRequest = { vin: vehicle.vin, licensePlate: '30A12345', modelId: vehicle.modelId, manufactureYear: vehicle.manufactureYear }
  acc.verification = { attemptId: uuid(), status: 'VERIFIED', failureReason: null, requestedAt: now, respondedAt: now, resolveAt: now, outcome: 'VERIFIED' }
  db.owner = { fullName: owner.fullName, phone: owner.phoneNumber }
  const linked = createOwnerVehicle({
    vin: vehicle.vin,
    licensePlate: vehicle.licensePlate,
    modelId: vehicle.modelId,
    productionYear: vehicle.manufactureYear,
    odoKm: 23_400,
    deliveredDaysAgo: 720,
    // Manufacturer service at 12,000 km a year ago ⇒ 24,000 km due in 12 days.
    firstDueInDays: 12,
    oemRecords: [
      { recordId: uuid(), serviceDate: dayOffset(-353), odoKm: 12_040, isPeriodic: true, itemsDone: 'Bảo dưỡng định kỳ mốc 12.000 km', centerName: 'VinFast Smart City' },
      { recordId: uuid(), serviceDate: dayOffset(-720), odoKm: 6, isPeriodic: false, itemsDone: 'Kiểm tra trước giao xe (PDI)', centerName: 'VinFast Smart City' },
    ],
  })
  seedOwnerHistory(linked)
  save()
}

function dayOffset(days: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(Date.now() + days * 86_400_000))
}

/** Turns the Workshop Portal account back into a new owner (to show the us-009 onboarding). */
export function restartWorkshopOnboarding() {
  setDemo(true)
  ensureSeeded()
  getDb().workshopAccount = newWorkshopAccount()
  save()
}

/** The survey opens 1 minute after completion; this opens it now. */
export function openFollowUpNow(bookingId: string) {
  const db = getDb()
  const booking = db.bookings.find(item => item.bookingId === bookingId)
  if (!booking || booking.status !== 'completed') return
  const followUp = scheduleFollowUp(booking, 0)
  if (followUp.status === 'pending') followUp.scheduledAt = nowIso()
  save()
}

const ORDER: BookingState[] = ['pending', 'confirmed', 'checked_in', 'in_progress', 'completed']

export interface DemoProgress {
  ownerActive: boolean
  workshopActive: boolean
  /** Latest booking made during the demo (wizard or chat), not seeded ones. */
  booking: {
    bookingId: string
    status: BookingState
    /** Shown once the workshop confirmed (what the owner reads out at check-in). */
    code: string | null
    reached: (state: BookingState) => boolean
    hasProgress: boolean
  } | null
  followUp: { followUpId: string; open: boolean; responded: boolean } | null
}

export function demoProgress(): DemoProgress {
  const db = getDb()
  const live = db.bookings.filter(item => item.live).sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0] ?? null
  const followUp = live ? db.followUps.find(item => item.bookingId === live.bookingId) ?? null : null
  return {
    ownerActive: db.account.status === 'ACTIVE',
    workshopActive: db.workshopAccount.status === 'ACTIVE',
    booking: live
      ? {
          bookingId: live.bookingId,
          status: live.status,
          code: visibleCode(live),
          reached: state => live.status !== 'cancelled' && ORDER.indexOf(live.status) >= ORDER.indexOf(state),
          hasProgress: live.progress.length > 1,
        }
      : null,
    followUp: followUp
      ? { followUpId: followUp.followUpId, open: followUp.status === 'sent' || new Date(followUp.scheduledAt).getTime() <= Date.now(), responded: followUp.response !== null }
      : null,
  }
}
