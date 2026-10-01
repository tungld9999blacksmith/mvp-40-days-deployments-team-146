/** Owner account & onboarding types — API-SPEC-AUTH-001 (us-001), backend vehicle_owner_onboarding. */

export type OnboardingStatus =
  | 'ONBOARDING_IN_PROGRESS'
  | 'PENDING_VEHICLE_VERIFICATION'
  | 'VERIFICATION_FAILED'
  | 'ACTIVE'

export type NextStep = 'PROFILE' | 'VEHICLE' | 'VERIFYING' | 'HOME'

export interface OnboardingState {
  status: OnboardingStatus
  nextStep: NextStep
  profileCompleted: boolean
  profileCompletedAt: string | null
  completedAt: string | null
  expiresAt?: string | null
}

export interface SignInUser {
  userId: number
  email: string | null
  displayName: string | null
  avatarUrl: string | null
  fullName: string | null
  accountStatus: string
  roles: string[]
}

export interface SignInData {
  isNewUser: boolean
  user: SignInUser
  onboarding: OnboardingState
}

export type LocationSource = 'MANUAL' | 'MAP_PICK' | 'GPS'

export interface OnboardingProfile {
  email: string | null
  displayName: string | null
  fullName: string | null
  phoneNumber: string | null
  nationalIdMasked: string | null
  dateOfBirth: string | null
}

export interface OnboardingLocation {
  addressLine: string
  ward: string | null
  district: string | null
  province: string
  latitude: number | string | null
  longitude: number | string | null
  source: LocationSource
}

export type VehicleVerificationStatus = 'PENDING' | 'VERIFIED' | 'FAILED'

export type VerificationFailureReason =
  | 'VIN_NOT_FOUND'
  | 'PLATE_MISMATCH'
  | 'MODEL_MISMATCH'
  | 'OWNER_MISMATCH'
  | 'OWNER_EMAIL_MISMATCH'
  | 'NATIONAL_ID_MISMATCH'
  | 'ALREADY_LINKED'
  | 'OEM_UNAVAILABLE'

export interface VehicleSpec {
  modelId: string | null
  modelName: string | null
  trim: string | null
  color: string | null
  manufactureDate: string | null
  productionYear: number | null
  batteryCapacityKwh: number | string | null
  motorPowerKw: number | string | null
}

export interface OnboardingVehicle {
  vehicleId: string
  vin: string
  licensePlate: string
  declaredModelId: string
  declaredManufactureYear?: number | null
  verificationStatus: VehicleVerificationStatus
  verificationFailureReason: VerificationFailureReason | null
  verifiedAt: string | null
  spec: VehicleSpec | null
}

export type WarrantyComponent = 'BATTERY' | 'MOTOR' | 'CHASSIS' | 'ELECTRONICS'

export interface OnboardingWarranty {
  component: WarrantyComponent | string
  startDate: string
  endDate: string
  kmLimit: number | null
  durationMonths: number | null
  status: string
  termsDescription: string | null
}

export interface ConsentState {
  granted: boolean
  policyVersion: string
}

export interface LatestVerification {
  attemptId: string
  status: VehicleVerificationStatus
  failureReason: VerificationFailureReason | null
  requestedAt: string
  respondedAt: string | null
}

export interface OnboardingSnapshot {
  onboarding: OnboardingState
  profile: OnboardingProfile
  location: OnboardingLocation | null
  vehicle: OnboardingVehicle | null
  warranties: OnboardingWarranty[]
  latestVerification: LatestVerification | null
  remainingAttempts: number
  consents: Record<string, ConsentState | null>
}

export interface VehicleModel {
  modelId: string
  modelName: string
  trim: string | null
  productionYear: number | null
}

export interface VerificationResult {
  attemptId: string
  status: VehicleVerificationStatus
  failureReason: VerificationFailureReason | null
  message: string
  remainingAttempts: number
}

export interface VerificationData {
  onboarding: OnboardingState
  verification: VerificationResult
  vehicle: OnboardingVehicle
  warranties: OnboardingWarranty[]
}

export interface ProfileUpdateRequest {
  fullName: string
  phoneNumber: string
  nationalId: string
  dateOfBirth: string | null
  location: {
    addressLine: string
    ward: string | null
    district: string | null
    province: string
    latitude: null
    longitude: null
    source: LocationSource
    placeId: null
  }
  personalDataConsent: ConsentState
}

export interface VehicleVerificationRequest {
  vin: string
  licensePlate: string
  modelId: string
  manufactureYear: number | null
  oemDataSharingConsent: ConsentState
}
