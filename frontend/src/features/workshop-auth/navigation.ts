import type { WorkshopOnboardingState } from './types'

/** Single place deciding the Workshop Portal route from `nextStep` (US-009 FE §13.2). */
export function resolveWorkshopRoute(onboarding: Pick<WorkshopOnboardingState, 'nextStep' | 'status'>): string {
  switch (onboarding.nextStep) {
    case 'DASHBOARD':
      return '/technician'
    case 'VERIFYING':
      return '/workshop/onboarding/verifying'
    case 'PROFILE':
      return '/workshop/onboarding/profile'
    case 'WORKSHOP':
      return onboarding.status === 'VERIFICATION_FAILED'
        ? '/workshop/onboarding/failed'
        : '/workshop/onboarding/operations'
    default:
      return '/workshop/onboarding/profile'
  }
}
