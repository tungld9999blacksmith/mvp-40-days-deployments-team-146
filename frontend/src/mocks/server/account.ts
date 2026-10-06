/**
 * Demo mode: owner sign-in and onboarding of the demo Google identity (us-001 API-001 → 005,
 * us-005 API-101/102). Like the backend, the submit waits for the manufacturer (~2 s here) and
 * answers 200 VERIFIED / FAILED; a VIN containing `FAIL` is not found by the manufacturer.
 */
import { bodyOf, fail, ok, rememberIdempotent, replayIdempotent, route } from './core'
import { getDb, nowIso, save, uuid, type MockOwnerAccount } from './db'
import { createOwnerVehicle, modelById, normalizePlate, onboardingWarranties, ownerVehicle, VEHICLE_MODELS, vehicleSpec } from './vehicles'

const GROUP = 'auth'
/** Time the manufacturer takes to answer (the backend waits up to ~8 s before falling back to 202). */
const VERIFY_DELAY_MS = 2_000
export const FAILING_VIN_MARKER = 'FAIL'

const PHONE_RE = /^(0|\+84)(3|5|7|8|9)[0-9]{8}$/
const NATIONAL_ID_RE = /^[0-9]{12}$/
const VIN_RE = /^[A-Z0-9]{17}$/
const PLATE_RE = /^[0-9]{2}[A-Z]{1,2}[0-9]?[0-9]{4,5}$/

function account(): MockOwnerAccount {
  return getDb().account
}

function nextStep(acc: MockOwnerAccount) {
  if (acc.status === 'ACTIVE') return 'HOME'
  if (acc.status === 'PENDING_VEHICLE_VERIFICATION') return 'VERIFYING'
  return acc.profile ? 'VEHICLE' : 'PROFILE'
}

export function onboardingOf(acc: MockOwnerAccount = account()) {
  return {
    status: acc.status,
    nextStep: nextStep(acc),
    profileCompleted: acc.profile !== null,
    profileCompletedAt: acc.profileCompletedAt,
    completedAt: acc.completedAt,
    expiresAt: null,
  }
}

function userOf(acc: MockOwnerAccount) {
  return {
    userId: acc.userId,
    email: acc.email,
    displayName: acc.displayName,
    avatarUrl: null,
    fullName: acc.profile?.fullName ?? null,
    accountStatus: 'ACTIVE',
    roles: ['VEHICLE_USER'],
  }
}

/** The manufacturer's answer, applied lazily once its time has come. */
export function reconcileVerification() {
  const acc = account()
  const check = acc.verification
  if (!check || check.status !== 'PENDING' || Date.now() < new Date(check.resolveAt).getTime()) return
  check.status = check.outcome
  check.respondedAt = check.resolveAt
  if (check.outcome === 'VERIFIED' && acc.vehicleRequest) {
    createOwnerVehicle({
      vin: acc.vehicleRequest.vin,
      licensePlate: acc.vehicleRequest.licensePlate,
      modelId: acc.vehicleRequest.modelId,
      productionYear: acc.vehicleRequest.manufactureYear,
    })
    acc.status = 'ACTIVE'
    acc.completedAt = check.resolveAt
  } else {
    check.failureReason = 'VIN_NOT_FOUND'
    acc.status = 'VERIFICATION_FAILED'
    acc.remainingAttempts = Math.max(acc.remainingAttempts - 1, 0)
  }
  save()
}

function onboardingVehicle(acc: MockOwnerAccount) {
  const request = acc.vehicleRequest
  if (!request) return null
  const verified = acc.verification?.status === 'VERIFIED'
  const vehicle = verified ? ownerVehicle() : null
  return {
    vehicleId: vehicle?.userVehicleId ?? `pending-${request.vin}`,
    vin: request.vin,
    licensePlate: request.licensePlate,
    declaredModelId: request.modelId,
    declaredManufactureYear: request.manufactureYear,
    verificationStatus: acc.verification?.status ?? 'PENDING',
    verificationFailureReason: acc.verification?.failureReason ?? null,
    verifiedAt: verified ? acc.verification!.respondedAt : null,
    spec: vehicle ? vehicleSpec(vehicle) : null,
  }
}

