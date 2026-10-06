/**
 * Demo mode: Workshop Portal sign-in and onboarding of the demo Google identity (us-009 API-201 → 204,
 * us-013 API-301/302). The demo starts with an activated workshop owner managing the first demo
 * workshop; `restartWorkshopOnboarding()` turns it back into a new owner to show the onboarding.
 */
import { SLOT_TIMES, TOTAL_TECHNICIANS, EMERGENCY_SLOTS } from './bookings'
import { bodyOf, fail, ok, rememberIdempotent, replayIdempotent, route } from './core'
import { getDb, newWorkshopAccount, nowIso, save, uuid, type MockWorkshop, type MockWorkshopAccount } from './db'

const GROUP = 'workshop-auth'
const BASE = '/workshop-owner'
/** Time the manufacturer takes to find the manager (answered within the request, like the backend). */
const VERIFY_DELAY_MS = 2_000
const MAX_FAILED_ATTEMPTS = 5

const OPEN_TIME = '08:00:00'
const CLOSE_TIME = `${String(Number(SLOT_TIMES[SLOT_TIMES.length - 1].slice(0, 2)) + 1).padStart(2, '0')}:00:00`

/** Mon–Sat open, Sunday closed — the hours the slot mocks use. */
function operatingHours() {
  return Array.from({ length: 7 }, (_, dayOfWeek) => ({
    dayOfWeek,
    isClosed: dayOfWeek === 0,
    openTime: dayOfWeek === 0 ? null : OPEN_TIME,
    closeTime: dayOfWeek === 0 ? null : CLOSE_TIME,
  }))
}

function account(): MockWorkshopAccount {
  return getDb().workshopAccount
}

function nextStep(acc: MockWorkshopAccount) {
  if (acc.status === 'ACTIVE') return 'DASHBOARD'
  if (acc.status === 'PENDING_WORKSHOP_VERIFICATION') return 'VERIFYING'
  return acc.profile ? 'WORKSHOP' : 'PROFILE'
}

function onboardingOf(acc: MockWorkshopAccount) {
  return {
    status: acc.status,
    nextStep: nextStep(acc),
    profileCompleted: acc.profile !== null,
    profileCompletedAt: acc.profileCompletedAt,
    completedAt: acc.completedAt,
    expiresAt: null,
  }
}

function workshopSummary(acc: MockWorkshopAccount) {
  const workshop = acc.workshopId ? getDb().workshops.find(item => item.workshopId === acc.workshopId) : null
  if (!workshop) return null
  return {
    workshopId: workshop.workshopId,
    centerId: `VF-${workshop.workshopId.slice(-4).toUpperCase()}`,
    name: workshop.name,
    region: workshop.region,
    type: 'DEALER',
    status: 'ACTIVE',
    address: workshop.address,
    latitude: workshop.lat ?? null,
    longitude: workshop.lng ?? null,
    hotline: workshop.phone.replace(/\s/g, '') || null,
    totalTechnicians: acc.registration?.totalTechnicians ?? TOTAL_TECHNICIANS,
    emergencySlotsReserved: acc.registration?.emergencySlotsReserved ?? EMERGENCY_SLOTS,
    operatingHours: acc.registration?.operatingHours ?? operatingHours(),
    onboardedAt: acc.completedAt,
  }
}

function ownerOf(acc: MockWorkshopAccount) {
  return {
    ownerId: acc.ownerId,
    email: acc.email,
    displayName: acc.displayName,
    avatarUrl: null,
    fullName: acc.profile?.fullName ?? null,
    accountStatus: 'ACTIVE',
    roles: ['WORKSHOP_OWNER'],
  }
}

function attemptOf(acc: MockWorkshopAccount) {
  const check = acc.verification
  if (!check) return null
  return {
    attemptId: check.attemptId,
    status: check.status,
    failureReason: check.failureReason,
    retryCount: 0,
    requestedAt: check.requestedAt,
    respondedAt: check.respondedAt,
    failedAttemptsLast24h: acc.failedAttempts,
    maxFailedAttempts: MAX_FAILED_ATTEMPTS,
  }
}

