import { Navigate, Outlet } from 'react-router-dom'
import SplashScreen from '@/features/auth/components/SplashScreen'
import { useWorkshopAuth } from '../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../navigation'

/** `/technician/*` needs a Workshop Portal session and a completed onboarding (BR-203). */
export default function RequireActiveWorkshopOwner() {
  const { authStatus, onboarding, bootError, retryBootstrap } = useWorkshopAuth()
  if (authStatus === 'initializing') {
    return <SplashScreen brand="Workshop Portal" label="Đang kiểm tra phiên đăng nhập..." error={bootError} onRetry={retryBootstrap} />
  }
  if (authStatus !== 'signed-in' || !onboarding) return <Navigate to="/workshop/login" replace />
  if (onboarding.status !== 'ACTIVE') return <Navigate to={resolveWorkshopRoute(onboarding)} replace />
  return <Outlet />
}
