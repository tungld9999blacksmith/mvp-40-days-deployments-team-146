import { useCallback, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Clock, ShieldCheck } from 'lucide-react'
import { usePolling } from '@/shared/hooks/usePolling'
import Button from '@/shared/ui/Button'
import Spinner from '@/shared/ui/Spinner'
import { ErrorState } from '@/shared/ui/States'
import { useAuth } from '../../context/AuthContext'
import { resolveOnboardingRoute } from '../../navigation'
import { useOnboarding } from '../OnboardingContext'

const POLL_INTERVAL_MS = 3_000
const POLL_MAX_MS = 2 * 60 * 1000

/** SCR-004 — waiting for the manufacturer; polls API-002 every 3 s for 2 min (US-001 FE §4.4). */
export default function VerifyingStep() {
  const navigate = useNavigate()
  const { onboarding, logout } = useAuth()
  const { loadSnapshot, setOutcome } = useOnboarding()
  const [checking, setChecking] = useState(false)
  const pending = onboarding?.status === 'PENDING_VEHICLE_VERIFICATION'

  const goToResult = useCallback(
    (nextStatus: string, route: string) => {
      if (nextStatus === 'ACTIVE' || nextStatus === 'VERIFICATION_FAILED') setOutcome(null)
      navigate(route, { replace: true })
    },
    [navigate, setOutcome],
  )

  const poll = useCallback(async () => {
    const data = await loadSnapshot()
    if (!data) throw new Error('poll failed')
    if (data.onboarding.nextStep === 'VERIFYING') return 'continue' as const
    goToResult(data.onboarding.status, resolveOnboardingRoute(data.onboarding))
    return 'stop' as const
  }, [loadSnapshot, goToResult])

  const { timedOut, failed, restart } = usePolling({
    enabled: pending,
    intervalMs: () => POLL_INTERVAL_MS,
    maxDurationMs: POLL_MAX_MS,
    poll,
  })

  if (!onboarding) return null
  if (!pending) return <Navigate to={resolveOnboardingRoute(onboarding)} replace />

  async function checkAgain() {
    setChecking(true)
    try {
      await poll()
    } catch {
      // keep showing the wait state
    } finally {
      setChecking(false)
      restart()
    }
  }

  if (failed) {
    return (
      <div className="bg-card border border-border rounded-2xl elevation-sm">
        <ErrorState onRetry={restart} description="Không kiểm tra được kết quả xác thực. Vui lòng thử lại." />
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-8 text-center elevation-sm" role="status" aria-live="polite">
      {timedOut ? (
        <>
          <div className="w-12 h-12 rounded-2xl bg-warning/10 flex items-center justify-center mx-auto">
            <Clock className="w-6 h-6 text-warning" aria-hidden />
          </div>
          <h1 className="text-lg font-semibold text-foreground mt-5">Hệ thống hãng đang xử lý lâu hơn dự kiến</h1>
          <p className="text-sm text-muted mt-2 max-w-sm mx-auto">
            Hệ thống hãng đang xử lý lâu hơn dự kiến. Chúng tôi sẽ cập nhật kết quả sớm.
          </p>
          <div className="mt-6 flex flex-col sm:flex-row gap-2 justify-center">
            <Button onClick={() => void checkAgain()} loading={checking}>
              Kiểm tra lại
            </Button>
            <Button variant="secondary" onClick={() => void logout()}>
              Để sau
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="w-12 h-12 rounded-2xl bg-emerald/10 flex items-center justify-center mx-auto">
            <ShieldCheck className="w-6 h-6 text-emerald" aria-hidden />
          </div>
          <h1 className="text-lg font-semibold text-foreground mt-5">Đang xác thực thông tin xe của bạn...</h1>
          <p className="text-sm text-muted mt-2">Hệ thống đang đối chiếu với dữ liệu của hãng. Vui lòng không đóng trang.</p>
          <div className="flex justify-center mt-6">
            <Spinner className="w-6 h-6 text-emerald" />
          </div>
        </>
      )}
    </div>
  )
}
