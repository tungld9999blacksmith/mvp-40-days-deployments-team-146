import { MapPin } from 'lucide-react'
import { useQuickBookingActions } from '../quickBooking/QuickBookingContext'
import type { QuickBookingNeedLocationCard } from '../types'

/** SCR-1502 (us-061 AF-1501) — no location known: pick an area that has active workshops. */
export default function RegionPickerCard({ card }: { card: QuickBookingNeedLocationCard }) {
  const actions = useQuickBookingActions()
  if (!card.regions.length) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Khu vực bảo dưỡng">
      {card.regions.map(region => (
        <button
          key={region}
          type="button"
          disabled={!actions || actions.busy}
          onClick={() => void actions?.start({ province: region })}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-2 text-xs text-foreground hover:bg-card-hover transition-colors disabled:opacity-50"
        >
          <MapPin className="w-3.5 h-3.5 text-emerald" aria-hidden />
          {region}
        </button>
      ))}
    </div>
  )
}
