import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { resolveOnboardingRoute } from '../navigation'

/** `/onboarding` → the step the backend points at. */
export default function OnboardingIndex() {
  const { onboarding } = useAuth()
  return <Navigate to={onboarding ? resolveOnboardingRoute(onboarding) : '/'} replace />
}
