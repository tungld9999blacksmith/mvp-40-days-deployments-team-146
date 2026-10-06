import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  CalendarCheck2,
  CalendarClock,
  CalendarSync,
  Car,
  ClipboardList,
  FileText,
  MapPin,
  Navigation,
  ShieldCheck,
  Star,
} from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card, CardHeader, InfoRow } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { BOOKING_STATUS, bookingStatusLabel } from '@/shared/domain/bookingLabels'
import { formatCountdown, formatKm, formatTimeDayMonth } from '@/shared/utils/format'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { formatVnd } from '@/features/estimate/utils'
import ProgressTimeline from '@/features/progress/components/ProgressTimeline'
import { cancelBooking, cancelHold, confirmAttendance, getBooking } from '../api'
import { invalidateUpcomingBookings } from '../hooks/useUpcomingBookings'
import BookingStatusBanner from '../components/BookingStatusBanner'
import CancelBookingDialog from '../components/CancelBookingDialog'
import HistoryTimeline from '../components/HistoryTimeline'
import TicketQr from '../components/TicketQr'
import type { TicketState } from './BookingConfirm'
import type { BookingDetail, BookingSource } from '../types'
import { bookingErrorMessage, formatLongDay, secondsLeft, slotLabel } from '../utils'

const BLOCKED_REASON: Record<string, string> = {
  TOO_CLOSE_TO_APPOINTMENT: 'Đã quá hạn đổi lịch (trước giờ hẹn 60 phút). Vui lòng liên hệ xưởng.',
  MAX_RESCHEDULES_REACHED: 'Bạn đã đổi lịch tối đa 2 lần cho lịch hẹn này.',
}

const CURRENT_STATUS_TOAST: Record<string, string> = {
  CANCELLED: 'Lịch hẹn đã huỷ trước đó.',
  CHECKED_IN: 'Xe đã check-in tại xưởng.',
  IN_PROGRESS: 'Xe đang được bảo dưỡng.',
  COMPLETED: 'Lịch hẹn đã hoàn tất.',
  PENDING: 'Lịch hẹn đang chờ xưởng xác nhận.',
}

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

