import { apiGet, apiRequest, type ApiResponse } from '@/shared/api/client'
import type {
  ConsentState,
  WorkshopOnboardingSnapshot,
  WorkshopOnboardingState,
  WorkshopSession,
  WorkshopSignInData,
  WorkshopVerificationData,
  WorkshopVerificationRequest,
} from './types'

const BASE = '/workshop-owner'

/** API-201 — account sync after Google sign-in (the backend writes a `login` audit log). */
export function signIn(): Promise<ApiResponse<WorkshopSignInData>> {
  return apiRequest<WorkshopSignInData>(`${BASE}/oauth/sign-in`, { method: 'POST', skipSessionExpiry: true, timeoutMs: 15_000 })
}

/** API-302 — session check with revocation. */
export function getSession(): Promise<WorkshopSession> {
  return apiGet<WorkshopSession>(`${BASE}/oauth/session`, { skipSessionExpiry: true, timeoutMs: 10_000 })
}

/** API-301 — logout, 204. */
export async function logout(): Promise<void> {
  await apiRequest<void>(`${BASE}/oauth/logout`, { method: 'POST', skipSessionExpiry: true, timeoutMs: 5_000 })
}

/** API-202 */
export function getOnboarding(): Promise<WorkshopOnboardingSnapshot> {
  return apiGet<WorkshopOnboardingSnapshot>(`${BASE}/onboarding`, { timeoutMs: 10_000 })
}

/** API-203 */
export async function updateProfile(body: {
  fullName: string
  phoneNumber: string
  nationalId: string
  personalDataConsent: ConsentState
}): Promise<{ onboarding: WorkshopOnboardingState; profile: WorkshopOnboardingSnapshot['profile'] }> {
  return (
    await apiRequest<{ onboarding: WorkshopOnboardingState; profile: WorkshopOnboardingSnapshot['profile'] }>(
      `${BASE}/onboarding/profile`,
      { method: 'PUT', body, timeoutMs: 15_000 },
    )
  ).data
}

/** API-204 — 200 VERIFIED/FAILED, 202 PENDING. */
export function submitWorkshopVerification(
  body: WorkshopVerificationRequest,
  idempotencyKey: string,
): Promise<ApiResponse<WorkshopVerificationData>> {
  return apiRequest<WorkshopVerificationData>(`${BASE}/onboarding/workshop-verification`, {
    method: 'POST',
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    timeoutMs: 15_000,
  })
}
