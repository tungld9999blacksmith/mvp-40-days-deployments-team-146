import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { Notice } from '@/shared/ui/States'
import { isFirebaseConfigured } from '@/shared/config/env'
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus'
import AuthBrandPanel from '@/features/auth/components/AuthBrandPanel'
import GoogleSignInButton from '@/features/auth/components/GoogleSignInButton'
import LoginErrorPanel from '@/features/auth/components/LoginErrorPanel'
import SplashScreen from '@/features/auth/components/SplashScreen'
import { blockingLoginContent, inlineLoginMessage, SESSION_NOTICE_TEXT } from '@/features/auth/messages'
import { getPortal } from '@/features/auth/portal'
import { useWorkshopAuth } from '../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../navigation'

const WORKSHOP_BLOCKING = {
  ACCOUNT_SUSPENDED: {
    title: 'Tài khoản chủ xưởng đang bị khoá',
    message: 'Tài khoản chủ xưởng của bạn đang bị khoá. Vui lòng liên hệ hãng.',
  },
  ACCOUNT_INACTIVE: {
    title: 'Tài khoản chủ xưởng ngừng hoạt động',
    message: 'Tài khoản chủ xưởng của bạn đã ngừng hoạt động. Vui lòng liên hệ hãng.',
  },
  EMAIL_ALREADY_LINKED: {
    title: 'Không thể đăng nhập',
    message: 'Email này đã được liên kết với một tài khoản chủ xưởng khác.',
  },
}

/** SCR-201 / SCR-301 — Workshop Portal login. */
export default function WorkshopLogin() {
  const navigate = useNavigate()
  const online = useOnlineStatus()
  const { authStatus, onboarding, sessionNotice, loginError, bootError, isSigningIn, signIn, retryBootstrap, clearLoginError } =
    useWorkshopAuth()

  useEffect(() => {
    if (authStatus === 'signed-in' && onboarding) navigate(resolveWorkshopRoute(onboarding), { replace: true })
  }, [authStatus, onboarding, navigate])

  if (authStatus === 'initializing' || authStatus === 'signed-in') {
    return <SplashScreen brand="Workshop Portal" label="Đang kiểm tra phiên đăng nhập..." error={bootError} onRetry={retryBootstrap} />
  }

  const blocking = blockingLoginContent(loginError, WORKSHOP_BLOCKING)
  const inline = blocking ? null : inlineLoginMessage(loginError)
  const notice = sessionNotice ? SESSION_NOTICE_TEXT[sessionNotice] : null

  return (
    <div className="min-h-screen flex bg-background">
      <AuthBrandPanel
        badge="Workshop Portal"
        headline="Quản lý xưởng dịch vụ"
        highlight="gọn gàng hơn"
        subtitle="Nhận lịch hẹn từ chủ xe, duyệt báo giá và theo dõi công suất xưởng trên một cổng duy nhất."
        chips={['Lịch hẹn', 'Báo giá', 'Công suất xưởng', 'Chính hãng']}
      />

      <main className="flex-1 flex flex-col justify-center items-center px-4 sm:px-8 py-12">
        <div className="lg:hidden flex items-center gap-2.5 mb-10">
          <div className="w-9 h-9 rounded-xl bg-emerald flex items-center justify-center">
            <Zap className="w-4 h-4 text-background" strokeWidth={2.5} />
          </div>
          <span className="text-foreground font-bold text-xl">EV Care</span>
          <span className="text-xs font-semibold text-emerald">Workshop</span>
        </div>

        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-bold text-foreground">Đăng nhập cổng xưởng dịch vụ</h2>
          <p className="text-muted text-sm mt-1 mb-8">
            Dùng đúng Gmail đã đăng ký với hãng làm người quản lý xưởng.
          </p>

          {notice && !blocking && (
            <Notice tone={notice.tone} role="alert" className="mb-5">
              {notice.text}
            </Notice>
          )}
          {!isFirebaseConfigured && (
            <Notice tone="error" role="alert" className="mb-5" title="Chưa cấu hình đăng nhập">
              Thiếu biến môi trường VITE_FIREBASE_* cho ứng dụng. Xem .env.example ở gốc repo.
            </Notice>
          )}

          {blocking ? (
            <LoginErrorPanel
              title={blocking.title}
              message={blocking.message}
              supportLabel="Liên hệ hãng"
              onOtherAccount={clearLoginError}
            />
          ) : (
            <div className="space-y-4">
              <GoogleSignInButton onClick={() => void signIn()} loading={isSigningIn} disabled={!isFirebaseConfigured || !online} />
              {!online && <p className="text-xs text-warning text-center">Không có kết nối mạng.</p>}
              {inline && (
                <div role="alert" className="text-center">
                  <p className="text-sm text-error">{inline}</p>
                  {loginError?.traceId && <p className="text-xs text-muted font-mono mt-1">Mã lỗi: {loginError.traceId}</p>}
                </div>
              )}
              {getPortal() === 'owner' && (
                <p className="text-xs text-muted text-center">
                  Bạn đang có phiên đăng nhập ở ứng dụng chủ xe. Đăng nhập tại đây để dùng Workshop Portal.
                </p>
              )}
            </div>
          )}

          <div className="mt-10 pt-6 border-t border-border text-center">
            <Link to="/" className="text-sm text-emerald hover:text-emerald-bright transition-colors">
              Bạn là chủ xe? Đăng nhập tại đây
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}
