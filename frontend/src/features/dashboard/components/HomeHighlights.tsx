import { Link } from 'react-router-dom'
import { CalendarCheck2, ChevronRight } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { useUpcomingBookings } from '@/features/bookings/hooks/useUpcomingBookings'
import { formatLongDay, slotLabel } from '@/features/bookings/utils'

/**
 * Home shortcut: next appointment (us-033 Q "Lịch hẹn sắp tới" → SCR-701).
 * Renders nothing while there is nothing to show.
 */
export default function HomeHighlights() {
  const upcoming = useUpcomingBookings()
  const next = upcoming.data?.items[0] ?? null
  if (!next) return null

  return (
    <div className="grid gap-3 sm:grid-cols-2 mb-6">
      <Link
        to={`/bookings/${encodeURIComponent(next.bookingId)}?src=APP`}
        className="group flex items-center gap-4 rounded-2xl border border-emerald/25 bg-card p-4 elevation-sm hover:-translate-y-0.5 hover:elevation-md transition-all"
      >
        <span className="w-11 h-11 rounded-xl bg-brand-gradient glow-emerald text-on-brand flex items-center justify-center shrink-0">
          <CalendarCheck2 className="w-5 h-5" />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-xs text-muted">Lịch hẹn sắp tới</span>
          <span className="block text-sm font-semibold text-foreground truncate">
            {slotLabel(next.timeSlot)} · {formatLongDay(next.bookingDate)}
          </span>
          <span className="block text-xs text-muted truncate">{next.workshop.name}</span>
        </span>
        {BOOKING_STATUS[next.status] && <Badge tone={BOOKING_STATUS[next.status].tone}>{BOOKING_STATUS[next.status].label}</Badge>}
        <ChevronRight className="w-4 h-4 text-muted group-hover:translate-x-0.5 transition-transform" />
      </Link>
    </div>
  )
}
