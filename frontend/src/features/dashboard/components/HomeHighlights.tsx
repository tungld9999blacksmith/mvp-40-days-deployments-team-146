import { Link } from 'react-router-dom'
import { CalendarCheck2, ChevronRight, FileCheck2 } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { useUpcomingBookings } from '@/features/bookings/hooks/useUpcomingBookings'
import { bookingsOfVehicle, formatLongDay, slotLabel } from '@/features/bookings/utils'
import { useUnseenQuotes } from '@/features/quotes/hooks'
import { useCurrentVehicle } from '@/features/vehicles/currentVehicle/CurrentVehicleContext'

/**
 * Home shortcuts: the selected vehicle's next appointment (us-033 Q "Lịch hẹn sắp tới" → SCR-701) and the
 * "Báo giá có kết quả" badge (us-049 BR-1109). Renders nothing while there is nothing to show.
 */
export default function HomeHighlights() {
  const vehicleId = useCurrentVehicle().current?.userVehicleId ?? null
  const upcoming = useUpcomingBookings()
  const quotes = useUnseenQuotes()
  const next = bookingsOfVehicle(upcoming.data?.items ?? [], vehicleId)[0] ?? null
  const results = quotes.data?.items.length ?? 0
  if (!next && results === 0) return null

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 mb-6">
      {next && (
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
      )}
      {results > 0 && (
        <Link
          to="/quotes?unseenResult=true"
          className="group flex items-center gap-4 rounded-2xl border border-border bg-card p-4 elevation-sm hover:-translate-y-0.5 hover:elevation-md transition-all"
        >
          <span className="w-11 h-11 rounded-xl bg-emerald/10 text-emerald flex items-center justify-center shrink-0">
            <FileCheck2 className="w-5 h-5" />
          </span>
          <span className="flex-1 min-w-0">
            <span className="block text-sm font-semibold text-foreground">Báo giá có kết quả</span>
            <span className="block text-xs text-muted">{results} báo giá vừa được xưởng xử lý</span>
          </span>
          <span className="min-w-6 h-6 px-2 rounded-full bg-emerald text-on-brand text-xs font-bold flex items-center justify-center">{results}</span>
          <ChevronRight className="w-4 h-4 text-muted group-hover:translate-x-0.5 transition-transform" />
        </Link>
      )}
    </div>
  )
}
