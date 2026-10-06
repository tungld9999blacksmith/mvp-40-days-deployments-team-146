/**
 * In-browser state of the mock API. Persisted in localStorage so the owner app and the
 * Workshop Portal opened in the same browser see the same bookings and follow-ups.
 * Statuses are stored in the backend's lower-case form and mapped at the API boundary.
 */

export type BookingState = 'pending' | 'confirmed' | 'checked_in' | 'in_progress' | 'completed' | 'cancelled'
export type Stage = 'CHECKED_IN' | 'INSPECTING' | 'SERVICING' | 'WAITING_PARTS' | 'QUALITY_CHECK' | 'READY_FOR_PICKUP'

export interface MockWorkshop {
  workshopId: string
  name: string
  address: string
  phone: string
  region: string
  active: boolean
  isPreferred: boolean
  /** Seeded when no real workshop is known yet; never picked as the default workshop. */
  demo?: boolean
  /** Demo-mode workshops carry coordinates (distance ranking of API-BK-01 and us-061). */
  lat?: number
  lng?: number
}

/** Manufacturer data of a vehicle the mock owns (demo mode; learned vehicles have none). */
export interface MockVehicleProfile {
  vin: string
  modelName: string
  trim: string | null
  color: string
  productionYear: number
  manufactureDate: string
  batteryCapacityKwh: number
  motorPowerKw: number
  odoKm: number
  odoRecordedAt: string
  /** Warranty start = delivery day. */
  deliveredAt: string
  /** Due date of the first milestone while the vehicle has no EV Care visit yet. */
  firstDueDate: string
  oemRecords: { recordId: string; serviceDate: string; odoKm: number | null; isPeriodic: boolean; itemsDone: string; centerName: string }[]
}

export interface MockVehicle {
  userVehicleId: string
  modelId: string
  modelName: string
  licensePlate: string
  nextOdoMilestone: number | null
  nextItems: { itemCode: string; itemName: string; covered: boolean }[]
  warrantyStatus: 'ACTIVE' | 'EXPIRED' | 'UNKNOWN'
  profile?: MockVehicleProfile
}

export interface StatusEvent {
  fromStatus: string | null
  toStatus: string
  actorType: 'VEHICLE_OWNER' | 'WORKSHOP_OWNER' | 'SYSTEM'
  source: string
  reasonCode: string | null
  note: string | null
  at: string
}

export interface ProgressEntry {
  stage: Stage
  note: string | null
  actorType: 'SYSTEM' | 'WORKSHOP_OWNER'
  actorName: string | null
  createdAt: string
}

export interface MockBooking {
  bookingId: string
  bookingCode: string
  status: BookingState
  workshopId: string
  userVehicleId: string | null
  vehicle: { modelName: string; licensePlate: string }
  customer: { fullName: string; phone: string }
  /** Booking of the signed-in owner (shown in "Lịch của tôi"); others only appear on the Board. */
  ownerSelf: boolean
  /** Shadow of a booking the real backend created (API-BK-03). */
  real: boolean
  bookingDate: string
  timeSlot: string
  createdAt: string
  holdExpiresAt: string | null
  ownerCancelableUntil: string | null
  confirmationMode: 'AUTO' | 'MANUAL'
  odoMilestone: number | null
  estimatedCost: number | null
  actualCost: number | null
  note: string | null
  attendanceConfirmedAt: string | null
  rescheduleCount: number
  checkedInAt: string | null
  /** Created during the demo through API-BK-03 (not seeded) — drives the demo checklist. */
  live?: boolean
  events: StatusEvent[]
  reschedules: { from: { date: string; timeSlot: string }; to: { date: string; timeSlot: string }; source: string; at: string }[]
  progress: ProgressEntry[]
}

export interface MockFollowUp {
  followUpId: string
  bookingId: string
  status: 'pending' | 'sent' | 'closed'
  closedReason: 'PROCESSED' | 'NO_RESPONSE' | null
  scheduledAt: string
  sentAt: string | null
  question: string
  response: { rating: number; comment: string | null; respondedAt: string } | null
  outcome: { hasIssue: boolean; safetyAdvice: boolean } | null
}

export interface MockSlotBlock {
  date: string
  timeSlot: string
  blockedCount: number
  reason: string
  note: string | null
}

export interface MockToken {
  token: string
  bookingId: string
  date: string
  timeSlot: string
  from: { date: string; timeSlot: string }
  expiresAt: number
  used: boolean
}

