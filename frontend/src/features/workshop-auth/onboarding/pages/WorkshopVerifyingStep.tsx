import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Clock, ShieldCheck } from 'lucide-react'
import { usePolling } from '@/shared/hooks/usePolling'
import Button from '@/shared/ui/Button'
import Spinner from '@/shared/ui/Spinner'
import { ErrorState } from '@/shared/ui/States'
import { useWorkshopAuth } from '../../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../../navigation'
import { useWorkshopOnboarding } from '../WorkshopOnboardingContext'

const FAST_PHASE_MS = 60_000
const POLL_MAX_MS = 35 * 60 * 1000

/** SCR-204 — polls API-202 every 3 s for 60 s, then every 30 s, up to 35 min (US-009 FE §4.4). */
export default function WorkshopVerifyingStep() {
  const navigate = useNavigate()
  const { onboarding, logout } = useWorkshopAuth()
  const { loadSnapshot, setOutcome } = useWorkshopOnboarding()
  const [slow, setSlow] = useState(false)
  const [checking, setChecking] = useState(false)
  const pending = onboarding?.status === 'PENDING_WORKSHOP_VERIFICATION'

  useEffect(() => {
    if (!pending) return
    const timer = window.setTimeout(() => setSlow(true), FAST_PHASE_MS)
    return () => window.clearTimeout(timer)
  }, [pending])

  const poll = useCallback(async () => {
    const data = await loadSnapshot()
    if (!data) throw new Error('poll failed')
    if (data.onboarding.nextStep === 'VERIFYING') return 'continue' as const
    setOutcome(null)
    navigate(resolveWorkshopRoute(data.onboarding), { replace: true })
    return 'stop' as const
  }, [loadSnapshot, navigate, setOutcome])

  const { timedOut, failed, restart } = usePolling({
    enabled: pending,
    intervalMs: elapsed => (elapsed < FAST_PHASE_MS ? 3_000 : 30_000),
    maxDurationMs: POLL_MAX_MS,
    poll,
  })

  if (!onboarding) return null
  if (!pending) return <Navigate to={resolveWorkshopRoute(onboarding)} replace />

  if (failed) {
    return (
      <div className="bg-card border border-border rounded-2xl elevation-sm">
        <ErrorState onRetry={restart} description="Không kiểm tra được kết quả xác thực. Vui lòng thử lại." />
      </div>
    )
  }

  async function checkAgain() {
    setChecking(true)
    try {
      await poll()
    } catch {
      // keep waiting
    } finally {
      setChecking(false)
      restart()
    }
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-8 text-center elevation-sm" role="status" aria-live="polite">
      <div
        className={`w-12 h-12 rounded-2xl flex items-center justify-center mx-auto ${slow ? 'bg-warning/10' : 'bg-emerald/10'}`}
      >
        {slow ? <Clock className="w-6 h-6 text-warning" aria-hidden /> : <ShieldCheck className="w-6 h-6 text-emerald" aria-hidden />}
      </div>
      <h1 className="text-lg font-semibold text-foreground mt-5">Đang xác thực thông tin của bạn với hãng...</h1>
      {slow ? (
        <p className="text-sm text-muted mt-2 max-w-md mx-auto">
          Hệ thống hãng phản hồi chậm, chúng tôi sẽ tiếp tục xác thực trong khoảng 30 phút. Bạn có thể quay lại sau.
        </p>
      ) : (
        <p className="text-sm text-muted mt-2">Vui lòng chờ trong giây lát.</p>
      )}
      {!timedOut && (
        <div className="flex justify-center mt-6">
          <Spinner className="w-6 h-6 text-emerald" />
        </div>
      )}
      {(slow || timedOut) && (
        <div className="mt-6 flex flex-col sm:flex-row gap-2 justify-center">
          {timedOut && (
            <Button onClick={() => void checkAgain()} loading={checking}>
              Kiểm tra lại
            </Button>
          )}
          <Button variant="secondary" onClick={() => void logout()}>
            Đăng xuất và quay lại sau
          </Button>
        </div>
      )}
    </div>
  )
}