function warrantiesOf(acc: MockOwnerAccount) {
  const vehicle = acc.verification?.status === 'VERIFIED' ? ownerVehicle() : null
  return vehicle ? onboardingWarranties(vehicle) : []
}

function snapshot(acc: MockOwnerAccount) {
  const check = acc.verification
  return {
    onboarding: onboardingOf(acc),
    profile: {
      email: acc.email,
      displayName: acc.displayName,
      fullName: acc.profile?.fullName ?? null,
      phoneNumber: acc.profile?.phoneNumber ?? null,
      nationalIdMasked: acc.profile?.nationalIdMasked ?? null,
      dateOfBirth: acc.profile?.dateOfBirth ?? null,
    },
    location: acc.location,
    vehicle: onboardingVehicle(acc),
    warranties: warrantiesOf(acc),
    latestVerification: check
      ? { attemptId: check.attemptId, status: check.status, failureReason: check.failureReason, requestedAt: check.requestedAt, respondedAt: check.respondedAt }
      : null,
    remainingAttempts: acc.remainingAttempts,
    consents: acc.consents,
  }
}

const invalidField = (field: string) => fail(400, 'INVALID_FIELD_FORMAT', 'Dữ liệu không hợp lệ.', { field })

function verificationData(acc: MockOwnerAccount) {
  const check = acc.verification!
  const message =
    check.status === 'VERIFIED'
      ? 'Xác thực xe thành công.'
      : check.status === 'FAILED'
        ? 'Hãng không tìm thấy xe với số VIN này.'
        : 'Đang chờ hệ thống hãng xác thực.'
  return {
    onboarding: onboardingOf(acc),
    verification: {
      attemptId: check.attemptId,
      status: check.status,
      failureReason: check.failureReason,
      message,
      remainingAttempts: acc.remainingAttempts,
    },
    vehicle: onboardingVehicle(acc),
    warranties: warrantiesOf(acc),
  }
}

