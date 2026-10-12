import { Navigate, Outlet, useLocation } from 'react-router-dom'
import SplashScreen from '@/features/auth/components/SplashScreen'
import { useCurrentVehicle } from './CurrentVehicleContext'
import { selectVehiclePath } from './resolve'

/**
 * An owner with several vehicles picks one before the owner screens open. A failed list is left to
 * the screens (VehicleGate shows the error and handles ONBOARDING_REQUIRED).
 */
export default function RequireCurrentVehicle() {
  const { vehicles, resolution, error } = useCurrentVehicle()
  const location = useLocation()

  if (resolution?.kind === 'needs-selection') {
    return <Navigate to={selectVehiclePath(location.pathname + location.search)} replace />
  }
  // Wait for the list so the first vehicle's dashboard never flashes before the picker.
  if (vehicles === null && !error) return <SplashScreen label="Đang tải xe của bạn..." />
  return <Outlet />
}
