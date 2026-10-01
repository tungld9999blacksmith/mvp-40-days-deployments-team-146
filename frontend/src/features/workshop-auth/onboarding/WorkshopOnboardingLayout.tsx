import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { LogOut, Zap } from 'lucide-react'
import Stepper from '@/shared/ui/Stepper'
import { Notice } from '@/shared/ui/States'
import { formatDate } from '@/shared/utils/format'
import SplashScreen from '@/features/auth/components/SplashScreen'
import LogoutConfirmDialog from '@/features/auth/components/LogoutConfirmDialog'
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
  const [logoutOpen, setLogoutOpen] = useState(false)

  useEffect(() => {
    if (!snapshot) void loadSnapshot()
  }, [snapshot, loadSnapshot])

  const current = stepIndex(location.pathname)
  const completed = onboarding?.status === 'ACTIVE' ? 3 : onboarding?.profileCompleted ? 1 : 0
  const operationsPage = location.pathname.endsWith('/operations')

  return (
    <div className="min-h-screen bg-background">
      <header className="h-16 bg-surface border-b border-border">
        <div className="max-w-3xl mx-auto h-full px-4 sm:px-6 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald flex items-center justify-center flex-shrink-0">
            <Zap className="w-4 h-4 text-background" strokeWidth={2.5} />
          </div>
          <span className="text-foreground font-bold tracking-tight">EV Care</span>
          <span className="text-xs font-semibold text-emerald">Workshop Portal</span>
          <span className="ml-auto hidden md:inline text-sm text-muted truncate max-w-[220px]">{owner?.email}</span>
          <button
            type="button"
            onClick={() => setLogoutOpen(true)}
            className="ml-auto md:ml-2 flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-muted hover:text-error hover:bg-error/10 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Đăng xuất
          </button>
        </div>
      </header>

      <main className={`${operationsPage ? 'max-w-3xl' : 'max-w-xl'} mx-auto px-4 sm:px-6 py-8 sm:py-10`}>
        <div className="mb-8">
          <Stepper steps={STEPS} current={current} completed={completed} />
        </div>
        {onboarding?.expiresAt && onboarding.status !== 'ACTIVE' && (
          <Notice className="mb-6">Hoàn tất trước {formatDate(onboarding.expiresAt)} để giữ dữ liệu đã nhập.</Notice>
        )}
        <Outlet />
      </main>

      <LogoutConfirmDialog
        open={logoutOpen}
        onClose={() => setLogoutOpen(false)}
        onConfirm={logout}
        title="Đăng xuất khỏi Workshop Portal?"
        description="Bạn sẽ cần đăng nhập lại bằng Google để tiếp tục."
        note="Nếu Gmail này cũng dùng ứng dụng EV Care dành cho chủ xe, bạn có thể phải đăng nhập lại ứng dụng đó."
      />
    </div>
  )
}

/** `/workshop/onboarding/*` layout (US-009 FE §3.1). */
export default function WorkshopOnboardingLayout() {
  const { authStatus, onboarding, bootError, retryBootstrap } = useWorkshopAuth()
  if (authStatus === 'initializing') {
    return <SplashScreen brand="Workshop Portal" label="Đang kiểm tra phiên đăng nhập..." error={bootError} onRetry={retryBootstrap} />
  }
  if (authStatus !== 'signed-in' || !onboarding) return <Navigate to="/workshop/login" replace />
  return (
    <WorkshopOnboardingProvider>
      <Shell />
    </WorkshopOnboardingProvider>
  )
}