/** `confirmationToken` of API-BK-02, spent by API-BK-03 (demo mode). */
export interface MockHoldToken {
  token: string
  workshopId: string
  date: string
  timeSlot: string
  expiresAt: number
  used: boolean
}

export interface MockConsent {
  granted: boolean
  policyVersion: string
}

/** Pending/finished manufacturer check of the onboarding (owner vehicle or workshop manager). */
export interface MockVerification {
  attemptId: string
  status: 'PENDING' | 'VERIFIED' | 'FAILED'
  failureReason: string | null
  requestedAt: string
  respondedAt: string | null
  /** The mock manufacturer answers at this time (polling of API-002 / API-202). */
  resolveAt: string
  /** Result it will give. */
  outcome: 'VERIFIED' | 'FAILED'
}

/** Owner account of the demo Google identity (us-001 / us-005). */
export interface MockOwnerAccount {
  userId: number
  email: string
  displayName: string
  createdAt: string | null
  status: 'ONBOARDING_IN_PROGRESS' | 'PENDING_VEHICLE_VERIFICATION' | 'VERIFICATION_FAILED' | 'ACTIVE'
  profile: { fullName: string; phoneNumber: string; nationalIdMasked: string; dateOfBirth: string | null } | null
  profileCompletedAt: string | null
  completedAt: string | null
  location: {
    addressLine: string
    ward: string | null
    district: string | null
    province: string
    latitude: null
    longitude: null
    source: 'MANUAL' | 'MAP_PICK' | 'GPS'
  } | null
  consents: Record<string, MockConsent | null>
  vehicleRequest: { vin: string; licensePlate: string; modelId: string; manufactureYear: number | null } | null
  verification: MockVerification | null
  remainingAttempts: number
}

/** Workshop owner account of the demo Google identity (us-009 / us-013). */
export interface MockWorkshopAccount {
  ownerId: string
  email: string
  displayName: string
  createdAt: string | null
  lastLoginAt: string | null
  lastLogoutAt: string | null
  status: 'ONBOARDING_IN_PROGRESS' | 'PENDING_WORKSHOP_VERIFICATION' | 'VERIFICATION_FAILED' | 'ACTIVE'
  profile: { fullName: string; phoneNumber: string; nationalIdMasked: string } | null
  profileCompletedAt: string | null
  completedAt: string | null
  registration: {
    registrationId: string
    address: string
    hotline: string
    totalTechnicians: number
    emergencySlotsReserved: number
    operatingHours: { dayOfWeek: number; isClosed: boolean; openTime: string | null; closeTime: string | null }[]
  } | null
  verification: MockVerification | null
  failedAttempts: number
  consents: Record<string, MockConsent | null>
  /** Workshop managed once ACTIVE. */
  workshopId: string | null
}

export interface MockNotificationSettings {
  remindersEnabled: boolean
  reminderLeadDays: number
  channels: Record<string, boolean>
}

export interface MockDb {
  version: number
  seededAt: string | null
  owner: { fullName: string; phone: string }
  workshops: MockWorkshop[]
  vehicles: MockVehicle[]
  bookings: MockBooking[]
  followUps: MockFollowUp[]
  slotBlocks: MockSlotBlock[]
  tokens: MockToken[]
  holdTokens: MockHoldToken[]
  confirmationMode: 'AUTO' | 'MANUAL'
  /** Idempotency-Key → stored response (API-BR-03, API-BT-04). */
  idempotency: Record<string, { status: number; body: unknown }>
  /** Demo mode only: the accounts of the demo Google identity. */
  account: MockOwnerAccount
  workshopAccount: MockWorkshopAccount
  notificationSettings: MockNotificationSettings
}

const STORAGE_KEY = 'evcare.mockApi.v1'
const VERSION = 3

export const DEMO_EMAIL = 'demo.evcare@gmail.com'

export function newOwnerAccount(): MockOwnerAccount {
  return {
    userId: 1001,
    email: DEMO_EMAIL,
    displayName: 'Minh Anh',
    createdAt: null,
    status: 'ONBOARDING_IN_PROGRESS',
    profile: null,
    profileCompletedAt: null,
    completedAt: null,
    location: null,
    consents: { personalDataProcessing: null, oemDataSharing: null },
    vehicleRequest: null,
    verification: null,
    remainingAttempts: 5,
  }
}

export function newWorkshopAccount(): MockWorkshopAccount {
  return {
    ownerId: 'demo-workshop-owner',
    email: DEMO_EMAIL,
    displayName: 'Minh Anh',
    createdAt: null,
    lastLoginAt: null,
    lastLogoutAt: null,
    status: 'ONBOARDING_IN_PROGRESS',
    profile: null,
    profileCompletedAt: null,
    completedAt: null,
    registration: null,
    verification: null,
    failedAttempts: 0,
    consents: { personalDataProcessing: null, oemDataSharing: null },
    workshopId: null,
  }
}