function snapshot(acc: MockWorkshopAccount) {
  return {
    onboarding: onboardingOf(acc),
    profile: {
      email: acc.email,
      fullName: acc.profile?.fullName ?? null,
      phoneNumber: acc.profile?.phoneNumber ?? null,
      nationalIdMasked: acc.profile?.nationalIdMasked ?? null,
    },
    registration: acc.registration
      ? {
          ...acc.registration,
          latitude: null,
          longitude: null,
          verificationStatus: acc.verification?.status ?? 'PENDING',
          failureReason: acc.verification?.failureReason ?? null,
        }
      : null,
    latestAttempt: attemptOf(acc),
    consents: acc.consents,
    workshop: workshopSummary(acc),
  }
}

/** Activated owner of `workshop` — the starting point of the demo. */
export function activeWorkshopAccount(workshop: MockWorkshop): MockWorkshopAccount {
  const now = nowIso()
  return {
    ...newWorkshopAccount(),
    createdAt: now,
    status: 'ACTIVE',
    profile: { fullName: 'Nguyễn Hoàng Nam', phoneNumber: '0987654321', nationalIdMasked: '********5678' },
    profileCompletedAt: now,
    completedAt: now,
    consents: {
      personalDataProcessing: { granted: true, policyVersion: 'WS-2026-09' },
      oemDataSharing: { granted: true, policyVersion: 'WS-2026-09' },
    },
    workshopId: workshop.workshopId,
  }
}

/** The manufacturer's answer, applied lazily once its time has come. The demo manager is always found. */
export function reconcileWorkshopVerification() {
  const db = getDb()
  const acc = db.workshopAccount
  const check = acc.verification
  if (!check || check.status !== 'PENDING' || Date.now() < new Date(check.resolveAt).getTime()) return
  check.status = 'VERIFIED'
  check.respondedAt = check.resolveAt
  const workshop = db.workshops.find(item => item.active) ?? null
  if (workshop && acc.registration) {
    workshop.address = acc.registration.address || workshop.address
    workshop.phone = acc.registration.hotline || workshop.phone
  }
  acc.workshopId = workshop?.workshopId ?? null
  acc.status = 'ACTIVE'
  acc.completedAt = check.resolveAt
  save()
}

