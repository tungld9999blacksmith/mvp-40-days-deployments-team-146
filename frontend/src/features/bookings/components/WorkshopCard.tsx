import { Clock, MapPin, Star } from 'lucide-react'
import { cn } from '@/shared/ui/cn'
import type { NearbyWorkshop } from '../types'
import { formatDistance, remainingLabel, slotLabel } from '../utils'

function hoursToday(workshop: NearbyWorkshop): string | null {
  const hours = workshop.operatingHoursToday
  if (!hours) return null
  if (hours.isClosed || !hours.openTime || !hours.closeTime) return 'Nghỉ ngày này'
  return `${slotLabel(hours.openTime)}–${slotLabel(hours.closeTime)}`
}

/** FE §4.2 — one ranked workshop. */
export default function WorkshopCard({
  workshop,
  onSelect,
}: {
  workshop: NearbyWorkshop
  onSelect: (workshop: NearbyWorkshop) => void
}) {
  const hours = hoursToday(workshop)
  const slot = workshop.availability
  const slotText = slot
    ? slot.available
      ? remainingLabel(slot.remaining, true) ?? `Còn chỗ lúc ${slotLabel(slot.timeSlot)}`
      : 'Hết chỗ khung này'
    : null

  return (
    <button
      type="button"
      onClick={() => onSelect(workshop)}
      className="w-full text-left bg-card border border-border rounded-2xl p-4 hover:bg-card-hover hover:border-emerald/40 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
            {workshop.isPreferred && (
              <Star className="w-3.5 h-3.5 text-warning fill-warning shrink-0" aria-label="Xưởng ưa thích" />
            )}
            <span className="truncate">{workshop.name}</span>
          </p>
          <p className="text-xs text-muted mt-1 flex items-start gap-1.5">
            <MapPin className="w-3.5 h-3.5 shrink-0 mt-px" />
            <span>{workshop.address}</span>
          </p>
        </div>
        <span className="text-xs font-medium text-muted whitespace-nowrap">{formatDistance(workshop.distanceKm)}</span>
      </div>
      {(hours || slotText) && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 text-xs">
          {hours && (
            <span className="inline-flex items-center gap-1 text-muted">
              <Clock className="w-3.5 h-3.5" />
              {hours}
            </span>
          )}
          {slotText && (
            <span className={cn('font-medium', slot?.available ? 'text-emerald' : 'text-error')}>{slotText}</span>
          )}
        </div>
      )}
    </button>
  )
}