function empty(): MockDb {
  return {
    version: VERSION,
    seededAt: null,
    owner: { fullName: 'Chủ xe', phone: '0900000000' },
    workshops: [],
    vehicles: [],
    bookings: [],
    followUps: [],
    slotBlocks: [],
    tokens: [],
    holdTokens: [],
    confirmationMode: 'MANUAL',
    idempotency: {},
    account: newOwnerAccount(),
    workshopAccount: newWorkshopAccount(),
    notificationSettings: { remindersEnabled: true, reminderLeadDays: 7, channels: {} },
  }
}

let demoMode = false

/** Demo mode (no backend): the mock owns accounts, vehicles and slots instead of learning them. */
export function isDemo(): boolean {
  return demoMode
}

export function setDemo(value: boolean): void {
  demoMode = value
}

let db: MockDb | null = null

export function getDb(): MockDb {
  if (db) return db
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? (JSON.parse(raw) as MockDb) : null
    db = parsed && parsed.version === VERSION ? parsed : empty()
  } catch {
    db = empty()
  }
  return db
}

export function save(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(getDb()))
  } catch {
    // Storage blocked: the state lasts for this page only.
  }
}

// The owner app and the Workshop Portal open side by side in two tabs: re-read after the other tab writes.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', event => {
    if (event.key === STORAGE_KEY) db = null
  })
}

/** Clears every mock record (also exposed as `window.evcareMock.reset()`). */
export function resetDb(): void {
  db = empty()
  save()
}

// ---------------------------------------------------------------- ids & time

export function uuid(): string {
  return crypto.randomUUID()
}

export function bookingCode(): string {
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(4)), byte => byte.toString(16).padStart(2, '0')).join('')
  return `EVC-${hex.toUpperCase()}`
}

const TIME_ZONE = 'Asia/Ho_Chi_Minh'

export function nowIso(): string {
  return new Date().toISOString()
}

export function todayVn(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE }).format(now)
}

export function addDays(day: string, amount: number): string {
  return todayVn(new Date(new Date(`${day}T12:00:00+07:00`).getTime() + amount * 86_400_000))
}

/** `HH:mm` (accepts `HH:mm:ss`). */
export function hhmm(timeSlot: string): string {
  return timeSlot.slice(0, 5)
}

/** UTC ISO of a Vietnam calendar day + `HH:mm`. */
export function appointmentAt(date: string, timeSlot: string): string {
  return new Date(`${date}T${hhmm(timeSlot)}:00+07:00`).toISOString()
}

export function hoursFromNow(hours: number): string {
  return new Date(Date.now() + hours * 3_600_000).toISOString()
}

export function isoMinus(iso: string, minutes: number): string {
  return new Date(new Date(iso).getTime() - minutes * 60_000).toISOString()
}

/** Deterministic 0..1 value from a string (stable prices, stable demo data). */
export function hash01(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 10_000) / 10_000
}

export function maskPlate(plate: string): string {
  const clean = plate.replace(/\s+/g, '')
  // `30A12345` → series `30A` + `123.45` (the optional series digit only when 3+2 digits remain).
  const match = /^(\d{2}[A-Z]{1,2}\d?)[-.]?(\d{3})[.]?(\d{2})$/i.exec(clean)
  if (!match) return clean.length > 4 ? `${clean.slice(0, 3)}***${clean.slice(-2)}` : clean
  return `${match[1].toUpperCase()}-***.${match[3]}`
}

/** Accent-insensitive lower-case text ("Hà Nội" matches "ha noi"). */
export function fold(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
    .trim()
}

/** Great-circle distance in km (haversine). */
export function distanceKm(from: { lat: number; lng: number }, to: { lat: number; lng: number }): number {
  const rad = (degrees: number) => (degrees * Math.PI) / 180
  const dLat = rad(to.lat - from.lat)
  const dLng = rad(to.lng - from.lng)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(from.lat)) * Math.cos(rad(to.lat)) * Math.sin(dLng / 2) ** 2
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

/** Whole days from `from` to `to` (Vietnam calendar days). */
export function daysBetween(from: string, to: string): number {
  return Math.round((new Date(`${to}T12:00:00+07:00`).getTime() - new Date(`${from}T12:00:00+07:00`).getTime()) / 86_400_000)
}