export function registerWorkshopAccountRoutes() {
  route(GROUP, 'POST', `${BASE}/oauth/sign-in`, () => {
    const acc = account()
    const isNewOwner = acc.createdAt === null
    const now = nowIso()
    if (isNewOwner) acc.createdAt = now
    acc.lastLoginAt = now
    save()
    return ok({ isNewOwner, owner: ownerOf(acc), onboarding: onboardingOf(acc), workshop: workshopSummary(acc) }, isNewOwner ? 201 : 200)
  })

  route(GROUP, 'GET', `${BASE}/oauth/session`, () => {
    const acc = account()
    if (acc.createdAt === null) return fail(404, 'WORKSHOP_OWNER_NOT_REGISTERED', 'Chưa có tài khoản Workshop Portal.')
    return ok({
      ownerId: acc.ownerId,
      email: acc.email,
      accountStatus: 'ACTIVE',
      onboarding: onboardingOf(acc),
      lastLoginAt: acc.lastLoginAt,
      lastLogoutAt: acc.lastLogoutAt,
    })
  })

  route(GROUP, 'POST', `${BASE}/oauth/logout`, () => {
    account().lastLogoutAt = nowIso()
    save()
    return { status: 204 }
  })

  route(GROUP, 'GET', `${BASE}/onboarding`, () => ok(snapshot(account())))

  route(GROUP, 'PUT', `${BASE}/onboarding/profile`, req => {
    const acc = account()
    if (acc.status === 'ACTIVE') return fail(409, 'ONBOARDING_ALREADY_COMPLETED', 'Tài khoản đã hoàn tất đăng ký.')
    const body = bodyOf<{ fullName: string; phoneNumber: string; nationalId: string; personalDataConsent: { granted: boolean; policyVersion: string } }>(req)
    const nationalId = (body.nationalId ?? '').replace(/\s/g, '')
    if ((body.fullName ?? '').trim().length < 2) return fail(400, 'INVALID_FIELD_FORMAT', 'Họ tên không hợp lệ.', { field: 'fullName' })
    if (!/^[0-9]{12}$/.test(nationalId)) return fail(400, 'INVALID_FIELD_FORMAT', 'CCCD không hợp lệ.', { field: 'nationalId' })
    if (!body.personalDataConsent?.granted) return fail(400, 'CONSENT_REQUIRED', 'Cần đồng ý xử lý dữ liệu cá nhân.')
    const now = nowIso()
    acc.profile = {
      fullName: body.fullName!.trim().replace(/\s+/g, ' '),
      phoneNumber: (body.phoneNumber ?? '').replace(/[\s.-]/g, ''),
      nationalIdMasked: `********${nationalId.slice(-4)}`,
    }
    acc.profileCompletedAt ??= now
    acc.consents.personalDataProcessing = body.personalDataConsent
    save()
    return ok({ onboarding: onboardingOf(acc), profile: snapshot(acc).profile })
  })

  route(GROUP, 'POST', `${BASE}/onboarding/workshop-verification`, async req => {
    const stored = replayIdempotent(req)
    if (stored) return stored
    const acc = account()
    if (acc.status === 'ACTIVE') return fail(409, 'ONBOARDING_ALREADY_COMPLETED', 'Tài khoản đã hoàn tất đăng ký.')
    if (!acc.profile) return fail(409, 'PROFILE_INCOMPLETE', 'Cần nhập thông tin cá nhân trước.')
    if (acc.status === 'PENDING_WORKSHOP_VERIFICATION') return fail(409, 'VERIFICATION_IN_PROGRESS', 'Đang xác thực.')
    const body = bodyOf<{
      address: string
      hotline: string
      totalTechnicians: number
      emergencySlotsReserved: number
      operatingHours: { dayOfWeek: number; isClosed: boolean; openTime: string | null; closeTime: string | null }[]
      oemDataSharingConsent: { granted: boolean; policyVersion: string }
    }>(req)
    if (!body.oemDataSharingConsent?.granted) return fail(400, 'CONSENT_REQUIRED', 'Cần đồng ý chia sẻ dữ liệu với hãng.')
    if (typeof window !== 'undefined') await new Promise(resolve => setTimeout(resolve, VERIFY_DELAY_MS))
    const now = Date.now()
    acc.consents.oemDataSharing = body.oemDataSharingConsent
    acc.registration = {
      registrationId: uuid(),
      address: (body.address ?? '').trim(),
      hotline: (body.hotline ?? '').replace(/[\s.-]/g, ''),
      totalTechnicians: body.totalTechnicians ?? TOTAL_TECHNICIANS,
      emergencySlotsReserved: body.emergencySlotsReserved ?? EMERGENCY_SLOTS,
      operatingHours: body.operatingHours ?? operatingHours(),
    }
    acc.verification = {
      attemptId: uuid(),
      status: 'PENDING',
      failureReason: null,
      requestedAt: new Date(now).toISOString(),
      respondedAt: null,
      resolveAt: new Date(now).toISOString(),
      outcome: 'VERIFIED',
    }
    acc.status = 'PENDING_WORKSHOP_VERIFICATION'
    reconcileWorkshopVerification()
    return rememberIdempotent(req, ok({ onboarding: onboardingOf(acc), verification: attemptOf(acc), workshop: workshopSummary(acc) }))
  })
}
