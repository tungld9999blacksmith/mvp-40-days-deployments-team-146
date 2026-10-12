// Browser-only integration harness. This entry is not imported by the product build.
import { useCallback, type ContextType } from 'react'
import { createRoot } from 'react-dom/client'
import { createMemoryRouter, Link, Outlet, RouterProvider } from 'react-router-dom'
import { AuthContext } from '../../src/features/auth/context/AuthContext'
import NotificationSettings from '../../src/features/notifications/pages/NotificationSettings'
import ReminderDetail from '../../src/features/notifications/pages/ReminderDetail'
import MaintenanceStatusCard from '../../src/features/vehicles/components/MaintenanceStatusCard'
import TripPlanningCard from '../../src/features/vehicles/components/TripPlanningCard'
import { getMaintenanceStatus } from '../../src/features/vehicles/api'
import { configureApiClient } from '../../src/shared/api/client'
import { useCachedQuery } from '../../src/shared/hooks/useCachedQuery'
import { ToastProvider } from '../../src/shared/ui/Toast'
import '../../src/styles/index.css'

configureApiClient({ getToken: async () => 'fixture-owner', onUnauthorized: () => {} })
const fixture = await fetch('/api/v1/__fixture/info').then(response => response.json())
const auth = {
  authStatus: 'signed-in', user: null, onboarding: null, displayName: 'Fixture owner',
  sessionNotice: null, loginError: null, bootError: null, isSigningIn: false, isLoggingOut: false,
  signIn: async () => {}, retryBootstrap: () => {}, logout: async () => true,
  setOnboarding: () => {}, clearLoginError: () => {}, expireSession: () => {},
  rememberReturnTo: () => {}, consumeReturnTo: () => null,
} as NonNullable<ContextType<typeof AuthContext>>

function Vehicle() {
  const fetcher = useCallback(() => getMaintenanceStatus(fixture.vehicleId), [])
  const query = useCachedQuery(`maintenance:${fixture.vehicleId}`, fetcher)
  return <div className="p-4 max-w-2xl space-y-5"><h1 className="text-2xl font-bold mb-4">Xe của tôi</h1><MaintenanceStatusCard status={query.data} error={query.error} onRetry={() => void query.refetch()} variant="full" /><TripPlanningCard vehicleId={fixture.vehicleId} /></div>
}
function Layout() {
  return <AuthContext.Provider value={auth}><ToastProvider><nav aria-label="Kiểm thử" className="p-4 flex gap-4"><Link to="/notifications/settings">Cài đặt</Link><Link to="/vehicle">Xe</Link></nav><main><Outlet /></main></ToastProvider></AuthContext.Provider>
}
const params = new URLSearchParams(location.search)
const initial = params.get('screen') === 'vehicle' ? '/vehicle' : params.get('reminderId') ? `/notifications/reminders/${params.get('reminderId')}` : '/notifications/settings'
const router = createMemoryRouter([{ element: <Layout />, children: [
  { path: '/notifications/settings', element: <NotificationSettings /> },
  { path: '/vehicle', element: <Vehicle /> },
  { path: '/notifications/reminders/:reminderId', element: <ReminderDetail /> },
  { path: '*', element: <p>Đường dẫn thao tác được kiểm tra trong test.</p> },
]}], { initialEntries: [initial] })
createRoot(document.getElementById('root')!).render(<RouterProvider router={router} />)
