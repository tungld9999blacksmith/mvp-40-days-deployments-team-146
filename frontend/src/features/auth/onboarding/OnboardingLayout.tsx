import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { LogOut, Zap } from 'lucide-react'
import Stepper from '@/shared/ui/Stepper'
import { Notice } from '@/shared/ui/States'
import { formatDate } from '@/shared/utils/format'
import { useAuth } from '../context/AuthContext'
import SplashScreen from '../components/SplashScreen'
import LogoutConfirmDialog from '../components/LogoutConfirmDialog'
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
  const [logoutOpen, setLogoutOpen] = useState(false)

  // Prefill data, remaining attempts and resume state (AF-002, EDGE-001).
  useEffect(() => {
    if (!snapshot) void loadSnapshot()
  }, [snapshot, loadSnapshot])

  const current = stepIndex(location.pathname)
  const completed = onboarding?.status === 'ACTIVE' ? 3 : onboarding?.profileCompleted ? 1 : 0
  const expiresAt = onboarding?.expiresAt

  return (
    <div className="min-h-screen bg-background">
      <header className="h-16 bg-surface border-b border-border">
        <div className="max-w-3xl mx-auto h-full px-4 sm:px-6 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald flex items-center justify-center flex-shrink-0">
            <Zap className="w-4 h-4 text-background" strokeWidth={2.5} />
          </div>
          <span className="text-foreground font-bold tracking-tight">EV Care</span>
          <span className="hidden sm:inline text-muted text-sm">· Thiết lập tài khoản</span>
          <span className="ml-auto hidden md:inline text-sm text-muted truncate max-w-[220px]">{user?.email}</span>
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

      <main className="max-w-xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <div className="mb-8">
          <Stepper steps={STEPS} current={current} completed={completed} />
        </div>
        {expiresAt && onboarding?.status !== 'ACTIVE' && (
          <Notice className="mb-6">Hoàn tất trước {formatDate(expiresAt)} để giữ dữ liệu đã nhập.</Notice>
        )}
        <Outlet />
      </main>

      <LogoutConfirmDialog open={logoutOpen} onClose={() => setLogoutOpen(false)} onConfirm={logout} />
    </div>
  )
}

/** Layout of `/onboarding/*` — no sidebar, the main features are locked until ACTIVE (BR-003). */
export default function OnboardingLayout() {
  const { authStatus, onboarding, bootError, retryBootstrap } = useAuth()
  if (authStatus === 'initializing') return <SplashScreen error={bootError} onRetry={retryBootstrap} />
  if (authStatus !== 'signed-in' || !onboarding) return <Navigate to="/" replace />
  return (
    <OnboardingProvider>
      <OnboardingShell />
    </OnboardingProvider>
  )
}
