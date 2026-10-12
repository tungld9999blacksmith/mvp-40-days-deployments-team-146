import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import Stepper from '@/shared/ui/Stepper'
import { Notice } from '@/shared/ui/States'
import { formatDate } from '@/shared/utils/format'
import SplashScreen from '@/features/auth/components/SplashScreen'
import StandaloneHeader from '@/features/auth/components/StandaloneHeader'
import { useWorkshopAuth } from '../context/WorkshopAuthContext'
import { WorkshopOnboardingProvider, useWorkshopOnboarding } from './WorkshopOnboardingContext'

const STEPS = ['Thông tin chủ xưởng', 'Vận hành xưởng', 'Xác thực']

function stepIndex(pathname: string): number {
  if (pathname.endsWith('/profile')) return 0
  if (pathname.endsWith('/operations')) return 1
  return 2
}

function Shell() {
  const { owner, onboarding, logout } = useWorkshopAuth()
  const { snapshot, loadSnapshot } = useWorkshopOnboarding()
  const location = useLocation()

  useEffect(() => {
    if (!snapshot) void loadSnapshot()
  }, [snapshot, loadSnapshot])

  const current = stepIndex(location.pathname)
  const completed = onboarding?.status === 'ACTIVE' ? 3 : onboarding?.profileCompleted ? 1 : 0
  const operationsPage = location.pathname.endsWith('/operations')

  return (
    <div className="min-h-screen bg-background">
      <StandaloneHeader
        width="max-w-3xl"
        label={<span className="text-xs font-semibold text-emerald">Workshop Portal</span>}
        email={owner?.email}
        onLogout={logout}
        logoutDialog={{
          title: 'Đăng xuất khỏi Workshop Portal?',
          description: 'Bạn sẽ cần đăng nhập lại bằng Google để tiếp tục.',
          note: 'Nếu Gmail này cũng dùng ứng dụng EV Care dành cho chủ xe, bạn có thể phải đăng nhập lại ứng dụng đó.',
        }}
      />

      <main className={`${operationsPage ? 'max-w-3xl' : 'max-w-xl'} mx-auto px-4 sm:px-6 py-8 sm:py-10`}>
        <div className="mb-8">
          <Stepper steps={STEPS} current={current} completed={completed} />
        </div>
        {onboarding?.expiresAt && onboarding.status !== 'ACTIVE' && (
          <Notice className="mb-6">Hoàn tất trước {formatDate(onboarding.expiresAt)} để giữ dữ liệu đã nhập.</Notice>
        )}
        <Outlet />
      </main>
    </div>
  )
}

/** `/workshop/onboarding/*` layout (US-009 FE §3.1). */
export default function WorkshopOnboardingLayout() {
  const { authStatus, onboarding, bootError, retryBootstrap } = useWorkshopAuth()
  const location = useLocation()
  if (authStatus === 'initializing') {
    return <SplashScreen brand="Workshop Portal" label="Đang kiểm tra phiên đăng nhập..." error={bootError} onRetry={retryBootstrap} />
  }
  if (authStatus !== 'signed-in' || !onboarding) return <Navigate to="/workshop/login" replace />
  if (onboarding.status === 'ACTIVE' && !['/workshop/onboarding/verifying', '/workshop/onboarding/success'].includes(location.pathname)) {
    return <Navigate to="/technician" replace />
  }
  return (
    <WorkshopOnboardingProvider>
      <Shell />
    </WorkshopOnboardingProvider>
  )
}
