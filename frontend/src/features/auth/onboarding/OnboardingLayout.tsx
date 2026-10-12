import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import Stepper from '@/shared/ui/Stepper'
import { Notice } from '@/shared/ui/States'
import { formatDate } from '@/shared/utils/format'
import { useAuth } from '../context/AuthContext'
import SplashScreen from '../components/SplashScreen'
import StandaloneHeader from '../components/StandaloneHeader'
import { OnboardingProvider, useOnboarding } from './OnboardingContext'

const STEPS = ['Thông tin cá nhân', 'Thông tin xe', 'Xác thực']

function stepIndex(pathname: string): number {
  if (pathname.endsWith('/profile')) return 0
  if (pathname.endsWith('/vehicle')) return 1
  return 2
}

function OnboardingShell() {
  const { user, onboarding, logout } = useAuth()
  const { snapshot, loadSnapshot } = useOnboarding()
  const location = useLocation()

  // Prefill data, remaining attempts and resume state (AF-002, EDGE-001).
  useEffect(() => {
    if (!snapshot) void loadSnapshot()
  }, [snapshot, loadSnapshot])

  const current = stepIndex(location.pathname)
  const completed = onboarding?.status === 'ACTIVE' ? 3 : onboarding?.profileCompleted ? 1 : 0
  const expiresAt = onboarding?.expiresAt

  return (
    <div className="min-h-screen bg-background">
      <StandaloneHeader
        width="max-w-3xl"
        label={<span className="hidden sm:inline text-muted text-sm">· Thiết lập tài khoản</span>}
        email={user?.email}
        onLogout={logout}
      />

      <main className="max-w-xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <div className="mb-8">
          <Stepper steps={STEPS} current={current} completed={completed} />
        </div>
        {expiresAt && onboarding?.status !== 'ACTIVE' && (
          <Notice className="mb-6">Hoàn tất trước {formatDate(expiresAt)} để giữ dữ liệu đã nhập.</Notice>
        )}
        <Outlet />
      </main>
    </div>
  )
}

/** Layout of `/onboarding/*` — no sidebar, the main features are locked until ACTIVE (BR-003). */
export default function OnboardingLayout() {
  const { authStatus, onboarding, bootError, retryBootstrap } = useAuth()
  const location = useLocation()
  if (authStatus === 'initializing') return <SplashScreen error={bootError} onRetry={retryBootstrap} />
  if (authStatus !== 'signed-in' || !onboarding) return <Navigate to="/" replace />
  if (onboarding.status === 'ACTIVE' && !['/onboarding/verifying', '/onboarding/success'].includes(location.pathname)) {
    return <Navigate to="/dashboard" replace />
  }
  return (
    <OnboardingProvider>
      <OnboardingShell />
    </OnboardingProvider>
  )
}