export function registerAccountRoutes() {
  route(GROUP, 'POST', '/oauth/sign-in', () => {
    const acc = account()
    const isNewUser = acc.createdAt === null
    if (isNewUser) acc.createdAt = nowIso()
    save()
    return ok({ isNewUser, user: userOf(acc), onboarding: onboardingOf(acc) }, isNewUser ? 201 : 200)
  })

  route(GROUP, 'POST', '/oauth/logout', () => ({ status: 204 }))

  route(GROUP, 'GET', '/oauth/profile', () => ok({ uid: 'demo-google-account', email: account().email }))

  route(GROUP, 'GET', '/onboarding', () => ok(snapshot(account())))

  route(GROUP, 'PUT', '/onboarding/profile', req => {
    const acc = account()
    if (acc.status === 'ACTIVE') return fail(409, 'ONBOARDING_ALREADY_COMPLETED', 'Tài khoản đã hoàn tất đăng ký.')
    const body = bodyOf<{
      fullName: string
      phoneNumber: string
      nationalId: string
      dateOfBirth: string | null
      location: { addressLine: string; ward: string | null; district: string | null; province: string; source: 'MANUAL' }
      personalDataConsent: { granted: boolean; policyVersion: string }
    }>(req)
    const fullName = (body.fullName ?? '').trim().replace(/\s+/g, ' ')
    const phone = (body.phoneNumber ?? '').replace(/[\s.-]/g, '')
    const nationalId = (body.nationalId ?? '').replace(/\s/g, '')
    if (fullName.length < 2) return invalidField('fullName')
    if (!PHONE_RE.test(phone)) return invalidField('phoneNumber')
    if (!NATIONAL_ID_RE.test(nationalId)) return invalidField('nationalId')
    if ((body.location?.addressLine ?? '').trim().length < 5) return invalidField('location.addressLine')
    if (!body.location?.province) return invalidField('location.province')
    if (!body.personalDataConsent?.granted) return fail(400, 'CONSENT_REQUIRED', 'Cần đồng ý xử lý dữ liệu cá nhân.')
    const now = nowIso()
    acc.profile = {
      fullName,
      phoneNumber: phone,
      nationalIdMasked: `********${nationalId.slice(-4)}`,
      dateOfBirth: body.dateOfBirth ?? null,
    }
    acc.profileCompletedAt ??= now
    acc.location = {
      addressLine: body.location.addressLine.trim(),
      ward: body.location.ward ?? null,
      district: body.location.district ?? null,
      province: body.location.province,
      latitude: null,
      longitude: null,
      source: body.location.source ?? 'MANUAL',
    }
    acc.consents.personalDataProcessing = body.personalDataConsent
    getDb().owner = { fullName, phone }
    save()
    return ok({ onboarding: onboardingOf(acc), profile: snapshot(acc).profile, location: acc.location })
  })

  route(GROUP, 'GET', '/onboarding/vehicle-models', () =>
    ok({
      items: VEHICLE_MODELS.map(model => ({
        modelId: model.modelId,
        modelName: model.modelName,
        trim: model.trim,
        productionYear: null,
      })),
    }),
  )

  route(GROUP, 'POST', '/onboarding/vehicle-verification', async req => {
    const stored = replayIdempotent(req)
    if (stored) return stored
    const acc = account()
    if (acc.status === 'ACTIVE') return fail(409, 'ONBOARDING_ALREADY_COMPLETED', 'Tài khoản đã hoàn tất đăng ký.')
    if (!acc.profile) return fail(409, 'PROFILE_INCOMPLETE', 'Cần nhập thông tin cá nhân trước.')
    if (acc.status === 'PENDING_VEHICLE_VERIFICATION') return fail(409, 'VERIFICATION_IN_PROGRESS', 'Đang xác thực xe.')
    if (acc.remainingAttempts <= 0) {
      return fail(429, 'VERIFICATION_ATTEMPTS_EXCEEDED', 'Đã hết số lần thử.', { retryAfterSeconds: 86_400 })
    }
    const body = bodyOf<{
      vin: string
      licensePlate: string
      modelId: string
      manufactureYear: number | null
      oemDataSharingConsent: { granted: boolean; policyVersion: string }
    }>(req)
    const vin = (body.vin ?? '').trim().toUpperCase()
    const plate = normalizePlate(body.licensePlate ?? '')
    if (!VIN_RE.test(vin)) return invalidField('vin')
    if (!PLATE_RE.test(plate)) return invalidField('licensePlate')
    if (!body.modelId || !VEHICLE_MODELS.some(model => model.modelId === body.modelId)) return invalidField('modelId')
    if (!body.oemDataSharingConsent?.granted) return fail(400, 'CONSENT_REQUIRED', 'Cần đồng ý chia sẻ dữ liệu với hãng.')
    if (typeof window !== 'undefined') await new Promise(resolve => setTimeout(resolve, VERIFY_DELAY_MS))
    const now = Date.now()
    acc.consents.oemDataSharing = body.oemDataSharingConsent
    acc.vehicleRequest = { vin, licensePlate: plate, modelId: modelById(body.modelId).modelId, manufactureYear: body.manufactureYear ?? null }
    acc.verification = {
      attemptId: uuid(),
      status: 'PENDING',
      failureReason: null,
      requestedAt: new Date(now).toISOString(),
      respondedAt: null,
      resolveAt: new Date(now).toISOString(),
      outcome: vin.includes(FAILING_VIN_MARKER) ? 'FAILED' : 'VERIFIED',
    }
    acc.status = 'PENDING_VEHICLE_VERIFICATION'
    reconcileVerification()
    return rememberIdempotent(req, ok(verificationData(acc)))
  })
}
