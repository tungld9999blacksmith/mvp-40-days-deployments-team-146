import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CalendarCheck2, CalendarClock, CircleX, Hourglass } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card, InfoRow } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { EmptyState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { formatCountdown } from '@/shared/utils/format'
import { cancelHold } from '../api'
import { WorkshopValue } from '../components/BookingSummaryCard'
import type { TicketState } from './BookingConfirm'
import type { Booking } from '../types'
import { bookingErrorMessage, formatLongDay, isConfirmedStatus, isPendingStatus, secondsLeft, slotLabel } from '../utils'

function useCountdown(until: string | null): number {
  const [left, setLeft] = useState(() => secondsLeft(until))
  useEffect(() => {
    setLeft(secondsLeft(until))
    if (!until) return
    const timer = window.setInterval(() => setLeft(secondsLeft(until)), 1000)
    return () => window.clearInterval(timer)
  }, [until])
  return left
}

function StatusBadge({ booking }: { booking: Booking }) {
  if (isConfirmedStatus(booking.status)) return <Badge tone="success">Đã xác nhận</Badge>
  if (isPendingStatus(booking.status)) return <Badge tone="warning">Chờ xưởng xác nhận</Badge>
  if (booking.status.toLowerCase() === 'cancelled') return <Badge tone="neutral">Đã huỷ</Badge>
  return <Badge tone="neutral">{booking.status}</Badge>
}

/**
 * Result of the hold (FE §4.6, AC-FE-403). A reduced SCR-1201 of us-053: without
 * GET /bookings/{id} yet, it shows the booking handed over by the confirm screen.
 */
export default function BookingTicket() {
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const handed = (location.state as TicketState | null) ?? null
  const [booking, setBooking] = useState<Booking | null>(handed?.booking ?? null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [windowClosed, setWindowClosed] = useState(false)
  const keepRef = useRef<HTMLButtonElement>(null)
  const left = useCountdown(booking && isPendingStatus(booking.status) ? booking.ownerCancelableUntil : null)

  if (!booking) {
    return (
      <div className="p-6 xl:p-8 max-w-2xl">
        <Card>
          <EmptyState
            icon={<CalendarClock className="w-5 h-5" />}
            title="Chưa xem lại được lịch hẹn này."
            description="Màn chi tiết lịch hẹn sẽ có khi backend mở API xem lịch hẹn (US-053). Lịch hẹn của bạn vẫn được giữ."
            action={<Button onClick={() => navigate('/dashboard')}>Về trang chủ</Button>}
          />
        </Card>
      </div>
    )
  }

  const pending = isPendingStatus(booking.status)
  const confirmed = isConfirmedStatus(booking.status)
  const canCancelHold = pending && !windowClosed && left > 0

  async function doCancel() {
    if (!booking) return
    setCancelling(true)
    try {
      const result = await cancelHold(booking.bookingId)
      const next = { ...booking, status: result.status }
      setBooking(next)
      navigate('.', { replace: true, state: { booking: next, workshopAddress: handed?.workshopAddress ?? null } })
      setConfirmOpen(false)
      toast.show('Đã huỷ giữ chỗ.', 'success')
    } catch (reason) {
      setConfirmOpen(false)
      if (isApiError(reason, 'HOLD_WINDOW_CLOSED')) {
        setWindowClosed(true)
        toast.show(bookingErrorMessage('HOLD_WINDOW_CLOSED') ?? '', 'warning')
      } else {
        toast.show('Không huỷ được giữ chỗ, bạn thử lại nhé.', 'error')
      }
    } finally {
      setCancelling(false)
    }
  }

  return (
    <div className="p-6 xl:p-8 max-w-2xl space-y-5">
      <div className="flex items-center gap-3">
        <span className="w-11 h-11 rounded-xl bg-emerald/10 text-emerald flex items-center justify-center shrink-0">
          {booking.status.toLowerCase() === 'cancelled' ? <CircleX className="w-5 h-5" /> : <CalendarCheck2 className="w-5 h-5" />}
        </span>
        <div>
          <h1 className="text-xl font-bold text-foreground">
            {confirmed ? 'Đặt lịch thành công' : pending ? 'Đã giữ chỗ' : 'Lịch hẹn'}
          </h1>
          <p className="text-sm text-muted mt-0.5">
            {pending ? 'Đang chờ xưởng xác nhận.' : confirmed ? 'Xưởng đã xác nhận lịch hẹn của bạn.' : 'Giữ chỗ đã được huỷ.'}
          </p>
        </div>
      </div>

      <Card>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted">Lịch hẹn</span>
          <StatusBadge booking={booking} />
        </div>
        <InfoRow
          label="Xưởng"
          value={<WorkshopValue name={booking.workshopName ?? 'Xưởng đã chọn'} address={handed?.workshopAddress ?? null} />}
        />
        <InfoRow label="Thời gian" value={`${slotLabel(booking.timeSlot)} · ${formatLongDay(booking.bookingDate)}`} />
        {booking.bookingCode && <InfoRow label="Mã lịch hẹn" value={booking.bookingCode} mono />}
        {booking.estimatedCost !== null && (
          <InfoRow label={booking.estimateLabel} value={`${new Intl.NumberFormat('vi-VN').format(Number(booking.estimatedCost))} đ`} />
        )}
        {booking.qrUrl && (
          <div className="pt-4 flex justify-center">
            <img src={booking.qrUrl} alt={`Mã QR check-in ${booking.bookingCode ?? ''}`} className="w-40 h-40 rounded-xl bg-white p-2" />
          </div>
        )}
      </Card>

      {pending && (
        <Notice
          tone={canCancelHold ? 'info' : 'warning'}
          title={canCancelHold ? `Bạn có thể huỷ giữ chỗ trong ${formatCountdown(left)}` : 'Đang chờ xưởng xác nhận'}
          action={
            canCancelHold ? (
              <Button variant="danger" size="sm" onClick={() => setConfirmOpen(true)}>
                Huỷ giữ chỗ
              </Button>
            ) : undefined
          }
        >
          <span className="inline-flex items-center gap-1.5">
            <Hourglass className="w-3.5 h-3.5" />
            Xưởng sẽ xác nhận trong thời gian sớm nhất, bạn sẽ nhận được thông báo.
          </span>
        </Notice>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        <Button variant="secondary" onClick={() => navigate('/dashboard')}>
          Về trang chủ
        </Button>
        {booking.status.toLowerCase() === 'cancelled' && <Button onClick={() => navigate('/booking')}>Đặt lịch khác</Button>}
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        role="alertdialog"
        title="Huỷ giữ chỗ?"
        description="Khung giờ sẽ được trả lại cho người khác đặt."
        initialFocusRef={keepRef}
        dismissable={!cancelling}
        footer={
          <>
            <Button ref={keepRef} variant="secondary" onClick={() => setConfirmOpen(false)} disabled={cancelling}>
              Giữ lịch
            </Button>
            <Button variant="danger" loading={cancelling} loadingText="Đang huỷ…" onClick={() => void doCancel()}>
              Huỷ giữ chỗ
            </Button>
          </>
        }
      />
    </div>
  )
}
