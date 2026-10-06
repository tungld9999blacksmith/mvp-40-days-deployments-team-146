const STANDALONE_DEMO_MODE = false
import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Notice } from '@/shared/ui/States'
import { isAuthConfigured } from '@/shared/config/env'
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus'
import { useAuth } from '../context/AuthContext'
import { resolveOnboardingRoute } from '../navigation'
import { blockingLoginContent, inlineLoginMessage, SESSION_NOTICE_TEXT } from '../messages'
import AuthBrandPanel from '../components/AuthBrandPanel'
import GoogleSignInButton from '../components/GoogleSignInButton'
import LoginErrorPanel from '../components/LoginErrorPanel'
import SplashScreen from '../components/SplashScreen'
import { getPortal } from '../portal'
import Logo from '@/shared/ui/Logo'

/** SCR-001 / SCR-101 — owner login (Google only). */
export default function Login() {
  const navigate = useNavigate()
  const online = useOnlineStatus()
  const {
    authStatus,
    onboarding,
    sessionNotice,
    loginError,
    bootError,
    isSigningIn,
    signIn,
    retryBootstrap,
    clearLoginError,
    consumeReturnTo,
  } = useAuth()

  // Already signed in: go where the backend says (US-005 FE §13.2).
  useEffect(() => {
    if (authStatus !== 'signed-in' || !onboarding) return
    const target = onboarding.nextStep === 'HOME' ? consumeReturnTo() ?? '/dashboard' : resolveOnboardingRoute(onboarding)
    navigate(target, { replace: true })
  }, [authStatus, onboarding, navigate, consumeReturnTo])

  if (authStatus === 'initializing' || authStatus === 'signed-in') {
    return <SplashScreen error={bootError} onRetry={retryBootstrap} />
  }

  const blocking = blockingLoginContent(loginError)
  const inline = blocking ? null : inlineLoginMessage(loginError)
  const notice = sessionNotice ? SESSION_NOTICE_TEXT[sessionNotice] : null
  const workshopSession = getPortal() === 'workshop'

  return (
    <div className="min-h-screen flex bg-background">
      <AuthBrandPanel
        headline="Chăm sóc xe"
        highlight="thông minh hơn"
        subtitle="Theo dõi bảo dưỡng, đặt lịch và nhận hỗ trợ từ AI Agent — mọi lúc, mọi nơi."
        chips={['AI 24/7', 'Lịch bảo dưỡng', 'Đặt lịch online', 'Theo dõi xe']}
      />

      <main className="flex-1 flex flex-col justify-center items-center px-4 sm:px-8 py-12 bg-app-backdrop">
        <div className="lg:hidden flex items-center gap-2.5 mb-10">
          <Logo className="h-9 text-foreground" />
        </div>

        <div className="w-full max-w-sm animate-pop-in sm:max-w-md sm:bg-card/70 sm:backdrop-blur-xl sm:border sm:border-border sm:rounded-3xl sm:p-8 sm:elevation-md">
          <h2 className="text-2xl font-bold tracking-tight text-foreground">Đăng nhập</h2>
          <p className="text-muted text-sm mt-1 mb-8">Dùng tài khoản Google để tiếp tục. Không cần tạo mật khẩu riêng.</p>

          {notice && !blocking && (
            <Notice tone={notice.tone} role="alert" className="mb-5">
              {notice.text}
            </Notice>
          )}

          {STANDALONE_DEMO_MODE && (
            <Notice tone="info" className="mb-5" title="Chế độ demo">
              Không cần tài khoản Google thật: bấm nút bên dưới để vào bằng tài khoản minh hoạ. Mọi dữ liệu là dữ liệu giả, lưu trong trình duyệt này.
            </Notice>
          )}
          {!isAuthConfigured && (
            <Notice tone="error" role="alert" className="mb-5" title="Chưa cấu hình đăng nhập">
              Thiếu biến môi trường VITE_FIREBASE_* cho ứng dụng. Xem .env.example ở gốc repo.
            </Notice>
          )}

          {blocking ? (
            <LoginErrorPanel title={blocking.title} message={blocking.message} onOtherAccount={clearLoginError} />
          ) : (
            <div className="space-y-4">
              <GoogleSignInButton
                onClick={() => void signIn()}
                loading={isSigningIn}
                disabled={!isAuthConfigured || !online}
              />
              {!online && <p className="text-xs text-warning text-center">Không có kết nối mạng.</p>}
              {inline && (
                <div role="alert" className="text-center">
                  <p className="text-sm text-error">{inline}</p>
                  {loginError?.traceId && <p className="text-xs text-muted font-mono mt-1">Mã lỗi: {loginError.traceId}</p>}
                </div>
              )}
              {workshopSession && (
                <p className="text-xs text-muted text-center">
                  Bạn đang có phiên đăng nhập ở Workshop Portal. Đăng nhập tại đây để dùng ứng dụng chủ xe.
                </p>
              )}
            </div>
          )}

          <div className="mt-10 pt-6 border-t border-border text-center">
            <Link to="/workshop/login" className="text-sm text-emerald hover:text-emerald-bright transition-colors">
              Bạn là chủ xưởng dịch vụ? Đăng nhập Workshop Portal
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}
