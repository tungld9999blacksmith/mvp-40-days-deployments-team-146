import { Link } from 'react-router-dom'
import { CalendarCheck2, CalendarPlus, ChevronRight, MapPin, Navigation, Phone, Store } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { Card, CardHeader } from '@/shared/ui/Card'
import RailRow from '@/shared/ui/RailRow'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { getBooking } from '@/features/bookings/api'
import { useUpcomingBookings } from '@/features/bookings/hooks/useUpcomingBookings'
import type { MyBookingItem } from '@/features/bookings/types'
import { bookingsOfVehicle, formatLongDay, mapsUrl, slotLabel } from '@/features/bookings/utils'
import { useCurrentVehicle } from '@/features/vehicles/currentVehicle/CurrentVehicleContext'
import { telHref } from '../logic'

const ACTION = 'inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors'
const PRIMARY = cn(ACTION, 'bg-brand text-on-brand font-semibold hover:brightness-110')
const SECONDARY = cn(ACTION, 'bg-card border border-border text-foreground/80 elevation-sm hover:text-foreground hover:bg-card-hover')

/** "Liên hệ xưởng": the workshop of the selected car's open booking, with call and directions. */
export default function WorkshopContactCard({ className }: { className?: string }) {
  const vehicleId = useCurrentVehicle().current?.userVehicleId ?? null
  const upcoming = useUpcomingBookings()

  if (upcoming.isLoading) return <SkeletonCard lines={4} className={className} />
  if (upcoming.error && !upcoming.data) {
    return (
      <Card className={className}>
        <CardHeader title="Liên hệ xưởng" />
        <ErrorState
          compact
          title="Không tải được lịch hẹn."
          description={null}
          traceId={upcoming.error.traceId}
          onRetry={upcoming.refetch}
          retrying={upcoming.isFetching}
        />
      </Card>
    )
  }

  const booking = bookingsOfVehicle(upcoming.data?.items ?? [], vehicleId)[0] ?? null
  if (!booking) {
    return (
      <Card className={className}>
        <CardHeader title="Liên hệ xưởng" />
        <EmptyState
          className="py-6"
          icon={<Store className="w-5 h-5" />}
          title="Bạn chưa có lịch hẹn sắp tới"
          description="Khi có lịch hẹn, số điện thoại và địa chỉ của xưởng sẽ hiện ở đây."
          action={
            <Link to="/booking" className={PRIMARY}>
              <CalendarPlus className="w-4 h-4" aria-hidden />
              Đặt lịch bảo dưỡng
            </Link>
          }
        />
      </Card>
    )
  }
  return <BookedWorkshop key={booking.bookingId} booking={booking} className={className} />
}

function BookedWorkshop({ booking, className }: { booking: MyBookingItem; className?: string }) {
  // The list row has no phone or address; the ticket (API-BR-01) does.
  const detail = useCachedQuery(`support:booking:${booking.bookingId}`, () => getBooking(booking.bookingId), 60_000)
  const workshop = detail.data?.workshop ?? null
  const status = BOOKING_STATUS[booking.status]
  const ticketPath = `/bookings/${encodeURIComponent(booking.bookingId)}`

  return (
    <Card className={className}>
      <CardHeader title="Liên hệ xưởng" action={status && <Badge tone={status.tone}>{status.label}</Badge>} />

      <div>
        <RailRow icon={<Store />} label="Xưởng của lịch hẹn">
          {booking.workshop.name}
        </RailRow>
        <RailRow icon={<CalendarCheck2 />} label="Thời gian">
          <span className="font-mono">
            {slotLabel(booking.timeSlot)} · {formatLongDay(booking.bookingDate)}
          </span>
        </RailRow>
        {workshop?.address && (
          <RailRow icon={<MapPin />} label="Địa chỉ">
            <span className="font-normal">{workshop.address}</span>
          </RailRow>
        )}
        {detail.isLoading && (
          <RailRow icon={<Phone />} label="Hotline" empty>
            Đang tải…
          </RailRow>
        )}
        {workshop?.phone && (
          <RailRow icon={<Phone />} label="Hotline">
            <span className="font-mono">{workshop.phone}</span>
          </RailRow>
        )}
      </div>

      {detail.error && !detail.data && (
        <ErrorState
          compact
          className="mt-2"
          title="Không tải được số điện thoại của xưởng."
          description={null}
          traceId={detail.error.traceId}
          onRetry={detail.refetch}
          retrying={detail.isFetching}
        />
      )}
      {workshop && !workshop.phone && (
        <Notice className="mt-4">Xưởng chưa cập nhật số điện thoại. Bạn có thể đến trực tiếp theo địa chỉ hoặc xem lịch hẹn.</Notice>
      )}

      <div className="mt-4 flex flex-col sm:flex-row gap-2">
        {workshop?.phone && (
          <a href={telHref(workshop.phone)} className={cn(PRIMARY, 'sm:flex-1')}>
            <Phone className="w-4 h-4" aria-hidden />
            Gọi xưởng
          </a>
        )}
        <a
          href={mapsUrl(booking.workshop.name, workshop?.address ?? null)}
          target="_blank"
          rel="noreferrer"
          className={cn(SECONDARY, 'sm:flex-1')}
        >
          <Navigation className="w-4 h-4" aria-hidden />
          Chỉ đường
        </a>
        <Link to={ticketPath} className={cn(SECONDARY, 'sm:flex-1')}>
          Xem lịch hẹn
          <ChevronRight className="w-4 h-4" aria-hidden />
        </Link>
      </div>
    </Card>
  )
}
