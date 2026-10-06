import { useEffect } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import Button from '@/shared/ui/Button'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { Notice } from '@/shared/ui/States'
import SupportLink from '@/shared/ui/SupportLink'
import { formatDuration } from '@/shared/utils/format'
import { useWorkshopAuth } from '../../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../../navigation'
import type { WorkshopFailureReason } from '../../types'
import { useWorkshopOnboarding } from '../WorkshopOnboardingContext'

/** SCR-206 — verification failed (US-009 FE §4.6). */
export default function WorkshopFailedStep() {
  const navigate = useNavigate()
  const { owner, onboarding, logout } = useWorkshopAuth()
  const { outcome, snapshot, loadSnapshot, setFocusField } = useWorkshopOnboarding()

  useEffect(() => {
    if (!snapshot) void loadSnapshot()
  }, [snapshot, loadSnapshot])

  const fromOutcome = outcome && (outcome.failureReason || outcome.retryAfterSeconds !== null) ? outcome : null
  const reason: WorkshopFailureReason | null =
    fromOutcome?.failureReason ?? snapshot?.latestAttempt?.failureReason ?? snapshot?.registration?.failureReason ?? null
  const attempt = fromOutcome?.attempt ?? snapshot?.latestAttempt ?? null
  const failedCount = attempt?.failedAttemptsLast24h ?? null
  const maxAttempts = attempt?.maxFailedAttempts ?? null
  const exceeded =
    fromOutcome?.retryAfterSeconds != null || (failedCount !== null && maxAttempts !== null && failedCount >= maxAttempts)
  const failed = onboarding?.status === 'VERIFICATION_FAILED'

  if (!onboarding) return null
  if (!failed && !exceeded) return <Navigate to={resolveWorkshopRoute(onboarding)} replace />
  if (!snapshot && !fromOutcome) return <SkeletonCard lines={4} />

  const messages: Record<WorkshopFailureReason, string> = {
    MANAGER_NOT_FOUND: `Gmail ${owner?.email ?? ''} chưa được hãng ghi nhận là người quản lý xưởng nào. Hãy đăng nhập bằng đúng Gmail đã đăng ký với hãng, hoặc liên hệ hãng để cập nhật.`,
    NATIONAL_ID_MISMATCH: 'Số CCCD không khớp với người quản lý xưởng trên hệ thống hãng. Vui lòng kiểm tra lại.',
    ALREADY_CLAIMED: 'Xưởng này đang được quản lý bởi một tài khoản khác. Vui lòng liên hệ hãng.',
    OEM_UNAVAILABLE: 'Hệ thống hãng không phản hồi. Vui lòng gửi lại sau.',
  }

  const primary = () => {
    switch (reason) {
      case 'MANAGER_NOT_FOUND':
        return (
          <Button onClick={() => void logout()}>
            Đăng nhập bằng Gmail khác
          </Button>
        )
      case 'NATIONAL_ID_MISMATCH':
        return (
          <Button
            onClick={() => {
              setFocusField('nationalId')
              navigate('/workshop/onboarding/profile')
            }}
          >
            Sửa CCCD
          </Button>
        )
      case 'OEM_UNAVAILABLE':
        return <Button onClick={() => navigate('/workshop/onboarding/operations')}>Gửi lại</Button>
      default:
        return <SupportLink label="Liên hệ hãng" variant="primary" />
    }
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-6 sm:p-8 elevation-sm" role="alert">
      <div className="w-12 h-12 rounded-2xl bg-error/10 flex items-center justify-center">
        <AlertTriangle className="w-6 h-6 text-error" aria-hidden />
      </div>
      <h1 className="text-lg font-semibold text-foreground mt-5">Xác thực chủ xưởng không thành công</h1>

      {exceeded ? (
        <>
          <p className="text-sm text-muted mt-2 leading-relaxed">
            Bạn đã xác thực thất bại quá {maxAttempts ?? 5} lần trong 24 giờ. Vui lòng thử lại sau.
          </p>
          {fromOutcome?.retryAfterSeconds != null && (
            <Notice tone="warning" className="mt-4">
              Có thể thử lại sau {formatDuration(fromOutcome.retryAfterSeconds)}.
            </Notice>
          )}
          <div className="mt-6">
            <SupportLink label="Liên hệ hãng" variant="primary" />
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-muted mt-2 leading-relaxed">
            {reason ? messages[reason] : 'Thông tin chưa được hãng xác thực. Vui lòng kiểm tra lại.'}
          </p>
          {failedCount !== null && maxAttempts !== null && failedCount >= 3 && reason !== 'ALREADY_CLAIMED' && (
            <Notice tone="warning" className="mt-4">
              Đã thất bại {failedCount}/{maxAttempts} lần trong 24 giờ.
            </Notice>
          )}
          <div className="mt-6 flex flex-col sm:flex-row gap-2">
            {primary()}
            {reason && reason !== 'ALREADY_CLAIMED' && <SupportLink label="Liên hệ hãng" />}
          </div>
          {reason !== 'ALREADY_CLAIMED' && (
            <button
              type="button"
              onClick={() => navigate('/workshop/onboarding/operations')}
              className="mt-4 text-sm text-emerald hover:text-emerald-bright transition-colors"
            >
              Sửa thông tin vận hành
            </button>
          )}
        </>
      )}
    </div>
  )
}
