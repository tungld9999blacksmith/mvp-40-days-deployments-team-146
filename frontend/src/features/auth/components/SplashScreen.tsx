import { useEffect, useState } from 'react'
import { WifiOff } from 'lucide-react'
import Button from '@/shared/ui/Button'
import Logo from '@/shared/ui/Logo'
import Spinner from '@/shared/ui/Spinner'
import { NETWORK_ERROR, type ApiError } from '@/shared/api/client'
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus'

/** SCR-102 / SCR-302 — full-screen while the session is being restored. */
export default function SplashScreen({
  label = 'Đang đăng nhập...',
  brand,
  error,
  onRetry,
}: {
  label?: string
  brand?: string
  error?: ApiError | null
  onRetry?: () => void
}) {
  const online = useOnlineStatus()
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 10_000)
    return () => window.clearTimeout(timer)
  }, [])

  const offline = !online || error?.code === NETWORK_ERROR

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div role="status" aria-live="polite" className="flex flex-col items-center text-center max-w-sm">
        <Logo className="h-12 text-foreground" />
        {brand && <p className="text-emerald text-xs font-semibold mt-1">{brand}</p>}

        {offline ? (
          <>
            <WifiOff className="w-5 h-5 text-warning mt-8" aria-hidden />
            <p className="text-sm text-muted mt-3">Không có kết nối mạng. Vui lòng kết nối để tiếp tục.</p>
          </>
        ) : error ? (
          <p className="text-sm text-muted mt-8">
            {error.status === 503 && error.code === 'AUTH_PROVIDER_UNAVAILABLE'
              ? 'Không kiểm tra được phiên đăng nhập. Vui lòng thử lại.'
              : 'Kết nối chậm hơn bình thường...'}
          </p>
        ) : (
          <div className="flex items-center gap-2 text-sm text-muted mt-8">
            <Spinner />
            {label}
          </div>
        )}
        {slow && !offline && !error && <p className="text-xs text-muted mt-2">Kết nối chậm hơn bình thường...</p>}

        {(offline || error || slow) && onRetry && (
          <Button variant="secondary" size="sm" className="mt-5" onClick={onRetry}>
            Thử lại
          </Button>
        )}
      </div>
    </div>
  )
}
