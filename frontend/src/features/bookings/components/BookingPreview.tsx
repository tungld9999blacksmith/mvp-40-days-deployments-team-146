import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CalendarCheck2, CalendarSync, ChevronRight, ClipboardList, Navigation, ShieldCheck, Store, Wallet } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import RailRow from '@/shared/ui/RailRow'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState } from '@/shared/ui/States'
import { BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import { getBooking } from '../api'
import type { BookingDetail } from '../types'
import TicketQr from './TicketQr'
import { formatLongDay, mapsUrl, slotLabel } from '../utils'

function costText(booking: BookingDetail): string | null {
  const { amount, label } = booking.cost
  if (amount === null) return null
  return label === 'APPROVED_QUOTE' ? `Theo báo giá: ${formatVnd(amount)}` : `${booking.estimateLabel}: ${formatVnd(amount)}`
}

/**
 * Right rail of "Lịch hẹn của tôi" (xl and up): the chosen booking at a glance, with its QR,
 * directions and rescheduling. Cancelling, attendance and progress stay on the ticket page.
 */
export default function BookingPreview({ bookingId, className }: { bookingId: string; className?: string }) {
  const navigate = useNavigate()
  const [loaded, setLoaded] = useState<{ bookingId: string; booking: BookingDetail | null; error: ApiError | null } | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    getBooking(bookingId)
      .then(booking => !cancelled && setLoaded({ bookingId, booking, error: null }))
      .catch((reason: unknown) => !cancelled && setLoaded({ bookingId, booking: null, error: isApiError(reason) ? reason : null }))
    return () => {
      cancelled = true
    }
  }, [bookingId, attempt])

  const retry = useCallback(() => {
    setLoaded(null)
    setAttempt(count => count + 1)
  }, [])

  // A previous booking's answer must never show under the newly chosen row.
  const current = loaded?.bookingId === bookingId ? loaded : null
  const ticketPath = `/bookings/${encodeURIComponent(bookingId)}`

  if (!current) {
    return (
      <div className={className} aria-busy>
        <SkeletonCard lines={6} />
      </div>
    )
  }
  if (!current.booking) {
    return (
      <div className={className}>
        <Card>
          <ErrorState compact title="Không tải được lịch hẹn." description={null} traceId={current.error?.traceId} onRetry={retry} />
        </Card>
      </div>
    )
  }

  const booking = current.booking
  const status = BOOKING_STATUS[booking.status]
  const qr = booking.status === 'CONFIRMED' && booking.bookingCode && booking.qrPayload ? { code: booking.bookingCode, payload: booking.qrPayload } : null
  const cost = costText(booking)
  const canReschedule = booking.allowedActions.includes('RESCHEDULE') && booking.rescheduleMode === 'F6B'

  return (
    <aside className={className} aria-label="Xem nhanh lịch hẹn">
      <Card className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          {qr ? (
            <span className="text-[13px] font-semibold text-muted">Vé check-in</span>
          ) : (
            <span className="font-mono text-lg font-semibold tracking-wider text-foreground">{booking.bookingCode ?? '—'}</span>
          )}
          {status && <Badge tone={status.tone}>{status.label}</Badge>}
        </div>

        {qr && (
          <div className="pb-4 border-b border-dashed border-border">
            <TicketQr bookingId={booking.bookingId} code={qr.code} payload={qr.payload} />
          </div>
        )}

        <div>
          <RailRow icon={<CalendarCheck2 />} label="Thời gian">
            <span className="font-mono">
              {slotLabel(booking.timeSlot)} · {formatLongDay(booking.bookingDate)}
            </span>
          </RailRow>
          <RailRow icon={<Store />} label="Xưởng">
            <span className="block">{booking.workshop.name}</span>
            {booking.workshop.address && <span className="block text-xs font-normal text-muted mt-0.5">{booking.workshop.address}</span>}
            <a
              href={mapsUrl(booking.workshop.name, booking.workshop.address)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-emerald font-medium mt-1 hover:text-emerald-bright"
            >
              <Navigation className="w-3 h-3" /> Chỉ đường
            </a>
          </RailRow>
          <RailRow icon={<ClipboardList />} label={booking.odoMilestone ? `Hạng mục · mốc ${formatKm(booking.odoMilestone)}` : 'Hạng mục'}>
            {booking.items.length === 0 ? (
              <span className="font-normal text-muted">Bảo dưỡng theo yêu cầu, xưởng tư vấn tại chỗ.</span>
            ) : (
              <ul className="space-y-1 font-normal">
                {booking.items.map(item => (
                  <li key={item.itemName} className="flex items-start justify-between gap-3 text-[13px]">
                    <span>{item.itemName}</span>
                    {item.covered && (
                      <span className="inline-flex items-center gap-1 text-xs text-emerald shrink-0">
                        <ShieldCheck className="w-3.5 h-3.5" aria-hidden /> Bảo hành
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </RailRow>
          <RailRow icon={<Wallet />} label="Chi phí" empty={cost === null}>
            {cost ?? 'Chưa có ước tính'}
          </RailRow>
        </div>

        <div className="flex flex-col gap-2 pt-1">
          {canReschedule && (
            <Button variant="secondary" icon={<CalendarSync className="w-4 h-4" />} onClick={() => navigate(`${ticketPath}/reschedule`)}>
              Đổi lịch
            </Button>
          )}
          <Link to={ticketPath} className="inline-flex items-center justify-center gap-1 text-sm font-medium text-emerald hover:text-emerald-bright py-1.5">
            Mở trang lịch hẹn <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </Card>
    </aside>
  )
}