function mapsUrl(name: string, address: string | null): string {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent([name, address].filter(Boolean).join(', '))}`
}

/** Shown when the ticket API is unreachable but the confirm screen handed the hold over (mock API off). */
function HandedOver({ state }: { state: TicketState }) {
  const navigate = useNavigate()
  const { booking } = state
  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-xl mx-auto space-y-4">
      <Notice tone="info" title="Đã giữ chỗ">
        Chi tiết lịch hẹn sẽ xem được khi backend mở API lịch hẹn (us-053).
      </Notice>
      <Card>
        <InfoRow label="Xưởng" value={booking.workshopName ?? 'Xưởng đã chọn'} />
        <InfoRow label="Thời gian" value={`${slotLabel(booking.timeSlot)} · ${formatLongDay(booking.bookingDate)}`} />
        <InfoRow label="Trạng thái" value={bookingStatusLabel(booking.status)} />
      </Card>
      <Button variant="secondary" onClick={() => navigate('/dashboard')}>
        Về trang chủ
      </Button>
    </div>
  )
}

/** SCR-701 (us-033) = SCR-1201 (us-053) — booking detail / ticket (`/bookings/:bookingId?src=`). */
export default function BookingTicket() {
  const { bookingId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const toast = useToast()
  const src: BookingSource = searchParams.get('src') === 'REMINDER_24H' ? 'REMINDER_24H' : 'APP'
  const handed = (location.state as TicketState | null) ?? null

  const [booking, setBooking] = useState<BookingDetail | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [dialog, setDialog] = useState<'cancel' | 'hold' | 'guide' | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [reasonError, setReasonError] = useState<string | null>(null)
  const cancelKey = useRef<string | null>(null)
  const actionsRef = useRef<HTMLDivElement>(null)
  const viewed = useRef(false)
  const holdLeft = useCountdown(booking?.allowedActions.includes('CANCEL_HOLD') ? booking.ownerCancelableUntil : null)

  const load = useCallback(
    () =>
      getBooking(bookingId, src)
        .then(data => {
          setBooking(data)
          setError(null)
          if (!viewed.current) {
            viewed.current = true
            track('booking_detail_viewed', { source: src, status: data.status })
            track('ticket_viewed', { status: data.status, src })
          }
        })
        .catch((reason: unknown) => setError(isApiError(reason) ? reason : null)),
    [bookingId, src],
  )

  useEffect(() => {
    setBooking(null)
    viewed.current = false
    void load()
  }, [load])

  // From the 24h reminder: bring the actions into view (us-033 §3.2).
  useEffect(() => {
    if (booking && src === 'REMINDER_24H') actionsRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [booking, src])

  const back = () => (location.key === 'default' ? navigate('/dashboard') : navigate(-1))

  if (!booking) {
    if (error) {
      if (handed && (error.status === 404 || error.status === 405) && !isApiError(error, 'BOOKING_NOT_FOUND')) return <HandedOver state={handed} />
      return (
        <div className="p-4 sm:p-6 xl:p-8 max-w-xl mx-auto">
          <Card>
            {isApiError(error, 'BOOKING_NOT_FOUND') ? (
              <EmptyState
                icon={<CalendarClock className="w-5 h-5" />}
                title="Không tìm thấy lịch hẹn"
                action={<Button onClick={() => navigate('/dashboard')}>Về trang chủ</Button>}
              />
            ) : (
              <ErrorState title="Không thể tải lịch hẹn." traceId={error.traceId} onRetry={() => void load()} />
            )}
          </Card>
        </div>
      )
    }
    return (
      <div className="p-4 sm:p-6 xl:p-8 max-w-xl mx-auto space-y-4" aria-busy>
        <SkeletonCard lines={2} />
        <SkeletonCard lines={6} />
      </div>
    )
  }

  const current = booking
  const can = (action: string) => current.allowedActions.includes(action as never)
  const showProgress = ['CHECKED_IN', 'IN_PROGRESS', 'COMPLETED'].includes(current.status)
  const status = BOOKING_STATUS[current.status]

  async function attend() {
    if (confirming) return
    setConfirming(true)
    try {
      const result = await confirmAttendance(current.bookingId)
      setBooking({
        ...current,
        attendanceConfirmedAt: result.attendanceConfirmedAt,
        allowedActions: current.allowedActions.filter(action => action !== 'CONFIRM_ATTENDANCE'),
      })
      track('attendance_confirmed', { source: src })
      toast.show('Cảm ơn bạn! Xưởng đã nhận được xác nhận.', 'success')
    } catch (reason) {
      handleConflict(reason)
    } finally {
      setConfirming(false)
    }
  }

  function handleConflict(reason: unknown) {
    if (isApiError(reason) && reason.code === 'BOOKING_NOT_CONFIRMED') {
      const currentStatus = String(reason.details?.currentStatus ?? '')
      toast.show(CURRENT_STATUS_TOAST[currentStatus] ?? 'Lịch hẹn vừa thay đổi.', 'warning')
      void load()
    } else if (isApiError(reason, 'APPOINTMENT_STARTED')) {
      toast.show('Đã tới giờ hẹn — vui lòng liên hệ xưởng.', 'warning')
      void load()
    } else {
      toast.show('Tạm thời chưa thực hiện được, bạn thử lại nhé.', 'error')
    }
  }

  function openCancel() {
    cancelKey.current = newId()
    setReasonError(null)
    setDialog('cancel')
    track('booking_cancel_dialog_opened', { source: src })
  }

  async function doCancel(reason: string) {
    if (cancelling || !cancelKey.current) return
    setCancelling(true)
    try {
      await cancelBooking(current.bookingId, { source: src, ...(reason ? { reason } : {}) }, cancelKey.current)
      track('booking_cancelled', { source: src, hasReason: Boolean(reason) })
      invalidateUpcomingBookings()
      setDialog(null)
      toast.show('Đã huỷ lịch hẹn.', 'success')
      void load()
    } catch (failure) {
      track('booking_cancel_failed', { errorCode: isApiError(failure) ? failure.code : 'UNKNOWN' })
      if (isApiError(failure, 'INVALID_REQUEST')) {
        setReasonError('Lý do tối đa 255 ký tự.')
      } else if (isApiError(failure) && failure.status === 409) {
        setDialog(null)
        handleConflict(failure)
      } else {
        // Keep the dialog and the reason: a retry reuses the same Idempotency-Key.
        toast.show('Tạm thời chưa thực hiện được, bạn thử lại nhé.', 'error')
      }
    } finally {
      setCancelling(false)
    }
  }

  async function doCancelHold() {
    setCancelling(true)
    try {
      await cancelHold(current.bookingId)
      invalidateUpcomingBookings()
      setDialog(null)
      toast.show('Đã huỷ giữ chỗ.', 'success')
      void load()
    } catch (failure) {
      setDialog(null)
      toast.show(isApiError(failure) ? bookingErrorMessage(failure.code) ?? 'Không huỷ được giữ chỗ.' : 'Không huỷ được giữ chỗ.', 'warning')
      void load()
    } finally {
      setCancelling(false)
    }
  }

  function reschedule() {
    track('booking_reschedule_clicked', { rescheduleMode: current.rescheduleMode })
    if (current.rescheduleMode === 'F6B') navigate(`/bookings/${encodeURIComponent(current.bookingId)}/reschedule`)
    else setDialog('guide')
  }

  const rebookable = current.status === 'CANCELLED' && current.cancelledBy !== 'VEHICLE_OWNER'
  const costText =
    current.cost.label === 'ESTIMATE' && current.cost.amount !== null ? (
      `${current.estimateLabel}: ${formatVnd(current.cost.amount)}`
    ) : (
      <span className="text-muted">Chưa có ước tính</span>
    )

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-xl mx-auto space-y-4 pb-28 sm:pb-8">
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={back} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground">
          <ArrowLeft className="w-4 h-4" /> Lịch hẹn
        </button>
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
      </div>

      <BookingStatusBanner
        booking={current}
        action={
          rebookable ? (
            <Button size="sm" onClick={() => navigate(`/booking${current.odoMilestone ? `?odoMilestone=${current.odoMilestone}` : ''}`)}>
              Đặt lịch lại
            </Button>
          ) : current.status === 'COMPLETED' && current.followUp?.canRespond ? (
            <Button size="sm" icon={<Star className="w-3.5 h-3.5" />} onClick={() => navigate(`/follow-ups/${encodeURIComponent(current.followUp!.followUpId)}`)}>
              Đánh giá dịch vụ
            </Button>
          ) : undefined
        }
      />

      <Card className="space-y-5">
        {current.status === 'CONFIRMED' && current.bookingCode && current.qrPayload && (
          <div className="pt-1 pb-4 border-b border-dashed border-border">
            <TicketQr bookingId={current.bookingId} code={current.bookingCode} payload={current.qrPayload} />
          </div>
        )}
        <div>
          <InfoRow
            label="Thời gian"
            value={
              <span className="inline-flex items-center gap-1.5">
                <CalendarCheck2 className="w-3.5 h-3.5 text-muted" />
                {formatLongDay(current.bookingDate)} · {slotLabel(current.timeSlot)}
              </span>
            }
          />
          <InfoRow
            label="Xưởng"
            value={
              <span className="flex flex-col items-end">
                <span>{current.workshop.name}</span>
                {current.workshop.address && (
                  <span className="inline-flex items-center gap-1 text-xs font-normal text-muted mt-0.5">
                    <MapPin className="w-3 h-3 shrink-0" />
                    {current.workshop.address}
                  </span>
                )}
                <a
                  href={mapsUrl(current.workshop.name, current.workshop.address)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-emerald font-medium mt-1 hover:text-emerald-bright"
                >
                  <Navigation className="w-3 h-3" /> Chỉ đường
                </a>
              </span>
            }
          />
          <InfoRow
            label="Xe"
            value={
              <span className="inline-flex items-center gap-1.5">
                <Car className="w-3.5 h-3.5 text-muted" />
                {current.vehicle.modelName} · <span className="font-mono">{current.vehicle.plateMasked}</span>
              </span>
            }
          />
          {current.bookingCode && current.status !== 'CONFIRMED' && <InfoRow label="Mã lịch hẹn" value={current.bookingCode} mono />}
        </div>
      </Card>

      {showProgress && <ProgressTimeline bookingId={current.bookingId} workshop={current.workshop} />}

      <Card>
        <CardHeader
          title={current.odoMilestone ? `Hạng mục · mốc ${formatKm(current.odoMilestone)}` : 'Hạng mục'}
          icon={<ClipboardList className="w-4 h-4 text-muted" />}
        />
        {current.items.length === 0 ? (
          <p className="text-sm text-muted">Bảo dưỡng theo yêu cầu, xưởng sẽ tư vấn tại chỗ.</p>
        ) : (
          <ul className="space-y-1.5">
            {current.items.map(item => (
              <li key={item.itemName} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-foreground">{item.itemName}</span>
                {item.covered && (
                  <span className="inline-flex items-center gap-1 text-xs text-emerald">
                    <ShieldCheck className="w-3.5 h-3.5" /> Bảo hành
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 pt-3 border-t border-border">
          <InfoRow label="Chi phí" value={costText} />
        </div>
      </Card>

      {current.documentsToBring.length > 0 && ['PENDING', 'CONFIRMED'].includes(current.status) && (
        <Card>
          <CardHeader title="Giấy tờ cần mang" icon={<FileText className="w-4 h-4 text-muted" />} />
          <ul className="list-disc pl-5 space-y-1 text-sm text-foreground">
            {current.documentsToBring.map(item => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
      )}

      {can('CANCEL_HOLD') && holdLeft > 0 && (
        <Notice
          tone="info"
          title={`Bạn có thể huỷ giữ chỗ trong ${formatCountdown(holdLeft)}`}
          action={
            <Button variant="danger" size="sm" onClick={() => setDialog('hold')}>
              Huỷ giữ chỗ
            </Button>
          }
        />
      )}

      {(can('CONFIRM_ATTENDANCE') || can('RESCHEDULE') || can('CANCEL') || current.rescheduleBlockedReason) && (
        <div
          ref={actionsRef}
          className="fixed sm:static bottom-0 inset-x-0 lg:left-60 z-20 sm:z-auto bg-surface/95 sm:bg-transparent backdrop-blur sm:backdrop-blur-none border-t border-border sm:border-0 px-4 py-3 sm:p-0 space-y-2"
        >
          {can('CONFIRM_ATTENDANCE') && (
            <Button fullWidth size={src === 'REMINDER_24H' ? 'lg' : 'md'} loading={confirming} loadingText="Đang gửi…" icon={<CalendarCheck2 className="w-4 h-4" />} onClick={() => void attend()}>
              Xác nhận sẽ đến
            </Button>
          )}
          <div className="flex gap-2">
            {can('RESCHEDULE') && (
              <Button variant="secondary" className="flex-1" icon={<CalendarSync className="w-4 h-4" />} onClick={reschedule}>
                Đổi lịch
              </Button>
            )}
            {can('CANCEL') && (
              <Button variant="ghost" className="flex-1 text-error hover:text-error hover:bg-error/10" onClick={openCancel}>
                Huỷ lịch
              </Button>
            )}
          </div>
          {!can('RESCHEDULE') && current.rescheduleBlockedReason && BLOCKED_REASON[current.rescheduleBlockedReason] && (
            <p className="text-xs text-muted">{BLOCKED_REASON[current.rescheduleBlockedReason]}</p>
          )}
        </div>
      )}

      {current.attendanceConfirmedAt && current.status === 'CONFIRMED' && (
        <p className="text-xs text-emerald text-center">Bạn đã xác nhận sẽ đến lúc {formatTimeDayMonth(current.attendanceConfirmedAt)}.</p>
      )}

      <HistoryTimeline history={current.history} />

      <CancelBookingDialog
        open={dialog === 'cancel'}
        onClose={() => setDialog(null)}
        onConfirm={reason => void doCancel(reason)}
        submitting={cancelling}
        bookingDate={current.bookingDate}
        timeSlot={current.timeSlot}
        workshopName={current.workshop.name}
        fieldError={reasonError}
      />
      <Dialog
        open={dialog === 'hold'}
        onClose={() => !cancelling && setDialog(null)}
        role="alertdialog"
        title="Huỷ giữ chỗ?"
        description="Khung giờ sẽ được trả lại cho người khác đặt."
        dismissable={!cancelling}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)} disabled={cancelling}>
              Giữ lịch
            </Button>
            <Button variant="danger" loading={cancelling} loadingText="Đang huỷ…" onClick={() => void doCancelHold()}>
              Huỷ giữ chỗ
            </Button>
          </>
        }
      />
      <Dialog
        open={dialog === 'guide'}
        onClose={() => setDialog(null)}
        title="Đổi lịch"
        description="Để đổi giờ, bạn hãy đặt lịch mới rồi quay lại huỷ lịch này. Lịch hiện tại vẫn được giữ cho đến khi bạn huỷ."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              Đóng
            </Button>
            <Button onClick={() => navigate('/booking')}>Đặt lịch mới</Button>
          </>
        }
      />
    </div>
  )
}
