import type { OnboardingState } from './types'

/** Single place deciding the owner onboarding route from the backend `nextStep` (US-001 FE §13.2). */
export function resolveOnboardingRoute(onboarding: Pick<OnboardingState, 'nextStep' | 'status'>): string {
  switch (onboarding.nextStep) {
    case 'HOME':
      return '/dashboard'
    case 'VERIFYING':
      return '/onboarding/verifying'
    case 'PROFILE':
      return '/onboarding/profile'
    case 'VEHICLE':
      return onboarding.status === 'VERIFICATION_FAILED' ? '/onboarding/failed' : '/onboarding/vehicle'
    default:
      return '/onboarding/profile'
  }
}
