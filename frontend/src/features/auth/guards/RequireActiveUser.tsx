import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { resolveOnboardingRoute } from '../navigation'
import SplashScreen from '../components/SplashScreen'

/** Owner routes need a session and a completed onboarding (BR-003, US-001 FE §4.7). */
export default function RequireActiveUser() {
  const { authStatus, onboarding, bootError, retryBootstrap, rememberReturnTo } = useAuth()
  const location = useLocation()

  if (authStatus === 'initializing') return <SplashScreen error={bootError} onRetry={retryBootstrap} />
  if (authStatus !== 'signed-in' || !onboarding) {
    rememberReturnTo(location.pathname + location.search)
    return <Navigate to="/" replace />
  }
  if (onboarding.status !== 'ACTIVE') return <Navigate to={resolveOnboardingRoute(onboarding)} replace />
  return <Outlet />
}
