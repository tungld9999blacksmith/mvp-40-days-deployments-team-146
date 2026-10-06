import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { QrCode } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Spinner from '@/shared/ui/Spinner'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { getPortal } from '@/features/auth/portal'
import { resolveBookingCode } from '../api'

/**
 * `/c/:bookingCode` — the URL inside the ticket QR (us-053 §8). A signed-in workshop owner goes to
 * check-in; anyone else continues to the owner resolver (login first when needed).
 */
export function QrEntry() {
  const { bookingCode = '' } = useParams()
  const code = encodeURIComponent(bookingCode.toUpperCase())
  if (getPortal() === 'workshop') return <Navigate to={`/technician/check-in?code=${code}`} replace />
  return <Navigate to={`/bookings/by-code/${code}`} replace />
}

/** Owner side of the QR (API-BT-03): the owner's own code opens the ticket; others are "not found". */
export default function BookingByCode() {
  const { bookingCode = '' } = useParams()
  const navigate = useNavigate()
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setError(null)
    resolveBookingCode(bookingCode)
      .then(({ bookingId }) => !cancelled && navigate(`/bookings/${encodeURIComponent(bookingId)}`, { replace: true }))
      .catch((reason: unknown) => !cancelled && setError(isApiError(reason) ? reason : null))
    return () => {
      cancelled = true
    }
  }, [bookingCode, attempt, navigate])

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-xl mx-auto">
      <Card>
        {error && isApiError(error, 'BOOKING_NOT_FOUND') ? (
          <EmptyState
            icon={<QrCode className="w-5 h-5" />}
            title="Không tìm thấy lịch hẹn của bạn"
            description="Mã này không thuộc lịch hẹn nào của tài khoản đang đăng nhập."
            action={<Button onClick={() => navigate('/bookings')}>Lịch hẹn của tôi</Button>}
          />
        ) : error ? (
          <ErrorState traceId={error.traceId} onRetry={() => setAttempt(count => count + 1)} />
        ) : (
          <EmptyState icon={<QrCode className="w-5 h-5" />} title="Đang mở lịch hẹn…" description={<Spinner className="w-5 h-5 mx-auto mt-2" />} />
        )}
      </Card>
    </div>
  )
}
