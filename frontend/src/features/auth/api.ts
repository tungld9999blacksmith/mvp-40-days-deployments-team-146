import { apiGet, apiRequest, type ApiResponse } from '@/shared/api/client'
import type {
  OnboardingSnapshot,
  OnboardingState,
  OnboardingProfile,
  OnboardingLocation,
  ProfileUpdateRequest,
  SignInData,
  VehicleModel,
  VehicleVerificationRequest,
  VerificationData,
} from './types'

/** API-001 — sync the account right after Google sign-in. 201 = new account. */
export function signIn(): Promise<ApiResponse<SignInData>> {
  return apiRequest<SignInData>('/oauth/sign-in', { method: 'POST', skipSessionExpiry: true, timeoutMs: 15_000 })
}

/** API-101 — record the logout and queue the refresh-token revoke. 204. */
export async function logout(): Promise<void> {
  await apiRequest<void>('/oauth/logout', { method: 'POST', skipSessionExpiry: true, timeoutMs: 5_000 })
}

/** API-102 — the only owner endpoint checking token revocation. */
export function getProfile(): Promise<{ uid: string; email: string | null }> {
  return apiGet('/oauth/profile', { skipSessionExpiry: true, timeoutMs: 10_000 })
}

/** API-002 — onboarding state + saved data (resume, polling). */
export function getOnboarding(signal?: AbortSignal): Promise<OnboardingSnapshot> {
  return apiGet<OnboardingSnapshot>('/onboarding', { signal, timeoutMs: 10_000 })
}

/** API-003 — save personal info + nearby location + consent. */
export async function updateProfile(
  body: ProfileUpdateRequest,
): Promise<{ onboarding: OnboardingState; profile: OnboardingProfile; location: OnboardingLocation }> {
  return (await apiRequest<{ onboarding: OnboardingState; profile: OnboardingProfile; location: OnboardingLocation }>(
    '/onboarding/profile',
    { method: 'PUT', body, timeoutMs: 15_000 },
  )).data
}

/** API-004 — manufacturer models for the dropdown. */
export function getVehicleModels(): Promise<{ items: VehicleModel[] }> {
  return apiGet<{ items: VehicleModel[] }>('/onboarding/vehicle-models', { timeoutMs: 10_000 })
}

/** API-005 — submit the vehicle to the manufacturer. 200 VERIFIED/FAILED, 202 PENDING. */
export function submitVehicleVerification(
  body: VehicleVerificationRequest,
  idempotencyKey: string,
): Promise<ApiResponse<VerificationData>> {
  return apiRequest<VerificationData>('/onboarding/vehicle-verification', {
    method: 'POST',
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    // The backend waits up to ~8 s for the manufacturer before answering 202.
    timeoutMs: 15_000,
  })
}
