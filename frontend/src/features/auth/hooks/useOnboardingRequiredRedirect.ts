import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { isApiError, type ApiError } from '@/shared/api/client'
import { useAuth } from '../context/AuthContext'
import { resolveOnboardingRoute } from '../navigation'
import * as authApi from '../api'

/**
 * A feature API answered `403 ONBOARDING_REQUIRED` (BR-003): refresh the onboarding
 * state from API-002 and send the owner to the step the backend points at.
 */
export function useOnboardingRequiredRedirect(error: ApiError | null | undefined) {
  const { setOnboarding } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!isApiError(error, 'ONBOARDING_REQUIRED')) return
    let cancelled = false
    authApi
      .getOnboarding()
      .then(data => {
        if (cancelled) return
        setOnboarding(data.onboarding)
        navigate(resolveOnboardingRoute(data.onboarding), { replace: true })
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [error, navigate, setOnboarding])
}
