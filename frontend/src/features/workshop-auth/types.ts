/** Workshop owner types — API-SPEC-AUTH-003 (us-009) and API-SPEC-AUTH-004 (us-013). */

export type WorkshopOnboardingStatus =
  | 'ONBOARDING_IN_PROGRESS'
  | 'PENDING_WORKSHOP_VERIFICATION'
  | 'VERIFICATION_FAILED'
  | 'ACTIVE'

export type WorkshopNextStep = 'PROFILE' | 'WORKSHOP' | 'VERIFYING' | 'DASHBOARD'

export interface WorkshopOnboardingState {
  status: WorkshopOnboardingStatus
  nextStep: WorkshopNextStep
  profileCompleted: boolean
  profileCompletedAt: string | null
  completedAt: string | null
  expiresAt: string | null
}

export interface WorkshopOwner {
  ownerId: string
  email: string
  displayName: string | null
  avatarUrl: string | null
  fullName: string | null
  accountStatus: string
  roles: string[]
}

export interface OperatingHour {
  dayOfWeek: number
  isClosed: boolean
  openTime: string | null
  closeTime: string | null
}

export type ServiceCenterType = 'DEALER' | 'SERVICE_ONLY'

export interface WorkshopSummary {
  workshopId: string
  centerId: string
  name: string
  region: string
  type: ServiceCenterType | string
  status: string
  address: string
  latitude: number | null
  longitude: number | null
  hotline: string | null
  totalTechnicians: number
  emergencySlotsReserved: number
  operatingHours: OperatingHour[]
  onboardedAt: string | null
}

export type WorkshopFailureReason = 'MANAGER_NOT_FOUND' | 'NATIONAL_ID_MISMATCH' | 'ALREADY_CLAIMED' | 'OEM_UNAVAILABLE'

export interface WorkshopRegistration {
  registrationId: string
  address: string
  latitude: number | null
  longitude: number | null
  hotline: string
  totalTechnicians: number
  emergencySlotsReserved: number
  operatingHours: OperatingHour[]
  verificationStatus: 'PENDING' | 'VERIFIED' | 'FAILED'
  failureReason: WorkshopFailureReason | null
}

export interface WorkshopAttempt {
  attemptId: string
  status: 'PENDING' | 'VERIFIED' | 'FAILED'
  failureReason: WorkshopFailureReason | null
  retryCount?: number
  requestedAt?: string
  respondedAt?: string | null
  failedAttemptsLast24h: number
  maxFailedAttempts: number
}

export interface WorkshopSignInData {
  isNewOwner: boolean
  owner: WorkshopOwner
  onboarding: WorkshopOnboardingState
  workshop: WorkshopSummary | null
}

export interface WorkshopSession {
  ownerId: string
  email: string
  accountStatus: string
  onboarding: WorkshopOnboardingState
  lastLoginAt: string | null
  lastLogoutAt: string | null
}

export interface ConsentState {
  granted: boolean
  policyVersion: string
}

export interface WorkshopOnboardingSnapshot {
  onboarding: WorkshopOnboardingState
  profile: {
    email: string
    fullName: string | null
    phoneNumber: string | null
    nationalIdMasked: string | null
  }
  registration: WorkshopRegistration | null
  latestAttempt: WorkshopAttempt | null
  consents: Record<string, ConsentState | null>
  workshop: WorkshopSummary | null
}

export interface WorkshopVerificationData {
  onboarding: WorkshopOnboardingState
  verification: WorkshopAttempt
  workshop: WorkshopSummary | null
}

export interface WorkshopVerificationRequest {
  address: string
  latitude: number | null
  longitude: number | null
  hotline: string
  totalTechnicians: number
  emergencySlotsReserved: number
  operatingHours: OperatingHour[]
  oemDataSharingConsent: ConsentState
}
