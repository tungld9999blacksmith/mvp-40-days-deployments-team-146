import { Navigate } from 'react-router-dom'
import { useWorkshopAuth } from '../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../navigation'

/** `/workshop/onboarding` → the step the backend points at. */
export default function WorkshopOnboardingIndex() {
  const { onboarding } = useWorkshopAuth()
  return <Navigate to={onboarding ? resolveWorkshopRoute(onboarding) : '/workshop/login'} replace />
}
