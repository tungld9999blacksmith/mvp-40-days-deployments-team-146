import { useEffect } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import Button from '@/shared/ui/Button'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { Notice } from '@/shared/ui/States'
import SupportLink from '@/shared/ui/SupportLink'
import { formatDuration } from '@/shared/utils/format'
import { useAuth } from '../../context/AuthContext'
import { resolveOnboardingRoute } from '../../navigation'
import type { VerificationFailureReason } from '../../types'
import { useOnboarding } from '../OnboardingContext'

type Action = 'edit' | 'nationalId' | 'resend' | 'otherVehicle' | 'support'

interface ReasonContent {
  message: string
  primary: Action
  secondary?: Action
  /** Field highlighted on SCR-003 / SCR-002. */
  focus?: string
}

const REASONS: Record<VerificationFailureReason, ReasonContent> = {
  VIN_NOT_FOUND: {
    message: 'Không tìm thấy số VIN trên hệ thống hãng. Vui lòng kiểm tra lại số VIN.',
    primary: 'edit',
    secondary: 'support',
    focus: 'vin',
  },
  PLATE_MISMATCH: {
    message: 'Biển số không khớp với số VIN trên hệ thống hãng. Vui lòng kiểm tra lại.',
    primary: 'edit',
    secondary: 'support',
    focus: 'licensePlate',
  },
  OWNER_MISMATCH: {
    message: 'Thông tin chủ xe trên hệ thống hãng không khớp với tài khoản của bạn.',
    primary: 'support',
    secondary: 'edit',
  },
  // TODO(spec): the three reasons below exist in the backend but not in US-001 FE §4.6.
  OWNER_EMAIL_MISMATCH: {
    message: 'Email Google của bạn không khớp với thông tin chủ xe trên hệ thống hãng.',
    primary: 'support',
    secondary: 'edit',
  },
  NATIONAL_ID_MISMATCH: {
    message: 'Số CCCD không khớp với chủ xe trên hệ thống hãng. Vui lòng kiểm tra lại số CCCD.',
    primary: 'nationalId',
    secondary: 'support',
  },
  MODEL_MISMATCH: {
    message: 'Mẫu xe không khớp với số VIN trên hệ thống hãng. Vui lòng kiểm tra lại.',
    primary: 'edit',
    secondary: 'support',
    focus: 'modelId',
  },
  OEM_UNAVAILABLE: {
    message: 'Hệ thống hãng tạm thời không phản hồi. Vui lòng thử lại sau.',
    primary: 'resend',
    secondary: 'support',
  },
  ALREADY_LINKED: {
    message: 'Xe đã được đăng ký bởi tài khoản khác. Vui lòng liên hệ bộ phận hỗ trợ.',
    primary: 'support',
    secondary: 'otherVehicle',
  },
}

const LABELS: Record<Action, string> = {
  edit: 'Sửa lại thông tin xe',
  nationalId: 'Sửa số CCCD',
  resend: 'Gửi lại',
  otherVehicle: 'Nhập xe khác',
  support: 'Liên hệ hỗ trợ',
}

/** SCR-006 — verification failed (US-001 FE §4.6). */
export default function FailedStep() {
  const navigate = useNavigate()
  const { onboarding } = useAuth()
  const { outcome, snapshot, loadSnapshot, setFocusField, setVehicleForm } = useOnboarding()

  const fromOutcome = outcome && (outcome.failureReason || outcome.retryAfterSeconds !== null) ? outcome : null
  const failureReason: VerificationFailureReason | null =
    fromOutcome?.failureReason ??
    snapshot?.latestVerification?.failureReason ??
    snapshot?.vehicle?.verificationFailureReason ??
    null
  const remaining = fromOutcome?.remainingAttempts ?? snapshot?.remainingAttempts ?? null
  const exceeded = fromOutcome?.retryAfterSeconds != null || remaining === 0
  const failed = onboarding?.status === 'VERIFICATION_FAILED'

  useEffect(() => {
    if (!snapshot) void loadSnapshot()
  }, [snapshot, loadSnapshot])

  if (!onboarding) return null
  if (!failed && !exceeded) return <Navigate to={resolveOnboardingRoute(onboarding)} replace />
  if (!snapshot && !fromOutcome) return <SkeletonCard lines={4} />

  const content = failureReason ? REASONS[failureReason] : null

  function run(action: Action) {
    switch (action) {
      case 'edit':
        setFocusField(content?.focus ?? null)
        navigate('/onboarding/vehicle')
        break
      case 'nationalId':
        setFocusField('nationalId')
        navigate('/onboarding/profile')
        break
      case 'resend':
        navigate('/onboarding/vehicle')
        break
      case 'otherVehicle':
        setVehicleForm({ vin: '', licensePlate: '', modelId: '', manufactureYear: '', consentGranted: false })
        navigate('/onboarding/vehicle')
        break
      case 'support':
        break
    }
  }

  function renderAction(action: Action, primary: boolean) {
    if (action === 'support') return <SupportLink key={action} variant={primary ? 'primary' : 'secondary'} />
    return (
      <Button key={action} variant={primary ? 'primary' : 'secondary'} onClick={() => run(action)}>
        {LABELS[action]}
      </Button>
    )
  }

  const retryAfter = fromOutcome?.retryAfterSeconds ?? null

  return (
    <div className="bg-card border border-border rounded-2xl p-6 sm:p-8 elevation-sm" role="alert">
      <div className="w-12 h-12 rounded-2xl bg-error/10 flex items-center justify-center">
        <AlertTriangle className="w-6 h-6 text-error" aria-hidden />
      </div>
      <h1 className="text-lg font-semibold text-foreground mt-5">Xác thực xe không thành công</h1>

      {exceeded ? (
        <>
          <p className="text-sm text-muted mt-2 leading-relaxed">
            Bạn đã xác thực thất bại quá nhiều lần. Vui lòng thử lại sau hoặc liên hệ hỗ trợ.
          </p>
          {retryAfter !== null && (
            <Notice tone="warning" className="mt-4">
              Bạn có thể thử lại sau {formatDuration(retryAfter)}.
            </Notice>
          )}
          <div className="mt-6 flex flex-col sm:flex-row gap-2">
            <SupportLink variant="primary" />
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-muted mt-2 leading-relaxed">
            {content?.message ?? 'Thông tin xe chưa được hãng xác thực. Vui lòng kiểm tra lại.'}
          </p>
          {remaining !== null && remaining <= 2 && failureReason !== 'ALREADY_LINKED' && (
            <Notice tone="warning" className="mt-4">
              Bạn còn {remaining} lần thử trong 24 giờ.
            </Notice>
          )}
          <div className="mt-6 flex flex-col sm:flex-row gap-2">
            {renderAction(content?.primary ?? 'edit', true)}
            {content?.secondary && renderAction(content.secondary, false)}
          </div>
        </>
      )}
    </div>
  )
}
