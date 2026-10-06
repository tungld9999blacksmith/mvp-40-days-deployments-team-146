import { useEffect, useState, type ReactNode } from 'react'
import { BadgeCheck, CalendarX2, CarFront, CircleCheckBig, Clock4, Hourglass, Wrench } from 'lucide-react'
import { cn } from '@/shared/ui/cn'
import { REASON_LABEL } from '@/shared/domain/bookingLabels'
import { formatTimeDayMonth } from '@/shared/utils/format'
import type { BookingDetail } from '../types'

function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])
  return now
}

function cancelText(booking: BookingDetail): string {
  if (booking.cancelledBy === 'VEHICLE_OWNER') return 'Bạn đã huỷ lịch hẹn này.'
  if (booking.cancelledBy === 'SYSTEM') return 'Xưởng chưa xác nhận kịp nên lịch hẹn đã tự huỷ.'
  if (booking.cancelReason === 'FULLY_BOOKED' || booking.cancelReason === 'NOT_SUPPORTED_SERVICE') {
    return `Xưởng chưa nhận được lịch này — ${REASON_LABEL[booking.cancelReason]}.`
  }
  return `Xưởng đã huỷ lịch hẹn${booking.cancelReason ? ` — ${REASON_LABEL[booking.cancelReason] ?? booking.cancelReason}` : ''}.`
}

/** us-033 §4.1 — status + reason when no action is left; text and icon, never colour alone. */
export default function BookingStatusBanner({ booking, action }: { booking: BookingDetail; action?: ReactNode }) {
  const now = useNow()
  const started = now >= new Date(booking.appointmentAt).getTime()
  let tone: 'success' | 'warning' | 'error' | 'neutral' = 'neutral'
  let icon = <Clock4 className="w-5 h-5" />
  let title = ''
  let text: string | null = null

  switch (booking.status) {
    case 'CONFIRMED':
      if (started) {
        tone = 'warning'
        title = 'Đã tới giờ hẹn'
        text = 'Nếu cần thay đổi, vui lòng liên hệ xưởng.'
      } else {
        tone = 'success'
        icon = <BadgeCheck className="w-5 h-5" />
        title = 'Đã xác nhận'
        text = booking.attendanceConfirmedAt ? `Bạn đã xác nhận sẽ đến lúc ${formatTimeDayMonth(booking.attendanceConfirmedAt)}.` : null
      }
      break
    case 'PENDING':
      tone = 'warning'
      icon = <Hourglass className="w-5 h-5" />
      title = 'Đang giữ chỗ — chờ xưởng xác nhận'
      text = 'Xưởng sẽ xác nhận sớm, bạn sẽ nhận được thông báo.'
      break
    case 'CHECKED_IN':
      tone = 'success'
      icon = <CarFront className="w-5 h-5" />
      title = 'Xe đã check-in tại xưởng'
      break
    case 'IN_PROGRESS':
      tone = 'warning'
      icon = <Wrench className="w-5 h-5" />
      title = 'Xe đang được bảo dưỡng'
      break
    case 'COMPLETED':
      icon = <CircleCheckBig className="w-5 h-5" />
      title = 'Đã hoàn tất'
      text = booking.completedAt ? `Hoàn tất lúc ${formatTimeDayMonth(booking.completedAt)}.` : null
      break
    case 'CANCELLED':
      tone = 'error'
      icon = <CalendarX2 className="w-5 h-5" />
      title = 'Lịch hẹn đã huỷ'
      text = `${cancelText(booking)}${booking.cancelledAt ? ` (${formatTimeDayMonth(booking.cancelledAt)})` : ''}`
      break
  }

  return (
    <div
      role="status"
      className={cn(
        'flex flex-wrap items-start gap-3 rounded-2xl border px-4 py-3.5',
        tone === 'success' && 'bg-emerald/10 border-emerald/20',
        tone === 'warning' && 'bg-warning/10 border-warning/20',
        tone === 'error' && 'bg-error/10 border-error/20',
        tone === 'neutral' && 'bg-card border-border',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'mt-0.5',
          tone === 'success' && 'text-emerald',
          tone === 'warning' && 'text-warning',
          tone === 'error' && 'text-error',
          tone === 'neutral' && 'text-muted',
        )}
      >
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {text && <p className="text-sm text-muted mt-0.5">{text}</p>}
      </div>
      {action}
    </div>
  )
}
